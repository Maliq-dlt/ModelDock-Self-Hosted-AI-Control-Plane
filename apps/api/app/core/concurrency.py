import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import HTTPException
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

_fallback_counts: dict[str, int] = defaultdict(int)
_fallback_lock = asyncio.Lock()
_redis: Redis | None = None


@asynccontextmanager
async def request_slot(subject: str, limit: int):
    settings = get_settings()
    key = f"modeldock:concurrency:{subject}"
    distributed = False
    fallback = False
    global _redis
    try:
        if _redis is None:
            _redis = Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=0.2, socket_timeout=0.2)
        count = await _redis.incr(key)
        if count == 1:
            await _redis.expire(key, max(60, int(settings.request_timeout_seconds) + 60))
        if count > limit:
            try:
                await _redis.decr(key)
            except RedisError:
                pass
            raise HTTPException(status_code=429, detail="Concurrent request limit exceeded")
        distributed = True
    except RedisError:
        async with _fallback_lock:
            if _fallback_counts[subject] >= limit:
                raise HTTPException(status_code=429, detail="Concurrent request limit exceeded")
            _fallback_counts[subject] += 1
            fallback = True
    try:
        yield
    finally:
        if distributed:
            try:
                await _redis.decr(key)
            except RedisError:
                pass
        elif fallback:
            async with _fallback_lock:
                _fallback_counts[subject] = max(0, _fallback_counts[subject] - 1)
