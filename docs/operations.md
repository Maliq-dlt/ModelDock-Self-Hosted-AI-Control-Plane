# Operations

## Startup dan Migration

Bootstrap membuat `.env` dengan secret lokal acak, lalu Compose menjalankan migration sebelum API start:

```powershell
.\scripts\bootstrap.ps1
docker compose up --build
```

Migration manual:

```powershell
docker compose run --rm api alembic -c alembic.ini upgrade head
```

Health check:

```powershell
Invoke-RestMethod http://localhost:8080/health
Invoke-RestMethod http://localhost:8080/ready
```

## Admin Session

Dashboard memakai `MODELDOCK_ADMIN_API_KEY` server-side. Client admin lain dapat memperoleh session delapan jam:

```powershell
$login = Invoke-RestMethod -Method Post -Uri http://localhost:8080/api/auth/login `
  -ContentType application/json `
  -Body (@{ email = $env:BOOTSTRAP_ADMIN_EMAIL; password = $env:BOOTSTRAP_ADMIN_PASSWORD } | ConvertTo-Json)
$headers = @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod -Headers $headers -Uri http://localhost:8080/api/projects
```

## Backup

PostgreSQL backup:

```powershell
New-Item -ItemType Directory -Force .tmp | Out-Null
docker compose exec -T db pg_dump -U modeldock -d modeldock > .tmp/modeldock.sql
```

Restore ke database kosong:

```powershell
Get-Content .tmp/modeldock.sql | docker compose exec -T db psql -U modeldock -d modeldock
```

Jangan commit `.tmp/modeldock.sql`; file dapat memuat trace dan metadata konfigurasi. Untuk produksi, enkripsi backup, simpan di lokasi terpisah, dan uji restore berkala.

## Retention

Default retention 30 hari. Jalankan manual:

```powershell
docker compose exec api python scripts/retention.py
```

Atau panggil `POST /api/retention/run` memakai admin credential. Request attempts terhapus bersama request; audit logs dipurge terpisah berdasarkan cutoff sama.

## Metrics dan Tracing

Prometheus text tersedia di `/metrics`. Set `OTEL_EXPORTER_OTLP_ENDPOINT` untuk mengirim FastAPI spans ke collector OTLP HTTP. Provider credential dan authorization header tidak diekspor.

## Kubernetes

Validasi manifest tanpa mengubah cluster:

```powershell
kubectl apply --dry-run=client -f deployments/kubernetes/modeldock.yaml
```

Manifest adalah baseline single-cluster. Production memerlukan Ingress TLS, secret manager, image registry, network policy, autoscaling, PostgreSQL/Redis HA, dan backup terjadwal.

## Production Baseline

Set nilai unik untuk `ADMIN_API_KEY`, `ADMIN_SESSION_SECRET`, `API_KEY_HASH_SECRET`, dan `CREDENTIAL_ENCRYPTION_KEY`. Letakkan gateway di belakang HTTPS, batasi management routes, backup PostgreSQL, dan jaga Redis pada jaringan privat. Lihat `SECURITY.md` sebelum deployment.