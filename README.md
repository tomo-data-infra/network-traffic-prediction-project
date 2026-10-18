# AI NetOps Query Agent & Network Telemetry Analytics Platform

A natural-language query agent for network telemetry: ask plain-English (or Japanese) questions about live latency, jitter, and packet loss, and get an answer synthesized from a live Cube.js semantic layer — backed by a multi-tier LLM cascade with automatic fallback. The same platform continuously ingests low-level ICMP stream telemetry into PostgreSQL and layers a statistical forecasting model on top, aligned with a business calendar schedule.

---

## Demo: AI NetOps Chat Agent

<video src="https://github.com/user-attachments/assets/e2e82014-5992-44c3-b967-86d7ed26c057" controls width="700"></video>

This is a network telemetry and analytics platform with a natural-language query interface. The engine ingests real-time raw telemetry streams, processing and rendering time-series metrics onto a unified React dashboard layout.

We can query the system natively via our natural-language data agent. Let's ask for the peak minutely average latency on a specific date. We target the query using a descriptive alias, `R1_DGW`, instead of a raw IP address — the underlying node's IP never appears in the prompt, the LLM's context, or the request logs.

The agent translates the question into a Cube.js semantic query, not raw SQL, so there's no SQL-injection surface to defend in the first place. A RAG layer retrieves the relevant business-metric vocabulary — embedded once per process, matched by cosine similarity — to ground the translation, which is then routed through a cascading multi-LLM architecture that defaults to a commercial API and falls back to offline local inference if it's unavailable.

The agent resolves the query end-to-end — LLM translation, Cube.js dispatch, and local synthesis chained across three network calls — in around 30+ seconds. Cross-referencing our time-series profile verifies the data: the actual mean RTT spikes to exactly 39.47 milliseconds at 15:09 JST.

---

## Infrastructure Migration Simulation: AWS EKS → GCP GKE

`infrastructure-simulation/` is a local, cost-free simulation of a tiered multi-tenant Kubernetes deployment — Namespaces, Deployments, Services, NetworkPolicies, and a HorizontalPodAutoscaler — run on Minikube to validate the manifest design before spending on a real EKS or GKE cluster.

### Tiered Multi-Tenant Namespace Isolation

| Layer | Premium (`prod-customer-alpha`) | Personal (`prod-customer-beta`) | Internal Dev (`netops-dev`) |
|---|---|---|---|
| Frontend replicas | 2–5, autoscaled on CPU (`HorizontalPodAutoscaler`) | 1 (fixed, by design — no scaling for single-user tier) | 1 (fixed) |
| Backend replicas | 1 | 1 | 1 |
| Load balancing | `Service` (ClusterIP) across all frontend replicas | `Service` (ClusterIP) | `Service` (ClusterIP) |
| Network isolation | `NetworkPolicy`, denies cross-namespace ingress — verified: cross-namespace `wget` times out | Same | Same — dev is isolated from both customer tenants, and they from it |
| Node spreading | `podAntiAffinity`, active by default on this 2-node cluster | Not applicable — single replica | Not applicable |

`netops-dev` represents the SaaS provider's own internal development/staging environment — distinct from both customer tenant namespaces, and isolated from them the same way they're isolated from each other, so neither real customer traffic nor in-progress dev work can cross that boundary.

### Production-readiness checklist

What's actually in place vs. deliberately deferred:
- ✅ Resource requests/limits on every container
- ✅ Liveness/readiness probes
- ✅ Real network isolation (`NetworkPolicy`, confirmed via cross-namespace connectivity test)
- ✅ Load-balanced frontend (`Service`, confirmed via `Endpoints` listing all replica IPs)
- ✅ CPU-based autoscaling on the premium tier (`HorizontalPodAutoscaler`)
- ✅ Dockerfiles for both real services (`calendar_api.Dockerfile`, `network-ui.Dockerfile`) — multi-stage, non-root, build and run verified locally: both containers boot cleanly (migrations succeed, gunicorn starts with no errors, nginx serves the real build), and a live browser test confirms the frontend calls the backend end-to-end — the Traffic Dashboard renders real data fetched from `/api/ping_data/`
- ❌ Not yet wired into the simulation — the `infrastructure-simulation/` Deployments still reference the placeholder containers (`nginx:alpine`, a Python stub), not these images, and neither image has been pushed or loaded into Minikube yet. The frontend's backend URL (`VITE_API_URL`) is a build-time Docker ARG, confirmed working for local testing — pointing it at the right in-cluster Service DNS name and rebuilding per-environment is still a follow-up step before this works inside `infrastructure-simulation/`
- ❌ Ingress/TLS, Secrets management, persistent storage — not yet ported to this cluster

