# Data Model: Concierge — Full System

**Phase 1 output for**: `specs/001-concierge-system-spec/plan.md`
**Date**: 2026-05-25

All tables use UUID primary keys. All timestamps are `TIMESTAMPTZ`. RLS noted per table.

---

## Entity Diagram (text)

```
tenants ─────────────── users (nullable tenant_id for tenant_manager)
    │
    ├──── widgets ──────── conversations ──── messages
    │                              │
    ├──── cms_content              └──────── leads
    │         │
    │         └──── embeddings (child chunk + parent chunk + vector)
    │
    └──── audit_log (actor_id → users.id; tenant_id nullable)
```

---

## Table Definitions

### tenants
**RLS**: None — platform-level table.
**Access**: `tenant_manager` writes; `tenant_admin` reads own row via app-layer check.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | `gen_random_uuid()` default |
| `name` | VARCHAR(255) NOT NULL | Display name |
| `slug` | VARCHAR(100) UNIQUE NOT NULL | URL-safe identifier, immutable after creation |
| `is_active` | BOOLEAN DEFAULT true | Suspending a tenant sets this false |
| `is_deleted` | BOOLEAN DEFAULT false | Soft delete |
| `allowed_origins` | TEXT[] DEFAULT '{}' | Fallback origin allowlist for all widgets |
| `created_at` | TIMESTAMPTZ DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ DEFAULT now() | Auto-updated via trigger |

**Indexes**: `slug` (unique); `is_active` (partial index for active tenants)

---

### users
**RLS**: `tenant_id = current_setting('app.tenant_id')::uuid` — `tenant_manager` rows exempt (their `tenant_id` is NULL; RLS policy must handle NULL correctly: `tenant_id IS NULL OR tenant_id = app.tenant_id`).

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants.id | NULL for `tenant_manager` role |
| `email` | VARCHAR(320) UNIQUE NOT NULL | Case-insensitive; lowercased at write |
| `hashed_password` | VARCHAR(1024) NOT NULL | bcrypt via fastapi-users |
| `role` | ENUM(tenant_manager, tenant_admin, member) NOT NULL | |
| `is_active` | BOOLEAN DEFAULT true | fastapi-users convention |
| `is_deleted` | BOOLEAN DEFAULT false | Soft delete |
| `created_at` | TIMESTAMPTZ DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ DEFAULT now() | |

**Indexes**: `email` (unique); `(tenant_id, role)` composite

---

### widgets
**RLS**: `tenant_id = current_setting('app.tenant_id')::uuid`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants.id NOT NULL | |
| `name` | VARCHAR(255) NOT NULL | Human-readable widget name |
| `widget_token_secret` | VARCHAR(64) NOT NULL | 32-byte hex; signs visitor JWTs |
| `allowed_origins` | TEXT[] DEFAULT '{}' | Per-widget origin allowlist |
| `theme_config` | JSONB DEFAULT '{}' | Colors, font, tenant rails config |
| `greeting` | TEXT | First message shown to visitor |
| `is_active` | BOOLEAN DEFAULT true | Inactive widget rejects token exchange |
| `is_deleted` | BOOLEAN DEFAULT false | |
| `created_at` | TIMESTAMPTZ DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ DEFAULT now() | |

**Indexes**: `(tenant_id, is_active)` composite; `is_deleted` filtered

---

### cms_content
**RLS**: `tenant_id = current_setting('app.tenant_id')::uuid`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants.id NOT NULL | |
| `title` | VARCHAR(512) NOT NULL | |
| `body` | TEXT NOT NULL | Full text; chunked at ingestion |
| `content_type` | ENUM(faq, page, product) NOT NULL | |
| `metadata` | JSONB DEFAULT '{}' | Tags, author, last-edited-by |
| `is_deleted` | BOOLEAN DEFAULT false | Triggers embedding deletion on soft-delete |
| `created_at` | TIMESTAMPTZ DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ DEFAULT now() | |

**Indexes**: `(tenant_id, content_type)`; `(tenant_id, is_deleted)` filtered

**Lifecycle note**: When `is_deleted` is set to true, the application MUST delete all
`embeddings` rows with `content_id = this.id` (hard delete — no orphan vectors).

---

### conversations
**RLS**: `tenant_id = current_setting('app.tenant_id')::uuid`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants.id NOT NULL | |
| `widget_id` | UUID FK → widgets.id NOT NULL | |
| `session_id` | VARCHAR(128) NOT NULL | Client-generated opaque session ID |
| `visitor_ip_hash` | VARCHAR(64) | SHA-256 of raw IP; ingested hashed, never raw |
| `status` | ENUM(active, escalated, closed) DEFAULT active | |
| `is_deleted` | BOOLEAN DEFAULT false | |
| `created_at` | TIMESTAMPTZ DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ DEFAULT now() | |

**Indexes**: `(tenant_id, status)`; `(tenant_id, widget_id)`

---

### messages
**RLS**: `tenant_id = current_setting('app.tenant_id')::uuid`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants.id NOT NULL | Denormalised for RLS |
| `conversation_id` | UUID FK → conversations.id NOT NULL | |
| `role` | ENUM(user, assistant) NOT NULL | |
| `content` | TEXT NOT NULL | PII-redacted before insert |
| `is_redacted` | BOOLEAN DEFAULT false | True if Presidio modified content |
| `created_at` | TIMESTAMPTZ DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ DEFAULT now() | |

**Indexes**: `(tenant_id, conversation_id, created_at)` — ordered message fetch

---

