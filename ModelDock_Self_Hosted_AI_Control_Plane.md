# ModelDock — Self-Hosted AI Control Plane

> Open-source control plane untuk menghubungkan, merutekan, memantau, dan mengendalikan penggunaan banyak model AI melalui satu API yang kompatibel dengan format OpenAI.

---

## 1. Ringkasan Proyek

**ModelDock** adalah platform self-hosted yang menyediakan satu gateway untuk mengakses berbagai penyedia model AI seperti OpenAI, Anthropic, Gemini, Groq, Ollama, dan server model lokal.

Alih-alih setiap aplikasi berkomunikasi langsung dengan masing-masing provider, seluruh request dikirim ke ModelDock. Platform kemudian menangani:

- autentikasi;
- pemilihan model;
- routing berdasarkan aturan;
- retry dan fallback;
- pembatasan anggaran;
- pencatatan token dan biaya;
- tracing setiap request;
- monitoring latency dan error;
- evaluasi kualitas respons;
- pengelolaan prompt dan konfigurasi.

ModelDock diposisikan sebagai kombinasi ringan dari:

- AI API gateway;
- model router;
- usage and budget manager;
- observability platform;
- prompt registry;
- evaluation engine.

---

## 2. Masalah yang Diselesaikan

Aplikasi AI yang menggunakan banyak provider biasanya menghadapi beberapa masalah:

1. Setiap provider mempunyai format API, autentikasi, model, dan error yang berbeda.
2. Aplikasi terlalu bergantung pada satu provider.
3. Sulit mengetahui biaya setiap aplikasi, tim, pengguna, atau API key.
4. Tidak ada fallback otomatis ketika provider gagal.
5. Pemilihan model sering dilakukan secara manual.
6. Riwayat request dan respons sulit ditelusuri.
7. Perubahan prompt atau model dapat menurunkan kualitas tanpa terdeteksi.
8. Tim sulit menerapkan limit, quota, dan kebijakan penggunaan AI.
9. Model lokal dan model cloud tidak memiliki satu interface yang konsisten.
10. Data sensitif dapat terkirim ke provider yang tidak sesuai kebijakan.

ModelDock menyediakan satu lapisan kontrol di antara aplikasi dan seluruh model AI yang digunakan.

---

## 3. Target Pengguna

### 3.1 AI Engineer

Membutuhkan satu endpoint untuk mencoba dan membandingkan banyak model tanpa mengubah kode aplikasi.

### 3.2 Backend Engineer

Membutuhkan retry, fallback, rate limiting, authentication, dan logging yang konsisten.

### 3.3 Startup atau Tim Produk

Membutuhkan kontrol biaya, quota, dashboard usage, dan ketersediaan layanan.

### 3.4 Tim dengan Infrastruktur Lokal

Membutuhkan routing antara model cloud dan model lokal seperti Ollama atau vLLM.

### 3.5 Peneliti dan Evaluator Model

Membutuhkan eksperimen terstruktur untuk membandingkan kualitas, latency, dan biaya model.

---

## 4. Tujuan Produk

### Tujuan Utama

- Menyediakan satu API universal untuk banyak provider AI.
- Mengurangi ketergantungan terhadap satu model atau provider.
- Mengontrol biaya dan quota secara terpusat.
- Menyediakan observability untuk setiap request.
- Mendukung routing, retry, dan fallback otomatis.
- Dapat dijalankan secara self-hosted.
- Mudah diintegrasikan dengan aplikasi yang sudah menggunakan OpenAI SDK.

### Bukan Tujuan Awal

- Menjadi platform pelatihan model.
- Menyediakan GPU orchestration skala besar.
- Menjadi chatbot end-user.
- Menjadi marketplace model.
- Menyediakan billing SaaS lengkap.
- Menyimpan seluruh data pengguna tanpa konfigurasi retensi.

---

## 5. Nilai Utama

### Satu Endpoint

```http
POST /v1/chat/completions
```

### Banyak Provider

```text
OpenAI
Anthropic
Google Gemini
Groq
Ollama
vLLM
Custom OpenAI-compatible Provider
```

### Routing Terkontrol

```text
Request sederhana  → model murah
Request coding     → model khusus coding
Context panjang    → model long-context
Provider gagal     → fallback provider
Data sensitif      → model lokal
Budget hampir habis → model ekonomis
```

### Observability

```text
Request
├── User
├── Application
├── Selected Route
├── Selected Model
├── Provider
├── Prompt Tokens
├── Completion Tokens
├── Cost
├── Latency
├── Retry
├── Fallback
├── Error
└── Evaluation Result
```

---

## 6. Contoh Penggunaan

Aplikasi mengirim request menggunakan OpenAI SDK, tetapi base URL diarahkan ke ModelDock.

```python
from openai import OpenAI

client = OpenAI(
    api_key="md_live_example_key",
    base_url="http://localhost:8080/v1",
)

response = client.chat.completions.create(
    model="smart-router",
    messages=[
        {
            "role": "user",
            "content": "Jelaskan penyebab utama inflasi dengan bahasa sederhana."
        }
    ],
)

print(response.choices[0].message.content)
```

