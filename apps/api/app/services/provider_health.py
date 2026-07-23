from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.models import Provider

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

def circuit_open(provider: Provider, now: datetime | None = None) -> bool:
    opened_until = _aware(provider.circuit_open_until)
    return opened_until is not None and opened_until > (now or now_utc())

def record_provider_success(provider: Provider, latency_ms: float) -> None:
    provider.health_status = "healthy"
    provider.last_health_checked_at = now_utc()
    provider.last_health_latency_ms = latency_ms
    provider.consecutive_failures = 0
    provider.circuit_open_until = None
    provider.reliability_score = min(1.0, provider.reliability_score * 0.9 + 0.1)

def record_provider_failure(provider: Provider, latency_ms: float) -> None:
    settings = get_settings()
    provider.last_health_checked_at = now_utc()
    provider.last_health_latency_ms = latency_ms
    provider.consecutive_failures += 1
    provider.reliability_score = max(0.0, provider.reliability_score * 0.9)
    if provider.consecutive_failures >= settings.circuit_breaker_failure_threshold:
        provider.health_status = "unhealthy"
        provider.circuit_open_until = now_utc() + timedelta(seconds=settings.circuit_breaker_cooldown_seconds)
    else:
        provider.health_status = "degraded"