### What Minikube does and doesn't simulate

The Kubernetes objects above (`Namespace`/`Deployment`/`Service`/`NetworkPolicy`/`HPA`) are identical whether the cluster is Minikube, EKS, or GKE — that portability is the point of the exercise. What's cloud-specific and *not* simulated here:

| Concern | AWS (EKS) | GCP (GKE) |
|---|---|---|
| Ingress / load balancing | AWS Load Balancer Controller, ALB | GKE Ingress, Cloud Load Balancing |
| Workload identity | IAM Roles for Service Accounts | Workload Identity |
| Storage class | EBS CSI (`gp3`) | GCE PD CSI (`pd-balanced`) |
| Managed DB equivalent | RDS | Cloud SQL |
| Node-level autoscaling | Cluster Autoscaler via EKS managed node groups | Cluster Autoscaler via GKE node pools |

### Diagram: this simulation's actual topology

![Minikube architecture diagram reflecting the actual namespaces, Deployments, Services, NetworkPolicies, and HPA in this repo](docs/minikube-architecture-diagram-v2.png)

Namespace-by-namespace breakdown of every object actually defined in `infrastructure-simulation/` — exact `apiVersion`/`kind`/`metadata`, resource `requests`/`limits` per tier, the HPA's real `minReplicas`/`maxReplicas`/CPU threshold, and how the readiness/liveness probes and HPA actually behave (the HPA box notes explicitly that it only adjusts pod replica count and has no awareness of underlying node capacity — see the next section for why that distinction matters). The cluster runs 2 nodes by default here so `podAntiAffinity` on the premium frontend has real effect; the specific `podAntiAffinity` YAML block itself isn't shown as its own text box yet (planned for a future update) — see `infrastructure-simulation/premium-tier-alpha/frontend-premium.yaml` for that in the meantime.

### Future work: pairing HPA with a real Cluster Autoscaler (GKE)

![Conceptual diagram showing a Cluster Autoscaler provisioning a third node in response to Pending pods](docs/minikube-architecture-diagram-Cluster-Autoscaler.png)

**This is a conceptual diagram, not something implemented in this Minikube simulation.** It illustrates the idea: `HorizontalPodAutoscaler` requests more pod replicas based on CPU load, and if existing nodes don't have capacity, those pods sit `Pending` until something provisions more node capacity — that "something" is a Cluster Autoscaler, a node-level mechanism distinct from the HPA's pod-level one.

Minikube doesn't have a cloud API to provision real nodes against, so a genuine Cluster Autoscaler doesn't run the same way here as it would on a managed cluster. I actually attempted this locally before concluding that — the attempt (and exactly why it fails) is documented in `infrastructure-simulation/cluster-autoscaler.yaml`: deploying the real upstream `cluster-autoscaler` binary with `--cloud-provider=gce` crashes immediately, since it queries GCP's instance metadata server (`169.254.169.254`) to self-identify, and a Minikube node is a Docker container on your own machine, not a real GCE VM. I also checked for Minikube's own native addon (`minikube addons enable cluster-autoscaler`) and confirmed via `minikube addons list` that it isn't available — that addon only exists in an unmerged, draft [upstream PR](https://github.com/kubernetes/minikube/pull/23809) as of this writing. The remaining alternative, a third-party addon requiring a privileged host-side bridge process and 16GB+ of RAM, was a heavy, unvetted (zero-adoption) dependency not worth taking on for a local demo.

The real implementation path is GKE's native, fully-supported Cluster Autoscaler on an actual node pool — and I've since actually run that test, not just planned it.

#### Attempted on real GKE — findings so far (cluster since deleted to stop billing)

Provisioned a real GKE Standard regional cluster (3 zones, `e2-medium` nodes, `--min-nodes=2 --max-nodes=5` per zone) and forced a scale-up scenario against the premium tier's frontend. Three concrete findings, documented honestly rather than as a finished clean success:

