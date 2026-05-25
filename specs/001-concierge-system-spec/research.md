# Research: Concierge — Full System

**Phase 0 output for**: `specs/001-concierge-system-spec/plan.md`
**Date**: 2026-05-25

No NEEDS CLARIFICATION markers remained in the spec. The seven open TODOs are tracked
in `spec.md` and will close as owners make decisions. This document records design
decisions with rationale for all areas that required a non-obvious choice.

---

## RLS Session Variable — Reset Strategy

**Decision**: Use a SQLAlchemy `event.listen(engine, "before_cursor_execute", ...)` +
`event.listen(engine, "after_cursor_execute", ...)` pair, plus an explicit
`try/finally` in the FastAPI dependency that sets and resets the session variable on
the raw DBAPI connection obtained from the pool.

**Rationale**: SQLAlchemy connection pool reuses connections; a variable set in one
request leaks into the next if not explicitly reset. The `after_cursor_execute` event
fires even on exception, which `finally` in the dependency ensures at the FastAPI
level. Both layers are needed — the event handles the low-level connection, the
dependency handles the HTTP request lifecycle.

**Alternative considered**: Setting the variable only in the SQLAlchemy event. Rejected
because an unhandled exception between `set_config` and the reset event can leave the
variable set. Belt-and-suspenders (`try/finally` in dependency + event listener reset)
is the safe approach.

---

## Widget Token Signing

**Decision**: Use `PyJWT` with `HS256`, signing key = `widgets.widget_token_secret`
(a 32-byte random hex string generated per widget at creation time and stored in the
DB). Token payload: `{ tenant_id, widget_id, exp, iat }`. Expiry: 3 600 s (1 hour).

**Rationale**: Per-widget secrets mean a leaked token for Widget A cannot be replayed
on Widget B even within the same tenant. `HS256` is sufficient — the secret never
leaves the API. HTTPS in production handles transport security.

**Alternative considered**: Platform-wide JWT secret (single `jwt_secret` from Vault).
Rejected because it creates a single point of failure: one leaked token is valid for
all widgets.

---

## pgvector Index Type and Distance Metric

**Decision**: IVFFlat index with `lists=100`, `probes=10`, using cosine distance
(`vector_cosine_ops`). Filtered by `tenant_id` before ANN, using `SET
ivfflat.probes` per session.

**Rationale**: IVFFlat is the simpler and more predictable index type for a small-to-
medium corpus. HNSW would have better recall at scale but requires more memory and
slower inserts. For a week-8 demo corpus the IVFFlat recall difference is negligible.
Cosine distance is the standard for sentence embeddings.

**Alternative considered**: Exact (flat) scan. Rejected for scale story — even 1 000
chunks per tenant × 100 tenants is 100 k vectors; flat scan becomes slow.

---

## NeMo Guardrails Integration Pattern

**Decision**: Run NeMo Guardrails as a separate FastAPI sidecar (not in-process with
the API). The API sends `POST /rails/input` before sending to the LLM and `POST
/rails/output` before returning the response to the visitor. The sidecar is a separate
Docker container; service-to-service calls carry a JWT service credential from Vault.

**Rationale**: The spec mandates the sidecar pattern. Running NeMo in-process would
merge its dependencies (which are heavier) with the API image and risk exceeding the
500 MB container limit. The sidecar is independently deployable and restartable.

**Alternative considered**: In-process NeMo within the API. Rejected — dependency
weight, 500 MB constraint, and constitution principle V.

---

## RAG: Reranking vs Query Rewriting Decision Framework

**Decision**: Both approaches will be tested against the 15-triple golden set using
hit@5 as the primary metric. The winner is shipped; both numbers are committed to
DECISIONS.md. Owner B makes this call after Tuesday's first eval run.

**Reranking approach**: After top-5 chunk retrieval, send `(query, chunk)` pairs to
`voyage-rerank-2` (Voyage reranking API) and re-order by relevance score before
returning parent chunks to the LLM.

**Query rewriting approach**: Before embedding, call Claude with a short prompt to
rewrite the visitor query into a more retrieval-friendly form (denser, less
conversational), then embed and retrieve.

**Rationale**: Both are well-established single-improvement techniques. Reranking
tends to help when retrieved chunks are relevant but poorly ordered. Query rewriting
tends to help when queries are conversational and the embedding model struggles with
colloquial phrasing. The test on the golden set will reveal which matters more for
this corpus.

