from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, RequestRecord


async def purge_retained_data(session: AsyncSession, retention_days: int) -> dict[str, int]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    request_result = await session.execute(delete(RequestRecord).where(RequestRecord.started_at < cutoff))
    audit_result = await session.execute(delete(AuditLog).where(AuditLog.created_at < cutoff))
    await session.commit()
    return {"requests_deleted": request_result.rowcount or 0, "audit_logs_deleted": audit_result.rowcount or 0}