**1. A regional IP-address quota capped real node count at 8, independent of the configured max.** Confirmed directly from GKE's own `cluster-autoscaler-status` configmap, not inferred:
```
errorCode: QUOTA_EXCEEDED
errorMessage: 'Instance ... creation failed: Quota "IN_USE_ADDRESSES" exceeded. Limit: 8.0 in region <REGION>.'
```
This is a default new-project quota, unrelated to CPU/machine-type sizing — it blocks the 9th node outright no matter how pod resources are sized. Next step: request an `IN_USE_ADDRESSES` quota increase before re-testing at real scale.

**2. CPU request sizing mattered more than expected, and the right number had to be derived empirically, not guessed.** `e2-medium` nodes have 940m allocatable CPU (2000m capacity − 1060m GKE system reservation), but GKE's own per-node system DaemonSets (`fluentbit`, `gke-metrics-agent`, `konnectivity-agent`, `kube-proxy`, `node-local-dns`, `pdcsi-node`, the GMP `collector`) consume real budget on top of that — measured directly via `kubectl describe node`, about 291m per node on this cluster:
```
Allocated resources:
  cpu   891m (94%)
# 891m total - 600m (this pod's request) = ~291m DaemonSet overhead
```
An earlier artificial CPU request of `1500m` (meant to force one-pod-per-node scheduling) actually exceeded the real ~650m usable headroom per node — no number of additional `e2-medium` nodes could ever have satisfied it, and the autoscaler correctly refused to scale up rather than waste a node on a pod that still wouldn't fit. `600m` and `500m` both worked once this overhead was accounted for.

**3. Manually forcing replica count fights the very autoscaling being tested.** The premium tier's `HorizontalPodAutoscaler` (`minReplicas: 2, maxReplicas: 5`) stayed attached throughout. With placeholder `nginx:alpine` pods doing essentially no real work, the HPA correctly observed near-zero CPU utilization and pulled the replica count back down on its own ~15–30s reconciliation loop, undoing manual `kubectl scale` commands in the background — including, at one point, replacing an already-`Running` pod with a new one once replicas were forced back up. This isn't an HPA bug; it's doing exactly its job. It means `kubectl scale` is the wrong tool for testing a Cluster Autoscaler on a Deployment that already has an active HPA — the correct test is generating genuine CPU load and letting the HPA (and by extension the Cluster Autoscaler) respond to real demand.

**Next steps, in priority order:**
- Switch to a **Private GKE Cluster with Cloud NAT**, rather than just requesting a quota increase. The `IN_USE_ADDRESSES` quota specifically tracks *external* IPs, and standard GKE nodes each get one by default — that's almost certainly why the wall landed at exactly 8. Private nodes only have internal IPs, with Cloud NAT handling outbound internet access (image pulls, etc.) through a small shared pool of external IPs instead of one per node — this avoids needing the quota at all, rather than asking GCP for more of it. (Not yet implemented — planned, not in progress.)
- Re-test by generating actual CPU load (e.g., a load generator against the Service) instead of `kubectl scale`, so the HPA and Cluster Autoscaler respond to real demand rather than being overridden.
- Move from `e2-medium` to a larger, dedicated-core machine type (`e2-standard-4`), and re-derive the node-sizing math above for that machine type rather than reusing the `e2-medium`-specific numbers. This is no longer just a sizing preference — the backend's own empirically-measured CPU request (below) already exceeds `e2-medium`'s ~650m real usable budget per node, so `e2-medium` can't schedule this pod at all, the same failure mode already documented above for the `1500m` test. `e2-standard-4` is dedicated-core rather than `e2-medium`'s shared-core type, so GKE's per-node reservation should be a much smaller fraction of capacity — expected, not yet measured the same way `e2-medium`'s numbers were.

### Container CPU/RAM sizing: Locust stress tests against the real images

The `resources.requests`/`limits` on the premium tier's backend/frontend containers (above) come from real load tests, not guesses — same "measure, don't guess" approach as the GKE node-sizing findings. Run from a separate, local-only directory (`infrastructure-simulation-local-sizing/`, kept apart from the production-bound manifests above so this testing doesn't disturb them) against the actual built images (`netops-backend:local`, `netops-frontend:local`) on Minikube, with Locust 2.x generating load and `kubectl top pods --containers` sampled continuously in parallel to capture real consumption.

**Backend** (`/api/ping_data/`, the in-process NumPy aggregation + statistical forecasting path — the genuine CPU-bound workload) at 10 concurrent users:

