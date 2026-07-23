# Architecture

ModelDock adalah control plane single-cluster dengan gateway kompatibel OpenAI, registry konfigurasi, routing terkontrol, observability request, dan dashboard server-rendered.

## Komponen

```mermaid
flowchart LR
    Client["OpenAI-compatible client"] --> API["FastAPI gateway"]
    Admin["Next.js dashboard / admin client"] --> API
    API --> Router["Routing and policy engine"]
    Router --> OpenAI["OpenAI"]
    Router --> Groq["Groq"]
    Router --> Gemini["Gemini"]
    Router --> Ollama["Ollama"]
    Router --> Custom["Custom OpenAI-compatible"]
    API --> PostgreSQL["PostgreSQL"]
    API --> Redis["Redis rate counters"]
    API --> Metrics["Prometheus metrics"]
    API -. optional .-> OTLP["OTLP collector"]
```

FastAPI memiliki gateway dan management API. PostgreSQL menyimpan konfigurasi, governance, trace, usage, dan audit. Redis menyimpan rate counter terdistribusi dengan fallback in-process. Next.js memanggil management API dari server sehingga admin key tidak masuk browser JavaScript.

## Alur Request

```text
Authorization dan IP check
  -> RPM dan concurrency check
  -> idempotency replay check
  -> monthly key quota dan project budget check
  -> routing-rule match
  -> virtual/direct model resolution
  -> capability, tag, dan context-window filtering
  -> priority atau cheapest ordering
  -> provider attempt dengan timeout dan safe retry
  -> fallback kandidat berikutnya
  -> response OpenAI normalization
  -> trace, attempt, token, cost, latency, dan health persistence
```

Request streaming memakai jalur yang sama. OpenAI/Groq/custom meneruskan SSE, Ollama membaca NDJSON, dan Gemini membaca SSE; output ke client tetap OpenAI-compatible SSE.

## Routing dan Policy

- Direct model menghasilkan strategi `static`.
- Virtual model mendukung `priority` dan `cheapest`.
- Routing rules dievaluasi berdasarkan priority lalu waktu pembuatan.
- Condition mendukung equality, `less_than`, `greater_than`, `in`, dan `contains`.
- Action dapat `route_to`, `deny`, atau menetapkan requirement capability, tag, dan minimum context window.
- Simulation endpoint mengembalikan kandidat terpilih dan kandidat yang ditolak tanpa memanggil provider.
- Retry hanya untuk kegagalan sementara; attempt dan fallback tetap berada dalam satu trace.

## Provider Adapter

Adapter menormalisasi request, response, usage, error, health check, dan streaming untuk:

- OpenAI;
- Groq;
- Gemini;
- Ollama;
- custom OpenAI-compatible endpoint.

OpenAI-compatible adapter meneruskan tools, tool choice, dan response format. Credential provider dapat memuat `api_key` dan custom `headers`, lalu dienkripsi sebelum disimpan.

## Governance

- Project API key: HMAC hash, expiry, revocation, rotation, allowlist, RPM, token quota, dan concurrency.
- Budget: batas bulanan project, warning threshold, projected usage, dan blocking sebelum provider call.
- Prompt registry: template, immutable versions, active version, rendering, dan rollback melalui aktivasi versi lama.
- Evaluation: rule checks untuk contains, regex, exact match, length, latency, dan cost; hasil dapat terhubung ke trace.
- Admin: bootstrap key, signed admin session, password hashing, role untuk user administration, dan audit log perubahan.
- Retention: request/attempt dan audit log dapat dipurge berdasarkan umur.

## Data Utama

```text
projects -> environments -> api_keys
providers -> models
projects -> virtual_models
projects -> routing_rules
requests -> request_attempts
projects -> budgets
projects -> prompt_templates -> prompt_versions
requests -> evaluations
admin_users
audit_logs
```

`requests.metadata_json` menyimpan routing decision dan error. Payload request/response hanya disimpan saat `LOG_PAYLOADS=true`.

## Observability

- Trace detail menampilkan lifecycle request dan semua provider attempt.
- Usage API menyediakan summary, timeseries, per-model, per-provider, dan per-project.
- Provider test menyimpan status, waktu pemeriksaan, dan latency terakhir.
- `/metrics` menyediakan metrik request format Prometheus.
- OTLP tracing FastAPI aktif bila `OTEL_EXPORTER_OTLP_ENDPOINT` diisi.

## Deployment

Docker Compose menjalankan API, web, PostgreSQL, dan Redis. Manifest Kubernetes menyediakan baseline single-cluster dengan Secret eksternal. Production tetap memerlukan HTTPS/Ingress, image registry, database/cache HA, backup jobs, secret manager, autoscaling, dan kebijakan jaringan.

## Batas Saat Ini

Belum termasuk OAuth provider, multi-region orchestration, Kubernetes operator, GPU scheduler, managed PostgreSQL/Redis HA, semantic routing, dan LLM-as-judge. Fitur itu berada di luar MVP v0.1 pada spesifikasi.