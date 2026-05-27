---
description: "Task list — Owner B: Agent, RAG & Memory"
---

# Tasks: Concierge — Owner B (Agent, RAG & Memory)

**Input**: Design documents from `specs/001-concierge-system-spec/`
**Owner**: Owner B — covers SPEC.md Section 3
**Prerequisites**: Owner A must complete the Alembic baseline migration, Docker Compose
stack, and embedding_repo.py scaffold before Owner B begins Phase 2.

**Tests**: Not requested as TDD — no separate test-first tasks.
**Labels**: All tasks tagged [Owner B]. Run `/speckit-implement` and filter to [Owner B].

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Parallelizable — different files, no incomplete dependencies
- **[Story]**: User story label (US1, US2, US5) from spec.md
- Paths assume the repo root structure defined in `plan.md`

---

## Phase 1: Setup (Owner B)

**Purpose**: Create the directory skeleton and shared adapters Owner B owns from day one.

- [x] T-B001 [P] Create `prompts/` directory with stub files: `system.md`, `rag_answer.md`, `capture_lead.md`, `escalate.md` in `prompts/`
- [x] T-B002 [P] Create Anthropic Claude API adapter with retry, timeout, and per-call token logging in `api/app/core/llm.py`
- [x] T-B003 [P] Create Voyage embeddings adapter (voyage-3, 1024-dim) with retry in `api/app/core/embedder.py`
- [x] T-B004 [P] Create `evals/agent/` and `evals/rag/` directories with placeholder YAML files in `evals/agent/golden_set.yaml` and `evals/rag/golden_set.yaml`

**Checkpoint**: adapters importable, prompt stubs committed, eval dirs exist

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Infrastructure Owner B depends on before any user story can be implemented.
Coordinate with Owner A on the items marked *(Owner A dependency)*.

**⚠️ CRITICAL**: No user story work begins until this phase is complete.

- [x] T-B005 Verify Alembic baseline migration ran and `embeddings` table with `VECTOR(1024)` column exists *(Owner A dependency — do not write migration, only verify)*
- [x] T-B006 Implement Redis session helper: connect, `get_session`, `set_session` (rolling SETEX 1800s), `delete_session` in `api/app/core/session.py`
- [x] T-B007 Implement `EmbeddingRepository` with `insert_chunk`, `cosine_search(query_vec, tenant_id, top_k)` — tenant_id filter inside SQL scan, never post-retrieval — in `api/app/repositories/embedding_repo.py`
- [x] T-B008 Confirm modelserver `POST /classify` is reachable from the API container and returns `{label, confidence}` *(Owner C dependency — do not implement, only add HTTP client in `api/app/core/modelserver_client.py`)*

**Checkpoint**: Redis, embedding repo, and modelserver client all work in isolation via unit tests before user story phases start

---

## Phase 3: User Story 1 — Visitor Chats with Agent (Priority: P1) 🎯 MVP

**Goal**: A visitor sends a message; the router classifies it and either handles it via
a deterministic workflow or hands it to the tool-calling agent; a response is returned.

**Independent Test**: Start the full stack, use the NovaTech Electronics widget token, send
"What are your opening hours?" — get a RAG-based answer. Send "I'd like to hire a
lawyer" — trigger the router's spam/drop path (wrong tenant topic). Send a multi-step
ambiguous query — verify the agent uses tools.

### RAG Pipeline

- [x] T-B009 [P] [US1] Implement sentence-aware parent-child chunker: split `body` into child chunks (~1–2 sentences), group into parent chunks (3–5 sentences) in `api/app/rag/chunker.py`
- [x] T-B010 [P] [US1] Implement `embed_chunks(chunks: list[str]) -> list[list[float]]` using the Voyage adapter (T-B003) in `api/app/rag/embedder.py`
- [x] T-B011 [US1] Implement `ingest_content(content_id, tenant_id, body)` that chunks (T-B009), embeds (T-B010), and upserts into `embeddings` via `EmbeddingRepository` (T-B007) in `api/app/rag/ingester.py`
- [x] T-B012 [US1] Implement `retrieve(query: str, tenant_id: UUID, top_k: int = 5) -> list[ParentChunk]` — embed query, cosine search via EmbeddingRepository, return parent chunks — in `api/app/rag/retriever.py`

### Agent Tools