| Phase | CPU | Memory |
|---|---|---|
| Idle | ~1m | 281Mi |
| Early ramp | 776–862m | 286–291Mi |
| Steady state, 10 users | 2054–2410m (peak 2.41 cores) | plateaus at 319–321Mi |

Zero request failures at any point — the backend stayed correct under load, just proportionally slower (12-hour-window tail latency hit 9.68s at peak CPU contention).

**Frontend** (nginx serving the built React static bundle) ramped from 10 to 200 concurrent users:

| Metric | Observed |
|---|---|
| CPU | 0–45m across the entire 10→200 range |
| Memory | flat 7–10Mi |
| Requests | 49,574 total, 0 failures |

Static-asset serving is essentially flat across that range — not a sizing concern at any tested concurrency.

**Caveat:** both tests only went up to the user counts above (10 for the backend, 200 for the frontend) — the real ceiling past those points is untested, not assumed to be higher or lower. The backend's `requests: 800m` is sized near the early-ramp level, not the full 10-user peak; the `limits: 2500m` is what actually has to cover that peak, and did (2.41 of 2.5 cores). Also note: the Deployments above still run the `python:3.11-slim`/`nginx:alpine` placeholders, not these real images (see the production-readiness checklist) — these resource numbers are sized for when the real images get wired in, not for the placeholders' own (much smaller) footprint.

Only `premium-tier-alpha` was updated with these numbers. `personal-tier-beta` and `netops-dev` intentionally still carry the original placeholder `resources` (`50m`/`200m` CPU, `32Mi`/`64Mi` memory) — both are single-user/internal tiers by design (see the tiered table above: personal is "fixed, by design — no scaling for single-user tier"), not the many-concurrent-user traffic pattern this Locust testing measured, so sizing them off a 10-concurrent-user backend test would overprovision them for load they're never expected to see.

### Background reference: how Minikube works (general)

![Comprehensive Minikube Architecture](docs/minikube-generic-base-architecture.png)

A generic, textbook-style diagram of Minikube's internals (multi-node cluster, Control Plane, Kubelet, Containerd, generic pod scheduling).

**This diagram is not a depiction of this project's actual architecture.** It shows a generic multi-node cluster with placeholder pods — this simulation's specific namespaces, Deployments, and Services are depicted accurately in the diagram above and described in "Tiered Multi-Tenant Namespace Isolation" earlier in this section. For the real topology, use those, not this generic diagram.

### Running it locally

```bash
minikube start --driver=docker --nodes=2
minikube addons enable metrics-server

kubectl apply -f infrastructure-simulation/namespaces.yaml
kubectl apply -f infrastructure-simulation/premium-tier-alpha/
kubectl apply -f infrastructure-simulation/personal-tier-beta/
kubectl apply -f infrastructure-simulation/dev-tier/
```

### Verifying the claims above

```bash
# load-balancing: confirm all 3 premium replicas are registered
kubectl get endpoints netops-frontend -n prod-customer-alpha

# network isolation: cross-namespace request should time out
kubectl exec -n prod-customer-alpha deploy/netops-frontend -- \
  wget -T 3 -qO- $(kubectl get pod -n prod-customer-beta -l app=netops-frontend -o jsonpath='{.items[0].status.podIP}')

# autoscaling: watch replica count respond to generated load
kubectl get hpa -n prod-customer-alpha -w
```

---

## System Architecture & Separation of Concerns

The project is intentionally engineered across decoupled layers to minimize resource contention, maximize system resilience, and isolate the real-time processing threads from the web presentation application layers.

```text
            [ Enterprise Client / User Browser ]
                             │
          HTTP API           │      Natural Language Chat
             ┌───────────────┴────────────────┐
             ▼                                ▼
┌─────────────────────────┐      ┌─────────────────────────┐
│     React / Vite UI     │      │  Ollama Agent Pipeline  │
│   (Frontend Viewport)   │      │   (Qwen2.5:1.5b Core)   │
└────────────┬────────────┘      └────────────┬────────────┘
             │                                │
             ▼                                ▼
┌─────────────────────────────────────────────────────────┐
│              Django REST Framework Backend              │
│    - AI Query Agent (LLM Cascade + Cube.js Dispatch)    │
│      - Statistical Forecasting (vectorized aggregation) │
│       - Security Guardrails & Input Validation          │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│               PostgreSQL Database Layer                 │
│    - Partitioned Telemetry Logs & Rollup Views          │
│    - NetOps Performance Auditing Traces                 │
└────────────────────────────▲────────────────────────────┘
                             │
                     Raw SQL │ (Decoupled Background Loop)
                             │
               ┌─────────────┴─────────────┐
               │ Lightweight Python Worker │
               │ (Continuous Ping Stream)  │
               └───────────────────────────┘
```

