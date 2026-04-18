# WAWI Architecture — Partsunion

## TL;DR

The WAWI is a fork of **InvenTree** (Django inventory system) with a
Partsunion-specific `wws` app bolted on top. The upstream InvenTree apps
(`part`, `stock`, `build`, `order`, `company`) are still installed but
are **deprecated** for new work. All new multi-tenant domain logic lives
in `wws/` and must inherit from `tenancy.TenantScopedModel`.

---

## Canonical domain models (use these)

Everything that holds dealer data must be `TenantScopedModel`. The
canonical set lives in `wws/models.py`:

| Concept | Model | Notes |
|---|---|---|
| Article / part | `wws.Product` | PK is `(tenant, IPN)` |
| Warehouse bin | `wws.StockLocation` | PK is `(tenant, code)` |
| Stock quantity | `wws.StockItem` | PK is `(tenant, product, location)` |
| Movement ledger | `wws.StockMovement` | append-only |
| Supplier | `wws.Supplier` | PK is `(tenant, name)` |
| Supplier price/lead | `wws.SupplierArticle` | PK is `(tenant, supplier, product)` |
| Purchase order | `wws.PurchaseOrder` + `PurchaseOrderItem` | |
| OEM cross-ref | `wws.OemCrossReference` | per-tenant cross-brand mapping |
| Vehicle fit | `wws.VehicleApplication` | KBA HSN/TSN, make/model/year |
| Returns | `wws.Return` | |
| Price rules | `wws.PriceRule` | endkunde / werkstatt / händler / partner |
| BOM / kit | `wws.BomItem` | |
| Supplier rating | `wws.SupplierRating` | |
| Bot/web order | `wws.Order` + `wws.Offer` | WhatsApp / dashboard entry point |
| Invoices | `billing.Invoice` + `billing.InvoiceLine` | per-tenant sequences |

## Deprecated (upstream InvenTree — do NOT build on)

The following apps are in `INSTALLED_APPS` but are **not** the source of
truth for Partsunion. They remain only because ripping them out breaks
existing migrations. Do **not** expose them via new APIs and do **not**
store dealer data in them.

- `part.*` — superseded by `wws.Product` + `wws.BomItem`
- `stock.*` — superseded by `wws.StockItem` + `wws.StockLocation`
- `build.*` — no use case, unused
- `order.*` — superseded by `wws.Order` + `wws.PurchaseOrder`
- `company.*` — superseded by `wws.Supplier` (and the CRM `channels.Contact`)

A follow-up cleanup should remove these apps once their tables are
confirmed empty in production. Until then, treat them as read-only
legacy.

## Why not both?

Running two parallel inventory models doubled the attack surface and
caused confusion about which migrations are authoritative. The upstream
models are also mostly **not** tenant-scoped (`PartStocktake`,
`PartStar`, `StockItemTracking`, `StockItemTestResult`, all `order.*`
models, etc.), which makes them unsafe in a 100-dealer SaaS without
substantial backfilling.

---

## Multi-tenancy rules

Hard requirements for every new model / endpoint:

1. **Inherit** `tenancy.TenantScopedModel`. Do not add your own
   `tenant = ForeignKey(...)` manually — the base class wires up the
   default manager, save hooks, and `for_tenant()` helper.
2. **Never** make `tenant` `null=True`. If you think you need a
   "global" row, you don't — make it a per-tenant default instead.
3. **ViewSets** must subclass `wws.api.TenantScopedViewSet` (or
   equivalent) so the queryset is auto-scoped to `request.tenant` and
   `perform_create()` stamps the tenant.
4. **Tests**: every new list/detail endpoint needs a cross-tenant
   leakage test in `wws/tests/test_tenant_isolation.py` (see existing
   patterns).

## Authentication layers (in order)

1. `SubdomainTenantMiddleware` — resolves tenant from `<slug>.partsunion.de`
2. `TenantJWTAuthentication` / `CookieJWTAuthentication` — JWT with
   `tenant_id`, `role`, optional `can_override`, optional `device_id`
   claims. A `device_id` claim ties the session to a row in
   `TenantDevice`; revoking the row invalidates the JWT.
3. `ServiceTokenAuthentication` — machine-to-machine. Tokens **must**
   have a tenant binding and explicit scopes (no `*`).
4. `TenantContextMiddleware` — last line; enforces `request.tenant` for
   downstream views and handles the `X-Tenant-Override` header (only
   honored for JWTs carrying `role=OWNER_ADMIN` **and**
   `can_override=true`).

## Throttling

- Global defaults: `100/min anon`, `1000/min user`, `20/min auth`.
- Per-tenant: `300 req / 10s burst`, `5000 req / hour sustained`.
- OEM lookup (`BotInventoryByOem`): `120/min per tenant`.

All rates are tunable via `INVENTREE_THROTTLE_*` env vars.

## Operational notes

- `SECRET_KEY` **must** be set via `INVENTREE_SECRET_KEY` in production.
  The settings module hard-fails on startup otherwise.
- Railway workers are set in `docker-entrypoint.sh` (`GUNICORN_WORKERS`).
- Background jobs (`outbox`, PDF, email) currently run in-process. A
  separate worker container for `django-q` is planned — see open
  todo in the audit.

## Known gaps (P1+)

See `AUDIT_2026Q2.md` for the full brutal audit. Highlights:

- No Postgres Row-Level Security yet (defense in depth missing).
- No separate worker container → PDF generation blocks gunicorn.
- Upstream InvenTree apps still installed.
- Per-tenant DB backup export not implemented.
- `django_session` is DB-backed; should move to Redis for 100 dealers.
