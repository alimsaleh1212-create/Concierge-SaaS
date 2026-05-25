---
description: "Shared pre-implementation tasks — whole team completes before any owner-specific work begins"
---

# Tasks: Concierge — Shared (Pre-Implementation)

**Input**: Design documents from `specs/001-concierge-system-spec/`
**Owner**: All four owners complete this file together
**When**: Monday morning session — done as a group before splitting into owner slices
**Blocks**: All owner-specific task files (tasks-owner-a.md, tasks-owner-b.md, etc.)

**Rule**: No owner begins their Phase 1 setup tasks until every task in this file is
checked off and committed to main.

---

## Phase 1: Spec Review & Agreement (Team Together)

**Purpose**: Every owner reads every section of the spec and agrees the contracts before
a single line of code is written. Changing `tenant_id` conventions on Thursday is agony.

- [ ] T-S001 Every owner reads `specs/001-concierge-system-spec/spec.md` in full — all 8 sections — and raises any ambiguity in team chat before proceeding
- [ ] T-S002 Every owner reads `specs/001-concierge-system-spec/data-model.md` — confirm all 9 table definitions, column types, and RLS policy patterns are understood and agreed
- [ ] T-S003 Every owner reads `specs/001-concierge-system-spec/contracts/api.md` — confirm every route, request/response shape, and auth requirement is agreed
- [ ] T-S004 [P] Every owner reads `specs/001-concierge-system-spec/contracts/modelserver.md` — agree the classify contract and boot SHA-256 check
- [ ] T-S005 [P] Every owner reads `specs/001-concierge-system-spec/contracts/guardrails.md` — agree the /rails/input and /rails/output contract shapes
- [ ] T-S006 [P] Every owner reads `specs/001-concierge-system-spec/contracts/widget-loader.md` — agree the embed flow and postMessage protocol
- [ ] T-S007 Every owner reads `specs/001-concierge-system-spec/plan.md` — confirm the full directory structure and each owner's file ownership
- [ ] T-S008 Team confirms the `tenant_id` UUID convention: every tenant-scoped table has a direct non-nullable `tenant_id` UUID column; no polymorphic or indirect references; agreed and immutable from this point forward

**Checkpoint**: All four owners have read all seven documents. No unresolved ambiguities remain.

---

## Phase 2: Open TODOs — Resolve Before Coding Starts

**Purpose**: Seven TODOs were deferred in the spec. Three of them must be resolved
before day-one coding begins (Monday). The rest have Tuesday/Wednesday deadlines.

**Due Monday before coding**:

- [ ] T-S009 Owner C: Choose classifier dataset — must be a public labeled text-classification set (sales/support/spam intent or close equivalent); record exact dataset name and file SHA-256 in `model_card.md`; announce choice in team chat
- [ ] T-S010 Owner D: Choose tracing backend — candidates: OpenTelemetry → Jaeger (simpler, fits Docker Compose) or OpenTelemetry → Tempo (Grafana stack); commit choice to `DECISIONS.md` with one-line rationale; announce in team chat
- [ ] T-S011 Owner A: Confirm per-tenant rate-limiting approach — Redis token bucket (simpler) vs slowapi (less code); document chosen library and placeholder threshold values in `DECISIONS.md`

**Due Tuesday (after first eval run)**:

- [ ] T-S012 Owner B: Set RAG CI threshold floors — after first RAGAS run on Tuesday, replace `0.00` placeholders in `eval_thresholds.yaml` for `rag.hit_at_5` and `rag.faithfulness` with real values
- [ ] T-S013 Owner B: Set agent tool-selection CI threshold floor — after first golden-set run on Wednesday, replace `0.00` placeholder for `agent_tool_selection.accuracy` in `eval_thresholds.yaml`

**Due Wednesday**:

- [ ] T-S014 Owner B: Set exact `capture_lead` rate-limit numbers (max leads per session + max per visitor IP per hour); document in `DECISIONS.md`
- [ ] T-S015 Owner B: Confirm Redis sliding window size N for session memory; document in `DECISIONS.md`

**Checkpoint**: T-S009, T-S010, T-S011 done before Monday coding begins. T-S012–T-S015 tracked and completed by their deadlines.

---

## Phase 3: Repository Skeleton (Owner A drives, everyone watches)

