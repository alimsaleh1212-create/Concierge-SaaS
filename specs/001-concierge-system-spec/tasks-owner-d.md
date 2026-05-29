---
description: "Task list — Owner D: Widget, Admin UI & CI/CD"
---

# Tasks: Concierge — Owner D (Widget, Admin UI & CI/CD)

**Input**: Design documents from `specs/001-concierge-system-spec/`
**Owner**: Owner D — covers FR-036–FR-045, widget bundle, admin UI, auth route, CI pipeline
**Prerequisites**: Shared tasks (tasks-shared.md) fully merged to main. Owner A Phase 2
(security.py, widgets table) must be complete before the auth route can be implemented.

**Tests**: Not requested as TDD — no separate test-first tasks.
**Labels**: All tasks tagged [Owner D]. Run `/speckit-implement` and filter to [Owner D].

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Parallelizable — different files, no incomplete dependencies
- **[Story]**: User story label (US1, US3, US5) from spec.md
- Paths assume the repo root structure defined in `plan.md`

---

## Phase 1: Setup (Owner D)

**Purpose**: Resolve the Monday tracing decision, scaffold the widget project, and create
all stub files Owner D owns from day one.

- [ ] T-D001 Choose tracing backend (OpenTelemetry → Jaeger vs OpenTelemetry → Tempo); record in DECISIONS.md D-007 with one-line rationale; update docker-compose.yml to add the chosen tracing service; announce in team chat (resolves T-S010)
- [X] T-D002 [P] Initialise `widget/` as a Vite + React + TypeScript project: `npm create vite@latest widget -- --template react-ts`; install no external UI libraries (bundle must be < 50 KB gzipped); add `widget/package.json`, `widget/vite.config.ts` with correct output path
- [X] T-D003 [P] Create `admin/requirements.txt` with: `streamlit>=1.35`, `requests`, `pyjwt`, `python-dotenv`
- [X] T-D004 [P] Create `admin/app.py`: Streamlit entry point; reads API base URL from env; handles login state via session; shows navigation to 5 pages; requires `tenant_admin` or `tenant_manager` role from JWT

**Checkpoint**: `npm run build` in `widget/` produces a dist/ folder. `streamlit run admin/app.py` starts without import errors. Tracing decision recorded in DECISIONS.md.

---

## Phase 2: Foundational (Auth Route & Widget Loader)

**Purpose**: The auth route and widget loader are the gateway for every visitor chat session.
Owner B's chat endpoint depends on a valid widget JWT; this phase produces that JWT.

**⚠️ IMPORTANT**: Owner B T-B026 (chat endpoint) depends on the widget JWT working.
Announce when `POST /auth/widget-token` is live.

- [X] T-D005 Create `api/app/api/auth/widget_token.py`: `POST /auth/widget-token` — accepts `{widget_id: uuid, origin: str}`; validates widget exists + `is_active=true` (→ 404); checks origin in `widgets.allowed_origins` OR `tenants.allowed_origins` using server-side check independent of CORS header (→ 403 on mismatch); signs JWT with `widgets.widget_token_secret` (1 hr expiry, claims: `tenant_id`, `widget_id`, `origin`); returns `{token, expires_in: 3600}`; also wires `POST /auth/login` via fastapi-users standard endpoint
- [X] T-D006 Create `widget/loader/widget.js` (vanilla JS, < 5 KB): reads `data-widget-id` from own `<script>` tag; reads `window.location.origin`; calls `POST /auth/widget-token`; on 403 logs to console and stops; on success creates `<iframe>` pointing at MinIO-hosted bundle URL with fixed position/z-index styles; after iframe `load` event sends `postMessage({type:"CONCIERGE_INIT", token, widget_id})` to the iframe
- [X] T-D007 [P] Create `widget/src/api.ts`: `sendMessage(token, conversation_id, content, session_id) -> ChatResponse` — `POST /chat/messages` with `Authorization: Bearer <token>`; token stored in React state (never localStorage); typed with the response shape from `contracts/api.md`
- [X] T-D008 Create `widget/src/main.tsx`: listen for `postMessage` with `type=CONCIERGE_INIT`; validate origin before accepting; store token in React state; render `<ChatWidget />`

