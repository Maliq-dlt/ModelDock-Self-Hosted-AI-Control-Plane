import argparse
import os

import httpx

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live ModelDock provider E2E request")
    parser.add_argument("--url", default=os.getenv("MODELDOCK_URL", "http://localhost:8080/v1/chat/completions"))
    parser.add_argument("--api-key", default=os.getenv("MODELDOCK_API_KEY"))
    parser.add_argument("--model", default=os.getenv("MODELDOCK_MODEL"))
    parser.add_argument("--prompt", default="Provider E2E smoke test")
    args = parser.parse_args()
    if not args.api_key or not args.model:
        raise SystemExit("set MODELDOCK_API_KEY and MODELDOCK_MODEL or pass flags")
    response = httpx.post(args.url, headers={"Authorization": f"Bearer {args.api_key}"}, json={"model": args.model, "messages": [{"role": "user", "content": args.prompt}]}, timeout=120)
    response.raise_for_status()
    payload = response.json()
    print({"status_code": response.status_code, "trace_id": response.headers.get("X-ModelDock-Trace-ID"), "model": payload.get("model"), "finish_reason": (payload.get("choices") or [{}])[0].get("finish_reason")})