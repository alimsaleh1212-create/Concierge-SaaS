---
description: "Task list — Owner C: Classifier, Guardrails & Security"
---

# Tasks: Concierge — Owner C (Classifier, Guardrails & Security)

**Input**: Design documents from `specs/001-concierge-system-spec/`
**Owner**: Owner C — covers FR-024–FR-035, modelserver, guardrails sidecar, Presidio, tracing
**Prerequisites**: Shared tasks (tasks-shared.md) fully merged to main. Owner A Phase 2
(database.py + security.py) needed before wiring guardrails client into chat flow.

**Tests**: Not requested as TDD — no separate test-first tasks.
**Labels**: All tasks tagged [Owner C]. Run `/speckit-implement` and filter to [Owner C].

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Parallelizable — different files, no incomplete dependencies
- **[Story]**: User story label (US1, US2, US5) from spec.md
- Paths assume the repo root structure defined in `plan.md`

---

## Phase 1: Setup (Owner C)

**Purpose**: Resolve the Monday dataset decision, scaffold training notebooks, and create
all stub files Owner C owns from day one.

- [ ] T-C001 Choose classifier dataset — must be a public labeled text-classification set (sales/support/spam intent or close equivalent); record exact dataset name and file SHA-256 in `model_card.md`; announce in team chat (resolves T-S009)
- [ ] T-C002 [P] Create `notebooks/train_classical.ipynb`: offline notebook for TF-IDF + logistic regression training; exports `model.joblib`; records macro-F1 on held-out test set
- [ ] T-C003 [P] Create `notebooks/train_dl.ipynb`: offline notebook for small DL model training (Colab-compatible, with torch); exports ONNX artifact; NO torch imports in any container image
- [ ] T-C004 [P] Create `evals/classifier/test_set.csv` with columns `text,label` using a representative sample from the chosen dataset (at least 50 rows covering sales/support/spam)
- [ ] T-C005 [P] Create `modelserver/requirements.txt` with ONLY: `fastapi`, `uvicorn`, `onnxruntime`, `scikit-learn`, `numpy`, `pyjwt`, `httpx` — NO torch, NO transformers
- [ ] T-C006 [P] Create `guardrails/requirements.txt` with: `fastapi`, `uvicorn`, `nemo-guardrails`, `presidio-analyzer`, `presidio-anonymizer`, `pyjwt`, `httpx`

**Checkpoint**: Dataset chosen and announced. Notebook stubs committed. requirements.txt files confirm no torch dependency.

---

## Phase 2: Foundational (Modelserver Build)

**Purpose**: Build and verify the modelserver end-to-end before it is needed by Owner B.

**⚠️ IMPORTANT**: Owner B depends on `POST /classify` being reachable. Announce when
the modelserver container passes its healthcheck.

- [ ] T-C007 Train the TF-IDF + logistic regression model using `notebooks/train_classical.ipynb`; export as `model.joblib` to `modelserver/artifacts/`; record macro-F1 in `model_card.md`
- [ ] T-C008 Train the small DL model using `notebooks/train_dl.ipynb` (Colab); export ONNX artifact to `modelserver/artifacts/`; record macro-F1 in `model_card.md`
- [ ] T-C009 Run LLM zero-shot baseline (Claude, zero-shot classification prompt) on `evals/classifier/test_set.csv`; record macro-F1 in `model_card.md` — no artifact exported
- [ ] T-C010 Choose the best artifact (classical or ONNX) based on macro-F1 ≥ 0.70 and container size; record choice + both F1 scores + rationale in `model_card.md` Deployment Choice section
- [ ] T-C011 Compute SHA-256 of chosen artifact: `sha256sum modelserver/artifacts/<file>`; record in `model_card.md` Artifact SHA-256 section
- [ ] T-C012 Create `modelserver/app/startup.py`: read expected SHA-256 from `model_card.md` at the configured path; compute actual SHA-256 of artifact file; call `sys.exit(1)` with clear message if they do not match
- [ ] T-C013 Create `modelserver/app/classifier.py`: load the chosen artifact (ONNX via `onnxruntime.InferenceSession` OR sklearn joblib); expose `predict(text: str) -> tuple[str, float]` returning (label, confidence); no torch import anywhere
- [ ] T-C014 Create `modelserver/app/main.py`: FastAPI app with `POST /classify` (validate service JWT from Vault, call `classifier.predict`, return `{"label":str,"confidence":float}`) and `GET /health` (returns model type + artifact SHA-256); call `startup.py` verify on app lifespan start
- [ ] T-C015 Create `modelserver/Dockerfile`: multi-stage build; base `python:3.12-slim`; copy only `app/`, `requirements.txt`, `artifacts/`; verify no torch in final layer; target < 500 MB total image