Model `smart-router` bukan model asli. Itu adalah alias routing yang dikonfigurasi di ModelDock.

---

## 7. Fitur Produk

## 7.1 Universal AI Gateway

- Endpoint kompatibel dengan format OpenAI.
- Provider adapter untuk setiap vendor.
- Standardisasi request dan response.
- Streaming response.
- Timeout management.
- Error normalization.
- Support custom headers.
- Support structured output.
- Support tool calling pada provider yang mendukung.

## 7.2 Provider Management

Administrator dapat:

- menambahkan provider;
- menyimpan API key terenkripsi;
- mengaktifkan atau menonaktifkan provider;
- menetapkan timeout;
- mengatur prioritas;
- menentukan batas concurrency;
- menguji koneksi;
- melihat health status.

Contoh konfigurasi:

```yaml
providers:
  openai_primary:
    type: openai
    enabled: true
    timeout_seconds: 30

  gemini_fallback:
    type: gemini
    enabled: true
    timeout_seconds: 35

  ollama_local:
    type: ollama
    enabled: true
    base_url: http://ollama:11434
```

## 7.3 Model Registry

Setiap model memiliki metadata:

```yaml
model_id: gpt-example
provider: openai_primary
capabilities:
  - chat
  - tools
  - structured_output
context_window: 128000
input_cost_per_million: 0
output_cost_per_million: 0
tags:
  - reasoning
  - premium
  - cloud
enabled: true
```

Metadata biaya diisi melalui konfigurasi administrator dan dapat diperbarui tanpa mengubah kode aplikasi.

## 7.4 Virtual Models

Virtual model adalah alias yang mengarah ke satu atau lebih model nyata.

Contoh:

```yaml
virtual_models:
  smart-router:
    strategy: weighted_score
    candidates:
      - model: provider-a/model-fast
        weight: 0.4
      - model: provider-b/model-balanced
        weight: 0.6

  local-only:
    strategy: priority
    candidates:
      - model: ollama/qwen
      - model: vllm/llama
```

## 7.5 Routing Engine

Routing dapat mempertimbangkan:

- jenis task;
- ukuran prompt;
- kebutuhan tool calling;
- structured output;
- estimasi biaya;
- latency historis;
- availability;
- lokasi deployment;
- sensitivitas data;
- quota pengguna;
- batas anggaran;
- tag model;
- provider health;
- model quality score.

### Strategi Routing Awal

#### Static

Selalu gunakan satu model.

#### Priority

Gunakan model pertama yang tersedia.

#### Cheapest

Pilih model dengan estimasi biaya terendah.

#### Fastest

Pilih model dengan latency historis terendah.

#### Weighted Random

Distribusikan traffic berdasarkan bobot.

#### Rule-Based

Gunakan aturan kondisi.

#### Weighted Score

Hitung skor gabungan kualitas, biaya, latency, dan reliability.

Contoh formula:

```text
score =
    quality_weight × normalized_quality
  - cost_weight × normalized_cost
  - latency_weight × normalized_latency
  + reliability_weight × normalized_reliability
```

## 7.6 Routing Rules

Contoh aturan:

```yaml
rules:
  - name: local-sensitive-data
    when:
      data_classification: sensitive
    route_to: local-only

  - name: coding-task
    when:
      task_type: coding
    route_to: coding-router

  - name: budget-protection
    when:
      monthly_budget_remaining_percent:
        less_than: 10
    route_to: economy-router

  - name: long-context
    when:
      estimated_prompt_tokens:
        greater_than: 50000
    require:
      minimum_context_window: 100000
```

## 7.7 Retry dan Fallback

Retry hanya dilakukan untuk error yang aman dicoba ulang.

```text
Timeout
Rate limit
Temporary provider failure
Network failure
Server error
```

Fallback chain:

```text
Primary Model
    ↓ failed
Secondary Model
    ↓ failed
Local Model
    ↓ failed
Return normalized error
```

Konfigurasi:

```yaml
fallback:
  max_retries_per_provider: 2
  backoff: exponential
  retryable_status_codes:
    - 408
    - 429
    - 500
    - 502
    - 503
    - 504
```

## 7.8 API Key Management

- Project API key.
- Environment separation.
- Key prefix.
- Key hashing.
- Key expiration.
- Key revocation.
- IP allowlist.
- Per-key quota.
- Per-key model permissions.
- Last-used timestamp.

Contoh key:

```text
md_live_********************************
md_test_********************************
```

API key asli hanya diperlihatkan sekali saat dibuat.

## 7.9 Rate Limiting dan Quota

Limit dapat ditentukan berdasarkan:

- request per minute;
- token per minute;
- request per day;
- token per month;
- maximum concurrent requests;
- maximum cost per day;
- maximum cost per month.

Scope limit:

```text
Organization
Project
Environment
API Key
User
Model
Provider
```

## 7.10 Budget Management

Dashboard budget memperlihatkan:

- budget bulanan;
- usage saat ini;
- projected monthly usage;
- usage per project;
- usage per model;
- usage per provider;
- usage per user;
- alert threshold;
- blocked request count.

