## Bot API Client Contract

Der Bot muss seine Logik nicht ändern, nur Base-URL + Token setzen.

### Konfiguration
- `API_BASE_URL`: Basis, z.B. `https://backend.example.com/api`
- `BOT_SERVICE_TOKEN`: Service Token (Prefix `svc_...`) aus Seed/DB

### Auth
- `Authorization: Bearer <BOT_SERVICE_TOKEN>`
- Token kann tenant-gebunden sein; dann wird der Tenant automatisch gesetzt.

### Endpunkte
- `GET /api/bot/health` → `{ status, tenant_id }`
- `GET /api/bot/config` → `{ tenant_id, connections: [{id,type,base_url}], requires_service_token }`
- `GET /api/whatsapp/resolve?phone_number_id=...` → `{ tenant_id, channel_id }`
- `POST /api/contacts/upsert` → `{ contact }` (Body: `{ wa_id, name?, type? }`)
- `POST /api/conversations/upsert` → `{ conversation }` (Body: `{ wa_id, state_json? }`)
- `GET /api/bot/inventory/by-oem/<oem>` → `{ oem, offers[], generated_at, errors[] }`

### Offer Schema (inventory/by-oem)
```json
{
  "supplier_name": "Demo Supplier",
  "price": 100.0,
  "currency": "EUR",
  "availability": "in_stock",
  "delivery_days": 2,
  "sku": "OEM123-DEMO",
  "meta": { "source": "demo" }
}
```

### Fehlerverhalten
- Wenn Adapter ausfällt: `errors: [{connection_id, error}]`, `offers` kann trotzdem teilweise gefüllt sein.

### Health/Config
- Beide Endpunkte sind read-only und erfordern nur das Service Token.
