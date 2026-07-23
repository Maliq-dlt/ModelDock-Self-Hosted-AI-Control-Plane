from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProviderAccount


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def select_provider_account(
    session: AsyncSession,
    provider_id: str,
) -> tuple[ProviderAccount | None, bool]:
    accounts = (
        await session.scalars(
            select(ProviderAccount)
            .where(ProviderAccount.provider_id == provider_id, ProviderAccount.enabled.is_(True))
            .order_by(ProviderAccount.priority, ProviderAccount.last_used_at, ProviderAccount.created_at)
        )
    ).all()
    if not accounts:
        return None, False

    now = datetime.now(timezone.utc)
    for account in accounts:
        if account.quota_remaining is not None and account.quota_remaining <= 0:
            if account.quota_reset_at and _utc(account.quota_reset_at) <= now:
                account.quota_remaining = None
                account.quota_reset_at = None
            else:
                continue
        account.last_used_at = now
        return account, True
    return None, True