Kebijakan budget:

```yaml
budget:
  monthly_limit_usd: 100
  warning_threshold_percent: 80
  action_at_limit: block
```

Pilihan aksi:

```text
warn
route_to_cheaper_model
disable_premium_models
block
```

## 7.11 Request Tracing

Setiap request memiliki trace ID.

```text
trace_id: trc_01JEXAMPLE
```

Satu trace dapat berisi beberapa attempt:

```text
Trace
├── Request Received
├── Authentication Passed
├── Policy Evaluated
├── Route Selected
├── Attempt 1: Provider A
│   └── Timeout
├── Attempt 2: Provider A
│   └── Rate Limited
├── Fallback Triggered
├── Attempt 3: Provider B
│   └── Success
├── Usage Recorded
└── Response Returned
```

## 7.12 Prompt Registry

Prompt dapat disimpan dan diberi versi.

```text
customer-support
├── v1
├── v2
└── v3
```

Fitur:

- prompt template;
- variables;
- environment;
- version history;
- diff;
- rollback;
- active version;
- model override;
- test cases;
- deployment notes.

## 7.13 Evaluation Engine

Evaluation awal dapat mencakup:

- response success;
- schema validity;
- keyword rules;
- regex rules;
- latency threshold;
- cost threshold;
- JSON validity;
- tool call validity;
- user feedback;
- LLM-as-judge opsional.

Contoh evaluasi:

```yaml
evaluation:
  name: valid-support-response
  checks:
    - type: max_latency
      value_ms: 8000
    - type: valid_json
    - type: required_fields
      fields:
        - answer
        - confidence
```

## 7.14 Dashboard

### Overview

- total requests;
- successful requests;
- failed requests;
- token usage;
- total cost;
- average latency;
- provider health;
- budget usage.

### Requests

- trace explorer;
- filter berdasarkan model;
- filter berdasarkan provider;
- filter berdasarkan status;
- filter berdasarkan API key;
- filter berdasarkan project;
- filter berdasarkan latency;
- filter berdasarkan cost.

### Providers

- provider status;
- success rate;
- p50 latency;
- p95 latency;
- error rate;
- rate limit count;
- cost.

### Models

- usage;
- estimated cost;
- latency;
- quality score;
- success rate;
- fallback count.

### Budgets

- current usage;
- forecast;
- threshold;
- limit violations.

### Prompts

- versions;
- active deployment;
- comparison;
- evaluation result.

---

## 8. Arsitektur Sistem

```text
┌───────────────────────────────────────────────────────────┐
│                       Client Apps                         │
│   Web App │ Mobile App │ Agent │ Backend │ CLI │ SDK     │
└──────────────────────────────┬────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────┐
│                      API Gateway                          │
│ Authentication │ Validation │ Rate Limit │ Streaming     │
└──────────────────────────────┬────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────┐
│                     Policy Engine                         │
│ Budget │ Permissions │ Data Policy │ Model Restrictions  │
└──────────────────────────────┬────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────┐
│                     Routing Engine                        │
│ Rules │ Model Selection │ Health │ Cost │ Latency        │
└──────────────────────────────┬────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────┐
│                    Provider Adapters                      │
│ OpenAI │ Anthropic │ Gemini │ Groq │ Ollama │ Custom     │
└──────────────────────────────┬────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────┐
│                  External / Local Models                  │
└───────────────────────────────────────────────────────────┘

Parallel services:

┌───────────────────┐
│ Trace Collector   │
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Event Queue       │
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Usage Aggregator  │
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ PostgreSQL        │
└───────────────────┘

┌───────────────────┐
│ Web Dashboard     │
└───────────────────┘
```

---

## 9. Komponen Backend

### 9.1 Gateway Service

Tanggung jawab:

- menerima request;
- autentikasi;
- validasi schema;
- membuat trace;
- meneruskan request ke routing engine;
- streaming response;
- mengembalikan format standar.

### 9.2 Routing Service

Tanggung jawab:

- membaca virtual model;
- mengambil candidate models;
- mengevaluasi rules;
- memeriksa model capabilities;
- menghitung ranking;
- memilih model;
- menjalankan fallback.

### 9.3 Provider Adapter

Interface dasar:

```python
from typing import Protocol, AsyncIterator


class ProviderAdapter(Protocol):
    async def chat(self, request: dict) -> dict:
        ...

    async def stream_chat(
        self,
        request: dict,
    ) -> AsyncIterator[dict]:
        ...

    async def health_check(self) -> bool:
        ...

    def estimate_cost(self, usage: dict) -> float:
        ...
```

### 9.4 Policy Service

Tanggung jawab:

- quota;
- budget;
- model permissions;
- environment policy;
- data classification;
- provider restrictions.

### 9.5 Usage Service

Tanggung jawab:

- token usage;
- estimated cost;
- daily aggregation;
- monthly aggregation;
- usage forecast.

### 9.6 Trace Service

Tanggung jawab:

- request lifecycle;
- attempt history;
- routing decision;
- retry;
- fallback;
- error;
- evaluation result.

### 9.7 Evaluation Worker

