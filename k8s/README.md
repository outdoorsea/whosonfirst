# Kubernetes Deployment

This directory contains a baseline Kubernetes deployment for the Who's On First API container. It covers the FastAPI service, configuration, autoscaling, and optional ingress rules. Use it as a starting point and tailor the manifests to match your cluster, networking model, and database endpoint.

## Prerequisites

- A running Kubernetes cluster (1.24+) with `kubectl` access
- Metrics Server installed if you plan to use the provided Horizontal Pod Autoscaler
- Container registry containing the built application image
- Reachable PostgreSQL/PostGIS instance populated with Who's On First data
- (Optional) Ingress controller such as AWS Load Balancer Controller, NGINX Ingress, or Traefik

## Files

| File | Purpose |
| --- | --- |
| `kustomization.yaml` | Applies all resources into the `wof-api` namespace |
| `namespace.yaml` | Creates an isolated namespace for the API |
| `configmap.yaml` | Default database host/name/port/pool sizing |
| `secret.example.yaml` | Template for the DB credentials secret (copy to `secret.yaml`) |
| `deployment.yaml` | Deploys the FastAPI container with probes and resources |
| `service.yaml` | ClusterIP service exposing the API on port 80 |
| `ingress.yaml` | Optional ingress definition for HTTP exposure |
| `hpa.yaml` | Horizontal Pod Autoscaler targeting 60% CPU |

## 1. Build and Push the Image

```bash
REGISTRY=ghcr.io/your-org
IMAGE=whosonfirst-api
TAG=$(git rev-parse --short HEAD)

docker build -t $IMAGE:$TAG .
docker tag $IMAGE:$TAG $REGISTRY/$IMAGE:$TAG
docker push $REGISTRY/$IMAGE:$TAG
```

Update `k8s/deployment.yaml` (or run `kustomize edit set image`) so the `image` field points at the pushed reference. Add image pull secrets if your registry requires authentication.

## 2. Configure Database Connectivity

1. Edit `k8s/configmap.yaml` and set `DB_HOST`, `DB_NAME`, and connection pool sizes for your environment.
2. Create the database credential secret. Either copy the template or create it directly:

```bash
cp k8s/secret.example.yaml k8s/secret.yaml    # edit values safely
# or
kubectl create secret generic wof-api-secrets \
  --from-literal=DB_USER=wofadmin \
  --from-literal=DB_PASS='strong-password' \
  --namespace wof-api
```

If you keep `secret.yaml` under version control, make sure real passwords are never committed.

## 3. Deploy the Stack

```bash
# Create/update all objects
kubectl apply -k k8s

# Watch the rollout
kubectl -n wof-api rollout status deploy/wof-api
kubectl -n wof-api get pods,svc
```

The namespace, ConfigMap, Deployment, Service, Ingress, and HPA are applied in a single command. Remove any resources you do not need (for example, delete `ingress.yaml` if your cluster does not run an ingress controller).

## 4. Verify

```bash
# Port-forward to test internally
kubectl -n wof-api port-forward svc/wof-api 8080:80
curl http://localhost:8080/health
curl "http://localhost:8080/api/v1/hierarchy?lat=37.7749&lon=-122.4194"
```

If you enabled the ingress resource, point DNS for `wof-api.example.com` (or your hostname) at the ingress controller and confirm requests succeed over HTTP/S.

## 5. Operations

- **Scaling:** Update `spec.replicas` in `deployment.yaml` or rely on the provided HPA (requires metrics). Adjust CPU targets in `hpa.yaml` to tune utilization.
- **Configuration changes:** Edit the ConfigMap or Deployment and re-run `kubectl apply -k k8s`. Pods will restart automatically when configuration changes.
- **Rolling updates:** Push a new image, update the deployment image tag, and re-apply. Kubernetes performs a rolling deployment with health checks tied to `/health`.
- **Secrets rotation:** Re-create the `wof-api-secrets` secret and roll the deployment (`kubectl -n wof-api rollout restart deploy/wof-api`).

This setup intentionally keeps the manifests simple so they can be adapted to managed Kubernetes platforms (EKS, GKE, AKS, etc.) or on-prem clusters. Layer on additional policies (PodSecurity, NetworkPolicy, TLS, service mesh) as required by your environment.