### Core Components
1. **Web Backend API (`calendar_api/`, `config/`)**: A Django REST Framework service that hosts the multi-tier AI query agent, a lightweight statistical forecasting engine, and time-boundary/input validation.
2. **Frontend UI (`network-ui/`)**: A single-page dashboard built with React and Vite. It renders the NetOps chat agent, real-time latency monitors, statistical uncertainty corridors, and business calendar schedules.
3. **Telemetry Ingestion Worker (`scripts/`)**: An ultra-lightweight, high-frequency standalone Python worker that interacts directly with network sockets and streams metrics without loading the web framework overhead.

---

## Text-to-Query NetOps AI Data Agent

The dashboard integrates a conversational AI assistant that translates natural language questions (English and Japanese) into a Cube.js semantic query, executes it against the rollup views, and synthesizes a plain-language answer.

```text
User Question ──► Anonymizer ──► LLM Cascade ──► Cube.js Query JSON
              (IP masking)   (Gemini → Remote GPU → Local Ollama)
                                                       │
                                                       ▼
Dashboard  ◄── Synthesis (Ollama qwen2.5:1.5b) ◄── Cube.js (read-only aggregate query)
Answer                                                │
                                                       ▼
                                          ai_agent_logs (full audit trail)
```

* **Multi-tier LLM cascade with graceful degradation:** each request is attempted through `cascade_llm_router` in order — a cloud-hosted Gemini 3.5 Flash Lite tier, a private remote-GPU Llama 3.1 tier (reached over an auto-managed SSH tunnel), and a local Ollama Qwen2.5:1.5B tier — falling through to the next tier on failure, timeout, or malformed JSON, so the agent keeps working even if a paid API key or the GPU box is unavailable.
* **Anonymization before anything leaves the process:** IPv4 addresses in the user's question are masked into per-request tokens (`TARGET_NODE_1`, ...) before the question is sent to any LLM or written to a log line, and are only resolved back to real IPs when building the final Cube.js filter (`anonymizer.py`).
* **Structurally read-only:** the LLM only ever produces a Cube.js query object (measures/dimensions/filters) — there is no raw-SQL generation path, so there's nothing to sanitize for mutation keywords in the first place.
* **Dynamic data routing:** the agent targets the appropriate rollup view (`minute_rollups`, `hourly_rollups`, `daily_rollups`) based on the requested time window.
* **Stage-level observability:** each request is timed independently at the LLM-routing, Cube-dispatch, and Ollama-synthesis stages (`time.perf_counter`), plus total request latency and process RSS memory, all emitted through structured logger output.
* **Full interaction logging:** every chat exchange (prompt, resolved query, DB output, response, latency) is written to `ai_agent_logs` for later review.
* **RAG-based semantic catalog retrieval:** `semantic_catalog.py` defines a business-term → technical-metric mapping (e.g. "high latency" → `PingLogs.highestRtt`). Rather than statically dumping the whole catalog into every prompt, `rag.py` embeds each catalog entry and the incoming question (Gemini `gemini-embedding-001`, asymmetric `RETRIEVAL_DOCUMENT`/`RETRIEVAL_QUERY` embeddings), ranks by cosine similarity, and injects only the relevant subset — falling back to the full catalog if embedding fails for any reason.

---

## Data & Semantic Architecture

The chat agent and dashboard are both served from the same pre-aggregated data layer:

```text
Raw table: ping_logs(ts, target_id, rtt_ms, is_timeout)
Rollup views:
  - minute_rollups(ts_minute, target_id, highest_rtt, mean_rtt, ...)
  - hourly_rollups(ts_hour, target_id, highest_rtt, mean_rtt, ...)
  - daily_rollups(ts_day, target_id, highest_rtt, mean_rtt, ...)
```

* Pre-aggregation reduces query load and keeps interactive response times low for both the dashboard and the chat agent.
* Cube.js exposes these rollups as a semantic layer (`PingLogs.highestRtt`, `PingLogs.meanRtt`, `PingLogs.packetLossRate`, `Targets.ip`) so the LLM only needs to reason about business-level measures, never raw SQL.
* Supports both raw event-level analysis and business-level summaries, and keeps the platform scalable and easy to debug.

