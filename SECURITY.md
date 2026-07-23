# Security

Laporkan kerentanan secara privat ke maintainer. Jangan membuka issue publik yang memuat exploit, credential, token, atau data request.

## Batas Autentikasi

- Endpoint gateway `/v1/*` memerlukan project API key melalui `Authorization: Bearer md_live_*` atau `md_test_*`.
- Endpoint management `/api/*` menerima `X-ModelDock-Admin-Key` untuk bootstrap/operasi server-side.
- Admin user dapat login melalui `POST /api/auth/login`, lalu memakai `Authorization: Bearer md_admin_*`.
- Admin session berlaku delapan jam dan ditandatangani HMAC-SHA256 menggunakan `ADMIN_SESSION_SECRET` atau fallback `ADMIN_API_KEY`.
- Password admin disimpan sebagai hash `scrypt` dengan salt acak.
- Role `owner`, `admin`, `developer`, dan `viewer` tersedia. Permission dibedakan berdasarkan method/resource; `admin` dapat mengelola user non-owner, sedangkan hanya `owner` dapat membuat atau mengubah owner. `POST /api/auth/logout-all` menaikkan session version dan mencabut semua session user.

`X-ModelDock-Admin-Key` adalah credential berkekuatan penuh dan melewati pemeriksaan role. Batasi pemakaiannya ke bootstrap, dashboard server-side, dan automation tepercaya.

## Credential dan Secret

- Credential provider dienkripsi dengan Fernet sebelum disimpan ke database.
- Project API key disimpan sebagai HMAC-SHA256; raw key hanya dikembalikan saat pembuatan atau rotasi.
- `ADMIN_API_KEY`, `ADMIN_SESSION_SECRET`, `API_KEY_HASH_SECRET`, dan `CREDENTIAL_ENCRYPTION_KEY` hanya berasal dari environment.
- Authorization header dan credential provider tidak disimpan dalam trace.
- `.env` diabaikan Git. Jangan commit file backup, dump database, atau log yang mungkin memuat data sensitif.

Rotasi `ADMIN_API_KEY`, `ADMIN_SESSION_SECRET`, dan `API_KEY_HASH_SECRET` akan memutus credential atau session lama. Rotasi `CREDENTIAL_ENCRYPTION_KEY` memerlukan migrasi terkontrol: decrypt memakai key lama, lalu encrypt ulang memakai key baru.

## Kontrol Project API Key

Setiap key mendukung:

- expiry dan revocation;
- rotasi dengan revocation key lama;
- request-per-minute limit;
- monthly token quota;
- maximum concurrent requests;
- model allowlist;
- IP allowlist;
- last-used timestamp.

Budget project dapat memblokir request sebelum provider dipanggil. `Idempotency-Key` dapat replay hasil non-streaming sukses tanpa memanggil provider lagi.

## Data dan Observability

- Request payload tidak disimpan kecuali `LOG_PAYLOADS=true`.
- Trace menyimpan keputusan routing, attempt, status, latency, token, dan estimasi biaya.
- Audit log merekam perubahan endpoint management beserta status HTTP, tetapi tidak menyimpan body atau credential.
- `/metrics` hanya mengeluarkan agregat status request.
- Retention default 30 hari dan dapat dijalankan lewat CLI atau `POST /api/retention/run`.

## Proteksi Runtime

- Request body dibatasi oleh `MAX_REQUEST_BODY_BYTES`.
- Timeout provider dan retry aman diterapkan per attempt.
- Provider concurrency limit, failure counter, reliability score, dan circuit breaker cooldown mencegah traffic terus dikirim ke provider gagal.
- Error `408`, `409`, `425`, `429`, dan `5xx` dapat di-retry; error lain tidak.
- Rate limiter memakai Redis dan fallback in-process saat Redis tidak tersedia.
- CORS dibatasi melalui `CORS_ORIGINS`.

## Checklist Produksi

1. Ganti seluruh secret contoh dengan nilai acak kuat.
2. Gunakan HTTPS dan batasi `/api/*`, `/docs`, dan `/metrics` pada jaringan admin.
3. Gunakan secret manager; jangan menaruh secret langsung di manifest Kubernetes.
4. Pakai PostgreSQL/Redis terkelola atau HA, backup terenkripsi, dan uji restore.
5. Biarkan `LOG_PAYLOADS=false` kecuali ada kebutuhan eksplisit dan kebijakan retensi memadai.
6. Atur `CORS_ORIGINS` ke origin dashboard produksi.
7. Aktifkan OTLP hanya ke collector tepercaya dan audit atribut yang diekspor.
8. Pastikan NetworkPolicy mengizinkan DNS dan hanya egress provider yang diperlukan pada TCP 80/443.
9. Jalankan migration sebelum menerima traffic.