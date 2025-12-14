## Deployment / Go-Live

### Schritte
1. `.env.local` aus `.env.example` kopieren und Werte setzen (DB, SECRET_KEY, MEDIA_ROOT, CORS).
2. `docker-compose up -d` (Postgres, Backend, Redis).
3. Migrations: `python3 src/backend/InvenTree/manage.py migrate`.
4. Seed Demo: `make seed` (erstellt Owner/Tenant/Channel/Supplier/Order/Offer, Service Token).
5. Login: `/api/auth/login` mit owner/owner (Tenant slug: demo-haendler).
6. Dashboard: setze `VITE_API_BASE_URL=http://localhost:8000` und starte Vite.
7. Owner-Onboarding:
   - POST `/api/tenants` (Owner)
   - POST `/api/tenants/:id/users` (Händler-Login)
   - POST `/api/tenants/:id/whatsapp-channels`
   - POST `/api/service-tokens` (Bot-Token)
8. Bot Setup: `API_BASE_URL` auf Backend, `BOT_SERVICE_TOKEN` aus Seed/Service-Tokens.
9. Invoice Flow: Bestellung → `/api/orders/:id/create-invoice` → `/api/invoices/:id/issue` → `/api/invoices/:id/pdf` → `/send`/`/mark-paid`.

### Wichtige Endpoints
- Auth: `/api/auth/login`, `/api/auth/refresh`, `/api/auth/me`
- Tenants Admin: `/api/tenants`, `/api/tenants/:id/users`, `/api/tenants/:id/whatsapp-channels`, `/api/service-tokens`
- WhatsApp/Bot: `/api/whatsapp/resolve`, `/api/contacts/upsert`, `/api/conversations/upsert`, `/api/bot/inventory/by-oem/:oem`, `/api/bot/health`, `/api/bot/config`
- WWS: `/api/wws-connections` (+ `/test`), `/api/orders`, `/api/orders/:id/offers`
- Billing: `/api/invoices`, `/api/invoices/:id/issue|send|mark-paid|cancel|pdf`, `/api/reports/invoices/export`, `/api/settings/billing`

### Hinweise
- Tenant-Scope via JWT `tenant_id` oder Service Token.
- CORS: lokale Vite-Origin whitelisted.
- Rate-Limit (basic) aktiv; Tokens nicht loggen. PDFs tenant-geprüft.
- Hintergrundjobs: Django-Q Worker (`python manage.py qcluster`) zieht Tasks wie `events.tasks.process_outbox`, `nightly_invoice_export`, `refresh_prices`, `refresh_offers`, `regenerate_missing_pdfs`. Alternativ manuell: `python manage.py process_outbox`.
- Outbox/Webhooks: Order-Create und Invoice-Issue erzeugen `OutboxEvent` (PENDING). Command/Worker markiert sie als SENT → idealer Hook für Webhooks.
