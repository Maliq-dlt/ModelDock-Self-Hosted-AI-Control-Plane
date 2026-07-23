# Contributing

ModelDock menerima perubahan kecil, teruji, dan dapat diaudit. Baca `GOVERNANCE.md` sebelum perubahan arsitektur besar.

## Setup

```powershell
.\scripts\bootstrap.ps1
$env:UV_CACHE_DIR = ".uv-cache"
uv sync --project apps/api --extra test
$env:npm_config_cache = ".cache/npm"
npm ci --prefix apps/web
```

## Quality Gate

Jalankan sebelum pull request:

```powershell
uv run --project apps/api pytest apps/api/tests -p no:cacheprovider
uv run --project apps/api ruff check apps/api/app apps/api/tests
npm run lint --prefix apps/web
npm run build --prefix apps/web
docker compose --env-file .env.example config
git diff --check
```

Non-trivial logic wajib punya test. Jangan commit secret, dump DB, `.env`, atau output runtime.

## Change Rules

- Pertahankan OpenAI-compatible behavior.
- Jangan potong output model untuk menghemat token.
- TokenPress hanya boleh memakai transformasi lossless atau output guidance eksplisit.
- Provider credential wajib tetap terenkripsi.
- Migration wajib backward-aware dan diuji pada fresh SQLite.
- Perubahan security, routing, schema, dan provider wajib menyertakan alasan pada pull request.

## Pull Request

Isi problem, scope, test command, migration impact, security impact, dan limitation. Gunakan template pull request.
