# Concierge-SaaS

A multi-tenant AI SaaS where any business signs up, manages its content in a CMS, and embeds an AI chat agent on its public website. The agent retrieves from tenant-owned content (RAG), captures leads, and escalates to humans. All tenants share one infrastructure stack but are fully isolated at three simultaneous layers: Postgres RLS, repository-layer query scoping, and pgvector query-time filtering.

## Architecture Overview

```
Browser Widget  ──►  API (FastAPI)  ──►  Postgres 16 + pgvector
                          │
                    ┌─────┼──────────┐
                    │     │          │
               Modelserver  Guardrails  Redis
               (classifier)  (NeMo)   (session)
                    │                   │
                 MinIO              Vault
               (widget bundle,   (all secrets)
                tenant media)
                    │
                 Jaeger
                (tracing)
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| `api` | 8000 | FastAPI backend — chat, CMS, leads, auth, admin routes |
| `modelserver` | 8001 | Lean classifier (TF-IDF + LogReg, sklearn/joblib) |
| `guardrails` | 8002 | NeMo Guardrails sidecar — platform-level rails |
| `admin` | 8501 | Streamlit admin UI |
| `demo` | 3000 | Widget demo page (nginx) |
| `postgres` | 5432 | Postgres 16 + pgvector |
| `redis` | 6379 | Session memory (30-min TTL) |
| `minio` | 9000/9001 | Object storage — widget bundle + tenant media |
| `vault` | 8200 | Secrets (never in source or .env) |
| `jaeger` | 16686 | Distributed tracing UI |
| `pgadmin` | 5050 | Postgres admin UI (dev only) |

## Tech Stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.12 (API, modelserver, guardrails) · TypeScript / Node 20 (widget) |
| API framework | FastAPI 0.115+ with SQLAlchemy 2.x + Alembic |
| Database | Postgres 16 + pgvector |
| LLM | Anthropic claude-sonnet-4-6 |
| Embeddings | Voyage AI `voyage-3` (hosted API) |
| Reranker | Voyage AI `rerank-2` |
| Classifier | TF-IDF (word 1–2-gram) + Logistic Regression, exported as joblib |
| Guardrails | NeMo Guardrails sidecar |
| PII redaction | Microsoft Presidio |
| Widget | Vite 5 + React 18 + TypeScript (~20 KB gzipped) |
| Admin UI | Streamlit 1.35+ |
| Session memory | Redis 7 (30-min TTL, last 10 messages) |
| Object storage | MinIO |
| Secrets | HashiCorp Vault |
| Tracing | OpenTelemetry → Jaeger |
| Packaging | `uv` + `pyproject.toml` |

## Tenant Isolation

Three simultaneous layers — any one layer alone is sufficient to prevent cross-tenant access; all three run together:

1. **Postgres RLS** — row-level security policies on every tenant-scoped table enforce `tenant_id` at the database engine level.
2. **Repository layer** — every query in `api/app/repositories/` adds `.filter(tenant_id == ...)` sourced from the verified JWT, never from the request body.
3. **pgvector query-time filter** — all vector similarity searches pass `tenant_id` as a metadata filter so embeddings from other tenants are never returned.

## Roles

| Role | Scope |
|------|-------|
| `tenant_manager` | Platform-level — create/suspend tenants, view audit log |
| `tenant_admin` | Tenant-level — manage CMS content, widgets, leads, guardrail topics |
| `member` | Visitor-level — chat only, no admin access |

## Classifier

The classifier gives a cheap first-pass intent prediction before the expensive LLM/agent path runs.

**Labels**: `faq` · `support` · `sales_or_leads` · `human_request` · `spam` · `other`

**Dataset**: Bitext customer-support-llm-chatbot-training-dataset + SMS Spam Collection + CLINC OOS — mapped into Concierge router labels (12,880 rows total; deduplicated and leak-checked before split).

| Approach | Macro-F1 (test) | Latency avg | Artifact |
|----------|-----------------|-------------|----------|
| TF-IDF + LogReg (C=2) | **0.9818** | 0.03 ms | `model.joblib` |
| CNN word-level (ONNX) | 0.9810 | 0.86 ms | `intent_cnn.onnx` |
| LLM zero-shot baseline | *(see model card)* | API latency | none |

**Shipped model**: `sklearn/joblib` — comparable F1 to ONNX with 30× lower latency and no `onnxruntime` dependency in the serving container.

**Artifact SHA-256** (pinned in `modelserver/artifacts/model_card.md`, verified at boot):
```
cd9df32928a567d39a8b5e0246112e1dc6d80a6a215cef336b58e99e5bbae7f0
```

See [modelserver/artifacts/model_card.md](modelserver/artifacts/model_card.md) for full evaluation results.

## RAG Pipeline

1. **Chunking** — parent-child sentence-aware chunking (`child_size=2` sentences, `parent_size=5`-sentence window centred on the child).
2. **Embedding** — Voyage AI `voyage-3` (1024-dim, hosted API).
3. **Retrieval** — cosine similarity search in pgvector, scoped to `tenant_id`.
4. **Reranking** — Voyage AI `rerank-2` cross-encoder (cosine top-15 → rerank → top-5). Selected over query-rewriting and HyDE — see [DECISIONS.md](docs/DECISIONS.md) `RAG-001`.

**Eval results** (15-triple golden set, `evals/rag/golden_set.yaml`):

| Metric | Value |
|--------|-------|
| hit@5 | 0.667 |
| faithfulness (RAGAS, 24 synthetic samples) | 0.944 |

## Agent

The `route()` function in `api/app/agent/router.py` classifies every inbound message and dispatches it:

| Classifier result | Dispatch |
|-------------------|----------|
| `spam` | Deterministic refusal — no LLM call |
| confidence ≥ 0.75 AND label = `support` | RAG workflow (retrieve → prompt → Claude) |
| confidence ≥ 0.75 AND label = `sales_or_leads` | Lead-capture workflow |
| confidence ≥ 0.75 AND label = `human_request` | Escalate workflow |
| low confidence or `faq` / `other` | Full tool-calling agent loop (max 5 iterations) |

**Agent tools**: `rag_search` · `capture_lead` · `escalate`

**Session memory**: last 10 messages per conversation, Redis TTL 30 min.

**Agent caps**: max 5 tool-call iterations, max 2,000 output tokens per turn.

## Guardrails

NeMo Guardrails sidecar runs platform-level rails that tenants cannot override:

| Rail type | Covers |
|-----------|--------|
| Input — prompt injection | Detects and refuses instructions to ignore/override system prompt |
| Input — jailbreak | Detects DAN, developer-mode, and unrestricted-mode attempts |
| Topical — cross-tenant extraction | Refuses requests to reveal another tenant's data |
| Topical — system prompt extraction | Refuses requests to reveal internal instructions |
| Output — cross-tenant leakage | Blocks responses containing another tenant's data |
| Output — system prompt leakage | Blocks responses that reveal the system prompt |

Tenant admins can add topical guardrails (allowed/blocked topics) from the Streamlit admin UI; platform rails are immutable.

## Security

- **Widget auth**: PyJWT signed per-widget token (1-hour expiry) + server-side origin check (CORS + CSP).
- **Service-to-service auth**: Vault-issued HS256 service JWTs for `api → modelserver` and `api → guardrails` calls.
- **PII redaction**: Presidio anonymises PII in visitor messages before they reach Claude or are stored.
- **Tenant ID**: sourced exclusively from the verified JWT — never from the request body.
- **Rate limiting**: 60 req/min per tenant on `/chat/messages`; `capture_lead` capped at 3/session and 5/IP/hour.
- **Secrets**: all credentials live in Vault; none in source, `.env`, or container images.

See [docs/SECURITY.md](docs/SECURITY.md) for the full threat model.

## CI Gates

All gates must pass before a PR merges (`.github/workflows/ci.yml`):

| Gate | Threshold |
|------|-----------|
| Classifier macro-F1 | ≥ 0.70 |
| Agent tool-selection accuracy | 1.000 (15/15) |
| RAG hit@5 | ≥ 0.667 |
| RAG faithfulness | ≥ 0.944 |
| Red-team pass rate | 1.00 (all probes refused) |
| PII redaction pass rate | 1.00 |
| Smoke test | docker-compose up from fresh clone |

Thresholds live in `eval_thresholds.yaml` — they can only be raised, never lowered (requires a `DECISIONS.md` entry).

## Quick Start

### Prerequisites

- Docker + Docker Compose
- `ANTHROPIC_API_KEY` and `VOYAGE_API_KEY`

### Setup

```bash
# 1. Clone and configure
git clone https://github.com/alimsaleh1212-create/Concierge-SaaS.git
cd Concierge-SaaS
cp .env.example .env
# Edit .env — fill in ANTHROPIC_API_KEY and VOYAGE_API_KEY