**Checkpoint**: `docker compose up modelserver` → `GET /health` returns `{"status":"ok","model":"classical|onnx"}`. `POST /classify` with service token returns `{label,confidence}`. Announce in team chat.

---

## Phase 3: Guardrails Sidecar (User Story 1 + 2)

**Goal**: NeMo Guardrails sidecar is running and correctly refuses prompt injection,
cross-tenant attempts, and jailbreak — while passing normal messages.

**Independent Test**: `POST /rails/input` with "Ignore previous instructions" → `{"allowed":false,"reason":"prompt_injection_detected"}`. `POST /rails/input` with "What are your hours?" → `{"allowed":true}`.

- [ ] T-C016 [P] [US1] Create `guardrails/config/config.yml`: NeMo Guardrails base config specifying the platform colang file; set model to `gpt-4` or Claude API compatible backend
- [ ] T-C017 [US1] Create `guardrails/app/rails/platform_rails.co`: NeMo colang definitions for the four immutable platform rails — prompt injection detection, jailbreak detection, cross-tenant data extraction refusal, system prompt extraction refusal; these MUST NOT be overridable by any tenant config
- [ ] T-C018 [P] [US1] Create `guardrails/app/rails/tenant_rails.py`: `build_tenant_rails(allowed_topics, blocked_topics, refusal_tone) -> str` — returns a colang snippet injected at request time from the `tenant_rails` field in the sidecar request body
- [ ] T-C019 [US1] Create `guardrails/app/main.py`: FastAPI app with `POST /rails/input` and `POST /rails/output` (exact contract from `contracts/guardrails.md`); validate service JWT from Vault; run platform rails first (always), then tenant rails; return `{"allowed":bool,"modified_content":null|str,"reason":null|str,"refusal_message":null|str}`; add `GET /health`
- [ ] T-C020 Create `guardrails/Dockerfile`: base `python:3.12-slim`; copy `app/`, `config/`, `requirements.txt`; verify no torch; target < 500 MB

**Checkpoint**: Both guardrails sidecar endpoints pass their contracts. `POST /rails/input` with a prompt injection attempt returns `allowed: false`. `POST /rails/input` with a normal question returns `allowed: true`.

---

## Phase 4: PII Redaction & Guardrails Client (User Story 1 + 2)

**Goal**: Presidio redacts PII from all messages before logs/traces/Redis/LLM.
The API's guardrails_client wires the sidecar into the chat flow.

**Independent Test**: Pass a string containing a synthetic API key to `redact(text)` →
assert the key is replaced with `<API_KEY>`. Pass `admin@example.com` → assert
`<EMAIL_ADDRESS>` in output.

- [ ] T-C021 [P] [US1] Create `api/app/redaction.py`: Presidio `AnalyzerEngine` + `AnonymizerEngine` wrapper; `redact(text: str) -> RedactionResult` that replaces these entity types: `EMAIL_ADDRESS`, `PHONE_NUMBER`, `CREDIT_CARD`, `CRYPTO`, `API_KEY`, `US_SSN`, `IP_ADDRESS`, `PASSWORD`; `is_redacted: bool` flag on result
- [ ] T-C022 [P] [US1] Create `api/app/guardrails_client.py`: async HTTP client for the guardrails sidecar; `check_input(tenant_id, conversation_id, content, tenant_rails) -> GuardrailsResult`; `check_output(tenant_id, conversation_id, content, tenant_rails) -> GuardrailsResult`; use `GUARDRAILS_SERVICE_TOKEN` from config; retry on 503