---

## Session Memory — Rolling TTL Implementation

**Decision**: Use Redis `SETEX` on every message write, not just on conversation
creation. Key: `session:{tenant_id}:{conversation_id}`. Value: JSON list of
`{role, content}` pairs. TTL: 1 800 s (30 min). Every new message resets the TTL.

**Rationale**: A rolling TTL (reset on activity) is more user-friendly than an
absolute TTL (fixed at session start) for a concierge — a visitor might read a long
FAQ for 20 minutes before typing again. The 30-minute window is a privacy/usability
balance: long enough for normal conversations, short enough that anonymous visitor
history does not persist indefinitely.

---

## Vault Secrets Injection in Docker Compose

**Decision**: Use the `vault agent` sidecar pattern at dev time via an `.env.example`
with placeholder values and a startup script (`api/startup.sh`) that fetches secrets
from Vault using the `VAULT_TOKEN` environment variable and writes them to environment.
In production this would be replaced by Vault Agent or Kubernetes secrets injection.

**Rationale**: Week-8 scope is Docker Compose. The `VAULT_TOKEN` is the one secret
that must be provided externally (via `cp .env.example .env` + fill in root token).
Everything else is fetched at startup. This keeps secrets out of source control while
keeping the workflow simple.

---

## Classifier — Three-Model Comparison Framework

**Decision**: All three models are trained and evaluated offline in `notebooks/`.

| Model | Training | Artifact | Serving |
|-------|----------|----------|---------|
| Classical (TF-IDF + LR) | scikit-learn in notebook | `artifacts/classical.joblib` | `joblib.load()` |
| DL (small Transformer or CNN) | PyTorch/Keras in Colab | `artifacts/dl_model.onnx` | `onnxruntime.InferenceSession` |
| LLM baseline | Anthropic Claude API zero-shot | N/A (API call) | Direct API call |

Evaluation metrics: macro-F1, per-class F1, p50/p95 inference latency, cost per 1 000
calls. Owner C records all three results in `model_card.md` and ships one model with a
one-line justification in DECISIONS.md.

**Alternative considered**: Only shipping the classical model (fastest to implement).
Rejected — the spec and constitution require all three to be evaluated; the graders
check for the three-number comparison.

---

## Presidio PII Redaction — Entity List and Integration Point

**Decision**: Presidio runs in the API process (not in the guardrails sidecar) as a
Python function call on every string that could leave the service boundary: log
messages, trace attributes, Redis write values, and LLM response content before it is
stored as a `messages` row or returned to the widget.

**Entities detected**: EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD, CRYPTO, API_KEY (via
custom recognizer — Presidio does not natively detect API keys, so a regex recognizer
for common API key patterns is added), US_SSN, IP_ADDRESS, PASSWORD.

**Rationale**: Centralising redaction in the API keeps the guardrails sidecar focused
on topic and injection rails, and means every service that writes logs/traces goes
through one redaction path.

---

## Tracing Backend

**Decision**: TBD by Owner D on Monday 2026-05-25. Candidates: OpenTelemetry →
Jaeger (fully open-source, fits in Docker Compose); OpenTelemetry → Tempo (Grafana
stack). Owner D commits the choice to DECISIONS.md. Every LLM call, embedding call,
and tool invocation emits a span tagged with `tenant_id`; all span attributes are
PII-redacted before export.

---

## Open TODOs Resolution Target Dates

| TODO | Owner | Due | Resolution |
|------|-------|-----|------------|
| Classifier dataset | C | 2026-05-25 (Mon) | Record in model_card.md |
| Tracing backend | D | 2026-05-25 (Mon) | Record in DECISIONS.md |
| RAG CI thresholds | B | 2026-05-26 (Tue) | Update eval_thresholds.yaml |
| Agent tool-selection CI threshold | B | 2026-05-27 (Wed) | Update eval_thresholds.yaml |
| `capture_lead` rate-limit numbers | B | 2026-05-27 (Wed) | Record in DECISIONS.md |
| Per-tenant rate-limiting thresholds | A | 2026-05-26 (Tue) | Record in DECISIONS.md |
| Redis rolling window size N | B | 2026-05-27 (Wed) | Record in DECISIONS.md |