**Checkpoint**: `POST /auth/widget-token` with a valid widget_id + allowed origin returns a signed JWT. With an invalid origin returns HTTP 403. With a missing token returns HTTP 401. Announce in team chat.

---

## Phase 3: User Story 1 — Widget Chat UI (Priority: P1)

**Goal**: Visitor sees the chat widget, types a message, and receives a response. The entire
bundle fits in < 50 KB gzipped.

**Independent Test**: Embed `widget.js` on a local HTML page at `localhost:3000` (an
allowed origin); type "What are your hours?" — a response appears; bundle gzipped size
< 50 KB (`du -sh dist/*.js` after `vite build`).

- [X] T-D009 [P] [US1] Create `widget/src/ChatWidget.tsx`: React functional component; manages message list state; displays conversation in a scrollable container; controlled input field with submit button; calls `sendMessage` from `api.ts` on submit; shows typing indicator while awaiting response
- [X] T-D010 [P] [US1] Style `ChatWidget.tsx` inline (no CSS framework — bundle budget): minimal chat bubble layout; `position: fixed; bottom: 24px; right: 24px`; z-index 9999; max 360px width; respects tenant `greeting` from widget config (passed via `CONCIERGE_INIT` postMessage if available)
- [X] T-D011 [US1] Add `vite.config.ts` build config: output to `dist/`, terser minification, no vendor chunk splitting; add `vite-plugin-compression` for gzip; CI fails if `dist/index.js.gz` > 51200 bytes (50 KB)
- [X] T-D012 [US1] Create MinIO upload script `widget/scripts/upload-bundle.sh`: uploads `dist/index.js` to MinIO bucket `concierge-widget` with `Cache-Control: public,max-age=31536000`; run as part of `docker compose up` widget service init

**Checkpoint**: Full embed test from `quickstart.md` widget section — token exchange succeeds, widget renders, chat message sent and response received. `dist/index.js.gz` < 50 KB.

---

## Phase 4: User Story 3 — Streamlit Admin UI (Priority: P2)

**Goal**: Tenant admin uses the Streamlit UI to manage CMS, widget config, guardrail topics,
leads, and copy the embed snippet.

**Independent Test**: Log in as Mario's Pizza tenant_admin; create a CMS page; see it
in the CMS list; open Widgets page and update the greeting; copy the embed snippet.

- [X] T-D013 [P] [US3] Create `admin/pages/1_CMS.py`: Streamlit page listing CMS items (`GET /admin/cms`); form to create new item (`POST /admin/cms`); edit button opens inline form (`PATCH /admin/cms/{id}`); delete button with confirmation (`DELETE /admin/cms/{id}`); requires tenant_admin JWT from session
- [X] T-D014 [P] [US3] Create `admin/pages/2_Widgets.py`: Streamlit page listing widgets (`GET /admin/widgets`); form to create widget (`POST /admin/widgets`); edit form for greeting, allowed_origins, theme_config JSONB (`PATCH /admin/widgets/{id}`)
- [X] T-D015 [P] [US3] Create `admin/pages/3_Guardrails.py`: Streamlit page to configure per-tenant guardrail topics (`PATCH /admin/widgets/{id}` targeting `theme_config.tenant_rails`); shows allowed_topics list, blocked_topics list, refusal_tone selector; changes stored in `widgets.theme_config`
- [X] T-D016 [P] [US3] Create `admin/pages/4_Leads.py`: Streamlit page listing leads (`GET /admin/leads?status=...`); status filter; update status button (`PATCH /admin/leads/{id}`)
- [X] T-D017 [P] [US3] Create `admin/pages/5_Snippet.py`: Streamlit page showing the embed HTML snippet for the selected widget (`GET /admin/widgets/{id}/snippet`); one-click copy to clipboard; preview iframe
- [X] T-D018 Create `admin/Dockerfile`: base `python:3.12-slim`; copy `pages/`, `app.py`, `requirements.txt`; expose port 8501; CMD `streamlit run app.py --server.port 8501 --server.address 0.0.0.0`

**Checkpoint**: Full admin workflow works via Streamlit UI. CMS create → chat returns
updated content. Leads list shows captured leads. Embed snippet copies correctly.

