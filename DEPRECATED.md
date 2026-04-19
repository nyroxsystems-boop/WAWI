# ⚠️ DEPRECATED — do not deploy

As of 2026-04-19 this Django / InvenTree-fork is no longer part of the
Partsunion production stack. The warehouse, orders, invoices, stock and
all other WAWI features are served directly by the **Bot-Service**
(`../Whatsapp-Bot`), whose Postgres is the single source of truth.

## What changed

| Before | After |
| ---- | ---- |
| Dashboard → Bot-Service → this Django WAWI | Dashboard → Bot-Service → Bot-Service Postgres |
| `WAWI_API_URL` / `WAWI_SERVICE_TOKEN` env vars on the Bot-Service | removed |
| Dual schema (bot-service `orders` ↔ Django `wws_order`) | single schema in Bot-Service |

See `../Whatsapp-Bot/src/services/invoicing/wawiClient.ts` — the file
name is preserved for backward compatibility but the implementation
now runs against the local DB instead of HTTP.

## Can I still run it?

Only for historical reference or a data-export one-off. Do NOT
redeploy it alongside the Bot-Service — you will end up with two
parallel warehouses that drift apart within hours.

## Why isn't the code just deleted?

It's kept around so (a) we can extract any forgotten domain logic,
and (b) anyone who wondered "where did WAWI go?" finds this readme
instead of a git-archaeology session. Safe to `git rm -rf` in a
future spring-cleaning pass.