**Checkpoint**: `redact("My email is foo@bar.com and my key is sk-abc123")` returns both entities anonymized. Guardrails client integration test passes against running sidecar container.

---

## Phase 5: User Story 2 — Red-Team Probe Suite (Priority: P1)

**Goal**: All adversarial probes are refused. This is the primary graded isolation artifact.

**Independent Test**: `pytest api/tests/red_team/ -v` — all probes return refusals.

- [ ] T-C023 [US2] Create `api/tests/red_team/probes.yaml` with at least 6 adversarial probes covering: (1) prompt injection via chat, (2) cross-tenant data extraction attempt, (3) system prompt extraction, (4) jailbreak ("DAN" style), (5) Tenant A token + Tenant B data in body, (6) stale/forged JWT — each probe has `input`, `expected_refused: true`, `probe_type`
- [ ] T-C024 [US2] Create `api/tests/red_team/test_probes.py`: load `probes.yaml`, for each probe send to `POST /chat/messages` against the running stack, assert HTTP response is either 401/403 OR response body contains the guardrails refusal message and zero Tenant B data appears in the response

**Checkpoint**: All 6 probes refused. Red-team pass_rate = 1.00 (matches `eval_thresholds.yaml`).

---

## Phase 6: User Story 5 — Classifier CI Gate (Priority: P2)

**Goal**: CI classifier gate passes with macro-F1 ≥ 0.70 on every push.

**Independent Test**: `pytest api/tests/evals/test_classifier.py -v` passes with real
macro-F1 ≥ 0.70 reported.

- [ ] T-C025 [US5] Create `api/tests/evals/test_classifier.py`: load `evals/classifier/test_set.csv`; for each row call `POST /classify` on the running modelserver; compute macro-F1 across all predictions; assert macro-F1 ≥ `eval_thresholds.yaml` `classifier.macro_f1` value (0.70)
- [ ] T-C026 [US5] Create `api/tests/evals/test_redaction.py`: paste a synthetic API key (`sk-test-1234567890abcdef`) into chat via `POST /chat/messages`; assert the key string never appears in: the HTTP response body, any `messages` row in the DB, any Redis session key — CI redaction pass_rate must be 1.00

**Checkpoint**: Both eval tests pass. Classifier macro-F1 ≥ 0.70 confirmed in CI output.

---

## Phase 7: Tracing & Polish

**Purpose**: OpenTelemetry tracing wired into the API container; all traces tagged with
`tenant_id` and PII-redacted.

- [ ] T-C027 Confirm tracing backend choice (Jaeger vs Tempo) and record in DECISIONS.md D-007 (resolves T-S010); update `docker-compose.yml` to add the chosen tracing service
- [ ] T-C028 [P] Create `api/app/core/tracing.py`: OpenTelemetry SDK setup pointing at chosen backend; `instrument_app(app: FastAPI)` function; add middleware that injects `tenant_id` as a span attribute on every request; ensure no raw PII appears in span attributes (run Presidio redaction on any user-supplied string before it enters a span)
- [ ] T-C029 [P] Update `modelserver/app/main.py` to emit OpenTelemetry traces for every `POST /classify` call tagged with `model_type` and `label`
- [ ] T-C030 [P] Update `guardrails/app/main.py` to emit OpenTelemetry traces for every rails check tagged with `allowed` and `reason`
- [ ] T-C031 Run full smoke test: `docker compose up --build`; send a chat message; verify traces appear in the chosen tracing backend UI for all three services

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: Start immediately on day one — dataset decision is Monday morning
- **Phase 2 (Modelserver)**: Starts after Phase 1 (needs dataset + notebooks); T-C007–T-C009 parallel; T-C010–T-C015 sequential
- **Phase 3 (Guardrails)**: Starts in parallel with Phase 2 — no dependency between them; T-C016–T-C018 parallel; T-C019 needs T-C016–T-C018
- **Phase 4 (Redaction + Client)**: T-C021 and T-C022 fully parallel, can start after Phase 1
- **Phase 5 (Red-team)**: Needs full stack running (Owner A Phase 2 + Owner B Phase 3 + Phase 3 here)
- **Phase 6 (Evals)**: Needs Phase 2 and Phase 3 complete
- **Phase 7 (Tracing)**: Fully parallel after Phase 1

