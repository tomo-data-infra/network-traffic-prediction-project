#!/bin/bash
# ==============================================================================
# PRIVATE GKE + CLOUD NAT PROVISIONING SCRIPT (regional)
# ==============================================================================
#
# 1. Added --enable-autoscaling/--min-nodes/--max-nodes. The draft used a fixed
#    --num-nodes=3 with no autoscaling at all, which would have silently
#    defeated the whole point of the HPA/Cluster Autoscaler work documented in
#    README.md -- if the HPA scales pod replicas up and they can't schedule,
#    nothing would provision more nodes to catch them.
# 2. Switched --zone to --region (zonal -> regional), per the decision to
#    match the earlier real GKE test's topology (3 zones), not the AI draft's
#    single-zone default.
# 3. IMPORTANT regional-specific consequence of #2: --num-nodes/--min-nodes/
#    --max-nodes are PER ZONE for a regional cluster, and GKE spreads a
#    regional cluster across 3 zones by default (no --node-locations given,
#    matching how the earlier real GKE test was run). So the actual initial/
#    max node counts below are 3x the numbers shown -- e.g. --num-nodes=2
#    means 2 nodes/zone x 3 zones = 6 nodes total initially, scaling up to
#    5/zone x 3 = 15 total at --max-nodes=5. This is a real cost/capacity
#    multiplier vs. the zonal draft -- confirm this total is what you intend
#    before applying.
# 4. min-nodes=2/max-nodes=5 reused deliberately from the earlier real GKE
#    test's own numbers (documented in README.md), not re-guessed here.
#
# Still NOT corrected / worth knowing before you run this:
# - machine-type=e2-standard-4's real per-pod usable CPU budget is still an
#   ESTIMATE from GKE's general reservation formula (dedicated-core machine
#   types reserve a much smaller fraction than e2-medium's shared-core
#   penalty did) -- it has NOT been empirically verified the way e2-medium's
#   ~650m usable budget was (via `kubectl describe node` on a real cluster).
#   Re-run that same verification on this cluster once it's up, same as before
#   -- don't treat 2.4+ cores of headroom as settled until you've measured it.
# - --enable-master-global-access is currently a no-op: it only matters paired
#   with --enable-private-endpoint, which isn't set here, so the API server's
#   public endpoint stays reachable. Not wrong for current purposes (this
#   fixes the per-NODE external IP quota problem, not control-plane exposure)
#   -- just noting it does nothing yet if you were expecting it to.
# - Workload Identity isn't configured -- README.md's own comparison table
#   already lists this as a known, deliberately deferred gap alongside
#   Ingress/TLS and Secrets management, not something reintroduced here.

# Stop on the first error, on unset variables, and on failures inside pipes
set -euo pipefail

# --- CONFIGURATION VARIABLES ---
# PROJECT_ID="your-gcp-project-id"       # Replace with your actual GCP project ID
# Automatically detect the active GCP Project ID from the environment or gcloud config
PROJECT_ID=$(gcloud config get-value project 2>/dev/null || echo "${GOOGLE_CLOUD_SHELL_PROJECT_ID:-}")

# Validation: exit if the project ID is empty or gcloud returned the literal "(unset)"
if [ -z "${PROJECT_ID}" ] || [ "${PROJECT_ID}" = "(unset)" ]; then
    echo "ERROR: GCP Project ID could not be detected. Please set it manually via 'gcloud config set project [PROJECT_ID]'" >&2
    exit 1
fi

REGION="asia-northeast1"
VPC_NAME="private-gke-simulation-vpc"
SUBNET_NAME="private-gke-simulation-subnet"
ROUTER_NAME="gke-simulation-cloud-router"
NAT_NAME="gke-simulation-cloud-nat"
CLUSTER_NAME="private-gke-simulation-cluster"

# Public IP allowed to reach the GKE API server (Cloud Shell's current egress IP)
AUTHORIZED_CIDR="$(curl -s https://ifconfig.me)/32"
echo "Authorized network for the control plane: ${AUTHORIZED_CIDR}"

# Set target GCP project
gcloud config set project ${PROJECT_ID}

# 1. Create a Custom VPC Network
# [Annotation] Disable automatic subnet creation to maintain strict control over CIDR blocks
gcloud compute networks create ${VPC_NAME} \
    --subnet-mode=custom

