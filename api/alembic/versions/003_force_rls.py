"""Activate RLS enforcement: safe policies + FORCE ROW LEVEL SECURITY

Revision ID: 003_force_rls
Revises: 002_messages_is_deleted
Create Date: 2026-05-27

Fixes two related gaps (C2 from spec analysis):
  1. The existing policies cast current_setting('app.tenant_id', true)::uuid directly,
     which throws "invalid input syntax for type uuid" when the setting is '' (empty).
     Safe policies guard the cast with a <> '' check so rows are blocked (not errored)
     when no tenant context is set.
  2. FORCE ROW LEVEL SECURITY ensures RLS fires even when the connection role is the
     table owner — which it is in dev (user: concierge).

The users table is intentionally left without FORCE RLS because platform routes
(tenant_manager) create and read users with NULL tenant_id.  The users RLS policy
already has a 'tenant_id IS NULL' branch, but FORCE RLS + platform ops that query
users without a tenant context would incorrectly hide tenant admin rows on refresh.
All other tenant-data tables are forced.
"""
from alembic import op

revision = "003_force_rls"
down_revision = "002_messages_is_deleted"
branch_labels = None
depends_on = None


_TENANT_TABLES = [
    "widgets",
    "cms_content",
    "conversations",
    "messages",
    "leads",
    "embeddings",
]

_SAFE_POLICY = (
    "current_setting('app.tenant_id', true) <> '' "
    "AND tenant_id = current_setting('app.tenant_id', true)::uuid"
)


def upgrade() -> None:
    for table in _TENANT_TABLES:
        # Replace the policy with the safe-cast version (no error on empty setting)
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({_SAFE_POLICY})"
        )
        # Now force RLS so the table owner is also bound by the policy
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    _ORIG_POLICY = "tenant_id = current_setting('app.tenant_id', true)::uuid"
    for table in _TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({_ORIG_POLICY})"
        )