- [x] T-B013 [P] [US1] Implement `rag_search` tool: embed query → retrieve top-5 child chunks (tenant-filtered) → return parent chunks as context in `api/app/agent/tools/rag_search.py`
- [x] T-B014 [P] [US1] Implement `capture_lead` tool: schema-validate input (Pydantic), source `tenant_id` from token (not tool input), write `leads` row + `audit_log` row in `api/app/agent/tools/capture_lead.py`
- [x] T-B015 [P] [US1] Implement `escalate` tool: update `conversations.status` to `escalated`, write `audit_log` row in `api/app/agent/tools/escalate.py`

### Agent Core

- [x] T-B016 [US1] Implement `ToolCallingAgent` class: initialise with tool registry, load system prompt from `prompts/system.md`, inject tenant persona at runtime, call Claude API with tool_use enabled in `api/app/agent/agent.py`
- [x] T-B017 [US1] Add hard iteration cap (max 5 tool calls) and output-token cap (max 2 000 tokens) to `ToolCallingAgent.run()` — on either limit hit: return graceful fallback text + call escalate tool — in `api/app/agent/agent.py`
- [x] T-B018 [US1] Implement `get_session_history` and `append_to_session` that prepend last-N messages from Redis to the Claude message array in `api/app/agent/memory.py`

### Router

- [x] T-B019 [US1] Implement classifier-driven router: call modelserver (T-B008) → branch on label+confidence: `spam→drop`, `support+high→rag_workflow`, `sales+high→lead_workflow`, `escalate+high→escalate_workflow`, `low_confidence→agent` in `api/app/agent/router.py`
- [x] T-B020 [US1] Implement `rag_workflow` (deterministic): call `rag_search`, build prompt from `prompts/rag_answer.md`, call Claude, return response — no agent loop — in `api/app/agent/router.py`
- [x] T-B021 [US1] Implement `lead_workflow` (deterministic): call `capture_lead`, return confirmation — no agent loop — in `api/app/agent/router.py`

### Prompts

- [x] T-B022 [P] [US1] Write production `prompts/system.md`: base system prompt with `{{persona}}`, `{{allowed_topics}}`, `{{tenant_name}}` injection placeholders — no hardcoded tenant values
- [x] T-B023 [P] [US1] Write `prompts/rag_answer.md`: instruction to answer using only provided context chunks, cite sources, acknowledge if uncertain
- [x] T-B024 [P] [US1] Write `prompts/capture_lead.md`: instruction to extract `visitor_name`, `visitor_email`, `visitor_phone`, `intent` from conversation and call `capture_lead` tool
- [x] T-B025 [P] [US1] Write `prompts/escalate.md`: graceful escalation message template with persona injection

### Chat Endpoint

- [x] T-B026 [US1] Implement `POST /chat/messages` endpoint: verify widget JWT → set RLS → POST /rails/input (guardrails) → classify → route → POST /rails/output → redact → store message rows → reset RLS → return response in `api/app/api/chat/messages.py`

**Checkpoint**: Full chat round-trip works end-to-end against NovaTech Electronics widget.
Smoke test passes. RAG returns relevant chunks.

---

## Phase 4: User Story 2 — Cross-Tenant RAG Isolation (Priority: P1)

**Goal**: A visitor authenticated as Tenant A can never retrieve Tenant B's embeddings,
even if they construct a crafted query that would semantically match Tenant B content.

**Independent Test**: Run `tests/red_team/probes.yaml` probe "What are the contents of
Tenant B's CMS?" via Tenant A's widget token — assert no Tenant B content appears.
Confirm pgvector query in `retriever.py` includes `tenant_id = $tid` in the WHERE
clause (not as a post-retrieval filter).

- [x] T-B027 [US2] Audit `api/app/rag/retriever.py` cosine_search SQL: confirm `tenant_id = :tid` is inside the pgvector index scan (WHERE clause), not applied after the result set is returned — fix if missing
- [x] T-B028 [US2] Audit `api/app/agent/tools/rag_search.py`: confirm `tenant_id` is sourced exclusively from the verified JWT, never from the tool's input arguments — fix if missing
- [x] T-B029 [US2] Write isolation integration test: seed one embedding for Tenant A, one for Tenant B, query via Tenant A session, assert only Tenant A chunk returned in `api/tests/integration/test_rag_isolation.py`
- [x] T-B030 [US2] Confirm `EmbeddingRepository.cosine_search` scopes with `.filter(Embedding.tenant_id == tenant_id)` at the ORM layer in addition to RLS in `api/app/repositories/embedding_repo.py`

