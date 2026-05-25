# Design Notes: Concierge

## Tenant Isolation Strategy

<!-- How tenant_id flows from JWT → RLS → repository layer → pgvector filter -->

## Role Model

<!-- Platform Admin, Tenant Admin, Widget Visitor — capabilities and JWT claim shapes -->

## Scaling Story (10→1000 tenants)

<!-- Approach for scaling from 2 demo tenants to 1 000 production tenants without architectural changes -->

## RLS Exception (audit_log)

<!-- Why audit_log is exempt from standard RLS and what compensating controls exist -->