# 2. Start all services (Vault init and DB migrations run automatically)
docker compose up --build

# 3. Seed demo tenants (runs automatically via the `seed` service)
#    Tenants: NovaTech Electronics, LearnSphere
#    To re-run manually:
docker compose run --rm seed

# 4. Open
#    Widget demo:   http://localhost:3000
#    Admin UI:      http://localhost:8501
#    API docs:      http://localhost:8000/docs
#    Jaeger:        http://localhost:16686
#    pgAdmin:       http://localhost:5050
#    MinIO console: http://localhost:9001
```

### Running Evals

```bash
# Classifier eval (requires modelserver running)
cd api && pytest ../api/tests/evals/test_classifier.py -v

# Agent tool-selection eval
cd api && pytest ../evals/agent/test_agent.py -v -s

# RAG eval (requires full stack)
cd api && pytest ../evals/rag/test_rag.py -v

# Red-team probes
cd api && pytest tests/red_team/ -v
```

## Project Structure

```
api/                    FastAPI backend (chat, CMS, auth, admin, agent, RAG)
├── app/
│   ├── agent/          Classifier-driven router + tool-calling agent
│   ├── rag/            Chunker, embedder, retriever (reranking)
│   ├── repositories/   Tenant-scoped query layer
│   ├── models/         SQLAlchemy ORM (9 tables)
│   └── api/            Route handlers (platform / admin / chat / auth)
├── seeds/              Demo tenant seed scripts
├── prompts/            Version-controlled LLM prompts
└── tests/              Unit, integration, eval, red-team

modelserver/            Lean sklearn/joblib classifier (no torch)
guardrails/             NeMo Guardrails sidecar
widget/                 Vite + React chat widget (~20 KB gzipped)
admin/                  Streamlit admin UI
evals/                  Golden sets for classifier, agent, RAG
notebooks/              Offline training only (never imported by containers)
docs/                   DESIGN.md, DECISIONS.md, EVALS.md, RUNBOOK.md, SECURITY.md
specs/                  Feature specs and implementation plan
```

## Documentation

| Document | Contents |
|----------|----------|
| [docs/DESIGN.md](docs/DESIGN.md) | Tenant isolation strategy, role model, scaling story |
| [docs/DECISIONS.md](docs/DECISIONS.md) | All architectural decisions with metrics and rationale |
| [docs/EVALS.md](docs/EVALS.md) | Classifier, agent, RAG, and red-team eval results |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | Setup, rebuild, troubleshooting |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model, isolation layers, erasure path |
| [docs/model_card.md](docs/model_card.md) | Classifier model card with dataset and evaluation details |
| [specs/001-concierge-system-spec/plan.md](specs/001-concierge-system-spec/plan.md) | Full implementation plan |