---

## Phase 5: User Story 5 — CI Pipeline (Priority: P2)

**Goal**: GitHub Actions CI runs on every push, all gates pass, any regression blocks merge.

**Independent Test**: Introduce a deliberate threshold regression in `eval_thresholds.yaml`
(lower `classifier.macro_f1` to 0.50) — CI fails. Revert — CI passes.

- [X] T-D019 [US5] Implement `.github/workflows/ci.yml` (replacing the stub): stages — (1) lint + typecheck: `ruff check api/` + `mypy api/` + `npm run typecheck` in widget/; (2) build images: `docker compose build` — fail if any image > 500 MB; (3) eval gates (parallel): `pytest api/tests/evals/test_classifier.py`, `pytest api/tests/evals/test_rag.py`, `pytest api/tests/evals/test_agent.py`, `pytest api/tests/red_team/test_probes.py`, `pytest api/tests/evals/test_redaction.py`, smoke test; all gates read thresholds from `eval_thresholds.yaml`
- [X] T-D020 [P] [US5] Create `.github/workflows/smoke.yml`: standalone smoke-test job — `docker compose up -d --build`, wait for healthchecks, run widget token exchange + one full chat round-trip via curl, `docker compose down`; used as the `smoke_test` gate
- [ ] T-D021 [P] [US5] Add CI image-size check to `.github/workflows/ci.yml`: after `docker compose build`, for each service image run `docker image inspect <name> --format '{{.Size}}'` and fail if > 524288000 bytes (500 MB)
- [ ] T-D022 [US5] Add widget bundle size check to CI: after `npm run build`, check `du -b dist/index.js.gz` and fail if > 51200 bytes; add as a step in the lint stage before build

**Checkpoint**: `git push` triggers CI. All stages pass on a clean branch. Deliberate regression test: lower threshold → CI blocks PR. Revert → CI passes.

---

## Phase 6: User Story 2 — Auth Isolation Tests (Priority: P1)

**Goal**: Verify the widget token auth boundary holds — stale token, invalid origin, and
missing token all get the correct HTTP response.

**Independent Test**: Three curl commands per `contracts/api.md` error cases — each must
return the documented status code.

- [ ] T-D023 [US2] Write token boundary integration tests in `api/tests/integration/test_widget_token.py`: (1) valid widget_id + allowed origin → HTTP 200 + JWT; (2) valid widget_id + disallowed origin → HTTP 403; (3) unknown widget_id → HTTP 404; (4) `POST /chat/messages` with stale/expired JWT → HTTP 401; (5) `POST /chat/messages` with missing Authorization header → HTTP 401
- [ ] T-D024 [P] [US2] Verify CORS + CSP headers are set on all chat/admin routes: add a test asserting `Access-Control-Allow-Origin` matches the tenant's allowed origin and `Content-Security-Policy: frame-ancestors` is present — in `api/tests/unit/test_cors_headers.py`

**Checkpoint**: All 5 token boundary tests pass. CORS + CSP headers test passes.

---

## Phase 7: Polish & Evals Golden Sets

**Purpose**: Commit required golden set files and run final full-stack validation.

- [x] T-D025 [P] Verify `evals/agent/golden_set.yaml` exists (Owner B creates it) and `evals/rag/golden_set.yaml` exists (Owner B creates it); if missing, create minimal placeholder files with correct YAML schema so CI golden-set tests do not error on load
- [x] T-D026 [P] Verify `tests/red_team/probes.yaml` exists (Owner C creates it); if missing, create minimal placeholder with one probe so the CI red-team gate does not error on load
- [ ] T-D027 Run complete `quickstart.md` validation: `git clone` to fresh directory → `docker compose up --build` → health checks pass on all 3 services → both demo tenants reachable → widget token exchange works → full chat round-trip completes → `pytest api/tests/evals/ -v` passes → `pytest api/tests/red_team/ -v` passes