Tanggung jawab:

- menjalankan evaluasi asinkron;
- membandingkan output;
- menghitung score;
- mendeteksi regression;
- memperbarui model quality metrics.

---

## 10. Pilihan Teknologi

## Backend

```text
Python
FastAPI
Pydantic
SQLAlchemy
Alembic
HTTPX
```

## Database dan Cache

```text
PostgreSQL
Redis
```

## Async Processing

Pilih salah satu:

```text
Celery
Dramatiq
RQ
Arq
```

Untuk versi awal, worker sederhana berbasis Redis sudah cukup.

## Frontend

```text
Next.js
TypeScript
Tailwind CSS
TanStack Query
Recharts atau ECharts
```

## Authentication

```text
JWT
Session-based authentication
API key hashing
Optional OAuth
```

## Infrastructure

```text
Docker
Docker Compose
Nginx atau Caddy
GitHub Actions
```

## Observability Internal

```text
OpenTelemetry
Prometheus
Grafana
Structured JSON Logging
```

---

## 11. Struktur Database

## organizations

```text
id
name
slug
created_at
updated_at
```

## users

```text
id
email
password_hash
display_name
created_at
updated_at
```

## organization_members

```text
organization_id
user_id
role
created_at
```

## projects

```text
id
organization_id
name
slug
description
created_at
updated_at
```

## environments

```text
id
project_id
name
type
created_at
```

Contoh type:

```text
development
staging
production
```

## api_keys

```text
id
project_id
environment_id
name
key_prefix
key_hash
status
expires_at
last_used_at
created_at
```

## providers

```text
id
organization_id
name
provider_type
encrypted_credentials
base_url
timeout_seconds
enabled
created_at
updated_at
```

## models

```text
id
provider_id
model_name
display_name
context_window
capabilities_json
pricing_json
tags_json
enabled
created_at
updated_at
```

## virtual_models

```text
id
project_id
name
strategy
configuration_json
enabled
created_at
updated_at
```

## routing_rules

```text
id
project_id
name
priority
condition_json
action_json
enabled
created_at
updated_at
```

## requests

```text
id
trace_id
project_id
environment_id
api_key_id
virtual_model
selected_model_id
provider_id
status
prompt_tokens
completion_tokens
total_tokens
estimated_cost
latency_ms
started_at
completed_at
metadata_json
```

## request_attempts

```text
id
request_id
attempt_number
provider_id
model_id
status
error_type
error_message
latency_ms
prompt_tokens
completion_tokens
estimated_cost
started_at
completed_at
```

## budgets

```text
id
scope_type
scope_id
period
limit_amount
warning_threshold
action_at_limit
created_at
updated_at
```

## prompt_templates

```text
id
project_id
name
description
created_at
updated_at
```

## prompt_versions

```text
id
prompt_template_id
version
content
variables_json
model_configuration_json
created_by
created_at
```

## evaluations

```text
id
request_id
evaluation_type
score
result_json
created_at
```

---

## 12. API Design

## Health

```http
GET /health
GET /ready
```

## Chat Completion

```http
POST /v1/chat/completions
```

## Models

```http
GET /v1/models
```

## Provider Management

```http
GET    /api/providers
POST   /api/providers
GET    /api/providers/{provider_id}
PATCH  /api/providers/{provider_id}
DELETE /api/providers/{provider_id}
POST   /api/providers/{provider_id}/test
```

## Model Registry

```http
GET    /api/models
POST   /api/models
PATCH  /api/models/{model_id}
DELETE /api/models/{model_id}
```

## Virtual Models

```http
GET    /api/virtual-models
POST   /api/virtual-models
GET    /api/virtual-models/{virtual_model_id}
PATCH  /api/virtual-models/{virtual_model_id}
DELETE /api/virtual-models/{virtual_model_id}
```

## Routing Rules

```http
GET    /api/routing-rules
POST   /api/routing-rules
PATCH  /api/routing-rules/{rule_id}
DELETE /api/routing-rules/{rule_id}
POST   /api/routing-rules/simulate
```

## API Keys

```http
GET    /api/api-keys
POST   /api/api-keys
DELETE /api/api-keys/{key_id}
POST   /api/api-keys/{key_id}/rotate
```

## Traces

```http
GET /api/traces
GET /api/traces/{trace_id}
```

## Usage

```http
GET /api/usage/summary
GET /api/usage/timeseries
GET /api/usage/by-model
GET /api/usage/by-provider
GET /api/usage/by-project
```

## Budgets

```http
GET    /api/budgets
POST   /api/budgets
PATCH  /api/budgets/{budget_id}
DELETE /api/budgets/{budget_id}
```

## Prompts

```http
GET  /api/prompts
POST /api/prompts
POST /api/prompts/{prompt_id}/versions
GET  /api/prompts/{prompt_id}/versions
POST /api/prompts/{prompt_id}/activate
```

## Evaluations

```http
GET  /api/evaluations
POST /api/evaluations/run
GET  /api/evaluations/{evaluation_id}
```

---

## 13. Contoh Request

