# Bot Setup (ohne Logik-Änderung)

Der WhatsApp-Bot kann ohne Codeänderungen weiterlaufen. Nur ENV/Base URL/Token anpassen.

## Benötigte ENV im Bot
- `API_BASE_URL` (z.B. `http://localhost:8000`)
- `BOT_SERVICE_TOKEN` (ServiceToken mit Scope `bot:*` aus `/api/service-tokens`)

## Genutzte Endpoints (tenant-scoped via Token)
- `GET /api/whatsapp/resolve?phone_number_id=...` → `{tenant_id, channel_id}`
- `POST /api/contacts/upsert` → `{contact}`
- `POST /api/conversations/upsert` → `{conversation}`
- `GET /api/bot/inventory/by-oem/<oem>` → `{oemNumber, offers[], errors?, generated_at}`
- `POST /api/requests` (Order Intake) → `{order_id, order}`  _oder_ `POST /api/orders`
- `POST /api/orders/:id/confirm` (optional Status/Preis bestätigen)

## Quick Steps
1) Owner erstellt Service Token (scope `bot:*`): `POST /api/service-tokens`
2) Bot ENV setzen: `API_BASE_URL`, `BOT_SERVICE_TOKEN`
3) Bot-Flow: resolve → contact upsert → conversation upsert → inventory → order create/confirm.

## Health/Config (optional)
- `GET /api/bot/health` → `{status:"ok", tenant_id}`
- `GET /api/bot/config` → `{tenant_id, connections[]}`
