# Implementation Plan: Concierge — Full System

**Branch**: `001-concierge-system-spec` | **Date**: 2026-05-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-concierge-system-spec/spec.md`

---

## Summary

Concierge is a multi-tenant AI SaaS where businesses sign up, get isolated tenants,
manage CMS content, and embed an AI chat agent on their public site. The agent
retrieves from tenant-owned content (RAG), captures leads, and escalates to humans.
All tenants share one Docker Compose infrastructure stack but are completely isolated
from one another at three simultaneous layers: Postgres RLS, repository-layer
query scoping, and pgvector query-time filtering.

The technical approach: FastAPI backend with SQLAlchemy + Alembic on Postgres 16 +
pgvector, a lean ONNX/sklearn modelserver for intent classification, a NeMo
Guardrails sidecar for platform-level rails, Presidio for PII redaction, a Vite +
React widget served from MinIO, a Streamlit admin UI, Redis for session memory, and
Vault for secrets. All LLM inference uses the Anthropic Claude hosted API; all
embeddings use the Voyage hosted API. No torch or transformers in any container.

---

## Technical Context

**Language/Version**: Python 3.12 (API, modelserver, guardrails) · TypeScript / Node 20 (widget)

**Primary Dependencies**:
- API: FastAPI 0.115+, SQLAlchemy 2.x, Alembic, fastapi-users 14+, PyJWT, anthropic SDK, voyageai SDK, redis-py, minio SDK, hvac (Vault)
- Modelserver: onnxruntime, scikit-learn, numpy, FastAPI (no torch)
- Guardrails: nemo-guardrails, presidio-analyzer, presidio-anonymizer, FastAPI
- Widget: Vite 5+, React 18, TypeScript
- Admin: Streamlit 1.35+
- Evals: ragas, pytest, pytest-asyncio

**Storage**:
- Postgres 16 + pgvector (primary DB + vector search)
- Redis 7 (session memory, TTL 30 min)
- MinIO (widget bundle blobs, tenant CMS media)
- Vault (all secrets — never in source or .env)

**Testing**: pytest + pytest-asyncio (API, evals, red-team); vitest (widget); Alembic for migration smoke

**Target Platform**: Linux containers via Docker Compose; browser (widget)

**Project Type**: Multi-service web application (API backend + modelserver + guardrails sidecar + React widget + Streamlit admin)

**Performance Goals**:
- Agent turn-around: < 5 s p95 (end-to-end chat round-trip)
- Classifier inference: < 100 ms p95 at the modelserver
- Widget first-paint: bundle < 50 KB gzipped
- Embeddings ingestion: not latency-sensitive (background on CMS save)

**Constraints**:
- No container image > 500 MB — CI fails the build if exceeded
- No torch, no transformers in any container image — ever
- Agent loop: max 5 tool-call iterations, max 2 000 output tokens per turn
- All tenant_id values sourced from verified JWT — never from request body

**Scale/Scope**: 2 demo tenants for week-8 demo; architecture must be sound to 1 000 tenants

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Gate | Status |
|-----------|------|--------|
| I. Isolation | RLS policy on every tenant table; repo-layer `.filter(tenant_id==...)`; pgvector filter at query time; RLS reset at request end | ✅ All three layers present in spec FR-001–FR-008 |
| II. Auth & Roles | fastapi-users (JWT + email/pw); exactly 3 roles; PyJWT widget token 1 hr; Vault service JWT for sidecar calls | ✅ FR-009–FR-014, FR-036–FR-040 |
| III. Database Contracts | UUID PKs/FKs; created_at+updated_at on all tables except audit_log; is_deleted soft-delete; audit_log immutable | ✅ FR-001–FR-008, schema in spec §1 |
| IV. Security Floor | NeMo sidecar platform rails (un-configurable); Presidio PII redaction; 5-iter / 2 000-token agent cap; capture_lead rate-limited | ✅ FR-029–FR-035 |
| V. Containers & Inference | Anthropic Claude + Voyage hosted API only; no torch/transformers; ONNX + onnxruntime for DL model; ≤ 500 MB images | ✅ FR-024–FR-028; §8 budget |
| VI. CI Gates | 7 gates in `eval_thresholds.yaml`; any regression blocks merge; classifier F1 ≥ 0.70 | ✅ FR-042–FR-045 |
| VII. Spec-Driven | This spec committed before any code; prompts in `prompts/`; decisions in DECISIONS.md | ✅ spec exists; prompts layout in §3 |

**Result: All 7 principles satisfied. No complexity violations. Proceed to Phase 0.**

---

## Project Structure

### Documentation (this feature)

```text
specs/001-concierge-system-spec/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── api.md
│   ├── modelserver.md
│   ├── guardrails.md
│   └── widget-loader.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
api/                          # FastAPI backend (Owners A, B, C)
├── app/
│   ├── core/
│   │   ├── config.py         # Vault-backed settings
│   │   ├── database.py       # Engine + session factory + RLS event listener
│   │   ├── security.py       # JWT verification, service-token verification
│   │   └── tracing.py        # Trace setup (Owner C, day 1)
│   ├── models/               # SQLAlchemy ORM models (9 tables)
│   │   ├── tenant.py
│   │   ├── user.py
│   │   ├── widget.py
│   │   ├── cms_content.py
│   │   ├── conversation.py
│   │   ├── message.py
│   │   ├── lead.py
│   │   ├── embedding.py
│   │   └── audit_log.py
│   ├── repositories/         # Tenant-scoped query layer
│   │   ├── base.py           # Base repo with .filter(tenant_id==...)
│   │   ├── tenant_repo.py
│   │   ├── cms_repo.py
│   │   ├── conversation_repo.py
│   │   ├── lead_repo.py
│   │   └── embedding_repo.py
│   ├── services/
│   │   ├── tenant_service.py
│   │   ├── auth_service.py
│   │   ├── cms_service.py
│   │   ├── lead_service.py
│   │   ├── erasure_service.py
│   │   └── cost_service.py
│   ├── agent/                # Owner B
│   │   ├── router.py         # Classifier-driven message router
│   │   ├── agent.py          # Tool-calling Claude agent (5-iter cap)
│   │   ├── tools/
│   │   │   ├── rag_search.py
│   │   │   ├── capture_lead.py
│   │   │   └── escalate.py
│   │   └── memory.py         # Redis session memory (30 min TTL)
│   ├── rag/                  # Owner B
│   │   ├── chunker.py        # Parent-child sentence-aware chunking
│   │   ├── embedder.py       # Voyage embeddings adapter
│   │   └── retriever.py      # pgvector cosine search + rerank/rewrite
│   ├── guardrails_client.py  # Owner C — HTTP client for sidecar
│   ├── redaction.py          # Owner C — Presidio wrapper
│   └── api/
│       ├── platform/         # Owner A — tenant_manager routes
│       │   ├── tenants.py
│       │   └── audit.py
│       ├── admin/            # Owner A/D — tenant_admin routes
│       │   ├── cms.py
│       │   ├── widgets.py
│       │   └── leads.py
│       ├── chat/             # Owner B — visitor chat route
│       │   └── messages.py
│       └── auth/             # Owner D — widget token exchange
│           └── widget_token.py
├── prompts/                  # Version-controlled prompts (Owner B)
│   ├── system.md
│   ├── rag_answer.md
│   ├── capture_lead.md
│   └── escalate.md
├── alembic/                  # Owner A — one baseline migration
│   ├── env.py
│   └── versions/
│       └── 001_baseline.py
├── seeds/                    # Owner A — demo tenant seed data
│   ├── marios_pizza.py
│   └── lawson_partners.py
└── tests/
    ├── unit/
    ├── integration/
    ├── red_team/
    │   └── probes.yaml       # Owner C
    └── evals/
        ├── test_redaction.py # Owner C
        ├── test_classifier.py
        ├── test_agent.py
        └── test_rag.py