```json
{
  "model": "smart-router",
  "messages": [
    {
      "role": "system",
      "content": "Jawab secara singkat dan jelas."
    },
    {
      "role": "user",
      "content": "Apa perbedaan supervised dan unsupervised learning?"
    }
  ],
  "temperature": 0.2,
  "stream": false,
  "metadata": {
    "user_id": "usr_123",
    "task_type": "education",
    "data_classification": "public"
  }
}
```

---

## 14. Contoh Routing Decision

```json
{
  "trace_id": "trc_01JEXAMPLE",
  "virtual_model": "smart-router",
  "strategy": "weighted_score",
  "selected_model": "provider-b/model-balanced",
  "reason": {
    "capability_match": true,
    "budget_match": true,
    "health_status": "healthy",
    "estimated_cost": 0.0021,
    "estimated_latency_ms": 1800,
    "quality_score": 0.87,
    "final_score": 0.82
  },
  "rejected_candidates": [
    {
      "model": "provider-a/model-premium",
      "reason": "estimated cost exceeds route policy"
    },
    {
      "model": "ollama/local-model",
      "reason": "required tool calling capability unavailable"
    }
  ]
}
```

---

## 15. Repository Structure

```text
modeldock/
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── api/
│   │   │   ├── auth/
│   │   │   ├── core/
│   │   │   ├── db/
│   │   │   ├── models/
│   │   │   ├── providers/
│   │   │   ├── routing/
│   │   │   ├── policies/
│   │   │   ├── tracing/
│   │   │   ├── usage/
│   │   │   ├── evaluations/
│   │   │   └── main.py
│   │   ├── tests/
│   │   ├── alembic/
│   │   └── pyproject.toml
│   │
│   ├── worker/
│   │   ├── worker/
│   │   ├── tests/
│   │   └── pyproject.toml
│   │
│   └── web/
│       ├── app/
│       ├── components/
│       ├── features/
│       ├── lib/
│       ├── public/
│       └── package.json
│
├── packages/
│   ├── python-sdk/
│   ├── typescript-sdk/
│   └── shared-schemas/
│
├── deployments/
│   ├── docker/
│   ├── docker-compose.yml
│   └── nginx/
│
├── docs/
│   ├── architecture.md
│   ├── api-reference.md
│   ├── provider-adapters.md
│   ├── routing.md
│   ├── security.md
│   └── self-hosting.md
│
├── examples/
│   ├── python-basic/
│   ├── node-basic/
│   ├── langgraph-agent/
│   └── local-model-routing/
│
├── scripts/
├── .github/
│   └── workflows/
├── .env.example
├── CONTRIBUTING.md
├── LICENSE
├── README.md
└── SECURITY.md
```

---

## 16. Alur Request

```text
1. Client mengirim request.
2. Gateway memvalidasi API key.
3. Sistem memeriksa quota dan budget.
4. Request dinormalisasi.
5. Virtual model dibaca.
6. Routing rules dievaluasi.
7. Candidate models difilter berdasarkan capability.
8. Routing strategy memilih model.
9. Provider adapter mengirim request.
10. Jika gagal, retry dijalankan.
11. Jika tetap gagal, fallback digunakan.
12. Response dinormalisasi.
13. Usage dan cost dicatat.
14. Trace disimpan.
15. Evaluation dijalankan secara sinkron atau asinkron.
16. Response dikirim ke client.
```

---

## 17. Security

### Credential Security

- API key provider disimpan terenkripsi.
- Encryption key tidak disimpan dalam database.
- Credential tidak pernah dikirim ke frontend.
- Secret tidak dicatat dalam log.
- API key project disimpan dalam bentuk hash.

### Access Control

Role awal:

```text
Owner
Admin
Developer
Viewer
```

### Data Protection

- Redaction untuk Authorization header.
- Configurable request and response logging.
- Configurable retention period.
- PII masking opsional.
- Local-only routing policy.
- Audit log untuk perubahan konfigurasi.
- HTTPS untuk deployment produksi.

### Abuse Protection

- rate limiting;
- request size limit;
- prompt size limit;
- timeout;
- concurrency limit;
- blocked model list;
- IP allowlist;
- anomaly alerts.

---

## 18. Observability

Metrics penting:

```text
modeldock_requests_total
modeldock_request_duration_seconds
modeldock_tokens_total
modeldock_estimated_cost_total
modeldock_provider_errors_total
modeldock_fallback_total
modeldock_rate_limit_total
modeldock_active_requests
modeldock_budget_usage
```

Log menggunakan format JSON:

```json
{
  "level": "info",
  "event": "request_completed",
  "trace_id": "trc_01JEXAMPLE",
  "project_id": "prj_123",
  "provider": "provider-b",
  "model": "model-balanced",
  "status": "success",
  "latency_ms": 2194,
  "prompt_tokens": 843,
  "completion_tokens": 214,
  "estimated_cost": 0.0032
}
```

---

## 19. Testing Strategy

## Unit Test

- routing score;
- rule matching;
- cost estimation;
- quota calculation;
- budget checks;
- retry policy;
- error normalization;
- API key hashing;
- provider request transformation.

## Integration Test

