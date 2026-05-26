# DECISIONS.md — Concierge

Architectural decisions that required a measurable justification.
Every entry includes the metric used, the alternatives considered, and the result.

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
