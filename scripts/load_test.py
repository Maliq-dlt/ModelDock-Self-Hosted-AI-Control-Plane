import argparse
import asyncio
import statistics
import time

import httpx

async def run(url: str, api_key: str, model: str, requests: int, concurrency: int) -> None:
    semaphore = asyncio.Semaphore(concurrency)
    results: list[tuple[int, float]] = []
    headers = {"Authorization": f"Bearer {api_key}"}
    body = {"model": model, "messages": [{"role": "user", "content": "ModelDock load test"}]}

    async with httpx.AsyncClient(timeout=120) as client:
        async def one() -> None:
            async with semaphore:
                started = time.perf_counter()
                try:
                    response = await client.post(url, headers=headers, json=body)
                    results.append((response.status_code, (time.perf_counter() - started) * 1000))
                except httpx.HTTPError:
                    results.append((0, (time.perf_counter() - started) * 1000))

        await asyncio.gather(*(one() for _ in range(requests)))
    latencies = [latency for _, latency in results]
    counts: dict[int, int] = {}
    for code, _ in results:
        counts[code] = counts.get(code, 0) + 1
    print({"requests": len(results), "status_counts": counts, "p50_ms": round(statistics.median(latencies), 2), "max_ms": round(max(latencies), 2)})

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ModelDock gateway load test")
    parser.add_argument("--url", default="http://localhost:8080/v1/chat/completions")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()
    if args.requests < 1 or args.concurrency < 1:
        raise SystemExit("requests and concurrency must be positive")
    asyncio.run(run(args.url, args.api_key, args.model, args.requests, args.concurrency))