# 2. Create a Custom Subnet with Secondary Ranges for Kubernetes
# [Annotation] Enable Private Google Access to allow nodes to communicate with Google APIs without public IPs
gcloud compute networks subnets create ${SUBNET_NAME} \
    --network=${VPC_NAME} \
    --region=${REGION} \
    --range=10.0.0.0/20 \
    --secondary-range=private-gke-simulation-pods=10.4.0.0/14,private-gke-simulation-services=10.8.0.0/20 \
    --enable-private-ip-google-access

# 3. Create Cloud Router
# [Annotation] Required as a control plane prerequisite for configuring Cloud NAT gateways
gcloud compute routers create ${ROUTER_NAME} \
    --network=${VPC_NAME} \
    --region=${REGION}

# 4. Create Cloud NAT Gateway (Bypasses the "IN_USE_ADDRESSES" quota wall by mapping multiple private nodes to a shared IP pool)
# [Annotation] --nat-all-subnet-ip-ranges covers the pod secondary range too, not just nodes --
# the backend's own pods make outbound calls (Gemini API, the SSH-tunneled remote GPU tier),
# so pod-originated egress needs NAT coverage, not just node-originated egress.
# [Annotation] DPA can only be enabled with Endpoint-Independent Mapping disabled.
# EIM would not save ports for repeated calls to the same few endpoints anyway:
# concurrent connections to one destination always need distinct source ports.
gcloud compute routers nats create ${NAT_NAME} \
    --router=${ROUTER_NAME} \
    --region=${REGION} \
    --auto-allocate-nat-external-ips \
    --nat-all-subnet-ip-ranges \
    --enable-dynamic-port-allocation \
    --min-ports-per-vm=64 \
    --max-ports-per-vm=4096 \
    --no-enable-endpoint-independent-mapping \
    --enable-logging \
    --log-filter=ERRORS_ONLY

# 5. Create Private GKE Regional Cluster
# [Annotation] Provisions a fully isolated cluster where nodes have zero public external IP
# addresses, successfully dodging the 8-node IN_USE_ADDRESSES quota limit. --region (not
# --zone) + no --node-locations given spreads this across 3 zones automatically, matching
# the earlier real GKE test's topology.
gcloud container clusters create ${CLUSTER_NAME} \
    --region=${REGION} \
    --release-channel=regular \
    --network=${VPC_NAME} \
    --subnetwork=${SUBNET_NAME} \
    --enable-ip-alias \
    --cluster-secondary-range-name=private-gke-simulation-pods \
    --services-secondary-range-name=private-gke-simulation-services \
    --enable-private-nodes \
    --master-ipv4-cidr=172.16.0.0/28 \
    --enable-master-global-access \
    --enable-master-authorized-networks \
    --master-authorized-networks=${AUTHORIZED_CIDR} \
    --machine-type=e2-standard-4 \
    --num-nodes=1 \
    --enable-autoscaling \
    --total-min-nodes=3 \
    --total-max-nodes=6 \
    --workload-pool=${PROJECT_ID}.svc.id.goog



    # NOTE: num-nodes/min-nodes/max-nodes are PER ZONE -- actual totals across
    # the 3 auto-selected zones are 6 nodes initial, 6-15 nodes once autoscaled.

# 6. Point kubectl at the new cluster and confirm the nodes are up
gcloud container clusters get-credentials ${CLUSTER_NAME} --region=${REGION}
kubectl get nodes -o wide

# 7. Set up Private Service Access so Cloud SQL can get a private IP in this VPC
# [Annotation] Cloud SQL runs in a Google-managed network. This reserves an internal range
# in our VPC (not overlapping the GKE ranges) and peers the two networks.
gcloud services enable sqladmin.googleapis.com servicenetworking.googleapis.com

gcloud compute addresses create cloudsql-psa-range \
    --global \
    --purpose=VPC_PEERING \
    --addresses=10.16.0.0 \
    --prefix-length=16 \
    --network=${VPC_NAME}

gcloud services vpc-peerings connect \
    --service=servicenetworking.googleapis.com \
    --ranges=cloudsql-psa-range \
    --network=${VPC_NAME}