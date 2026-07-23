from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


async def init_db() -> None:
    from app import models  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def ensure_bootstrap_admin() -> None:
    from app.core.config import get_settings
    from app.core.security import hash_password
    from app.models import AdminUser
    from sqlalchemy import select

    settings = get_settings()
    if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
        return
    async with session_factory() as session:
        existing = await session.scalar(select(AdminUser).where(AdminUser.email == settings.bootstrap_admin_email.lower()))
        if not existing:
            session.add(AdminUser(email=settings.bootstrap_admin_email.lower(), password_hash=hash_password(settings.bootstrap_admin_password), role="owner"))
            await session.commit()


async def dispose_db() -> None:
    await engine.dispose()
