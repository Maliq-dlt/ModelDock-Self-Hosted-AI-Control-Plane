import time
from collections import defaultdict

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

_fallback: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
_redis: Redis | None = None


async def enforce_rate_limit(subject: str, limit: int | None = None) -> None:
    settings = get_settings()
    limit = settings.rate_limit_per_minute if limit is None else limit
    if limit <= 0:
        return
    minute = int(time.time() // 60)
    key = f"modeldock:rate:{subject}:{minute}"
    global _redis
    try:
        if _redis is None:
            _redis = Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=0.2, socket_timeout=0.2)
        count = await _redis.incr(key)
        if count == 1:
            await _redis.expire(key, 70)
    except RedisError:
        seen_minute, count = _fallback[subject]
        count = count + 1 if seen_minute == minute else 1
        _fallback[subject] = (minute, count)
    if count > limit:
        from fastapi import HTTPException

        raise HTTPException(status_code=429, detail="Rate limit exceeded")
