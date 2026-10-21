"""Make the users RLS policy safe when app.tenant_id is unset

The users policy cast current_setting('app.tenant_id', true)::uuid directly.
Once a session has set and reset the variable it reads as '' and the cast
raises "invalid input syntax for type uuid". That never surfaced while the API
connected as a superuser (RLS bypassed); under the NOBYPASSRLS app role it
would fail any users query outside a tenant context. NULLIF turns '' into NULL
so the comparison is simply false.

Revision ID: 004_users_rls_safe_cast
Revises: 003_force_rls
Create Date: 2026-10-21
"""
from alembic import op

revision = "004_users_rls_safe_cast"
down_revision = "003_force_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON users")
    op.execute(
        "CREATE POLICY tenant_isolation ON users USING ("
        "tenant_id IS NULL "
        "OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON users")
    op.execute(
        "CREATE POLICY tenant_isolation ON users USING ("
        "tenant_id IS NULL "
        "OR tenant_id = current_setting('app.tenant_id', true)::uuid)"
    )
