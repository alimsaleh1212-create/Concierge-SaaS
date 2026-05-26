"""baseline: all enums, tables, indexes, triggers, RLS policies

Revision ID: 001_baseline
Revises:
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extensions ────────────────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ── Enums ─────────────────────────────────────────────────────────────────
    op.execute("CREATE TYPE user_role AS ENUM ('tenant_manager', 'tenant_admin', 'member')")
    op.execute("CREATE TYPE actor_role AS ENUM ('tenant_manager', 'tenant_admin', 'member')")
    op.execute("CREATE TYPE content_type AS ENUM ('faq', 'page', 'product')")
    op.execute("CREATE TYPE conversation_status AS ENUM ('active', 'escalated', 'closed')")
    op.execute("CREATE TYPE lead_status AS ENUM ('new', 'contacted', 'closed')")
    op.execute("CREATE TYPE message_role AS ENUM ('user', 'assistant')")

    # ── updated_at trigger function ───────────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
          NEW.updated_at = NOW();
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    # ── tenants (no RLS — platform table) ────────────────────────────────────
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("allowed_origins", postgresql.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=True)
    op.create_index("ix_tenants_is_active", "tenants", ["is_active"],
                    postgresql_where=sa.text("is_active = true"))
    op.execute("""
        CREATE TRIGGER trg_tenants_updated_at
        BEFORE UPDATE ON tenants
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("hashed_password", sa.String(1024), nullable=False),
        sa.Column("role", sa.Enum("tenant_manager", "tenant_admin", "member", name="user_role", create_type=False), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_tenant_role", "users", ["tenant_id", "role"])
    op.execute("""
        CREATE TRIGGER trg_users_updated_at
        BEFORE UPDATE ON users
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON users
        USING (
            tenant_id IS NULL
            OR tenant_id = current_setting('app.tenant_id', true)::uuid
        )
    """)

    # ── widgets ───────────────────────────────────────────────────────────────
    op.create_table(
        "widgets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("widget_token_secret", sa.String(64), nullable=False),
        sa.Column("allowed_origins", postgresql.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("theme_config", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("greeting", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_widgets_tenant_active", "widgets", ["tenant_id", "is_active"])
    op.create_index("ix_widgets_is_deleted", "widgets", ["is_deleted"],
                    postgresql_where=sa.text("is_deleted = false"))
    op.execute("""
        CREATE TRIGGER trg_widgets_updated_at
        BEFORE UPDATE ON widgets
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)
    op.execute("ALTER TABLE widgets ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON widgets
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    """)

    # ── cms_content ───────────────────────────────────────────────────────────
    op.create_table(
        "cms_content",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("content_type", sa.Enum("faq", "page", "product", name="content_type", create_type=False), nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_cms_content_tenant_type", "cms_content", ["tenant_id", "content_type"])
    op.create_index("ix_cms_content_tenant_deleted", "cms_content", ["tenant_id", "is_deleted"],
                    postgresql_where=sa.text("is_deleted = false"))
    op.execute("""
        CREATE TRIGGER trg_cms_content_updated_at
        BEFORE UPDATE ON cms_content
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)
    op.execute("ALTER TABLE cms_content ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON cms_content
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    """)

    # ── conversations ─────────────────────────────────────────────────────────
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("widget_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("widgets.id"), nullable=False),
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("visitor_ip_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.Enum("active", "escalated", "closed", name="conversation_status", create_type=False), nullable=False, server_default="active"),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_conversations_tenant_status", "conversations", ["tenant_id", "status"])
    op.create_index("ix_conversations_tenant_widget", "conversations", ["tenant_id", "widget_id"])
    op.execute("""
        CREATE TRIGGER trg_conversations_updated_at
        BEFORE UPDATE ON conversations
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)
    op.execute("ALTER TABLE conversations ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON conversations
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    """)

    # ── messages ──────────────────────────────────────────────────────────────
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("role", sa.Enum("user", "assistant", name="message_role", create_type=False), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("is_redacted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_messages_tenant_conv_time", "messages", ["tenant_id", "conversation_id", "created_at"])
    op.execute("""
        CREATE TRIGGER trg_messages_updated_at
        BEFORE UPDATE ON messages
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)
    op.execute("ALTER TABLE messages ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON messages
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    """)

    # ── leads ─────────────────────────────────────────────────────────────────
    op.create_table(
        "leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("visitor_name", sa.String(255), nullable=True),
        sa.Column("visitor_email", sa.String(320), nullable=True),
        sa.Column("visitor_phone", sa.String(50), nullable=True),
        sa.Column("intent", sa.Text, nullable=False),
        sa.Column("score", sa.Float, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("status", sa.Enum("new", "contacted", "closed", name="lead_status", create_type=False), nullable=False, server_default="new"),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_leads_tenant_status", "leads", ["tenant_id", "status"])
    op.create_index("ix_leads_tenant_created", "leads", ["tenant_id", "created_at"])
    op.execute("""
        CREATE TRIGGER trg_leads_updated_at
        BEFORE UPDATE ON leads
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)
    op.execute("ALTER TABLE leads ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON leads
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    """)

    # ── embeddings ────────────────────────────────────────────────────────────
    # VECTOR(1024) is added via raw DDL after table creation to avoid pgvector
    # type registration issues in non-connected Alembic contexts.
    op.create_table(
        "embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("content_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cms_content.id"), nullable=False),
        sa.Column("chunk_text", sa.Text, nullable=False),
        sa.Column("parent_chunk_text", sa.Text, nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.execute("ALTER TABLE embeddings ADD COLUMN embedding VECTOR(1024) NOT NULL")
    op.create_index("ix_embeddings_tenant_content", "embeddings", ["tenant_id", "content_id"])
    # IVFFlat index created after initial data load — not at table creation time
    # op.execute("CREATE INDEX ix_embeddings_ivfflat ON embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists=100)")
    op.execute("""
        CREATE TRIGGER trg_embeddings_updated_at
        BEFORE UPDATE ON embeddings
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)
    op.execute("ALTER TABLE embeddings ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON embeddings
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    """)

    # ── audit_log (no RLS — app-layer access control) ─────────────────────────
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_role", sa.Enum("tenant_manager", "tenant_admin", "member", name="actor_role", create_type=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_log_tenant_time", "audit_log", ["tenant_id", "created_at"])
    op.create_index("ix_audit_log_actor_time", "audit_log", ["actor_id", "created_at"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("embeddings")
    op.drop_table("leads")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("cms_content")
    op.drop_table("widgets")
    op.drop_table("users")
    op.drop_table("tenants")

    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE")

    op.execute("DROP TYPE IF EXISTS message_role")
    op.execute("DROP TYPE IF EXISTS lead_status")
    op.execute("DROP TYPE IF EXISTS conversation_status")
    op.execute("DROP TYPE IF EXISTS content_type")
    op.execute("DROP TYPE IF EXISTS actor_role")
    op.execute("DROP TYPE IF EXISTS user_role")