- PostgreSQL;
- Redis;
- provider adapters;
- request tracing;
- streaming;
- retry;
- fallback;
- budget blocking.

## Contract Test

Setiap provider adapter harus menghasilkan response internal dengan schema yang sama.

## End-to-End Test

```text
Create project
→ Add provider
→ Register model
→ Create virtual model
→ Generate API key
→ Send completion request
→ Inspect trace
→ Verify usage dashboard
```

## Failure Injection

- simulated timeout;
- rate limit;
- malformed response;
- invalid credential;
- provider outage;
- Redis unavailable;
- database latency;
- streaming interrupted.

## Load Test

Ukur:

- request per second;
- p50 latency;
- p95 latency;
- p99 latency;
- concurrent streams;
- database write throughput;
- queue delay.

Tools yang dapat digunakan:

```text
Locust
k6
Pytest
Testcontainers
```

---

## 20. Tahapan Implementasi

## Phase 0 — Foundation

Target:

- monorepo;
- Docker Compose;
- FastAPI;
- PostgreSQL;
- Redis;
- migration;
- basic Next.js dashboard;
- CI;
- linting;
- testing.

Acceptance criteria:

- seluruh service berjalan melalui satu perintah;
- health endpoint tersedia;
- migration dapat dijalankan otomatis;
- CI menjalankan test dan lint.

## Phase 1 — Universal Gateway

Target:

- `/v1/chat/completions`;
- OpenAI-compatible request;
- non-streaming response;
- satu provider;
- model registry;
- request logging;
- trace ID.

Acceptance criteria:

- OpenAI SDK dapat menggunakan ModelDock hanya dengan mengganti base URL;
- request dan response tersimpan;
- error dikembalikan dengan schema konsisten.

## Phase 2 — Multi-Provider

Target:

- OpenAI adapter;
- Gemini adapter;
- Groq adapter;
- Ollama adapter;
- provider health check;
- provider configuration.

Acceptance criteria:

- satu request schema dapat digunakan untuk seluruh provider;
- administrator dapat mengaktifkan dan menonaktifkan provider;
- health status terlihat pada dashboard.

## Phase 3 — Routing and Fallback

Target:

- virtual model;
- priority routing;
- cheapest routing;
- rule-based routing;
- retry;
- fallback;
- routing decision log.

Acceptance criteria:

- model dapat dipilih tanpa perubahan kode client;
- fallback otomatis terjadi saat provider gagal;
- alasan pemilihan model terlihat pada trace.

## Phase 4 — Usage and Budget

Target:

- token tracking;
- cost estimation;
- usage aggregation;
- project budget;
- API key quota;
- dashboard usage.

Acceptance criteria:

- usage dapat difilter berdasarkan model, provider, dan project;
- request dapat diblokir setelah melewati budget;
- projected monthly usage tersedia.

## Phase 5 — Prompt Registry

Target:

- prompt templates;
- prompt versions;
- variable rendering;
- active version;
- prompt diff;
- rollback.

Acceptance criteria:

- prompt dapat diperbarui tanpa deployment aplikasi;
- setiap request dapat dikaitkan dengan prompt version;
- versi lama dapat diaktifkan kembali.

## Phase 6 — Evaluation

Target:

- test dataset;
- schema checks;
- latency checks;
- cost checks;
- user feedback;
- evaluation dashboard;
- regression comparison.

Acceptance criteria:

- dua model atau dua prompt version dapat dibandingkan;
- regression dapat terlihat pada dashboard;
- evaluation result terhubung ke trace.

## Phase 7 — Production Hardening

Target:

- RBAC;
- audit log;
- encrypted credentials;
- OpenTelemetry;
- Prometheus metrics;
- retention policy;
- backup guide;
- security documentation.

Acceptance criteria:

- deployment produksi memiliki security baseline;
- seluruh perubahan penting tercatat;
- request retention dapat dikonfigurasi.

---

## 21. MVP yang Disarankan

Jangan membangun semua fitur sekaligus.

### MVP v0.1

```text
Universal OpenAI-compatible API
OpenAI, Gemini, Groq, dan Ollama adapters
Provider management
Model registry
Virtual model
Priority routing
Retry dan fallback
Project API keys
Request tracing
Token dan cost tracking
Usage dashboard
Docker Compose deployment
```

### Fitur yang Ditunda

```text
LLM-as-judge
Semantic routing
Prompt playground kompleks
Multi-region deployment
Advanced RBAC
Custom billing
Marketplace
GPU scheduler
Kubernetes operator
```

---

## 22. User Stories MVP

### Provider

> Sebagai administrator, saya ingin menambahkan provider agar tim dapat memakai model tersebut melalui satu gateway.

### Virtual Model

> Sebagai developer, saya ingin menggunakan nama model virtual agar saya dapat mengganti provider tanpa mengubah kode aplikasi.

### Fallback

> Sebagai backend engineer, saya ingin request otomatis dialihkan saat provider gagal agar aplikasi tetap tersedia.

### Usage

> Sebagai pemilik project, saya ingin melihat token dan biaya agar saya dapat mengontrol pengeluaran.

### Trace