### External Dependencies (Owners A, B, D)

| This task | Depends on |
|-----------|------------|
| T-C022 (guardrails_client.py) | Owner A: `api/app/core/config.py` (for service token) |
| T-C024 (red-team test) | Owner A Phase 2 (DB + RLS) + Owner B Phase 3 (chat endpoint) |
| T-C026 (redaction eval) | Owner B T-B026 (chat endpoint) |

### Owner C Blocks

| Owner C output | Blocks |
|----------------|--------|
| T-C014 (modelserver running) | Owner B T-B008 (modelserver client) |
| T-C019 (guardrails running) | Owner B T-B026 (chat endpoint rails calls) |
| T-C021 (redaction.py) | Owner B T-B026 (chat endpoint PII redaction) |
| T-C022 (guardrails_client.py) | Owner B T-B026 (guardrails integration) |

---

## Parallel Opportunities

### Phase 2 — after Phase 1 complete

```
# Parallel training (do in Colab/locally — not in containers):
T-C007 classical training  ─┐
T-C008 DL/ONNX training    ─┤ all parallel
T-C009 LLM zero-shot       ─┘

# Then sequentially:
T-C010 choose winner
T-C011 compute SHA-256
T-C012 startup.py
T-C013 classifier.py (needs T-C010)
T-C014 main.py (needs T-C012, T-C013)
T-C015 Dockerfile
```

### Phase 3 — fully internal parallel

```
T-C016 config.yml           ─┐
T-C017 platform_rails.co    ─┤ parallel
T-C018 tenant_rails.py      ─┘
→ T-C019 main.py (needs all three)
→ T-C020 Dockerfile
```

---

## Implementation Strategy

### MVP (Wednesday end-of-day target)

1. Phase 1 → Dataset chosen, notebooks scaffolded — Monday morning
2. Phase 2 → Modelserver running with real artifact — Monday/Tuesday
3. Phase 3 → Guardrails sidecar running — Tuesday
4. Phase 4 → `redaction.py` + `guardrails_client.py` done — Tuesday
5. **STOP and VALIDATE**: Owner B can now wire guardrails + redaction into chat flow

### Incremental Delivery

1. Phase 1 + 2 → Modelserver container done; Owner B unblocked
2. Phase 3 + 4 → Guardrails + redaction done; Owner B's chat endpoint complete
3. Phase 5 → Red-team probes written + passing
4. Phase 6 → Classifier + redaction CI gates green
5. Phase 7 → Tracing wired across all services

---

## Notes

- The SHA-256 boot check (T-C012) is a hard constraint — the modelserver MUST exit 1 if
  the artifact SHA-256 doesn't match `model_card.md`. Test this by deliberately corrupting
  the artifact and verifying the container exits.
- torch and transformers MUST NOT appear in any container's final image layer. Use
  `docker run --rm <image> pip freeze | grep torch` to verify.
- Three model results (classical F1, DL/ONNX F1, LLM zero-shot F1) must ALL be committed
  in `model_card.md` — the graders check all three.
- Platform rails in `platform_rails.co` are immutable — no tenant configuration may
  override them. Tenant rails are injected at request time from the `tenant_rails` field.
- Presidio `API_KEY` entity detection requires the English NLP pipeline; add
  `python -m spacy download en_core_web_lg` to the guardrails/api Dockerfile.
- PII redaction (T-C021) must run BEFORE: writing to `messages` table, writing to Redis
  session, writing to any log or trace. The `is_redacted` flag on `messages` tracks
  whether Presidio modified the content.
