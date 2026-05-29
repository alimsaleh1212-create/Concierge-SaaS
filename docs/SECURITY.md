# Security Notes: Concierge

## Threat Model

<!-- Attack surface, trust boundaries, and primary threats for a multi-tenant SaaS -->

## Isolation Layers

<!-- Three simultaneous isolation layers: Postgres RLS, repository-layer query scoping, pgvector query-time filtering -->

## Guardrail Architecture

<!-- NeMo Guardrails sidecar — platform-level rails (immutable) vs tenant-level topic overrides -->

## PII Redaction

<!-- Presidio pipeline: detection → anonymization → what flows to Claude vs. what is stored -->

## Service-to-Service Auth

<!-- Vault-issued service JWTs for API → guardrails and API → modelserver calls -->

## Erasure Path

<!-- GDPR right-to-erasure flow: what is deleted, what is anonymized, audit_log immutability exception -->