> Sebagai AI engineer, saya ingin melihat seluruh attempt dalam satu request agar saya dapat mendiagnosis error.

### Budget

> Sebagai administrator, saya ingin menetapkan budget bulanan agar penggunaan AI tidak melewati batas.

---

## 23. Acceptance Criteria MVP

- Dapat dijalankan dengan Docker Compose.
- Pengguna dapat membuat project.
- Pengguna dapat membuat API key.
- Pengguna dapat menambahkan minimal tiga provider.
- Pengguna dapat membuat virtual model.
- Aplikasi dapat menggunakan endpoint OpenAI-compatible.
- Request dapat dirutekan berdasarkan prioritas.
- Retry dan fallback bekerja.
- Token dan estimasi biaya tersimpan.
- Dashboard memperlihatkan request, error, latency, dan biaya.
- Trace memperlihatkan routing decision dan seluruh attempt.
- API key provider tersimpan terenkripsi.
- Test utama berjalan melalui CI.

---

## 24. Demo Utama

### Skenario

Sebuah aplikasi customer support menggunakan virtual model:

```text
support-production
```

Routing chain:

```text
Provider A / Premium Model
        ↓ fallback
Provider B / Balanced Model
        ↓ fallback
Ollama / Local Model
```

### Demo Steps

1. Kirim request normal.
2. Perlihatkan trace dan biaya.
3. Nonaktifkan provider utama.
4. Kirim request yang sama.
5. Perlihatkan fallback ke provider kedua.
6. Simulasikan budget hampir habis.
7. Perlihatkan routing otomatis ke model lebih murah.
8. Buka dashboard usage.
9. Bandingkan latency dan cost antar-provider.
10. Buka trace lengkap.

### Narasi Demo

```text
Aplikasi tidak mengetahui provider yang digunakan.
Aplikasi hanya memanggil virtual model.
ModelDock mengatur provider, fallback, budget, dan observability.
```

---

## 25. Dashboard Pages

```text
/overview
/providers
/models
/virtual-models
/routing-rules
/requests
/traces/[trace-id]
/usage
/budgets
/api-keys
/prompts
/evaluations
/settings
```

---

## 26. Tampilan Trace

```text
Request trc_01JEXAMPLE
Status: Success
Total latency: 4.9 seconds
Estimated cost: $0.0042

Timeline
14:20:31.102  Request received
14:20:31.108  API key authenticated
14:20:31.115  Budget policy passed
14:20:31.120  Route selected: support-production
14:20:31.131  Attempt 1 sent to Provider A
14:20:33.133  Attempt 1 timed out
14:20:33.141  Fallback activated
14:20:33.148  Attempt 2 sent to Provider B
14:20:35.982  Attempt 2 completed
14:20:35.990  Usage recorded
14:20:36.002  Response returned
```

---

## 27. Potensi Pengembangan Lanjutan

- Semantic routing.
- Automatic model benchmarking.
- A/B testing.
- Canary deployment untuk model dan prompt.
- Response caching.
- Semantic caching.
- Guardrails.
- PII detection.
- Data residency policies.
- Human approval workflow.
- Model load balancing.
- Provider circuit breaker.
- Automatic cost optimization.
- Multi-tenant billing.
- Kubernetes deployment.
- Terraform module.
- MCP gateway.
- Agent trace visualization.
- Evaluation dataset management.
- Custom provider plugin SDK.

---

## 28. Risiko Teknis

## Perbedaan Capability Provider

Tidak seluruh provider mendukung tool calling, structured output, streaming, atau parameter yang sama.

Mitigasi:

- capability registry;
- request validation;
- graceful degradation;
- feature-specific routing.

## Cost Tidak Akurat

Harga dapat berubah dan beberapa provider memiliki aturan perhitungan yang berbeda.

Mitigasi:

- konfigurasi pricing manual;
- pricing version;
- label `estimated_cost`;
- admin update workflow.

## Streaming Complexity

Format streaming setiap provider berbeda.

Mitigasi:

- internal event schema;
- adapter-level translation;
- contract testing.

## Log Sensitif

Prompt dan response dapat mengandung data pribadi.

Mitigasi:

- logging opt-out;
- redaction;
- retention policy;
- encryption;
- local-only mode.

## Retry Menghasilkan Duplikasi

Tool call atau operasi eksternal dapat terjadi lebih dari sekali.

Mitigasi:

- idempotency key;
- retry policy berdasarkan error;
- non-retryable operation flag;
- human approval untuk operasi berisiko.

---

## 29. Quality Metrics

### Reliability

```text
Success rate
Provider error rate
Fallback success rate
Timeout rate
Circuit breaker activation
```

### Performance

```text
p50 latency
p95 latency
p99 latency
Time to first token
Streaming interruption rate
```

### Cost

```text
Cost per request
Cost per project
Cost per user
Cost per model
Projected monthly cost
Savings from routing
```

### Quality

```text
Evaluation score
Schema validity
Tool call accuracy
User rating
Regression rate
```

---

## 30. Keunikan Portofolio

ModelDock bukan hanya aplikasi yang menggunakan AI.