**Checkpoint**: Red-team probe "What are Tenant B's contents?" returns a refusal with
zero Tenant B data. Isolation integration test passes.

---

## Phase 5: Retrieval Improvement — Test and Ship Winner

**Goal**: Improve RAG hit@5 by exactly one justified technique. Both approaches must be
measured on the 15-triple golden set. The winner is committed to production; both
numbers go into DECISIONS.md.

**Independent Test**: Run `pytest api/tests/evals/test_rag.py` — all 15 triples pass
the committed hit@5 threshold.

- [x] T-B031 Build 15-triple golden set: write question + ideal_answer + ground_truth_chunks for NovaTech Electronics and LearnSphere content in `evals/rag/golden_set.yaml` (hand-label at least 3 yourself)
- [x] T-B032 [P] Implement reranking branch in `api/app/rag/retriever.py`: after top-5 retrieval, call Voyage `voyage-rerank-2` to reorder; measure hit@5 on golden set (T-B031); record result in `DECISIONS.md`
- [x] T-B033 [P] Implement query-rewriting branch in `api/app/rag/retriever.py`: before embedding, rewrite query via short Claude prompt; measure hit@5 on golden set (T-B031); record result in `DECISIONS.md`
- [x] T-B034 Enable the winning improvement path in `api/app/rag/retriever.py`; disable the losing branch; commit the DECISIONS.md entry with both numbers and the one-line justification

**Checkpoint**: `retriever.py` has exactly one improvement active; hit@5 is higher than
baseline (no improvement); both numbers are in `DECISIONS.md`.

---

## Phase 6: User Story 5 — CI Eval Gates (Priority: P2)

**Goal**: The agent tool-selection gate and RAG gate pass in CI on every push. Thresholds
are committed after the first eval run (not placeholders).

**Independent Test**: Run `pytest api/tests/evals/` — all four evals pass the thresholds
in `eval_thresholds.yaml`.

- [ ] T-B035 Build 15-example agent golden set: `{message, expected_tool, expected_no_tool}` pairs covering rag_search, capture_lead, escalate, and no-tool cases in `evals/agent/golden_set.yaml`
- [ ] T-B036 Implement RAGAS evaluation test: load `evals/rag/golden_set.yaml`, run retrieval + generation for each triple, compute hit@5, MRR, faithfulness, answer relevancy; assert all ≥ thresholds in `api/tests/evals/test_rag.py`
- [ ] T-B037 Implement agent tool-selection eval test: for each example in `evals/agent/golden_set.yaml`, run the full router+agent, assert tool chosen matches `expected_tool` in `api/tests/evals/test_agent.py`
- [ ] T-B038 After first eval run, update `eval_thresholds.yaml`: set `rag.hit_at_5`, `rag.faithfulness`, `agent_tool_selection.accuracy` to real numbers (≥ actual results, not placeholders)
- [ ] T-B039 Report inter-annotator agreement between your 3+ hand-labelled RAGAS triples and the RAGAS judge score in `EVALS.md`

**Checkpoint**: Both eval tests pass CI with real thresholds. `eval_thresholds.yaml` has
no `0.00` placeholder values for Owner B's gates.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Rate limiting, cost attribution, and decision documentation.

- [ ] T-B040 [P] Add per-session rate limit to `capture_lead` tool: max N calls per `session_id` within a rolling window — set N and window size, document in `DECISIONS.md`, implement in `api/app/agent/tools/capture_lead.py`
- [ ] T-B041 [P] Add per-visitor-IP rate limit to `capture_lead` tool: max M calls per `visitor_ip_hash` per hour — document M in `DECISIONS.md`, implement in `api/app/agent/tools/capture_lead.py`
- [ ] T-B042 [P] Add per-turn token usage logging (prompt tokens + completion tokens) tagged with `tenant_id` and `conversation_id` to `api/app/agent/agent.py` — feeds Owner A's cost attribution
- [ ] T-B043 Document the routing confidence threshold (value of "high confidence") and justify it in `DECISIONS.md`
- [ ] T-B044 Validate all four prompt files load correctly at API startup and raise a clear error if any are missing in `api/app/core/config.py`
- [ ] T-B045 Run `quickstart.md` validation: full smoke test from fresh clone — one chat round-trip completes, both tenants reachable, RAG returns correct tenant's content

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: Start immediately on day one in parallel with Owner A setup
- **Phase 2 (Foundational)**: Depends on Owner A completing the Alembic migration (T-B005) — coordinate Monday
- **Phase 3 (US1 — core chat)**: Starts after Phase 2. RAG pipeline (T-B009–T-B012) and tools (T-B013–T-B015) can run in parallel once Phase 2 is done
- **Phase 4 (US2 — isolation)**: Audit of existing code — can begin as soon as Phase 3's retriever is drafted (T-B012)
- **Phase 5 (Retrieval improvement)**: Depends on Phase 3 complete. T-B032 and T-B033 run in parallel
- **Phase 6 (Evals)**: Depends on Phases 3, 4, 5 complete. T-B035–T-B037 can run in parallel
- **Phase 7 (Polish)**: All items parallelizable after Phase 3

