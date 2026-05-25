# API Contract: FastAPI Backend (port 8000)

**Owner**: A (platform/admin routes) · B (chat route) · C (guardrails client) · D (auth route)
**Base URL**: `http://localhost:8000` (Docker Compose)

All protected routes require `Authorization: Bearer <token>`. Token type depends on route group.

---

## Auth Routes (Owner D)

### POST /auth/widget-token
Exchange a public widget_id + origin for a short-lived signed JWT.
No auth header required.

**Request**
```json
{ "widget_id": "uuid", "origin": "https://example.com" }
```

**Validation (in order)**
1. Widget exists and `is_active = true` → else 404
2. Origin in `widgets.allowed_origins` OR `tenants.allowed_origins` → else 403
3. Server-side origin check is independent of CORS header

**Response 200**
```json
{ "token": "eyJ...", "expires_in": 3600 }
```

**Error responses**: 404 widget not found · 403 origin not allowed · 422 bad payload

---

### POST /auth/login
fastapi-users standard login endpoint. Returns access JWT for `tenant_admin` /
`tenant_manager` roles. Not used by widget visitors.

**Request**: `application/x-www-form-urlencoded` — `username`, `password`
**Response 200**: `{ "access_token": "eyJ...", "token_type": "bearer" }`

---

## Platform Routes (Owner A)
All routes require `role = tenant_manager` JWT.

### POST /platform/tenants
Provision a new tenant.

**Request**
```json
{ "name": "Acme Corp", "slug": "acme-corp", "allowed_origins": ["https://acme.com"] }
```
**Response 201**
```json
{ "id": "uuid", "name": "Acme Corp", "slug": "acme-corp", "is_active": true }
```
**Side effects**: Inserts `tenants` row · writes `audit_log` action=`tenant.created`

---

### POST /platform/tenants/{tenant_id}/invite
Invite the first tenant_admin.

**Request**: `{ "email": "admin@acme.com" }`
**Response 200**: `{ "status": "invited", "email": "admin@acme.com" }`
**Side effects**: Creates `users` row (role=tenant_admin, is_active=false) · sends invite email · writes audit_log

---

### PATCH /platform/tenants/{tenant_id}/suspend
**Request**: `{ "reason": "payment failure" }`
**Response 200**: `{ "id": "uuid", "is_active": false }`
**Side effects**: Sets `tenants.is_active=false` · writes audit_log action=`tenant.suspended`

---

### DELETE /platform/tenants/{tenant_id}
Right-to-erasure. Synchronous hard delete across all stores.

**Response 200**
```json
{ "status": "erased", "tenant_id": "uuid", "stores_purged": ["redis","pgvector","minio","postgres"] }
```
**Side effects**: See spec §5 deletion order · writes audit_log action=`tenant.erased` LAST
**Error**: 409 if erasure is already in progress

---

### GET /platform/tenants
List all tenants with aggregate cost/usage.

**Response 200**
```json
{
  "tenants": [
    { "id": "uuid", "slug": "acme-corp", "is_active": true,
      "cost_7d_usd": 0.42, "message_count_7d": 312 }
  ]
}
```

---

### GET /platform/audit-log
Read audit log. Supports `?tenant_id=<uuid>&limit=100&offset=0`.

**Response 200**: `{ "entries": [ { "id", "actor_id", "actor_role", "tenant_id", "action", "metadata", "created_at" } ] }`

---

## Admin Routes (Owner A / D)
All routes require `role = tenant_admin` JWT. `tenant_id` derived from JWT — never from URL/body.

### CMS

**GET /admin/cms** — list content items (excludes `is_deleted=true`)
**POST /admin/cms** — create item; triggers async embedding ingestion
**PATCH /admin/cms/{id}** — update; re-triggers embedding for changed body
**DELETE /admin/cms/{id}** — soft-delete; triggers hard-delete of linked embeddings

**POST /admin/cms body**
```json
{ "title": "string", "body": "string", "content_type": "faq|page|product", "metadata": {} }
```

### Widgets

**GET /admin/widgets** — list widgets for this tenant
**POST /admin/widgets** — create widget (generates `widget_token_secret` server-side)
**PATCH /admin/widgets/{id}** — update theme, greeting, origins, guardrail config
**GET /admin/widgets/{id}/snippet** — returns embed HTML snippet

### Leads

**GET /admin/leads** — list leads (`?status=new|contacted|closed&limit=50&offset=0`)
**PATCH /admin/leads/{id}** — update status only

---

## Chat Route (Owner B)
Requires `Authorization: Bearer <widget_jwt>`. `tenant_id` and `widget_id` from JWT.

### POST /chat/messages
Send a visitor message; receive the agent or workflow response.

**Request**
```json
{
  "conversation_id": "uuid",
  "content": "Do you offer gluten-free pizza?",
  "session_id": "client-generated-opaque-string"
}
```

**Response 200**
```json
{
  "conversation_id": "uuid",
  "response": "Yes! We offer three gluten-free options...",
  "tool_used": "rag_search",
  "escalated": false,
  "lead_captured": false
}
```

**Internal flow**:
1. Verify JWT → extract tenant_id, widget_id
2. Set RLS session variable
3. POST /rails/input to guardrails sidecar → refuse if flagged
4. POST /classify to modelserver → get label + confidence
5. Router branches on label/confidence → workflow or agent
6. Agent/workflow produces response
7. POST /rails/output to guardrails sidecar → refuse if flagged
8. PII-redact response + store message rows
9. Reset RLS session variable (finally block)
10. Return response

**Error responses**: 401 invalid token · 403 origin mismatch · 429 rate limit · 400 bad payload

---

## Health / Internal

**GET /health** — `{ "status": "ok", "version": "0.1.0" }` — no auth required
**GET /metrics** — Prometheus metrics (internal only)
