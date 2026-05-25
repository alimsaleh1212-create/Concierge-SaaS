<!--
SYNC_IMPACT
Version: template → 1.0.0
Modified principles: none — first ratification from blank template
Added sections:
  I.   Isolation
  II.  Authentication & Roles
  III. Database Contracts
  IV.  Security Floor
  V.   Containers & Inference
  VI.  CI Gates — All Must Pass Before Merge
  VII. Spec-Driven Development
Removed sections: all placeholder template content
Templates requiring updates:
  - .specify/templates/plan-template.md  ✅ Constitution Check section already present; gates now derivable from this file
  - .specify/templates/spec-template.md  ✅ No changes required; template is technology-agnostic
  - .specify/templates/tasks-template.md ✅ No changes required; task structure is compatible
Follow-up TODOs:
  - TODO(CLASSIFIER_DATASET): Classifier dataset not yet chosen — update model card and DECISIONS.md when dataset is locked
  - TODO(TRACING_BACKEND): Tracing backend TBD by Owner D — update DESIGN.md when decided
  - TODO(RAG_THRESHOLDS): RAG hit@k and faithfulness CI floor values are placeholders; tighten after first eval run
  - TODO(AGENT_ACCURACY_THRESHOLD): Agent tool-selection accuracy CI floor is a placeholder; tighten after first eval run
-->

# Concierge Constitution

## Core Principles

### I. Isolation (NON-NEGOTIABLE)

Every tenant-scoped database table MUST carry a `tenant_id` UUID column protected by a
Postgres Row-Level Security (RLS) policy. The per-request RLS session variable
(`app.tenant_id`) is set by a SQLAlchemy event listener at the start of every request
and reset at the end — pooled connections persist it, and a leftover value is a
cross-tenant breach.

The repository layer MUST also scope every query explicitly with `.filter(tenant_id == ...)`
as a second, independent defence layer. RLS is the backstop; the filter is the primary guard.

pgvector retrieval MUST apply the `tenant_id` filter at query time inside the SQL/index
scan — never as a post-retrieval Python filter on the result set.

`tenant_id` MUST always be derived from the verified signed token. A client-supplied
`tenant_id` field in any request body or query string MUST be rejected with a 400/403.

**Rationale**: Cross-tenant data leakage is the #1 failure mode for multi-tenant AI
products. Three independent enforcement layers (RLS, repo filter, vector filter) ensure
that forgetting any one of them is not a breach.

### II. Authentication & Roles (NON-NEGOTIABLE)

Authentication MUST use `fastapi-users` (JWT + email/password). No custom auth
implementation is permitted.

Exactly three roles exist — `tenant_manager` (platform), `tenant_admin` (per tenant),
`member` / visitor. No configurable permission matrix, no fourth role.

Widget visitors MUST authenticate with a short-lived PyJWT-signed token (1-hour expiry)
obtained by the loader script exchanging the public `widget_id` plus origin. A raw
`widget_id` MUST NOT be accepted as authentication.

All service-to-service calls (API ↔ guardrails sidecar ↔ modelserver) MUST carry a
JWT service credential resolved from Vault. Network adjacency alone is not authentication.

CORS and `Content-Security-Policy: frame-ancestors` are defence-in-depth controls, not
the authentication boundary. A server-side origin check MUST be performed in the request
handler independent of CORS.

**Rationale**: A general RBAC engine is untestable in a week. Three named roles with
enumerable powers can be audited, tested, and reasoned about.

### III. Database Contracts (NON-NEGOTIABLE)

Every primary key and every foreign key MUST be UUID. Integer PKs are forbidden.

Every table MUST have `created_at` and `updated_at` timestamps, except `audit_log`
which is immutable and carries `created_at` only.

Every tenant-scoped table MUST carry `is_deleted` (soft delete). Hard deletes are
permitted only on a right-to-erasure request, and only via the narrow
write/delete-only maintenance path — not through any general read bypass.

`audit_log` rows are append-only. No `UPDATE` or `DELETE` is ever issued against them.

One baseline Alembic migration authored by Owner A on the first day of coding MUST
cover all tables. Subsequent migrations are additive.

**Rationale**: UUID PKs prevent enumeration attacks. Soft deletes preserve the audit
trail. A single baseline migration prevents schema drift across team branches.

### IV. Security Floor (NON-NEGOTIABLE)

Platform guardrail rails — prompt injection detection, jailbreak detection,
cross-tenant refusal — MUST run through the NeMo Guardrails sidecar on every inbound
message. No tenant configuration may weaken or disable these rails.

