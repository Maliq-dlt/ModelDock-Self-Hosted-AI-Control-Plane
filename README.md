# ModelDock

Self-hosted AI control plane untuk menghubungkan banyak provider melalui satu API kompatibel OpenAI. Platform menyediakan registry provider/model, virtual model, priority/cheapest routing, rule-based routing, retry/fallback, streaming, project API key, quota, idempotency, trace, token/cost tracking, prompt registry, evaluation, budget blocking, dashboard, PostgreSQL, Redis, OpenTelemetry, dan Docker Compose.

## Quick Start

Prasyarat: Docker Desktop dengan Docker Compose.

```powershell
.\scripts\bootstrap.ps1
docker compose up --build
```

Atau satu command:

```powershell
.\scripts\start.ps1
```

Service:

- Dashboard: `http://localhost:3000`
- Gateway: `http://localhost:8080/v1`
- API docs: `http://localhost:8080/docs`
- Metrics: `http://localhost:8080/metrics`
- Health: `http://localhost:8080/health`

`bootstrap.ps1` membuat `.env` berisi secret acak. File `.env` diabaikan Git.

## Demo Local Ollama

ModelDock tidak menyertakan model atau credential. Jalankan Ollama host yang dapat diakses container API melalui `host.docker.internal`, pull `llama3.2`, lalu seed konfigurasi demo:

```powershell
docker compose exec api python scripts/seed_demo.py
```

Catat `MODELDOCK_API_KEY` yang hanya dicetak saat key dibuat. Kirim request:

```powershell
$headers = @{ Authorization = "Bearer $env:MODELDOCK_API_KEY" }
$body = @{
  model = "smart-router"
  messages = @(@{ role = "user"; content = "Jelaskan fallback routing." })
} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post -Uri http://localhost:8080/v1/chat/completions -Headers $headers -ContentType application/json -Body $body
```

Contoh OpenAI SDK tersedia di `examples/python-basic/main.py`.

## Management API

Semua endpoint `/api/*` menerima bootstrap/admin header:

```http
X-ModelDock-Admin-Key: <ADMIN_API_KEY dari .env>
```

Admin user juga dapat login melalui `POST /api/auth/login`, lalu mengirim `Authorization: Bearer md_admin_*`. Role `owner` dan `admin` diperlukan untuk membuat atau melihat admin user. Dashboard menyimpan admin credential hanya pada proses server Next.js.

Alur konfigurasi:

1. `POST /api/projects`
2. `POST /api/providers`
3. `POST /api/models`
4. `POST /api/virtual-models`
5. `POST /api/api-keys`
6. `POST /v1/chat/completions`
7. `GET /api/traces/{trace_id}`
8. `GET /api/usage/summary`

Contoh virtual model priority:

```json
{
  "project_id": "<project-id>",
  "name": "support-production",
  "strategy": "priority",
  "candidates": [
    { "model_id": "<primary-model-id>" },
    { "model_id": "<fallback-model-id>" }
  ]
}
```

Provider types: `openai`, `gemini`, `groq`, `ollama`, dan `openai_compatible`. Credential dikirim sebagai object `credentials`, dienkripsi dengan Fernet, dan tidak pernah dikembalikan API. Provider test menyimpan health status dan latency terakhir.

## Gateway Behavior

- Client memakai project API key `md_live_*` atau `md_test_*`.
- Request model dapat menunjuk virtual model atau model langsung.
- `priority` mencoba kandidat sesuai urutan; `cheapest` mengurutkan metadata biaya.
- Error `408`, `409`, `425`, `429`, dan `5xx` dapat di-retry.
- Setelah retry habis, request pindah ke kandidat berikutnya.
- Setiap attempt tersimpan di trace yang sama.
- Usage provider dinormalisasi dan biaya dihitung dari harga per satu juta token.
- Budget bulanan dengan aksi `block` mengembalikan HTTP `402` sebelum provider dipanggil.
- API key mendukung RPM, token bulanan, concurrency, model allowlist, IP allowlist, expiry, dan revocation.
- `Idempotency-Key` mencegah pengulangan request non-streaming yang sudah sukses.
- `stream=true` meneruskan SSE dari OpenAI-compatible/Groq, NDJSON Ollama, dan SSE Gemini.
- Routing rules mendukung condition match, `route_to`, deny, capability, tag, dan context-window requirement.
- Prompt versions dapat dirender, diaktifkan, dan di-rollback. Evaluation checks mencakup contains, regex, exact match, length, latency, dan cost.

## Development

API:

```powershell
$env:UV_CACHE_DIR = ".uv-cache"
uv sync --project apps/api --extra test
uv run --project apps/api pytest apps/api/tests -p no:cacheprovider
uv run --project apps/api ruff check apps/api/app apps/api/tests
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
```

Dashboard:

```powershell
$env:npm_config_cache = ".cache/npm"
npm install --prefix apps/web
npm run lint --prefix apps/web
npm run build --prefix apps/web
npm audit --prefix apps/web
```

Compose validation:

```powershell
docker compose --env-file .env.example config
```

## Architecture

```text
Client
  | OpenAI-compatible request
  v
FastAPI gateway
  | API key + rate limit + budget
  v
Virtual-model router
  | priority / cheapest + retry / fallback
  v
OpenAI | Gemini | Groq | Ollama | OpenAI-compatible
  |
  +--> PostgreSQL traces, attempts, tokens, cost
  +--> Redis distributed rate counters
  +--> Next.js dashboard
```

Detail: `docs/architecture.md`.

## Security

- Provider credential: Fernet encrypted at rest.
- Project key: HMAC-SHA256 hash; raw key shown once.
- Admin key, HMAC secret, dan encryption key: environment only.
- Authorization header dan credential tidak ditulis ke trace.
- Request size, timeout, rate, budget, expiry, revocation: enforced.

Lihat `SECURITY.md` sebelum deployment produksi.

## Current MVP Scope

Selesai: provider/model management, project/environment setup, virtual models, priority/cheapest/rule routing, safe retry/fallback, streaming adapters, API keys/quota, idempotency, trace attempts, usage forecast, prompt registry, evaluations, monthly project budget blocking, admin JWT/RBAC, audit logs, retention, Prometheus metrics, optional OpenTelemetry, dashboard CRUD/charts/filter, migration, seed, CI, Docker Compose, dan Kubernetes baseline.

Batasan tersisa: OAuth provider integration, multi-region orchestration, managed database HA, GPU scheduler, Kubernetes operator, dan true LLM-as-judge belum termasuk; deployment Kubernetes tersedia sebagai single-cluster baseline.

## License

Apache License 2.0.
