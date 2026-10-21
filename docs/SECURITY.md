# Security Notes: Concierge

## Threat Model

<!-- Attack surface, trust boundaries, and primary threats for a multi-tenant SaaS -->

## Isolation Layers

<!-- Three simultaneous isolation layers: Postgres RLS, repository-layer query scoping, pgvector query-time filtering -->

**Postgres RLS is only enforced for roles that cannot bypass it** — superusers and
`BYPASSRLS` roles skip every policy, even with `FORCE ROW LEVEL SECURITY`. The API
therefore uses two roles (DECISIONS.md D-015):

| Role | Attributes | Used by |
|------|------------|---------|
| `concierge_app` | `NOSUPERUSER NOBYPASSRLS`, DML only; `audit_log` is `SELECT, INSERT` only | All request traffic via `get_db` (`DATABASE_URL`) |
| `concierge` (owner) | superuser | `get_system_db` / `SystemSessionLocal` (`SYSTEM_DATABASE_URL`): login and widget-token lookups (no tenant yet), widget-token verification, `/platform/*` routes, seeds, Alembic |

`app.core.db_roles` creates the app role and syncs its password and grants on every
API boot. `tests/integration/test_rls_enforced.py` proves the policies hold for the
app role (set `RLS_TEST_DATABASE_URL`); against the owner role it fails by design.

## Guardrail Architecture

<!-- NeMo Guardrails sidecar — platform-level rails (immutable) vs tenant-level topic overrides -->

## PII Redaction

<!-- Presidio pipeline: detection → anonymization → what flows to Claude vs. what is stored -->

## Service-to-Service Auth

<!-- Vault-issued service JWTs for API → guardrails and API → modelserver calls -->

## Erasure Path

<!-- GDPR right-to-erasure flow: what is deleted, what is anonymized, audit_log immutability exception -->