PII redaction via Presidio MUST execute before any data leaves the service boundary:
logs, traces, Redis session writes, and LLM response payloads.

A CI test that pastes a synthetic API key into chat and asserts it never appears
unredacted in any output MUST pass before any merge to main.

The agent loop MUST be capped at 5 tool-call iterations and 2,000 tokens per turn.
`capture_lead` writes MUST be rate-limited per session and per visitor IP.

The right-to-erasure path MUST synchronously hard-delete all tenant data across
Postgres rows, pgvector embeddings, MinIO blobs, and Redis sessions, and log every
deletion to `audit_log` before returning success.

**Rationale**: Platform rails protect every tenant from every other tenant's
misconfiguration. Making them un-configurable is the only guarantee that is actually
a guarantee.

### V. Containers & Inference (NON-NEGOTIABLE)

All LLM calls MUST use the Anthropic Claude hosted API. All embedding calls MUST use
the Voyage hosted API. No local model weights are permitted in any container.

`torch` and `transformers` are FORBIDDEN in any container image — ever. Training
happens offline (notebook / Colab, ephemeral). The DL classifier artifact MUST be
exported to ONNX and served via `onnxruntime`. The classical classifier MUST be
serialised with `joblib` and served via `scikit-learn`.

No container image may exceed 500 MB. If an image exceeds this limit, the build MUST
fail CI.

The model-server MUST refuse to start if the loaded artifact's SHA-256 does not match
the value pinned in the model card.

**Rationale**: Hosted-API inference keeps images small and builds fast. ONNX +
onnxruntime is the production-honest pattern for serving DL without dragging the
training framework into the serving stack.

### VI. CI Gates — All Must Pass Before Merge (NON-NEGOTIABLE)

Every gate below MUST be green on every push to main. A regression in any gate MUST
block the merge.

| Gate | Metric | Floor |
|------|--------|-------|
| Classifier (held-out test set) | Macro-F1 | ≥ 0.70 (tighten after real eval) |
| Agent tool-selection (15 golden examples) | Accuracy | TODO — placeholder |
| RAG retrieval (15 golden triples) | hit@5, MRR | TODO — placeholder |
| RAG generation (15 golden triples) | Faithfulness, answer relevancy | TODO — placeholder |
| Red-team injection + cross-tenant probes | All attempts refused | 100% |
| PII redaction test | Fake key never appears unredacted | 100% |
| Stack smoke test | `docker-compose up` from fresh clone | Pass |

Thresholds are committed in `eval_thresholds.yaml`. Updating a threshold requires a
DECISIONS.md entry explaining the change.

**Rationale**: CI that does not gate on agent behaviour and isolation is theatre.
These gates ensure no refactor silently reopens a security hole or degrades eval quality.

### VII. Spec-Driven Development (NON-NEGOTIABLE)

Every major component MUST have a `SPEC.md` committed and reviewed before any
implementation code is written for that component.

Prompts MUST live in the `prompts/` directory under version control. Tenant persona
MUST be injected at runtime from tenant config — it MUST NOT be hardcoded in any
prompt file or source file.

Every architectural decision MUST be backed by a measurement (F1, latency, hit-rate,
or similar) recorded in `DECISIONS.md`. "A blog post told me to" is not a decision.

Required documentation artifacts that MUST exist before the Friday demo:
`DESIGN.md`, `DECISIONS.md`, `RUNBOOK.md`, `EVALS.md`, `SECURITY.md`, model card.

**Rationale**: Specs are contracts. A decision without a number is an opinion. The
graders will ask each teammate to defend any part of the system — shared specs are
the only way the team shares the design.

## Governance

### Amendment Procedure

Any change to a Non-Negotiable principle requires:
1. A written proposal in `DECISIONS.md` explaining the motivation.
2. Agreement from all four team members.
3. A version bump to this file following semantic versioning:
   - **MAJOR**: Removing or redefining a Non-Negotiable principle.
   - **MINOR**: Adding a new principle or materially expanding guidance.
   - **PATCH**: Clarifications, wording fixes, typo corrections.
4. An updated `LAST_AMENDED_DATE` in the version line below.

### Compliance Review

Every pull request MUST include a Constitution Check section in its plan confirming
each principle is satisfied or explicitly noting a justified exception. A PR that
introduces a query without a `tenant_id` filter, a container with `torch`, or a
skipped CI gate MUST be rejected in code review.

The Constitution supersedes all other project documents. In case of conflict, this
file wins.

**Version**: 1.0.0 | **Ratified**: 2026-05-25 | **Last Amended**: 2026-05-25