**Purpose**: Create the full directory tree and empty stub files so every owner can
start work without merge conflicts on directory creation. One person drives on a
shared screen; everyone else reviews.

- [X] T-S016 Create all top-level directories per `plan.md` project structure: `api/`, `modelserver/`, `guardrails/`, `widget/`, `admin/`, `evals/`, `notebooks/`, `prompts/`, `.github/workflows/` in the repo root
- [X] T-S017 Create all `api/app/` subdirectories: `core/`, `models/`, `repositories/`, `services/`, `agent/agent/tools/`, `rag/`, `api/platform/`, `api/admin/`, `api/chat/`, `api/auth/` with `.gitkeep` files
- [X] T-S018 [P] Create `evals/classifier/`, `evals/agent/`, `evals/rag/` with `.gitkeep` files in `evals/`
- [X] T-S019 [P] Create `api/tests/unit/`, `api/tests/integration/`, `api/tests/red_team/`, `api/tests/evals/` with `.gitkeep` files
- [X] T-S020 [P] Create `api/alembic/versions/` directory with `.gitkeep` in `api/alembic/versions/`
- [X] T-S021 [P] Create `api/seeds/` directory with `__init__.py` stub in `api/seeds/__init__.py`
- [X] T-S022 Create `.gitignore` covering: `__pycache__/`, `*.pyc`, `.env`, `*.joblib`, `*.onnx`, `node_modules/`, `dist/`, `.DS_Store`, `*.egg-info/`, `.venv/`, `vault-data/` in `.gitignore`

**Checkpoint**: `git status` shows the full directory tree. Every owner can pull and start work in their directories without conflicts.

---

## Phase 4: Stub Documentation Files

**Purpose**: Create all required documentation files as stubs on day one so they appear
in the repo from the start. Owners fill them in as decisions are made.

- [X] T-S023 [P] Create `DESIGN.md` stub with section headers: Tenant Isolation Strategy, Role Model, Scaling Story (10→1000 tenants), RLS Exception (audit_log) in `DESIGN.md`
- [X] T-S024 [P] Create `DECISIONS.md` stub with section headers and a template row: `| Decision | Options Considered | Chosen | Rationale | Number | Date |` in `DECISIONS.md`
- [X] T-S025 [P] Create `RUNBOOK.md` stub with section headers: Prerequisites, First-time Setup, Rebuilding Services, Running Evals, Common Issues in `RUNBOOK.md`
- [X] T-S026 [P] Create `EVALS.md` stub with section headers: Classifier Results, Agent Tool-Selection Results, RAG Results, Red-Team Results, Inter-Annotator Agreement in `EVALS.md`
- [X] T-S027 [P] Create `SECURITY.md` stub with section headers: Threat Model, Isolation Layers, Guardrail Architecture, PII Redaction, Service-to-Service Auth, Erasure Path in `SECURITY.md`
- [X] T-S028 [P] Create `model_card.md` stub with all required fields from spec §4: Task Description, Dataset (TODO), Three Model Results (TODO), Deployment Choice (TODO), Artifact SHA-256 (TODO) in `model_card.md`

**Checkpoint**: All 6 required doc files exist in the repo. CI can reference them from day one.

---

## Phase 5: eval_thresholds.yaml — Day One Commit

**Purpose**: Commit `eval_thresholds.yaml` with day-one placeholder values so the CI
pipeline has something to read from the first push. Real values replace placeholders
as evals run.

- [X] T-S029 Create `eval_thresholds.yaml` with exact contents below — commit to main on day one in `eval_thresholds.yaml`:

```yaml
# Concierge CI Eval Thresholds
# Update placeholders (0.00) after first eval run — never lower a threshold.
# Every change to this file requires a DECISIONS.md entry.

classifier:
  macro_f1: 0.70           # Floor from spec; tighten after real eval run

agent_tool_selection:
  accuracy: 0.00           # TODO Owner B — set after Wednesday golden-set run

rag:
  hit_at_5: 0.00           # TODO Owner B — set after Tuesday RAGAS run
  faithfulness: 0.00       # TODO Owner B — set after Tuesday RAGAS run

red_team:
  pass_rate: 1.00          # All probes must be refused — never lower this

redaction:
  pass_rate: 1.00          # Fake key must never appear unredacted — never lower this

smoke_test:
  pass: true               # docker-compose up from fresh clone must succeed
```

