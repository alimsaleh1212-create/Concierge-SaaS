"""add is_deleted to messages table (FR-006 compliance)

Revision ID: 002_messages_is_deleted
Revises: 001_baseline
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa

revision = "002_messages_is_deleted"
down_revision = "001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_messages_tenant_deleted",
        "messages",
        ["tenant_id", "is_deleted"],
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    op.drop_index("ix_messages_tenant_deleted", table_name="messages")
    op.drop_column("messages", "is_deleted")
