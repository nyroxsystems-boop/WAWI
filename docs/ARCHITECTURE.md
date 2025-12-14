# Architektur & Synergie-Leitplanken

**Leitsatz:** Dashboard + Bot sind Kanäle; WWS (Django/DRF) ist Single Source of Truth mit stabilen Contracts und Tests.

## Komponenten
- **Backend (InvenTree Erweiterung)**: Apps `tenancy`, `channels`, `wws`, `billing`, `audit`, `events`. DRF Endpoints unter `/api/...` + `/api/v1/...`.
- **Dashboard (React/Vite)**: Konsumiert ausschließlich REST-API, Auth via JWT, Base URL aus `VITE_API_BASE_URL`.
- **Bot-Service (WhatsApp)**: Unveränderte Logik, nutzt stabile Bot-Endpoints + Service Token.

## Flow-Überblick
1) **Auth/Tenant**: Login -> JWT mit `tenant_id`; Middleware setzt `request.tenant`. Owner kann via `X-Tenant-Override` (Audit) umschalten.
2) **Bot Intake**: `/api/whatsapp/resolve` → Contact/Conversation Upsert → `/api/bot/inventory/by-oem/:oem` → `/api/requests` bzw. `/api/orders` → `/api/orders/:id/confirm`.
3) **Orders/Offers**: Dashboard nutzt `/dashboard/orders` + `/dashboard/orders/:id/offers`; Backend liefert camel/snake Felder parallel.
4) **Invoice Flow**: Order → `/api/orders/:id/create-invoice` (Draft) → `/api/invoices/:id/issue` (Nummer + PDF) → optional `send` / `mark-paid` / `cancel` → PDF Download.
5) **Outbox/Audit**: `ORDER_CREATED`, `INVOICE_ISSUED` landen in Outbox; Login/Tenant-Override/Billing-Settings/Invoice-Actions werden auditiert.

## Adapter-Schicht (Inventory)
- `wws.adapters` mit Typen `demo_wws`, `http_api`, `scraper` → normalisierte Offers (`supplier_name`, `price`, `currency`, `availability`, `delivery_days`, `sku`, `meta`).
- `/api/bot/inventory/by-oem/:oem` iteriert aktive Connections, sammelt partial results + `errors[]`, cache 60s pro tenant+oem.

## Compatibility Layer
- Dealer == Tenant (z.B. `/api/dealers/:id/suppliers`).
- Dashboard-Routen gespiegelt unter `/dashboard/...` für Orders/Offers/WwsConnections/MerchantSettings.
- Serializer liefern doppelte Keys (camel + snake) an kritischen Stellen (Orders/Offers/Connections).

## Statusmaschinen
- Order: freier Statusstring, Confirm-Action (`POST /api/orders/:id/confirm`) setzt Status/Preis; Erstellung via `/api/orders` oder `/api/requests`.
- Invoice: fester Automat (`DRAFT` → `ISSUED` → `SENT` → `PAID`/`CANCELED`), Nummernkreis pro Tenant, `invoice_number` unveränderlich nach Issue.

## Datenquellen & Files
- DB: Postgres (docker-compose), Tenant-Scoped Models.
- Media: Invoice PDFs unter `MEDIA_ROOT/invoices/`.

## Tests & Checks
- Contract Tests (`wws/tests/test_contract_schema.py`) prüfen wesentliche Endpoints gegen Dashboard-Keys.
- Smoke Script `scripts/smoke_e2e.py`: login → health → orders → inventory → invoice create/issue → pdf.
- Outbox Tasks: `python manage.py process_outbox` (stub) oder Django-Q Worker.

## Setup-Quickstart
- `.env.example` ausfüllen, `docker-compose up -d`, `python manage.py migrate`, `python manage.py seed_wws`, Dashboard mit `VITE_API_BASE_URL` starten.