**Checkpoint**: `eval_thresholds.yaml` is committed. The CI pipeline can read it immediately.

---

## Phase 6: GitHub Setup

**Purpose**: Branch protection and CI skeleton so every push is validated from day one,
even before gate logic is implemented.

- [ ] T-S030 Enable branch protection on `main`: require PR review, require CI status checks to pass, no direct push to main in GitHub repository settings
- [X] T-S031 Create GitHub Actions skeleton workflow `.github/workflows/ci.yml` with stages that pass immediately (no logic yet): lint stub, build stub, gates stub — stages exist so branch protection can reference them; Owner D fills in logic in their tasks in `.github/workflows/ci.yml`
- [ ] T-S032 [P] Push the full spec artifact tree to main: `specs/001-concierge-system-spec/` (all docs + contracts), `eval_thresholds.yaml`, all stub docs, `.gitignore` — confirm CI passes on first push

**Checkpoint**: Main branch is protected. CI runs and passes (stubs only). Every subsequent PR must pass CI before merge.

---

## Phase 7: Team Agreements (Verbal + Written)

**Purpose**: Decisions that must be made verbally and recorded in writing before coding.
These have no code artifact — they live in DECISIONS.md.

- [X] T-S033 Record the `tenant_id` convention decision in `DECISIONS.md`: UUID, direct column on every tenant-scoped table, sourced from verified JWT only, never from request body — agreed by all four owners on 2026-05-25
- [X] T-S034 Record the "high confidence" routing threshold definition in `DECISIONS.md`: Owner B proposes the value (e.g. 0.80); team agrees; written down before router is implemented
- [X] T-S035 [P] Record the Redis rolling TTL justification in `DECISIONS.md`: 30 minutes from last message — balances usability vs anonymous visitor privacy
- [X] T-S036 [P] Record the widget JWT expiry justification in `DECISIONS.md`: 1 hour — short enough to limit replay risk, long enough for a normal visitor session
- [X] T-S037 Agree on demo tenant CMS content scope: Mario's Pizza gets 5 CMS items (menu, hours, delivery FAQ, location, specials); Lawson & Partners gets 5 CMS items (practice areas, team bios, consultation FAQ, fees, contact) — these seed the RAG golden set too; record in `DECISIONS.md`

**Checkpoint**: `DECISIONS.md` has at least 5 entries before any owner starts coding.

---

## Completion Gate

**All shared tasks complete when**:
- [ ] T-S038 Every task in this file is checked off and committed to main
- [ ] T-S039 All four owners confirm readiness in team chat: "ready to split into owner slices"
- [ ] T-S040 Owner A begins `tasks-owner-a.md` Phase 1; other owners begin their Phase 1 in parallel

---

## Execution Order

```
Monday morning (together, ~2 hours):

T-S001–T-S008  Spec review (sequential reads, parallel across owners)
     ↓
T-S009 + T-S010 + T-S011  Resolve Monday TODOs (parallel decisions)
     ↓
T-S016–T-S022  Repo skeleton (Owner A drives on shared screen)
     ↓
T-S023–T-S028  Stub docs (all parallel — one owner per file)
     ↓
T-S029         eval_thresholds.yaml (Owner D writes, all review)
     ↓
T-S030–T-S032  GitHub setup (Owner D drives)
     ↓
T-S033–T-S037  Written agreements in DECISIONS.md (Owner B/D write, all review)
     ↓
T-S038–T-S040  Confirm complete → split into owner slices
```

**Time target**: Complete by Monday noon → owner slices begin Monday afternoon.

---

## Notes

- No code is written in this file — these are spec, agreement, skeleton, and config tasks
- T-S009 (dataset choice) and T-S010 (tracing backend) are the two decisions with the
  longest downstream impact — do not skip them to "figure it out later"
- The CI skeleton (T-S031) must exist before branch protection is enabled (T-S030) —
  otherwise the first PR has no status checks to satisfy
- eval_thresholds.yaml (T-S029) is committed with `0.00` placeholders intentionally —
  the CI classifier gate still has `0.70` from the spec; only the eval gates are
  placeholder; the CI will pass on day one even with placeholders because the eval
  scripts don't exist yet
- The "ready to split" confirmation (T-S039) is a social contract — once given, owners
  work in parallel and coordinate only on the external dependencies listed in their
  individual task files
