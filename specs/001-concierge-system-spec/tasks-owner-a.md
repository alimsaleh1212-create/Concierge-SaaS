---
description: "Task list — Owner A: Platform, Tenancy & Infrastructure"
---

# Tasks: Concierge — Owner A (Platform, Tenancy & Infrastructure)

**Input**: Design documents from `specs/001-concierge-system-spec/`
**Owner**: Owner A — covers FR-001–FR-014, docker-compose, Alembic, seeds, rate limiting
**Prerequisites**: Shared tasks (tasks-shared.md) fully merged to main before Phase 1 begins.

**Tests**: Not requested as TDD — no separate test-first tasks.
**Labels**: All tasks tagged [Owner A]. Run `/speckit-implement` and filter to [Owner A].

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Parallelizable — different files, no incomplete dependencies
- **[Story]**: User story label (US2, US3, US4) from spec.md
- Paths assume the repo root structure defined in `plan.md`

---

## Phase 1: Setup (Owner A)

**Purpose**: Create the project configuration layer, Docker Compose stack, and Vault wiring
so every other owner can pull and start services without manual environment setup.

- [x] T-A001 [P] Create `api/pyproject.toml` (uv) with pinned versions: fastapi==0.115.*, sqlalchemy==2.x, alembic, fastapi-users[sqlalchemy]>=14, pyjwt, anthropic, voyageai, redis, minio, hvac, presidio-analyzer, presidio-anonymizer, asyncpg, pgvector
- [x] T-A002 [P] Create `api/app/core/config.py`: Pydantic Settings class that reads all secrets from Vault (via hvac); expose `DATABASE_URL`, `REDIS_URL`, `MINIO_ENDPOINT`, `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, `MODELSERVER_SERVICE_TOKEN`, `GUARDRAILS_SERVICE_TOKEN`
- [x] T-A003 [P] Create `.env.example` with the three user-supplied values (`VAULT_ROOT_TOKEN`, `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`) and comments explaining all other secrets are Vault-managed
- [x] T-A004 Create `docker-compose.yml` with services: `api` (port 8000), `modelserver` (port 8001), `guardrails` (port 8002), `admin` (port 8501), `postgres` (port 5432, pgvector image), `redis` (port 6379), `minio` (ports 9000/9001), `vault` (port 8200, dev mode) — healthchecks on all services; api depends_on postgres, redis, minio, vault
- [x] T-A004a Create `vault/init.sh`: shell script that runs on `docker compose up` via a one-shot `vault-init` service; writes all required secrets to Vault dev instance: `DATABASE_URL`, `REDIS_URL`, `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MODELSERVER_SERVICE_TOKEN`, `GUARDRAILS_SERVICE_TOKEN`; creates MinIO buckets `concierge-widget` and `concierge-cms`; script is idempotent (skips if secrets already exist); exits 0 when complete

**Checkpoint**: `docker compose up --build` starts all services with zero manual steps; Vault auto-unsealed; `curl localhost:8000/health` returns `{"status":"ok"}`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: SQLAlchemy engine, RLS event listener, and Alembic baseline migration.
Every other owner waits on this phase before touching the database.

**⚠️ CRITICAL**: All user story phases depend on this completing first.

- [x] T-A005 Create `api/app/core/database.py`: async SQLAlchemy engine (asyncpg driver), `AsyncSession` factory, `get_db` FastAPI dependency that sets `app.tenant_id` via `set_config` before yield and resets it in a `finally` block on every request regardless of exception
- [x] T-A006 Create `api/app/core/security.py`: `verify_admin_token(token) -> TokenClaims` (fastapi-users JWT), `verify_widget_token(token) -> WidgetTokenClaims`, `verify_service_token(token)` — all raise HTTP 401 on invalid; `verify_widget_token` raises HTTP 403 if `tenant_id` in request body mismatches JWT claim
- [x] T-A007 Create all 9 SQLAlchemy ORM models with exact schema from `data-model.md` — UUID PKs, `tenant_id` on every scoped table, `is_deleted`, `created_at`/`updated_at`, `VECTOR(1024)` on embeddings — in `api/app/models/` (one file per model: `tenant.py`, `user.py`, `widget.py`, `cms_content.py`, `conversation.py`, `message.py`, `lead.py`, `embedding.py`, `audit_log.py`)
- [x] T-A008 Create `api/alembic/env.py` with async Alembic setup pointing at `DATABASE_URL` from config; import all models so autogenerate picks up every table
- [x] T-A009 Create `api/alembic/versions/001_baseline.py`: single migration that creates all 5 Postgres enums, all 9 tables with exact columns, all indexes, `updated_at` trigger on 8 tables, all RLS policies (`ENABLE ROW LEVEL SECURITY` + `CREATE POLICY tenant_isolation`) for the 7 tenant-scoped tables — `audit_log` and `tenants` get no RLS
- [x] T-A010 Create `api/app/repositories/base.py`: `BaseRepository(model, session)` with `.all(tenant_id)`, `.get(id, tenant_id)`, `.create(data)`, `.update(id, data, tenant_id)`, `.soft_delete(id, tenant_id)` — every query scoped with `.filter(model.tenant_id == tenant_id)`
- [x] T-A011 [P] Create `api/app/repositories/tenant_repo.py`: `TenantRepository` inheriting `BaseRepository` — NOT scoped by tenant_id (platform table); add `get_by_slug(slug)`, `list_active()`, `suspend(id)`, `hard_delete(id)`
- [x] T-A012 [P] Create `api/app/repositories/cms_repo.py`: `CmsRepository` inheriting `BaseRepository`; add `list_active(tenant_id)` (excludes `is_deleted=true`), `get_with_embeddings(id, tenant_id)`
- [x] T-A013 [P] Create `api/app/repositories/conversation_repo.py`: `ConversationRepository` inheriting `BaseRepository`; add `get_by_session(session_id, tenant_id)`, `set_escalated(id, tenant_id)`, `set_closed(id, tenant_id)`
- [x] T-A014 [P] Create `api/app/repositories/lead_repo.py`: `LeadRepository` inheriting `BaseRepository`; add `list_by_status(tenant_id, status)`, `update_status(id, status, tenant_id)`

**Checkpoint**: Run `alembic upgrade head` — zero errors; all 9 tables and RLS policies present in `psql \dt` and `\d cms_content` output.

---

## Phase 3: User Story 4 — Tenant Provisioning & Erasure (Priority: P2)

**Goal**: Platform operator provisions tenants, invites the first admin, suspends, and
triggers full right-to-erasure across all stores.

**Independent Test**: Call `POST /platform/tenants` → verify tenant row. Call
`POST /platform/tenants/{id}/invite` → verify user row + audit_log. Call
`DELETE /platform/tenants/{id}` → verify zero rows in all tables + audit_log erasure entry.

- [x] T-A015 [US4] Create `api/app/services/tenant_service.py`: `provision_tenant(name, slug, allowed_origins) -> Tenant` — inserts `tenants` row + writes `audit_log` action=`tenant.created`; `invite_admin(tenant_id, email) -> User` — creates `users` row (role=tenant_admin, is_active=false) + writes `audit_log` action=`tenant.admin_invited`; `suspend_tenant(id) -> Tenant` — sets `is_active=false` + writes `audit_log` action=`tenant.suspended`
- [x] T-A016 [US4] Create `api/app/services/erasure_service.py`: `erase_tenant(tenant_id)` — executes full erasure in exact order from FR-008: Redis session keys → pgvector embeddings → MinIO blobs → Postgres rows (messages → leads → conversations → embeddings → cms_content → widgets → users → tenants) → writes `audit_log` action=`tenant.erased` LAST; raises HTTP 409 if erasure already in progress
- [x] T-A017 [P] [US4] Create `api/app/api/platform/tenants.py`: wire `POST /platform/tenants` (201), `POST /platform/tenants/{id}/invite` (200), `PATCH /platform/tenants/{id}/suspend` (200), `DELETE /platform/tenants/{id}` (200), `GET /platform/tenants` (200 list with cost_7d_usd + message_count_7d); all require `role=tenant_manager` JWT
- [x] T-A018 [P] [US4] Create `api/app/api/platform/audit.py`: wire `GET /platform/audit-log` with `?tenant_id=&limit=&offset=` query params; `tenant_manager` reads all rows; requires `role=tenant_manager` JWT
- [x] T-A019 [US4] Create `api/app/services/cost_service.py`: `get_cost_usage(tenant_id, days=7) -> CostUsage` — aggregates message_count and estimated cost from `messages` table; used by `GET /platform/tenants`

**Checkpoint**: All platform routes return correct status codes. Erasure test: create tenant, add data across all tables, call DELETE, assert zero rows everywhere.

---

## Phase 4: User Story 3 — Tenant Admin CMS & Widget Management (Priority: P2)

**Goal**: Tenant admin creates and manages CMS content (which triggers RAG ingestion)
and configures widget appearance and guardrail topics.

**Independent Test**: Log in as Mario's Pizza tenant_admin, call `POST /admin/cms` with
FAQ content, verify embedding is created, verify `DELETE /admin/cms/{id}` hard-deletes
the linked embeddings row.

- [x] T-A020 [US3] Create `api/app/services/cms_service.py`: `create_content(tenant_id, data) -> CmsContent` — inserts row + triggers async embedding ingestion (fire-and-forget via background task); `update_content(id, tenant_id, data) -> CmsContent` — updates row + re-triggers embedding for changed body; `soft_delete_content(id, tenant_id)` — sets `is_deleted=true` + hard-deletes linked `embeddings` rows
- [x] T-A021 [US3] Create `api/app/services/auth_service.py`: `create_access_token(user) -> str` — signs JWT with fastapi-users conventions; `get_current_user(token) -> User` dependency; `require_role(role: str)` dependency factory that raises HTTP 403 on mismatch
- [x] T-A022 [P] [US3] Create `api/app/api/admin/cms.py`: wire `GET /admin/cms`, `POST /admin/cms` (201), `PATCH /admin/cms/{id}` (200), `DELETE /admin/cms/{id}` (200); all scope `tenant_id` from JWT — never URL/body; all require `role=tenant_admin` JWT
- [x] T-A023 [P] [US3] Create `api/app/api/admin/widgets.py`: wire `GET /admin/widgets`, `POST /admin/widgets` (201 — generate `widget_token_secret` server-side as 32-byte hex), `PATCH /admin/widgets/{id}` (200), `GET /admin/widgets/{id}/snippet` (returns embed HTML); all require `role=tenant_admin` JWT; `tenant_id` from JWT only
- [x] T-A024 [P] [US3] Create `api/app/api/admin/leads.py`: wire `GET /admin/leads` (with `?status=` filter), `PATCH /admin/leads/{id}` (status update only); require `role=tenant_admin` JWT; `tenant_id` from JWT only

**Checkpoint**: Full admin workflow works — CMS CRUD + widget CRUD + leads list.
`POST /admin/cms` followed by a chat message returns CMS content in the RAG answer.

---

## Phase 5: User Story 2 — Isolation Foundation (Priority: P1)

**Goal**: RLS + repository double-layer + pgvector filter hold against all cross-tenant attempts.

**Independent Test**: With two seeded tenants, use Tenant A's JWT to call any admin or
chat route — assert zero Tenant B rows ever returned at the HTTP layer.

- [x] T-A025 [US2] Verify `api/app/core/database.py` `get_db` dependency: the `finally` block ALWAYS resets `app.tenant_id` to empty string (not NULL) after every request, even on unhandled exceptions — add integration test asserting reset in `api/tests/integration/test_rls_reset.py`
- [x] T-A026 [US2] Write cross-tenant isolation unit test: seed one `cms_content` row for each demo tenant; query `CmsRepository.list_active(tenant_a_id)` → assert only Tenant A row returned; repeat with Tenant B; assert ORM `.filter(tenant_id==...)` is present in query in `api/tests/unit/test_cms_repo_isolation.py`
- [x] T-A027 [US2] Verify `FR-014` enforcement in `verify_widget_token`: write test sending a request with valid Tenant A JWT but `tenant_id` of Tenant B in request body — assert HTTP 403 returned — in `api/tests/unit/test_security_tenant_id_body.py`

**Checkpoint**: All three isolation tests pass. RLS reset test confirms `finally` block fires on exception.

---

## Phase 6: Seeds & Demo Tenants

**Purpose**: Seed both demo tenants with CMS content so chat, RAG, and red-team probes
work end-to-end from first `docker compose up`.

- [x] T-A028 Create `api/seeds/marios_pizza.py`: idempotent upsert of Mario's Pizza tenant + tenant_admin user + widget (with a localhost:3000 allowed origin) + 5 CMS items (menu, hours, delivery FAQ, location, specials) as per DECISIONS.md D-005; triggers embedding ingestion for all 5 items
- [x] T-A029 Create `api/seeds/lawson_partners.py`: idempotent upsert of Lawson & Partners tenant + tenant_admin user + widget + 5 CMS items (practice areas, team bios, consultation FAQ, fees, contact); triggers embedding ingestion for all 5 items
- [x] T-A030 Wire seed scripts to run on `docker compose up` via an API startup event or a separate `seed` Docker Compose service that exits 0 after seeding; ensure idempotency (skip if already exists)

**Checkpoint**: Fresh `docker compose up` → both tenants reachable in DB → `GET /admin/cms` returns 5 items for each admin → RAG returns relevant answer for each tenant.

---

## Phase 7: Rate Limiting & Polish

**Purpose**: Per-tenant rate limiting, `GET /health` endpoint, and Alembic baseline cleanup.

- [x] T-A031 Implement per-tenant rate-limiting middleware using Redis token bucket (`redis-py`, already a dep — see DECISIONS.md D-006): apply to all `/chat/messages` requests; key by `tenant_id` from JWT; placeholder thresholds — Owner A sets real values after Tuesday eval run and records in DECISIONS.md
- [x] T-A032 [P] Create `GET /health` endpoint returning `{"status":"ok","version":"0.1.0"}` — no auth required — in `api/app/api/__init__.py` or `api/main.py`
- [x] T-A033 [P] Create `api/main.py`: FastAPI app factory; include all routers (`platform`, `admin`, `chat`, `auth`); mount Prometheus metrics at `/metrics`; register RLS event listener on app startup
- [x] T-A034 [P] Create `api/Dockerfile`: multi-stage build, no torch, final image based on `python:3.12-slim`; copy only `app/` and `requirements.txt`; run `alembic upgrade head` as entrypoint pre-hook; target < 500 MB
- [x] T-A035 Run `quickstart.md` full smoke test: fresh `docker compose up --build`, seed both tenants, hit `/health` on all three services, verify both demo tenant admins can log in

---

## Phase 8: PII Redaction (User Story 1)

**Purpose**: Presidio-backed redaction module inside the API container. Moved from Owner C
(T-C021 series) — Owner A owns the API container, deps, and Dockerfile.

**Independent Test**: `redact("My email is foo@bar.com and my key is sk-test-1234567890abcdef")`
→ both entities replaced, `is_redacted=True`. Plain text → `is_redacted=False`.

- [x] T-C021-deps [P] [US1] Add `presidio-analyzer>=2.2`, `presidio-anonymizer>=2.2`, `spacy>=3.7` to `api/pyproject.toml`; download `en_core_web_md` in `api/Dockerfile` builder stage — completed.
- [ ] T-C021 [P] [US1] Create `api/app/redaction.py`: Presidio `AnalyzerEngine` + `AnonymizerEngine` wrapper; `redact(text: str) -> RedactionResult` replacing entity types `EMAIL_ADDRESS`, `PHONE_NUMBER`, `CREDIT_CARD`, `CRYPTO`, `API_KEY`, `US_SSN`, `IP_ADDRESS`, `PASSWORD`; `is_redacted: bool` flag on result.
- [ ] T-C021a [P] [US1] Add custom Presidio recognizers in `api/app/redaction.py` for `API_KEY` (pattern: `sk-[a-zA-Z0-9]{16,}`) and `PASSWORD` (pattern: `(?i)password\s*[=:]\s*\S+`) — default Presidio does not catch these reliably.
- [ ] T-C021b [P] [US1] Create `api/tests/unit/test_redaction.py`: assert emails, phone numbers, credit cards, IP addresses, API keys (`sk-test-1234567890abcdef`), and password strings (`password=secret123`) are replaced; assert `is_redacted=True` only when content changed.
- [ ] T-C021c [US1] Integration note for Owner B: `redact()` must be called before writing user/model text to the `messages` table, Redis session, logs, or traces; Owner A provides the helper; Owner B wires it in `api/app/api/chat/messages.py`.

**Checkpoint**: `pytest api/tests/unit/test_redaction.py -v` — all entity-type and `is_redacted` assertions pass.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: Start immediately on day one in parallel with shared tasks
- **Phase 2 (Foundational)**: Begin Monday morning after Phase 1; this phase BLOCKS Owners B and C
- **Phase 3 (US4 — provisioning)**: Starts after Phase 2; T-A015 and T-A016 are sequential; T-A017–T-A019 are parallel
- **Phase 4 (US3 — CMS/admin)**: Starts after Phase 2; T-A022–T-A024 are parallel after T-A020 and T-A021
- **Phase 5 (US2 — isolation)**: Can begin as soon as Phase 2's RLS event listener is drafted
- **Phase 6 (Seeds)**: After Phase 3 and Phase 4 routes exist; T-A028 and T-A029 parallel
- **Phase 7 (Polish)**: All items parallelizable after Phase 2

### Critical External Dependencies (Owners B, C, D)

| This task | Blocks |
|-----------|--------|
| T-A009 (Alembic migration) | Owner B T-B005, T-B007 |
| T-A005 (database.py + RLS) | Owner B T-B026 (chat endpoint) |
| T-A033 (api/main.py) | Owner D smoke test |
| T-C021 (redaction.py) | Owner B T-B026 (chat endpoint PII redaction) |

---

## Parallel Opportunities

### Phase 2 — all can start once Phase 1 is done

```
# These groups can run simultaneously after Phase 1:

Group A (Core):
  T-A005 database.py
  T-A006 security.py

Group B (Models — fully parallel):
  T-A007 all 9 ORM models (one per file)

# Then:
T-A008 alembic/env.py (needs T-A007)
T-A009 001_baseline.py (needs T-A008)
T-A010 base.py (needs T-A009)

Group C (Repos — parallel after T-A010):
  T-A011 tenant_repo.py
  T-A012 cms_repo.py
  T-A013 conversation_repo.py
  T-A014 lead_repo.py
```

---

## Implementation Strategy

### MVP (Tuesday end-of-day target)

1. Phase 1 + 2 → Stack boots, migration runs — Monday morning
2. Phase 3 → Provisioning routes working — Monday afternoon
3. Phase 4 → CMS + widget admin routes working — Tuesday
4. Phase 6 → Seeds run on startup — Tuesday
5. **STOP and VALIDATE**: `docker compose up`, both tenants seeded, chat round-trip works

### Incremental Delivery

1. Phase 1 + 2 → Infrastructure layer (blocks all other owners)
2. Phase 3 → Tenant lifecycle complete
3. Phase 4 → Admin UI flows unblocked
4. Phase 5 → Isolation hardened and tested
5. Phase 6 → Demo-ready from first clone
6. Phase 7 → Rate limiting + polish

---

## Notes

- The `finally` block in `get_db` is non-negotiable — a pooled connection that keeps a
  stale `app.tenant_id` is a cross-tenant breach. Test it explicitly (T-A025).
- `widget_token_secret` is generated server-side (32-byte hex) — never accepted from
  the client body. Owner D's token exchange relies on this field being present.
- The Alembic baseline migration (T-A009) is the single most critical artifact for the
  whole team. Announce in team chat when it is merged to main.
- Seed scripts must be idempotent — `docker compose up` may be run many times.
- MinIO bucket creation (`concierge-widget`, `concierge-cms`) should be part of the
  Vault/MinIO init script, not the seed scripts.
