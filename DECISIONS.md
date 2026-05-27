# Decisions Log: Concierge

> Every decision that affects interfaces, thresholds, or conventions must have a row here.
> Never lower a CI threshold — add a new row explaining why a change was necessary.

| Decision | Options Considered | Chosen | Rationale | Number | Date |
|----------|--------------------|--------|-----------|--------|------|
| tenant_id convention | Polymorphic FK, indirect join, direct UUID column | Direct non-nullable UUID column on every tenant-scoped table, sourced from verified JWT only | Simple, auditable, RLS-friendly; no ambiguity at query time | D-001 | 2026-05-25 |
| "High confidence" classifier routing threshold | 0.70, 0.75, 0.80, 0.85 | TODO Owner B — propose before router is implemented | Threshold drives agent vs. direct-tool routing; wrong value adds latency or mis-routes | D-002 | TODO |
| Redis session TTL | 15 min, 30 min, 60 min | 30 minutes from last message | Balances usability for typical visitor session vs. anonymous visitor privacy | D-003 | 2026-05-25 |
| Widget JWT expiry | 30 min, 1 hr, 4 hr | 1 hour | Short enough to limit replay risk; long enough for a normal visitor session | D-004 | 2026-05-25 |
| Demo tenant CMS content scope | Various | Mario's Pizza: 5 items (menu, hours, delivery FAQ, location, specials); Lawson & Partners: 5 items (practice areas, team bios, consultation FAQ, fees, contact) | Minimal but representative; also seeds the RAG golden set | D-005 | 2026-05-25 |
| Per-tenant rate-limiting approach | Redis token bucket (redis-py), slowapi | Redis token bucket via redis-py custom middleware | Already a dependency; cluster-safe; no new deps added to API container | D-006 | 2026-05-26 |
| Per-tenant /chat/messages rate-limit thresholds | 10/min, 30/min, 60/min, 100/min | 60 req/min per tenant; window = 60 s (fixed) | Eval run (2026-05-26) showed p99 load of ~8 req/min per tenant in demo scenarios; 60/min gives 7× headroom for burst; lowering further would block legitimate multi-turn sessions; raising is a DECISIONS.md amendment | D-006a | 2026-05-27 |
| Tracing backend | OpenTelemetry → Jaeger, OpenTelemetry → Tempo | TODO Owner D — document in this table before day-one coding | Choice affects Docker Compose service count and Grafana stack | D-007 | TODO |
| Classifier dataset | Any public labeled text-classification set | TODO Owner C — record exact dataset name + file SHA-256 in model_card.md and here | Dataset choice is immutable once training starts | D-008 | TODO |
| Redis sliding window size N (session memory) | TBD | TODO Owner B — set after design; document here before implementation | Window size affects context quality and Redis memory budget | D-009 | TODO |
| capture_lead rate-limit numbers | TBD | TODO Owner B — set max leads per session + max per visitor IP per hour | Wrong values allow spam or block legitimate leads | D-010 | TODO |
