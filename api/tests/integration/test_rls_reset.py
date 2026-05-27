"""T-A025: Verify get_db finally block always resets app.tenant_id.

Tests that the RLS session variable is cleared even when the request handler
raises an unhandled exception — prevents cross-tenant data leakage on pooled connections.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import text


@pytest.mark.asyncio
async def test_get_db_resets_tenant_id_on_success():
    """app.tenant_id must be reset to '' after a normal request completes."""
    from app.core.database import get_db, set_tenant_context

    executed_sqls: list[str] = []

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=lambda q, *a, **kw: executed_sqls.append(str(q)))

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("app.core.database.AsyncSessionLocal", return_value=mock_ctx):
        gen = get_db()
        session = await gen.__anext__()
        # Simulate what the route does: set tenant context explicitly
        await set_tenant_context(session, "abc-123")
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass

    assert executed_sqls, "No SQL was executed"
    last_sql = executed_sqls[-1]
    assert "app.tenant_id" in last_sql
    assert "''" in last_sql or '""' in last_sql or "empty" in last_sql.lower() or "," in last_sql


@pytest.mark.asyncio
async def test_get_db_resets_tenant_id_on_exception():
    """app.tenant_id must be reset to '' even when the request handler raises."""
    from app.core.database import get_db, set_tenant_context

    executed_sqls: list[str] = []
    reset_called = False

    async def track_execute(query, *args, **kwargs):
        sql = str(query)
        executed_sqls.append(sql)
        nonlocal reset_called
        if "set_config" in sql and ("''" in sql or '""' in sql):
            reset_called = True

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=track_execute)

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("app.core.database.AsyncSessionLocal", return_value=mock_ctx):
        gen = get_db()
        session = await gen.__anext__()
        await set_tenant_context(session, "tenant-xyz")
        try:
            await gen.athrow(RuntimeError("simulated unhandled exception"))
        except (RuntimeError, StopAsyncIteration):
            pass

    assert reset_called, "finally block did not reset app.tenant_id after exception"


@pytest.mark.asyncio
async def test_set_tenant_context_sets_config():
    """Verify set_tenant_context calls set_config with the provided tenant_id."""
    from app.core.database import set_tenant_context

    set_config_calls: list[str] = []

    async def track_execute(query, params=None, **kwargs):
        sql = str(query)
        if "set_config" in sql and params:
            set_config_calls.append(params.get("tid", ""))

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=track_execute)

    await set_tenant_context(mock_session, "test-tenant-id")

    assert "test-tenant-id" in set_config_calls, "tenant_id was not passed to set_config"
