# Contributing

1. Create `.env` with `scripts/bootstrap.ps1`.
2. Install API dependencies with `uv sync --project apps/api --extra test`.
3. Install web dependencies with `npm install --prefix apps/web`.
4. Run `uv run --project apps/api pytest` and `npm run build --prefix apps/web`.
5. Keep changes focused and include tests for non-trivial routing, policy, or provider behavior.