### leads
**RLS**: `tenant_id = current_setting('app.tenant_id')::uuid`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants.id NOT NULL | |
| `conversation_id` | UUID FK → conversations.id NOT NULL | |
| `visitor_name` | VARCHAR(255) | Optional — nullable |
| `visitor_email` | VARCHAR(320) | Optional — nullable; PII-redacted if present |
| `visitor_phone` | VARCHAR(50) | Optional — nullable; PII-redacted if present |
| `intent` | TEXT NOT NULL | Free-text intent string from agent |
| `score` | FLOAT | Classifier confidence at capture time |
| `notes` | TEXT | Agent-generated summary |
| `status` | ENUM(new, contacted, closed) DEFAULT new | Updated by tenant_admin |
| `is_deleted` | BOOLEAN DEFAULT false | |
| `created_at` | TIMESTAMPTZ DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ DEFAULT now() | |

**Indexes**: `(tenant_id, status)`; `(tenant_id, created_at DESC)` for leads list

---

### embeddings
**RLS**: `tenant_id = current_setting('app.tenant_id')::uuid`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants.id NOT NULL | |
| `content_id` | UUID FK → cms_content.id NOT NULL | |
| `chunk_text` | TEXT NOT NULL | Child chunk — embedded and retrieved |
| `parent_chunk_text` | TEXT NOT NULL | Parent chunk — returned as LLM context |
| `embedding` | VECTOR(1024) NOT NULL | Voyage voyage-3 output |
| `chunk_index` | INTEGER NOT NULL | Ordering within content item |
| `created_at` | TIMESTAMPTZ DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ DEFAULT now() | |

**Indexes**:
- IVFFlat: `USING ivfflat (embedding vector_cosine_ops) WITH (lists=100)`
  — created after initial bulk insert, not at table creation time
- `(tenant_id, content_id)` — for deletion cascade when CMS content is soft-deleted

**pgvector query pattern** (must include tenant filter inside the scan):
```sql
SELECT parent_chunk_text, chunk_text,
       embedding <=> $query_vec AS distance
FROM embeddings
WHERE tenant_id = $tid        -- RLS also enforces this; belt-and-suspenders
  AND is_deleted = false       -- embeddings table has no is_deleted; deletion is hard
ORDER BY distance
LIMIT 5;
```
*(Note: `embeddings` has no `is_deleted` — orphaned embeddings are hard-deleted when
their `cms_content` is soft-deleted or when the tenant is erased.)*

---

### audit_log
**RLS**: None — append-only, special access rules enforced at app layer.
**Access**: `tenant_manager` reads all rows; `tenant_admin` reads rows where
`tenant_id = their tenant_id`; no other role reads.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `actor_id` | UUID NOT NULL | FK → users.id (not enforced as FK to allow erasure) |
| `actor_role` | ENUM(tenant_manager, tenant_admin, member) NOT NULL | |
| `tenant_id` | UUID | Nullable — NULL for platform-level actions |
| `action` | VARCHAR(128) NOT NULL | e.g. `tenant.created`, `tenant.erased`, `lead.captured` |
| `metadata` | JSONB DEFAULT '{}' | Action-specific context (PII-redacted) |
| `created_at` | TIMESTAMPTZ DEFAULT now() | ONLY timestamp — no updated_at |

**Constraints**: No `is_deleted` column. No `updated_at` column. No `UPDATE` or
`DELETE` permissions granted to the application role. Enforced via Postgres `GRANT`.

**Indexes**: `(tenant_id, created_at DESC)`; `(actor_id, created_at DESC)`

---

## Postgres Triggers

One trigger applied to every table that carries `updated_at`:

```sql
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Applied as: CREATE TRIGGER trg_<table>_updated_at
--             BEFORE UPDATE ON <table>
--             FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

Tables receiving this trigger: `tenants`, `users`, `widgets`, `cms_content`,
`conversations`, `messages`, `leads`, `embeddings`.

---

## Enums (Postgres native)

```sql
CREATE TYPE user_role AS ENUM ('tenant_manager', 'tenant_admin', 'member');
CREATE TYPE content_type AS ENUM ('faq', 'page', 'product');
CREATE TYPE conversation_status AS ENUM ('active', 'escalated', 'closed');
CREATE TYPE lead_status AS ENUM ('new', 'contacted', 'closed');
CREATE TYPE actor_role AS ENUM ('tenant_manager', 'tenant_admin', 'member');
```

---

## RLS Policies (one per tenant-scoped table)

```sql
-- Example for cms_content; same pattern for users, widgets,
-- conversations, messages, leads, embeddings.

ALTER TABLE cms_content ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON cms_content
  USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
```

The `true` flag on `current_setting` makes it return NULL (not raise an error) when
the variable is not set — this allows DDL migrations and superuser connections to
work without setting the variable.

---

## SQLAlchemy RLS Event Listener (pseudocode)

```python
from sqlalchemy import event, text

@event.listens_for(engine, "connect")
def set_search_path(dbapi_connection, connection_record):
    pass  # No-op at connect time — variable is set per-request

# In FastAPI dependency:
async def get_db_session(token: str = Depends(verify_widget_token)):
    async with AsyncSession(engine) as session:
        tid = token.tenant_id
        try:
            await session.execute(
                text("SELECT set_config('app.tenant_id', :tid, true)"),
                {"tid": str(tid)}
            )
            yield session
        finally:
            # Reset on every request — pooled connections persist the variable
            await session.execute(
                text("SELECT set_config('app.tenant_id', '', true)")
            )
```

The `finally` block runs even if the request handler raises an exception.

---

## State Transitions

### conversation.status
```
active → escalated  (via escalate tool or explicit visitor request)
active → closed     (via admin action or timeout)
escalated → closed  (via admin action)
```

### lead.status
```
new → contacted  (via tenant_admin action in admin UI)
contacted → closed
new → closed     (admin skips contacted)
```
