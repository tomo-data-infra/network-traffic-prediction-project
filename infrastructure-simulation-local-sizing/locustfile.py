"""
Container-sizing load test for the Minikube sizing-test namespace (Locust 2.32.0).

Run against the NodePort Services directly (no port-forward needed):
    locust -f locustfile.py --host http://$(minikube ip):30800

While this runs, watch real resource consumption in another terminal:
    kubectl top pods -n sizing-test --containers

That `kubectl top` output -- not Locust's own response-time numbers -- is the actual data
you want: real CPU/RAM usage under load, to set resources.requests/limits in the production
infra-simulation/ manifests from measured numbers instead of guesses.

IMPORTANT, read before running a large test: the chat endpoint task below
(ChatbotQueryUser) hits /api/netops_agent_core/, which runs the real multi-tier LLM cascade
-- a live Gemini API call, ~30+ seconds of external network wait per request (see this
project's README: "resolves the query end-to-end ... in around 30+ seconds"). That latency
is dominated by waiting on Google's API, not this container's own CPU, so it's a poor signal
for CPU/RAM sizing on its own, and running it at real concurrency will generate real Gemini
API cost and can hit rate limits. It's included because it was explicitly requested, but its
task weight is kept deliberately low (see `weight` below) so it doesn't dominate the test.
If you want to exercise this path harder without external cost, temporarily unset
GEMINI_API_KEY in backend-local.yaml before applying -- the cascade will fail over to the
local Ollama tier only, keeping everything in-cluster.
"""

from locust import HttpUser, task, between


class DashboardUser(HttpUser):
    """The real CPU-sizing signal: PingDataView does in-process NumPy aggregation
    (features.make_features) and statistical forecasting (predictor.forecast_remaining_day)
    for every request -- actual in-container compute, not network wait."""

    wait_time = between(0.5, 2)
    weight = 20

    @task(3)
    def recent_window(self):
        # Last 30 minutes -- matches the dashboard's own default window.
        self.client.get("/api/ping_data/", name="/api/ping_data/ (30min)")

    @task(1)
    def wider_window(self):
        # Closer to the 12-hour cap (views.py enforces this as the max) -- more rows to
        # aggregate per request, a heavier version of the same real workload.
        self.client.get(
            "/api/ping_data/?start=2026-09-10T00:00&end=2026-09-10T12:00",
            name="/api/ping_data/ (12hr)",
        )


class StaticFrontendUser(HttpUser):
    """Static asset serving via nginx -- cheap, high-throughput, good for confirming the
    frontend container's baseline footprint under concurrent connections."""

    wait_time = between(0.5, 1.5)
    weight = 10

    @task
    def load_dashboard_shell(self):
        self.client.get("/", name="/ (static shell)")


# DISABLED for now -- CUBE_API_SECRET/CUBE_API_URL aren't wired into backend-local.yaml yet,
# so this 500s on every request (settings.CUBE_API_SECRET is None). Not needed for CPU/RAM
# sizing anyway (ping_data above is the real compute-bound signal); this is purely for
# testing the chat path itself later. To re-enable: uncomment the class below, add
# CUBE_API_SECRET and CUBE_API_URL (pointed at host.minikube.internal, not localhost) to
# backend-local.yaml's env list, and confirm Cube.js is actually reachable from Minikube.
#
# class ChatbotQueryUser(HttpUser):
#     """Low weight deliberately -- see module docstring. Each request is slow (~30s+) and,
#     unless GEMINI_API_KEY is unset for this test, costs real external API calls."""
#
#     wait_time = between(10, 20)
#     weight = 1
#
#     @task
#     def ask_traffic_spike_question(self):
#         self.client.post(
#             "/api/netops_agent_core/",
#             json={"question": "What was the highest traffic spike on node minikube on September 10?"},
#             name="/api/netops_agent_core/ (chat)",
#             timeout=60,
#         )
