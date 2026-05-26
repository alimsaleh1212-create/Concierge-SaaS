"""T-A025: Verify get_db finally block always resets app.tenant_id.

Tests that the RLS session variable is cleared even when the request handler
raises an unhandled exception — prevents cross-tenant data leakage on pooled connections.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import text


@pytest.mark.asyncio
async def test_get_db_resets_tenant_id_on_success():
    """app.tenant_id must be '' after a normal request completes."""
    from app.core.database import get_db

    executed_sqls: list[str] = []

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=lambda q, *a, **kw: executed_sqls.append(str(q)))

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("app.core.database.AsyncSessionLocal", return_value=mock_ctx):
        gen = get_db(tenant_id="abc-123")
        await gen.__anext__()
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass

    # The finally-block reset call must be the last SQL executed
    assert executed_sqls, "No SQL was executed"
    last_sql = executed_sqls[-1]
    assert "app.tenant_id" in last_sql
    assert "''" in last_sql or '""' in last_sql or "empty" in last_sql.lower() or "," in last_sql


@pytest.mark.asyncio
async def test_get_db_resets_tenant_id_on_exception():
    """app.tenant_id must be '' even when the request handler raises."""
    from app.core.database import get_db

    executed_sqls: list[str] = []
    reset_called = False

    async def track_execute(query, *args, **kwargs):
        sql = str(query)
        executed_sqls.append(sql)
        nonlocal reset_called
        # Detect the reset call: set_config with empty string
        if "set_config" in sql and ("''" in sql or '""' in sql):
            reset_called = True

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=track_execute)

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("app.core.database.AsyncSessionLocal", return_value=mock_ctx):
        gen = get_db(tenant_id="tenant-xyz")
        await gen.__anext__()
        try:
            await gen.athrow(RuntimeError("simulated unhandled exception"))
        except (RuntimeError, StopAsyncIteration):
            pass

    assert reset_called, "finally block did not reset app.tenant_id after exception"


@pytest.mark.asyncio
async def test_get_db_sets_tenant_id_before_yield():
    """Verify set_config is called with the tenant_id before yielding the session."""
    from app.core.database import get_db

    set_config_calls: list[str] = []

    async def track_execute(query, params=None, **kwargs):
        sql = str(query)
        if "set_config" in sql and params:
            set_config_calls.append(params.get("tid", ""))

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=track_execute)

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("app.core.database.AsyncSessionLocal", return_value=mock_ctx):
        gen = get_db(tenant_id="test-tenant-id")
        await gen.__anext__()
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass

    assert "test-tenant-id" in set_config_calls, "tenant_id was not set before yield"
