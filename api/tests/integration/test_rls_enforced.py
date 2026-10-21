"""Postgres RLS is enforced for the API's app role (isolation layer 1).

Runs against a live, seeded database as the app role, so it proves the policies
themselves isolate tenants — independent of repository-layer filters.

    RLS_TEST_DATABASE_URL=postgresql://concierge_app:<password>@localhost:5432/concierge \
        pytest tests/integration/test_rls_enforced.py

Skipped when RLS_TEST_DATABASE_URL is unset. Needs at least two tenants with
CMS content (the demo seeds provide this).
"""
import os
import uuid

import pytest

asyncpg = pytest.importorskip("asyncpg")

DSN = os.getenv("RLS_TEST_DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")

pytestmark = pytest.mark.skipif(not DSN, reason="RLS_TEST_DATABASE_URL not set")

_TENANT_TABLES = ["widgets", "cms_content", "conversations", "messages", "leads", "embeddings"]


@pytest.fixture
async def conn():
    connection = await asyncpg.connect(DSN)
    try:
        yield connection
    finally:
        await connection.close()


async def _tenant_ids(conn) -> list[uuid.UUID]:
    """Tenants that have CMS content, checked inside each tenant's own context."""
    # tenants has no RLS; cms_content is only visible once the tenant is set
    with_content = []
    for row in await conn.fetch("SELECT id FROM tenants ORDER BY id"):
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(row["id"]))
            if await conn.fetchval("SELECT count(*) FROM cms_content") > 0:
                with_content.append(row["id"])
    return with_content


async def test_app_role_cannot_bypass_rls(conn):
    row = await conn.fetchrow(
        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
    )
    assert row["rolsuper"] is False
    assert row["rolbypassrls"] is False


async def test_no_tenant_context_sees_no_tenant_rows(conn):
    for table in _TENANT_TABLES:
        assert await conn.fetchval(f"SELECT count(*) FROM {table}") == 0, table
    # users must not error on an unset/empty tenant (migration 004)
    await conn.execute("SELECT set_config('app.tenant_id', '', false)")
    tenant_users = await conn.fetchval("SELECT count(*) FROM users WHERE tenant_id IS NOT NULL")
    assert tenant_users == 0


async def test_tenant_context_sees_only_own_rows(conn):
    tenants = await _tenant_ids(conn)
    if len(tenants) < 2:
        pytest.skip("needs two seeded tenants")

    for tenant in tenants:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(tenant))
            for table in _TENANT_TABLES:
                foreign = await conn.fetchval(
                    f"SELECT count(*) FROM {table} WHERE tenant_id <> $1", tenant
                )
                assert foreign == 0, f"{table} leaked rows from another tenant"


async def test_cannot_write_rows_for_another_tenant(conn):
    tenants = await _tenant_ids(conn)
    if len(tenants) < 2:
        pytest.skip("needs two seeded tenants")
    tenant_a, tenant_b = tenants[0], tenants[1]

    # Always roll back: against a role that bypasses RLS the insert would succeed
    tx = conn.transaction()
    await tx.start()
    try:
        await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(tenant_a))
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            await conn.execute(
                "INSERT INTO cms_content (id, tenant_id, title, body, content_type) "
                "VALUES ($1, $2, 'rls probe', 'rls probe', 'faq')",
                uuid.uuid4(),
                tenant_b,
            )
    finally:
        await tx.rollback()


async def test_audit_log_is_append_only(conn):
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
        await conn.execute("UPDATE audit_log SET action = action WHERE false")
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
        await conn.execute("DELETE FROM audit_log WHERE false")
