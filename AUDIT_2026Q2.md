# WAWI Audit — 2026 Q2

Brutal honest state-of-the-WAWI as of this commit. Sibling doc to
`ARCHITECTURE.md`, which describes the target state.

## Fixed in this commit

- **SECRET_KEY hard-fail** in production (settings.py).
- **Invoice-PDF HTML-injection** closed — all string interpolations into
  the WeasyPrint template are now `escape()`-wrapped; CSS knobs
  (color/font/enum) are whitelisted.
- **Tenant-Override header** now requires both `OWNER_ADMIN` role **and**
  explicit `can_override=true` JWT claim — a stolen A-tenant JWT can no
  longer pivot to B even if the user has OWNER membership in B.
- **Per-tenant throttling** added — `tenant_burst`, `tenant_sustained`,
  `oem_lookup` scopes, keyed by `(tenant_id, user_or_service_id)`.
- **Service tokens** with `tenant=NULL` or scope `*` are rejected at
  authentication; `ServiceToken.has_scope()` no longer honors wildcards.
- **Tenant NOT NULL** re-enforced on the six `wws` models broken by
  migration 0005. Orphan rows (if any) get backfilled to a sentinel
  `__orphan__` tenant so they don't disappear silently.
- **Cross-tenant isolation tests** added for Supplier, Order, Offer,
  WwsConnection, plus override / service-token rejection tests.

## Still open (not safe to ship inside a single Claude turn)

### P0 — before 5 customers

- `wws/migrations/0006` runs `RunPython` + `AlterField` in one migration
  against Postgres. Needs to be validated against the Railway prod DB
  (expected: zero orphan rows). If there are orphans, triage them before
  deploying.
- Upstream InvenTree apps (`part`, `stock`, `build`, `order`, `company`)
  are still in `INSTALLED_APPS`. Models there are mostly not
  tenant-scoped. Either delete them once their tables are confirmed
  empty, or tenant-scope every remaining model.
- `PartStocktake`, `PartStar`, `PartTestTemplate`, `StockItemTracking`,
  `StockItemTestResult`, all `order.*` models have no tenant FK and are
  potential cross-tenant leaks.

### P1 — before 20 customers

- Redis-backed sessions (currently DB-backed via `allauth.usersessions`).
- Separate `django-q` worker container for PDF / outbox / email.
- Per-tenant DB backup / export (currently only global `dbbackup`).
- Postgres Row-Level Security as defense in depth.
- Rotation policy for `bot-service` long-lived tokens.
- Structured metrics per-tenant (Sentry tags, Grafana board).

### P2 — before 100 customers

- Tenant-sharded Postgres or at least read-replica per region.
- Zero-downtime migrations strategy (the `migrate --noinput` retry loop
  in `docker-entrypoint.sh` is not a strategy).
- Decommission the unused `src/frontend` InvenTree UI (~250 MB of
  `node_modules`) — dealer UI lives in the separate `User-Dashboard`.

## Architectural decisions made in this commit

- **`wws` models are the source of truth**, upstream InvenTree models
  are deprecated. See `ARCHITECTURE.md` for the mapping.

## Test coverage snapshot

| Area | Lines | Status |
|---|---|---|
| `tenancy/tests` | 392 | basic |
| `wws/tests` | ~520 (after this commit) | improved |
| Cross-tenant isolation | yes (new) | added this commit |
| `billing/tests` | minimal | needs work |
| `audit/tests` | minimal | needs work |
| `outbox/tests` | minimal | needs work |

See `wws/tests/test_tenant_isolation.py` for the new scaffolding — extend
it for every new endpoint.
