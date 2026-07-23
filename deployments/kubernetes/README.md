# Kubernetes deployment

Manifest runs API, web, PostgreSQL, and Redis in one namespace. It expects locally available images:

```powershell
docker build -f apps/api/Dockerfile -t modeldock-api:0.1.0 .
docker build -f apps/web/Dockerfile -t modeldock-web:0.1.0 .
```

Create strong secrets outside Git, then apply:

```powershell
kubectl -n modeldock create secret generic modeldock-secrets `
  --from-literal=ADMIN_API_KEY="..." `
  --from-literal=ADMIN_SESSION_SECRET="..." `
  --from-literal=API_KEY_HASH_SECRET="..." `
  --from-literal=CREDENTIAL_ENCRYPTION_KEY="..." `
  --from-literal=POSTGRES_PASSWORD="..." `
  --from-literal=DATABASE_URL="postgresql+asyncpg://modeldock:<encoded-password>@postgres:5432/modeldock" `
  --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f deployments/kubernetes/modeldock.yaml
```

For production, replace in-cluster PostgreSQL/Redis with managed HA services, use an Ingress with TLS, external secret management, image registry references, backup jobs, and region-local gateway deployments. Manifest is single-cluster baseline, not a multi-region control plane.
