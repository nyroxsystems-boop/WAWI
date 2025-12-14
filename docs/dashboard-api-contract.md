# Dashboard API Contract

Alle API-Calls, die das React-Dashboard aktuell verwendet. Backend muss diese Pfade, Felder und Datentypen bereitstellen (JSON, camelCase kompatibel).

## Auth
- **POST /api/auth/login**
  - Body: `{ email: string, password: string, tenant?: string }`
  - Response: `{ access: string, refresh: string, user: {id, username, email}, tenant: {id, slug, name, role} }`
  - Verwendet in: `src/auth/AuthContext.tsx`

## Orders & Offers (Dashboard-prefixed)
- **GET /dashboard/orders**
  - Query: none
  - Response: `Order[]` – Felder: `id (string)`, `status (string)`, `language (string|null)`, `order_data (object|null)`, `created_at/createdAt (ISO)`, `updated_at/updatedAt (ISO)`, `total_price/totalPrice (number|null)`, `vehicle_json/vehicle`, `part_json/part`
  - Verwendet in: `src/api/orders.ts` (`listOrders`), `src/pages/OverviewPage.tsx`
- **GET /dashboard/orders/:id**
  - Response: `Order` (siehe oben)
  - Verwendet in: `src/api/orders.ts` (`getOrder`), `src/pages/OrderDetailPage.tsx`
- **GET /dashboard/orders/:id/offers**
  - Response: `ShopOffer[]`
    - Felder: `id`, `orderId`, `shopName/supplierName`, `brand`, `productName`, `productUrl`, `oemNumber`, `basePrice`, `finalPrice`, `currency`, `marginPercent`, `status`, `availability`, `deliveryTimeDays`, `tier`, `rating`, `isRecommended`
  - Verwendet in: `src/api/orders.ts` (`getOrderOffers`)
- **POST /dashboard/orders/:id/offers/publish**
  - Body: `{ offerIds: string[] }`
  - Response: `{ success: boolean, updated?: number }`
  - Verwendet in: `src/api/orders.ts` (`publishOffers`)

## Offers (Shop view)
- **GET /api/orders/:id/offers**
  - Response: entweder `Offer[]` oder `{ offers: Offer[] }`
  - Offer Felder (ShopOffersTable): `id`, `supplier_id/supplierId`, `supplier_name/supplierName/shopName`, `product_name`, `brand`, `base_price/price`, `tier`, `url/product_url`, `status`
  - Verwendet in: `src/ShopOffersTable.tsx`

## Dealer Supplier Settings
- **GET /api/dealers/:dealerId/suppliers**
  - Response: `DealerSupplierItem[]` mit `supplier { id, name, country?, actor_variant? }`, `enabled (bool)`, `priority (number)`, `is_default (bool)`
  - Verwendet in: `src/pages/DealerSuppliersPage.tsx`
- **PUT /api/dealers/:dealerId/suppliers**
  - Body: `{ items: [{ supplier_id: string, enabled: boolean, priority: number, is_default: boolean }] }`
  - Response: `DealerSupplierItem[]`
  - Verwendet in: `src/pages/DealerSuppliersPage.tsx`

## Merchant Settings
- **GET /dashboard/merchant/settings/:merchantId**
  - Response: `{ merchantId: string, selectedShops: string[], marginPercent: number, priceProfiles?: PriceProfile[] }`
    - `PriceProfile`: `{ id: string, name: string, description: string, margin: number, isDefault?: boolean }`
  - Verwendet in: `src/api/merchant.ts`, `src/pages/PricingPage.tsx`
- **POST /dashboard/merchant/settings/:merchantId**
  - Body: `{ selectedShops?: string[], marginPercent?: number, priceProfiles?: PriceProfile[] }`
  - Response: `{ ok: boolean }`
  - Verwendet in: `src/api/merchant.ts`, `src/pages/PricingPage.tsx`

## WWS Connections
- **GET /api/wws-connections**
  - Response: `WwsConnection[]` – Felder: `id`, `name`, `type (demo_wws|http_api|scraper)`, `baseUrl`, `isActive`, `authConfig`, `config`
  - Verwendet in: `src/features/wws/api.ts`, `src/pages/IntegrationsPage.tsx`
- **POST /api/wws-connections**
  - Body: `{ name, type, baseUrl, isActive?, authConfig?, config? }`
  - Response: `WwsConnection`
- **PUT /api/wws-connections/:id**
  - Body: wie POST (partiell)
  - Response: `WwsConnection`
- **DELETE /api/wws-connections/:id**
  - Response: `{}` (ignoriert im UI)
- **POST /api/wws-connections/:id/test**
  - Body: `{ oemNumber: string }`
  - Response: `{ ok: boolean, error?: string, sampleResultsCount?: number }`
  - Verwendet in: `src/features/wws/api.ts`

## Bot Inventory
- **GET /api/bot/inventory/by-oem/:oem**
  - Response: `{ oemNumber: string, offers: any[] }` (+ ggf. `errors`)
  - Verwendet in: `src/features/wws/api.ts` (`testInventory`)

## Billing / Invoices
- **GET /api/invoices**
  - Response: `Invoice[]`
    - Felder: `id`, `invoice_number|null`, `status`, `order`, `contact`, `issue_date|null`, `due_date|null`, `subtotal`, `tax_total`, `total`, `currency`, `billing_address_json`, `shipping_address_json`, `lines?`, `created_at`
  - Verwendet in: `src/pages/InvoicesPage.tsx`
- **GET /api/invoices/:id**
  - Response: `Invoice`
  - Verwendet in: `src/pages/InvoiceDetailPage.tsx`
- **POST /api/invoices**
  - Body: `Partial<Invoice>` (mind. status/billing/contact/lines)
  - Response: `Invoice` (draft)
  - Verwendet in: `src/api/invoices.ts` (`createInvoice`)
- **POST /api/invoices/:id/issue**
  - Response: `Invoice` (mit `invoice_number`, `status=ISSUED`, `pdf_file` optional)
  - Verwendet in: `InvoiceDetailPage.tsx`
- **POST /api/invoices/:id/send**
  - Response: `Invoice` (`status=SENT`)
- **POST /api/invoices/:id/mark-paid**
  - Response: `Invoice` (`status=PAID`)
- **POST /api/invoices/:id/cancel**
  - Response: `Invoice` (`status=CANCELED`)
- **GET /api/invoices/:id/pdf**
  - Response: PDF Stream (Download/Inline)
- **POST /api/orders/:orderId/create-invoice**
  - Response: `Invoice` (Draft, lines aus Order/Offers)
  - Verwendet in: `src/api/invoices.ts` (`createInvoiceFromOrder`)

## Health
- **GET /api/health**
  - Response: `{ status: "ok" }`
  - Verwendet für Deployment/Smoke (manuell)

## Schema Dateien
Für jedes Endpoint findet sich ein JSON Schema in `docs/contract-schemas/` (siehe Dateinamen analog Endpoint). Diese Schemas sind Grundlage für Contract-Tests.
