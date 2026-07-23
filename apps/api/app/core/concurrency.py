import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import HTTPException

_counts: dict[str, int] = defaultdict(int)
_lock = asyncio.Lock()


@asynccontextmanager
async def request_slot(subject: str, limit: int):
    async with _lock:
        if _counts[subject] >= limit:
            raise HTTPException(status_code=429, detail="Concurrent request limit exceeded")
        _counts[subject] += 1
    try:
        yield
    finally:
        async with _lock:
            _counts[subject] = max(0, _counts[subject] - 1)
