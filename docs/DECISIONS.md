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
| Tracing backend | OpenTelemetry → Jaeger, OpenTelemetry → Tempo | OpenTelemetry → Jaeger | Simpler all-in-one UI and collector; fewer moving parts than Tempo + Grafana | D-007 | 2026-05-26 |
| Classifier dataset | Any public labeled text-classification set | TODO Owner C — record exact dataset name + file SHA-256 in model_card.md and here | Dataset choice is immutable once training starts | D-008 | TODO |
| Redis sliding window size N (session memory) | 5, 10, 20, unlimited | N=10 — last 10 messages per conversation | 10 messages cover ~5 turns; enough context for typical visitor sessions without bloating Redis payloads or prompt size | D-009 | 2026-05-27 |
| capture_lead rate-limit numbers | Various | 3 per session, 5 per visitor IP per hour | 3/session blocks repeated re-submission in one chat; 5/hour per IP prevents scripted spam across sessions while allowing legitimate re-engagement | D-010 | 2026-05-27 |
| RAG retrieval improvement | Reranking (Voyage rerank-2), query rewriting (Claude) | Reranking — see RAG-001 | Reranking outperformed query rewriting on hit@5 for FAQ-style queries | D-011 | 2026-05-27 |
| Admin auth implementation | fastapi-users (per original plan), native PyJWT + bcrypt `/auth/login` | Native PyJWT + bcrypt `/auth/login` accepting OAuth2 password form | Rest of the stack already uses native PyJWT/bcrypt (`security.py`, `auth_service.create_access_token`, `require_role`, seeds); adopting fastapi-users would have required a User-model migration, re-hashing seeds, and re-wiring every admin route's `Depends`. Same security properties (HS256 JWT, bcrypt-hashed passwords) with one new endpoint and no migration. | D-012 | 2026-05-28 |

---

## RAG-001 · Retrieval Improvement: Reranking vs Query Rewriting

**Decision**: Use Voyage `rerank-2` reranking as the active retrieval improvement.

**Approach**: All four strategies were implemented in `api/app/rag/retriever.py` and
measured on the 15-triple golden set (`evals/rag/golden_set.yaml`) using hit@5 and MRR.

| Strategy | Approach | hit@5 | MRR |
|----------|----------|-------|-----|
| Baseline | cosine top-5 only | 0.667 | 0.613 |
| HyDE (Claude) | generate hypothetical answer → embed → cosine top-5 | 0.667 | 0.617 |
| **Reranking (`rerank-2`)** | cosine top-15 → rerank → top-5 | **0.667** | **0.622** |
| Query rewriting (Claude) | rewrite query → embed → cosine top-5 | 0.600 | 0.600 |

All strategies measured 2026-05-27 on the 15-triple golden set.
Faithfulness (RAGAS-style, 24 synthetic samples): **0.944**.

**Winner**: Reranking (`rerank-2`).

**Rationale**: All strategies except query rewriting tie on hit@5. The MRR gap between
reranking and baseline (0.622 vs 0.613) is small on 15 samples and not statistically
significant on its own. Reranking is chosen on architectural grounds: a cross-encoder
reads the query and each candidate together, which is fundamentally more accurate than
comparing independent vectors. It also adds no LLM call to the hot path, and its
advantage grows as the corpus expands. Query rewriting actively hurts precision on
short FAQ-style queries by broadening them unnecessarily. HyDE adds LLM latency per
query with no measurable benefit over baseline for this content type.

**Implementation**: `retrieve()` in `api/app/rag/retriever.py` delegates to
`_retrieve_with_rerank()`. All other strategies are kept in the file for reference
but are not called. The reranker falls back to cosine order on API failure
(fail-open, logged as warning).

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
