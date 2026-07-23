# ModelDock Helm chart

Chart deploys API, dashboard, evaluation worker, HPA, Services, and a baseline NetworkPolicy. PostgreSQL and Redis are external by default. Provide an existing Kubernetes Secret containing:

- `DATABASE_URL`
- `REDIS_URL`
- `ADMIN_API_KEY`
- `ADMIN_SESSION_SECRET`
- `API_KEY_HASH_SECRET`
- `CREDENTIAL_ENCRYPTION_KEY`

Render locally:

```powershell
helm template modeldock deployments/helm/modeldock `
  --set image.api.repository=modeldock-api `
  --set image.web.repository=modeldock-web
```

Install with external secret:

```powershell
helm upgrade --install modeldock deployments/helm/modeldock `
  --namespace modeldock --create-namespace `
  --set secrets.existingSecret=modeldock-secrets
```

NetworkPolicy baseline permits cluster DNS plus external provider egress on TCP 80/443. Restrict egress CIDRs/destinations for production. Use managed PostgreSQL/Redis HA, an Ingress with TLS, an image registry, external secret management, and a PodDisruptionBudget. API container runs migrations before serving; worker retries while schema is unavailable.