modelserver/                  # Owner C — lean classifier (no torch)
├── app/
│   ├── main.py               # FastAPI app
│   ├── classifier.py         # Load TF-IDF + Logistic Regression joblib artifact
│   └── startup.py            #  Verify joblib SHA-256 against artifacts/model_card.md at boot
├── artifacts/                # Joblib model artifact only (not in git — fetched/copied at build)
├── model_card.md             #Human-facing summary: task, dataset, ML/DL/LLM comparison, final choice
├── pyproject.toml           # uv-managed dependencies: fastapi, uvicorn, scikit-learn, joblib, numpy
└── Dockerfile                # Lean modelserver image, no torch, no transformers, no ONNX needed

guardrails/                   # Owner C — NeMo sidecar
├── app/
│   ├── main.py
│   └── rails/
│       ├── platform_rails.co # NeMo colang config (platform — immutable)
│       └── tenant_rails.py   # Dynamic tenant topic injection
├── config/
│   └── config.yml
├── requirements.txt
└── Dockerfile

widget/                       # Owner D — Vite + React
├── src/
│   ├── ChatWidget.tsx
│   ├── api.ts                # Token exchange + chat fetch
│   └── main.tsx
├── public/
├── vite.config.ts
├── package.json
└── loader/
    └── widget.js             # /widget.js loader script (injected into API static)

admin/                        # Owner D — Streamlit
├── pages/
│   ├── 1_CMS.py
│   ├── 2_Widgets.py
│   ├── 3_Guardrails.py
│   ├── 4_Leads.py
│   └── 5_Snippet.py
├── app.py
└── requirements.txt

evals/                        # Owners B, C, D
├── classifier/
│   └── test_set.csv
├── agent/
│   └── golden_set.yaml
└── rag/
    └── golden_set.yaml

notebooks/                    # Owner C — offline training only (never in containers)
├── train_classical.ipynb
└── train_dl.ipynb

.github/
└── workflows/
    ├── ci.yml                # Owner D — main CI pipeline
    └── smoke.yml

docker-compose.yml            # Owner A
eval_thresholds.yaml          # Owner D — committed day one
DECISIONS.md
DESIGN.md
EVALS.md
SECURITY.md
RUNBOOK.md
model_card.md
.env.example
```

**Structure Decision**: Multi-service layout with one directory per deployable container
(`api/`, `modelserver/`, `guardrails/`, `widget/`, `admin/`). Shared eval golden sets
live at the repo root under `evals/`. Offline training notebooks live in `notebooks/`
and are never imported by any container. The `api/` service is the monolithic FastAPI
backend owned collectively by Owners A, B, C — each owns specific sub-packages.

---

## Complexity Tracking

No constitution violations. No extra complexity to justify.