**Note**: T-D027 depends on Vault + full Compose stack (secrets seeded, DB migrated, tenants seeded). Defer until Owner A/B/C services and Vault secrets are available.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: Start immediately on day one in parallel with all other owners
- **Phase 2 (Auth + Loader)**: T-D005 needs Owner A's `security.py` + `widgets` table (Owner A Phase 2); T-D006–T-D008 are fully parallel and can start without Owner A
- **Phase 3 (Widget UI)**: T-D009–T-D010 are parallel; T-D011 needs T-D009; T-D012 needs T-D011
- **Phase 4 (Admin UI)**: T-D013–T-D017 fully parallel once Owner A's admin routes are live; T-D018 (Dockerfile) anytime
- **Phase 5 (CI)**: T-D019 can be partially built without other owners; fill gate steps as each owner's evals are ready; T-D020–T-D022 are parallel
- **Phase 6 (Auth tests)**: After T-D005 is live
- **Phase 7 (Polish)**: Final validation requires all other owners' phases complete

### External Dependencies (Owners A, B, C)

| This task | Depends on |
|-----------|------------|
| T-D005 (auth route) | Owner A: `widgets` table + `security.py` |
| T-D019 (CI gates) | Owner B: eval test files exist; Owner C: `test_classifier.py`, `test_redaction.py` |
| T-D023 (token tests) | Owner A: `widgets` seeded |
| T-D027 (smoke test) | All owners' Phase 2+ complete |

### Owner D Blocks

| Owner D output | Blocks |
|----------------|--------|
| T-D005 (widget-token endpoint) | Owner B T-B026 (full chat round-trip) |
| T-D019 (ci.yml gates) | Branch protection meaningful CI checks |

---

## Parallel Opportunities

### Phase 2 — partial parallelism

```
T-D005 auth route          (needs Owner A Phase 2)
T-D006 widget.js loader    ─┐ fully parallel, independent
T-D007 widget/src/api.ts   ─┤ of Owner A
T-D008 widget/src/main.tsx ─┘
```

### Phase 3 — widget components

```
T-D009 ChatWidget.tsx  ─┐
T-D010 styling         ─┤ parallel (same file — one person works sequentially)
T-D011 vite.config.ts  ─┘
→ T-D012 upload script
```

### Phase 4 — all 5 admin pages are fully parallel

```
T-D013 1_CMS.py        ─┐
T-D014 2_Widgets.py    ─┤
T-D015 3_Guardrails.py ─┤ all fully parallel
T-D016 4_Leads.py      ─┤
T-D017 5_Snippet.py    ─┘
T-D018 Dockerfile (anytime)
```

---

## Implementation Strategy

### MVP (Tuesday end-of-day target)

1. Phase 1 → Tracing decided, widget scaffolded — Monday morning
2. Phase 2 → Auth route + widget loader done — Monday afternoon (coordinate with Owner A)
3. Phase 3 → Widget UI renders and sends messages — Tuesday
4. **STOP and VALIDATE**: Full chat round-trip works from an embedded widget page

### Incremental Delivery

1. Phase 1 + 2 → Auth gateway done; Owner B unblocked for chat endpoint
2. Phase 3 → Widget UI working end-to-end
3. Phase 4 → Admin UI complete; tenant admins can self-serve
4. Phase 5 → CI fully wired with all gates
5. Phase 6 → Auth boundary tests pass
6. Phase 7 → Full smoke test from fresh clone passes

---

## Notes

- The token MUST be stored in React state — never in `localStorage` or a cookie. XSS
  would expose localStorage; React state is wiped on iframe unload.
- The loader script (`widget.js`) is served with `Cache-Control: no-cache` from the API
  static mount — changes propagate immediately. The widget bundle itself is served from
  MinIO with long-lived cache headers (content-addressed by bundle hash).
- The server-side origin check in T-D005 is the actual auth boundary. CORS and CSP
  are defence-in-depth only — a `curl` with a valid token but wrong origin header still
  gets HTTP 403 from the server check.
- CI gates run eval scripts against a running Docker Compose stack — the smoke test
  workflow (T-D020) is the integration harness. Local `pytest` without the stack will
  skip tests that need live services.
- Widget bundle size gate (T-D022) fails the build at 51 200 bytes, not 50 000 — this
  gives a small buffer for build tooling metadata while keeping the gzip budget honest.
- When adding new CI stages, always add them to BOTH `ci.yml` (PR gate) and ensure
  they run on `push` to main, not only on PRs.
