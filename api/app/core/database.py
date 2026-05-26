from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    settings = get_settings()
    return create_async_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )


engine = _make_engine()

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db(tenant_id: str = "") -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a session with app.tenant_id set for RLS.

    The finally block ALWAYS resets app.tenant_id to '' — a pooled connection
    that retains a stale tenant_id is a cross-tenant breach.
    """
    async with AsyncSessionLocal() as session:
        try:
            if tenant_id:
                await session.execute(
                    text("SELECT set_config('app.tenant_id', :tid, true)"),
                    {"tid": tenant_id},
                )
            yield session
        finally:
            await session.execute(
                text("SELECT set_config('app.tenant_id', '', true)")
            )
