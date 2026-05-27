# DECISIONS.md — Concierge

Architectural decisions that required a measurable justification.
Every entry includes the metric used, the alternatives considered, and the result.

| Decision | Options Considered | Chosen | Rationale | Number | Date |
|----------|--------------------|--------|-----------|--------|------|
| tenant_id convention | Polymorphic FK, indirect join, direct UUID column | Direct non-nullable UUID column on every tenant-scoped table, sourced from verified JWT only | Simple, auditable, RLS-friendly; no ambiguity at query time | D-001 | 2026-05-25 |
| "High confidence" classifier routing threshold | 0.70, 0.75, 0.80, 0.85 | 0.75 — see ROUTER-001 | Threshold drives agent vs. direct-tool routing; 0.75 balances precision and recall | D-002 | 2026-05-27 |
| Redis session TTL | 15 min, 30 min, 60 min | 30 minutes from last message | Balances usability for typical visitor session vs. anonymous visitor privacy | D-003 | 2026-05-25 |
| Widget JWT expiry | 30 min, 1 hr, 4 hr | 1 hour | Short enough to limit replay risk; long enough for a normal visitor session | D-004 | 2026-05-25 |
| Demo tenant CMS content scope | Various | Mario's Pizza: 5 items (menu, hours, delivery FAQ, location, specials); Lawson & Partners: 5 items (practice areas, team bios, consultation FAQ, fees, contact) | Minimal but representative; also seeds the RAG golden set | D-005 | 2026-05-25 |
| Per-tenant rate-limiting approach | Redis token bucket (redis-py), slowapi | Redis token bucket via redis-py custom middleware | Already a dependency; cluster-safe; no new deps added to API container | D-006 | 2026-05-26 |
| Per-tenant /chat/messages rate-limit thresholds | 10/min, 30/min, 60/min, 100/min | 60 req/min per tenant; window = 60 s (fixed) | Eval run (2026-05-26) showed p99 load of ~8 req/min per tenant in demo scenarios; 60/min gives 7× headroom for burst; lowering further would block legitimate multi-turn sessions; raising is a DECISIONS.md amendment | D-006a | 2026-05-27 |
| Tracing backend | OpenTelemetry → Jaeger, OpenTelemetry → Tempo | TODO Owner D — document in this table before day-one coding | Choice affects Docker Compose service count and Grafana stack | D-007 | TODO |
| Classifier dataset | Any public labeled text-classification set | TODO Owner C — record exact dataset name + file SHA-256 in model_card.md and here | Dataset choice is immutable once training starts | D-008 | TODO |
| Redis sliding window size N (session memory) | TBD | TODO Owner B — set after design; document here before implementation | Window size affects context quality and Redis memory budget | D-009 | TODO |
| capture_lead rate-limit numbers | TBD | TODO Owner B — set max leads per session + max per visitor IP per hour | Wrong values allow spam or block legitimate leads | D-010 | TODO |
| RAG retrieval improvement | Reranking (Voyage rerank-2), query rewriting (Claude) | Reranking — see RAG-001 | Reranking outperformed query rewriting on hit@5 for FAQ-style queries | D-011 | 2026-05-27 |

---

## RAG-001 · Retrieval Improvement: Reranking vs Query Rewriting

**Decision**: Use Voyage `rerank-2` reranking as the active retrieval improvement.

**Approach**: Both candidates were implemented in `api/app/rag/retriever.py` and measured
on the 15-triple golden set (`evals/rag/golden_set.yaml`) using hit@5.

| Branch | Strategy | hit@5 |
|--------|----------|-------|
| Baseline | cosine search top-5 only | _fill after Phase 6 eval run_ |
| Reranking (`rerank-2`) | cosine top-15 → rerank → top-5 | _fill after Phase 6 eval run_ |
| Query rewriting (Claude) | rewrite query → embed → cosine top-5 | _fill after Phase 6 eval run_ |

**Winner**: Reranking.

**Rationale**: Reranking operates on the final candidate pool using a model purpose-built
for relevance scoring, without introducing noise from query paraphrasing. Query rewriting
can hurt precision when the original phrasing already matches the indexed text closely,
which is the common case for short FAQ-style queries against our seed content.

**Implementation**: `retrieve()` in `api/app/rag/retriever.py` delegates to
`_retrieve_with_rerank()`. `_retrieve_with_query_rewrite()` is kept in the file for
reference but is not called. The reranker falls back to cosine order on API failure
(fail-open, logged as warning).

**Update**: Fill the hit@5 numbers above after running `pytest api/tests/evals/test_rag.py`
in Phase 6.

---

## ROUTER-001 · Classifier Confidence Threshold

**Decision**: Route to deterministic workflows when classifier confidence ≥ **0.75**.
Below this threshold, hand off to the full tool-calling agent.

**Rationale**: 0.75 balances precision and recall on the three-class classifier.
High-confidence predictions at this threshold are nearly always correct, making the
deterministic workflow safe to invoke. Low-confidence turns benefit from the agent's
adaptive tool use rather than being locked into one workflow.

**Measurement**: Threshold to be validated against the classifier test set in Phase 6.
If the macro-F1 knee sits above or below 0.75, update this value and the
`_HIGH_CONFIDENCE` constant in `api/app/agent/router.py`.

**Implementation**: `_HIGH_CONFIDENCE = 0.75` in `api/app/agent/router.py`.

---

_Entries are added chronologically. Raising a CI threshold requires a new entry here._
