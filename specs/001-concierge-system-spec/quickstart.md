# Quickstart: Concierge

**Validated against**: `docker-compose.yml` on branch `001-concierge-system-spec`

---

## Prerequisites

- Docker 24+ and Docker Compose v2
- A Vault root token (provided by Owner A at project setup)
- Anthropic API key (from Anthropic console)
- Voyage API key (from Voyage AI console)

---

## First-time Setup

```bash
# 1. Clone and enter the repo
git clone https://github.com/alimsaleh1212-create/concierge-saas
cd concierge-saas

# 2. Copy env template and fill in the three required values
cp .env.example .env
# Edit .env — set VAULT_ROOT_TOKEN, ANTHROPIC_API_KEY, VOYAGE_API_KEY
# All other secrets are loaded from Vault at container startup

# 3. Build and start the stack
docker compose up --build

# 4. Verify the stack is up
curl http://localhost:8000/health   # API
curl http://localhost:8001/health   # Modelserver
curl http://localhost:8002/health   # Guardrails
```

The first `docker compose up` runs the Alembic baseline migration and seeds two demo
tenants automatically.

---

## Demo Tenants (seeded automatically)

| Tenant | Slug | Role | Email | Password |
|--------|------|------|-------|----------|
| Mario's Pizza | `marios-pizza` | tenant_admin | `admin@marios.example` | `pizza123` |
| Lawson & Partners | `lawson-partners` | tenant_admin | `admin@lawson.example` | `legal123` |
| Platform | — | tenant_manager | `platform@concierge.example` | `platform123` |

---

## Widget Embed Test

```bash
# Get a widget token for Mario's Pizza widget
WIDGET_ID=$(curl -s http://localhost:8000/admin/widgets \
  -H "Authorization: Bearer <marios-pizza-admin-jwt>" | jq -r '.widgets[0].id')

TOKEN=$(curl -s -X POST http://localhost:8000/auth/widget-token \
  -H "Content-Type: application/json" \
  -d "{\"widget_id\": \"$WIDGET_ID\", \"origin\": \"http://localhost:3000\"}" \
  | jq -r '.token')

# Send a chat message
curl -X POST http://localhost:8000/chat/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id": "new", "content": "What are your opening hours?", "session_id": "test-session-1"}'
```

---

## Run the Evals

```bash
# All CI gates
cd api && pytest tests/evals/ -v

# Red-team probes only
pytest tests/red_team/ -v

# Classifier gate
pytest tests/evals/test_classifier.py -v

# RAG gate (RAGAS)
pytest tests/evals/test_rag.py -v
```

---

## Rebuild a Single Service

```bash
docker compose up --build api          # API only
docker compose up --build modelserver  # Classifier serving
docker compose up --build guardrails   # NeMo sidecar
```

---

## Common Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `modelserver` exits immediately | SHA-256 mismatch in model_card.md | Re-export artifact and update model_card.md |
| 403 on widget token exchange | Origin not in `allowed_origins` | Add origin via PATCH /admin/widgets/{id} |
| Cross-tenant 403 | Correct — RLS is working | This is expected behaviour |
| `app.tenant_id` not set error | RLS reset issue | Check SQLAlchemy event listener in `api/app/core/database.py` |
| Container > 500MB | torch leaked into image | Check all `requirements.txt` — torch must not appear |

---

## Admin UI

```
http://localhost:8501   Streamlit admin (tenant_admin login)
```

---

## Vault UI (dev only)

```
http://localhost:8200   Vault UI (use VAULT_ROOT_TOKEN from .env)
```