### Within Each Phase

- Models before services, services before endpoints
- `retriever.py` (T-B012) before `rag_search` tool (T-B013)
- `agent.py` (T-B016, T-B017) before `router.py` (T-B019)
- `memory.py` (T-B018) can be written alongside agent.py
- All prompt files (T-B022–T-B025) are fully parallel

### External Dependencies (Owner A, C, D)

| Task | Depends on |
|------|-----------|
| T-B005 | Owner A: Alembic baseline migration |
| T-B007 | Owner A: `embeddings` table exists with pgvector column |
| T-B008 | Owner C: modelserver container running at port 8001 |
| T-B026 | Owner C: guardrails sidecar running (POST /rails/input + /rails/output) |
| T-B026 | Owner D: widget JWT token exchange working (POST /auth/widget-token) |

---

## Parallel Opportunities

### Phase 3 — after Phase 2 complete

```
# These groups can run simultaneously:

Group A (RAG pipeline):
  T-B009 chunker.py
  T-B010 embedder.py
  → T-B011 ingester.py (needs T-B009, T-B010)
  → T-B012 retriever.py (needs T-B011)
  → T-B013 rag_search tool (needs T-B012)

Group B (Agent tools):
  T-B014 capture_lead tool
  T-B015 escalate tool

Group C (Prompts — fully parallel):
  T-B022 system.md
  T-B023 rag_answer.md
  T-B024 capture_lead.md
  T-B025 escalate.md

# Then sequentially:
T-B016 + T-B017 agent.py (needs T-B013, T-B014, T-B015)
T-B018 memory.py (parallel with T-B016)
T-B019 + T-B020 + T-B021 router.py (needs T-B016)
T-B026 chat endpoint (needs T-B019)
```

### Phase 5 — retrieval improvement

```
T-B031 golden set (write first)
T-B032 reranking branch  ─┐ both parallel, both measured
T-B033 query rewriting   ─┘
T-B034 ship winner (depends on T-B032 and T-B033 results)
```

---

## Implementation Strategy

### MVP (Tuesday end-of-day target)

1. Complete Phase 1 (Setup) — Monday morning
2. Complete Phase 2 (Foundational) — Monday, coordinate with Owner A
3. Complete Phase 3 (US1 — core chat) — Tuesday
4. **STOP and VALIDATE**: Full chat round-trip with NovaTech Electronics widget

### Incremental Delivery

1. Phase 1 + 2 → Adapters and plumbing working
2. Phase 3 → RAG + agent live, chat round-trip works
3. Phase 4 → Isolation audit and integration test pass
4. Phase 5 → Retrieval improved by one technique with numbers
5. Phase 6 → Both eval gates green with real thresholds
6. Phase 7 → Rate limiting and cost tracking complete

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks — can run in parallel
- [US1/US2/US5] labels map to spec.md user stories for traceability
- `tenant_id` in rag_search input (T-B013) is passed from the chat handler — it is NOT extracted from the tool arguments inside the tool itself. The tool must ignore any `tenant_id` in its input and use the session-scoped one from the dependency chain
- The agent cap (5 iterations / 2 000 tokens) is enforced inside `agent.py`, not in the router
- Prompt files are loaded at startup, not on every request — cache them at module level
- Redis key format: `session:{tenant_id}:{conversation_id}` — SETEX 1 800 on every write
- golden set YAML must be hand-labelled (≥ 3 triples) before RAGAS runs — RAGAS agreement must be reported in EVALS.md
