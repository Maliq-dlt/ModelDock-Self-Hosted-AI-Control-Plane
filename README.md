# ModelDock

[![CI](https://github.com/Maliq-dlt/ModelDock-Self-Hosted-AI-Control-Plane/actions/workflows/ci.yml/badge.svg)](https://github.com/Maliq-dlt/ModelDock-Self-Hosted-AI-Control-Plane/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Release](https://img.shields.io/badge/release-v0.2.0-orange.svg)](CHANGELOG.md)

Self-hosted AI control plane untuk menghubungkan banyak provider melalui satu API kompatibel OpenAI. Platform menyediakan registry provider/model, virtual model, priority/cheapest/fastest/weighted/canary routing, rule-based routing, retry/fallback, circuit breaker, streaming, project API key, quota, idempotency, trace, token/cost tracking, prompt registry, rule dan LLM-judge evaluation, budget blocking, TokenPress input efficiency, Caveman/Ponytail modes, dashboard topology/consumption, Decision Receipt replay, project TokenPress policy, PostgreSQL, Redis, OpenTelemetry, dan Docker Compose.

## Quick Start

Prasyarat: Docker Desktop dengan Docker Compose.

```powershell
.\scripts\bootstrap.ps1
docker compose -p modeldock up --build
```

Docker Desktop BuildKit membutuhkan path workspace ASCII-only. `scripts/start.ps1` otomatis memakai temporary ASCII drive saat path mengandung `—` atau aksara non-ASCII. Jika drive sementara tidak tersedia, tutup VS Code lalu rename folder ke `ModelDock-Self-Hosted-AI-Control-Plane`, buka ulang workspace, dan jalankan kembali script.

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

Provider types: `openai`, `openai_responses`, `anthropic`, `gemini`, `groq`, `ollama`, dan `openai_compatible`. Credential dikirim sebagai object `credentials`, dienkripsi dengan Fernet, dan tidak pernah dikembalikan API. Provider test menyimpan health status dan latency terakhir.

## Gateway Behavior

- Client memakai project API key `md_live_*` atau `md_test_*`.
- Request model dapat menunjuk virtual model atau model langsung.
- `priority` mencoba kandidat sesuai urutan; `cheapest` mengurutkan metadata biaya; `fastest` memakai latency health terakhir; `weighted_random` memakai bobot; `weighted_score` menggabungkan health, reliability, quality, latency, dan cost.
- Error `408`, `409`, `425`, `429`, dan `5xx` dapat di-retry.
- Setelah retry habis, request pindah ke kandidat berikutnya.
- Setiap attempt tersimpan di trace yang sama.
- Usage provider dinormalisasi dan biaya dihitung dari harga per satu juta token.
- Budget bulanan dengan aksi `block` mengembalikan HTTP `402` sebelum provider dipanggil.
- API key mendukung RPM, token bulanan, concurrency, model allowlist, IP allowlist, expiry, dan revocation.
- `Idempotency-Key` mencegah pengulangan request non-streaming yang sudah sukses.
- `stream=true` meneruskan SSE dari OpenAI-compatible/Groq, NDJSON Ollama, dan SSE Gemini.
- Routing rules mendukung condition match, `route_to`, deny, capability, tag, dan context-window requirement.
- Provider failure state menjalankan concurrency limit, reliability tracking, dan circuit breaker cooldown sebelum kandidat dipakai lagi.
- Prompt versions dapat dirender, diaktifkan, dan di-rollback. Evaluation checks mencakup contains, regex, exact match, length, latency, dan cost. Evaluation dapat sinkron, masuk durable queue, atau memakai LLM judge dari provider/model terdaftar.

## Competitive Gateway Core

ModelDock exposes one internal request path for three client protocols:

- `POST /v1/chat/completions` untuk OpenAI-compatible clients.
- `POST /v1/responses` untuk OpenAI Responses clients.
- `POST /v1/messages` untuk Anthropic Messages clients; API key dapat dikirim melalui `Authorization: Bearer` atau `x-api-key`.

Provider adapters tersedia untuk `anthropic` dan `openai_responses`, selain adapter yang sudah ada. Adapter menerima request internal yang sama, menghasilkan `ProviderResponse` yang sama, dan dapat ditambah melalui `register_adapter()` tanpa mengubah gateway.

Account pool:

- `POST /api/providers/{provider_id}/accounts` menambah credential account terenkripsi.
- Routing melewati account dengan `quota_remaining=0` sampai `quota_reset_at` lewat.
- Trace menyimpan `provider_account_id` dan nama account terpilih tanpa credential.
- `POST /api/providers/{provider_id}/models/sync` menyegarkan catalog provider tanpa menghapus model lama.

Kompatibilitas tidak memotong output. Responses/Anthropic streaming meneruskan seluruh delta dan trace yang sama.

## Token Efficiency

TokenPress mengurangi overhead input tanpa memotong capability output:

- `safe`: compact tool JSON, buang ANSI, normalisasi line ending; user/system/code tetap utuh.
- `caveman`: safe mode + output guidance ringkas; detail teknis tetap wajib.
- `ponytail`: safe mode + prinsip smallest sufficient code change.
- `stacked`: Caveman + Ponytail.
- Output tidak dipotong, tidak diringkas pascaproses, dan `max_tokens` tetap sama.
- Stats before/after tersimpan pada trace sebagai `token_efficiency`.

Project policy dapat diatur melalui `PATCH /api/projects/{project_id}/token-policy`; request `inherit` memakai policy project, sedangkan mode eksplisit menang override.

Request example:

```json
{
  "model": "smart-router",
  "messages": [{"role": "user", "content": "Fix this service."}],
  "modeldock": {"token_mode": "stacked"}
}
```

Offline preprocess:

```powershell
Get-Content request.json | python scripts/tokenpress.py --mode safe
```

Design detail: `docs/token-efficiency.md`.

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
  | OpenAI Chat / Responses / Anthropic Messages
  v
FastAPI gateway
  | API key + rate limit + budget
  v
Virtual-model router
  | priority / cheapest / fastest / weighted + rules + retry / fallback
  v
OpenAI Chat | OpenAI Responses | Anthropic | Gemini | Groq | Ollama | OpenAI-compatible
  |
  +--> PostgreSQL traces, attempts, tokens, cost
  +--> Redis distributed rate and concurrency counters
  +--> Next.js dashboard
```

Detail: `docs/architecture.md`. Adapter contract: `docs/provider-adapters.md`.

## Security

- Provider credential: Fernet encrypted at rest.
- Project key: HMAC-SHA256 hash; raw key shown once.
- Admin key, HMAC secret, dan encryption key: environment only.
- Authorization header dan credential tidak ditulis ke trace.
- Request size, timeout, rate, budget, expiry, revocation: enforced.

Lihat `SECURITY.md` sebelum deployment produksi.

Project governance: `CONTRIBUTING.md`, `GOVERNANCE.md`, `SUPPORT.md`, dan `CHANGELOG.md`.

## Current MVP Scope

Baseline v0.2.0 plus Stage 1, Stage 2, dan Stage 3 (in progress): TokenPress safe/caveman/ponytail/stacked modes, provider/model management, project/environment setup, virtual models, priority/cheapest/fastest/weighted/canary/rule routing, safe retry/fallback, provider concurrency dan circuit breaker, streaming adapters, API keys/quota, idempotency, trace attempts, usage forecast, prompt registry, rule dan LLM-judge evaluations dengan durable worker queue, monthly project budget blocking, admin JWT/RBAC dan session revocation, audit logs, retention, Prometheus metrics, optional OpenTelemetry, orbital dashboard topology/consumption/policy controls, Decision Receipt replay, migration, seed, CI, Docker Compose, dan Kubernetes/Helm baseline.

Batasan tersisa: provider OAuth integration, automatic quota-header ingestion, multi-region orchestration, managed database HA, GPU scheduler, Kubernetes operator, shadow evaluation, tool-call success routing, dan cost/quality optimization. Deployment Kubernetes/Helm tetap single-cluster baseline; external provider egress perlu disesuaikan dengan jaringan cluster.

## License

Apache License 2.0.