ModelDock adalah infrastruktur yang digunakan oleh aplikasi AI lain.

Proyek ini menunjukkan kemampuan pada:

```text
AI Engineering
Backend Engineering
API Design
Distributed Systems
Database Design
Observability
Security
DevOps
Evaluation
Cost Optimization
Frontend Dashboard
Open-Source Product Design
```

---

## 31. Deskripsi GitHub

### Short Description

```text
Self-hosted AI control plane for routing, governing, tracing, and monitoring multiple language models through one OpenAI-compatible API.
```

### Topics

```text
ai-gateway
llm-router
openai-compatible
llm-observability
model-routing
self-hosted
fastapi
nextjs
ollama
ai-infrastructure
```

---

## 32. Contoh README Hero

```markdown
# ModelDock

Self-hosted AI control plane for multi-provider model routing, fallback,
usage tracking, budget enforcement, and request tracing.

## Why ModelDock?

- One OpenAI-compatible endpoint
- Multiple cloud and local providers
- Rule-based routing
- Retry and automatic fallback
- Per-project API keys
- Token and cost tracking
- Request trace explorer
- Self-hosted with Docker Compose
```

---

## 33. CV Bullet Points

```text
Built a self-hosted AI control plane that unified multiple cloud and local
language-model providers behind an OpenAI-compatible API.

Implemented rule-based model routing, provider retry and fallback, per-project
API keys, quota enforcement, token tracking, and request-level cost estimation.

Designed an end-to-end observability system for tracing routing decisions,
provider attempts, latency, errors, and model usage.

Developed a containerized architecture using FastAPI, PostgreSQL, Redis,
Next.js, and Docker Compose.
```

---

## 34. Interview Talking Points

### Mengapa Tidak Memakai Provider Langsung?

Agar aplikasi tidak terikat dengan satu vendor dan seluruh kebijakan penggunaan dapat dikelola secara terpusat.

### Mengapa Self-Hosted?

Untuk memberikan kontrol atas credential, log, biaya, data retention, dan model lokal.

### Bagaimana Menghindari Retry yang Berbahaya?

Retry hanya dilakukan untuk error tertentu. Operasi non-idempotent membutuhkan idempotency key atau tidak boleh di-retry otomatis.

### Bagaimana Routing Diputuskan?

Candidate model difilter berdasarkan capability dan policy, kemudian dipilih menggunakan strategy seperti priority, cheapest, fastest, atau weighted score.

### Bagaimana Biaya Dihitung?

Biaya dihitung berdasarkan pricing configuration yang dikaitkan dengan model dan versi pricing. Nilainya ditandai sebagai estimasi.

### Bagaimana Menangani Perbedaan API Provider?

Setiap provider menggunakan adapter yang menerjemahkan schema universal ke format provider dan mengubah response provider kembali ke schema internal.

---

## 35. Definition of Done

ModelDock dianggap siap dipamerkan ketika:

- repository memiliki dokumentasi lengkap;
- instalasi dapat dilakukan dengan satu perintah;
- minimal tiga provider tersedia;
- OpenAI SDK dapat terhubung;
- fallback dapat didemonstrasikan;
- dashboard memperlihatkan biaya dan latency;
- trace memperlihatkan seluruh lifecycle request;
- test berjalan di CI;
- tersedia contoh integrasi;
- tersedia video demo;
- tersedia arsitektur diagram;
- tersedia seed data untuk demo;
- tidak ada credential dalam repository.

---

## 36. Command Awal

```bash
git clone https://github.com/username/modeldock.git
cd modeldock
cp .env.example .env
docker compose up --build
```

Dashboard:

```text
http://localhost:3000
```

Gateway:

```text
http://localhost:8080/v1
```

API documentation:

```text
http://localhost:8080/docs
```

---

## 37. Prioritas Pengerjaan

Urutan implementasi yang paling aman:

```text
1. Project foundation
2. Universal request schema
3. Satu provider adapter
4. Request tracing
5. API key authentication
6. Provider dan model registry
7. Multi-provider adapters
8. Virtual models
9. Retry dan fallback
10. Usage dan cost tracking
11. Dashboard
12. Budget dan quota
13. Prompt registry
14. Evaluation
15. Production hardening
```

Jangan mulai dari dashboard atau routing berbasis AI. Bangun jalur request paling sederhana terlebih dahulu, lalu tambahkan kontrol dan observability secara bertahap.

---

## 38. Lisensi

Rekomendasi awal:

```text
Apache License 2.0
```

Lisensi ini cocok untuk proyek open-source infrastructure dan tetap mengizinkan penggunaan komersial dengan ketentuan lisensinya.

---

## 39. Kesimpulan

ModelDock adalah proyek portofolio berbentuk produk dan infrastructure platform, bukan sekadar fitur machine learning.

Versi awal harus fokus pada tiga hal:

1. satu API untuk banyak provider;
2. routing, retry, dan fallback yang dapat dijelaskan;
3. observability biaya, latency, dan error.

Setelah fondasi tersebut stabil, prompt management, evaluation, semantic routing, dan fitur enterprise dapat ditambahkan secara bertahap.