---

## Additional Engineering Notes

* **Request window validation:** the API rejects requests where `start_time >= end_time` and caps query windows to 12 hours to bound memory usage during aggregation.
* **Environment isolation:** database credentials and API keys live outside the codebase in `.env`; the app fails fast at startup if a required variable is missing. Admin-only actions (editing calendar events, retraining the model, running maintenance) are enforced server-side via a JWT issued after a password check.
* **NumPy array masking for baseline training:** to avoid an N+1 query pattern during model retraining, historical metrics are fetched in a single bulk query and sliced per event using vectorized boolean masks instead of querying the database inside a loop.

### Known Gaps
* `google-genai` is now a load-bearing dependency (pinned in `requirements.in`) — it backs both the Gemini Tier 1 LLM cascade and the RAG catalog-retrieval embeddings, so it's required on a fresh install, not just an optional fallback path.
* Telemetry ingestion and the baseline predictor currently target a single hardcoded node (`target_id=1`); the schema (`Targets` table, Cube.js `Targets` cube) supports multiple targets, but target selection isn't yet exposed in the UI/API.

---

## Predictive Modeling & Jitter Corridor

Hovering over the **Latency Profile** chart shows the RTT ± jitter envelope for that minute bucket, rather than a flattened average. Jitter is computed per RFC 3550 — the mean absolute difference between consecutive RTT samples:

$$
\text{Jitter} = \frac{1}{N}\sum_{i=1}^{N}\vert{}RTT_{i} - RTT_{i-1}\vert{}
$$

![Real-Time Tooltip Telemetry](docs/telemetry-tooltip-hover.png)

`Actual Mean RTT: 6.73 ms (Jitter Upper Boundary: 10.64 ms, Jitter Lower Boundary: 2.82 ms)`

A lightweight statistical baseline (per-event-category mean RTT/jitter/loss coefficients, `predictor.py`) is trained from historical logs and used to forecast the remainder of the day by overlaying those coefficients on upcoming calendar events.

---

## Project Structure & Directory Mapping

```text
├── network-ui/                 # Frontend Client Workspace (React, Vite, Tailwind)
├── calendar_api/               # Core API App Layer
│   ├── utils/
│   │   ├── llm_router.py       # LLM routing and fallback logic
│   │   ├── semantic_catalog.py # Business-term/metric catalog (retrieved via rag.py)
│   │   ├── rag.py              # Gemini-embedding RAG retrieval over the semantic catalog
│   │   ├── features.py         # Aggregation, data imputation, cyclic math
│   │   └── predictor.py        # Baseline analytics and RFC 3550 jitter
│   ├── models.py               # Database mappings and audit schema
│   ├── serializers.py          # REST serializers
│   ├── permissions.py          # Admin-JWT write-access guard
│   ├── urls.py                 # Django API routing
│   ├── views.py                # Guarded web views and AI query pipeline
│   └── apps.py                 # App initialization and remote GPU tunnel setup
├── cube/                       # Cube.js semantic layer service
│   ├── docker-compose.yml      # Cube Core container definition
│   └── schema/                 # Cube.js data model (measures/dimensions)
├── config/                     # Global project settings (Django ASGI/WSGI)
│   └── urls.py
├── scripts/                    # Isolated telemetry workers
│   └── ingest_ping_stream.py   # Lightweight independent ingestion engine
├── infrastructure-simulation/  # Vendor-neutral Kubernetes topology simulation (Minikube validation)
├── .env.example                # Deployment configuration template
├── .gitignore                  # Repository ignore rules
├── requirements.txt            # Python dependencies
├── start_app.sh                # Local dev launcher (Django dev server + Vite dev server)
└── start_ping_collecting.sh    # Isolated telemetry stream launcher
```

---

## Local Development Setup

### 1. Environmental Setup
Clone the repository and build your isolated python virtual environment inside the root directory:
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Initialize your localized deployment profile credentials. Copy the template and fill out your specific database passwords:
```bash
cp .env.example .env
```

### 2. Execution Entry Points
To grant execution privileges to the infrastructure boot scripts, run:
```bash
chmod +x start_app.sh start_ping_collecting.sh
```

* **To initialize continuous, 24/7 database telemetry logging:**
  ```bash
  ./start_ping_collecting.sh
  ```
* **To launch the local web interface and Django API services:**
  ```bash
  ./start_app.sh
  ```
