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


_engine = None
_session_local = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = _make_engine()
    return _engine


def _get_session_local():
    global _session_local
    if _session_local is None:
        _session_local = async_sessionmaker(
            _get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _session_local


def get_session_local():
    """Return the sessionmaker, creating the engine on first call."""
    return _get_session_local()


# Kept for Alembic env.py and any code that needs a direct engine reference.
def get_engine():
    return _get_engine()


# Backwards-compatible module-level name used by seeds and tests that
# import AsyncSessionLocal directly — resolved lazily via __getattr__.
class _LazySessionLocal:
    """Proxy so `async with AsyncSessionLocal() as s:` works without eager init."""
    def __call__(self, *args, **kwargs):
        return _get_session_local()(*args, **kwargs)


AsyncSessionLocal = _LazySessionLocal()


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
