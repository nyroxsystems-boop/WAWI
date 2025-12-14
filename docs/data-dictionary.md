# Data Dictionary (gemeinsame Sprache)

Zentrale Begriffe und Pflichtfelder, damit Dashboard, Bot und Backend dieselben Namen/Typen verwenden. CamelCase/SnakeCase-Kombis sind angegeben, Backend liefert beide wo nötig (siehe `docs/dashboard-api-contract.md`).

## Tenant / Dealer
- Felder: `id`, `name`, `slug`, `status`
- Rolle (JWT claim `role`): `OWNER_ADMIN`, `TENANT_ADMIN`, `TENANT_USER`

## User / TenantUser
- Felder: `user{id, username, email}`, `tenant`, `role`, `is_active`

## Contact
- Felder: `id`, `wa_id`, `name`, `type` (`CUSTOMER|WORKSHOP|DEALER|UNKNOWN`), `tenant`
- Beziehungen: `Conversation`, `Order`, `Invoice`

## Conversation
- Felder: `id`, `contact`, `state_json`, `last_message_at`

## WhatsAppChannel
- Felder: `id`, `tenant`, `phone_number_id`, `display_number`, `provider`, `webhook_secret`, `status`
- Endpoint: `/api/whatsapp/resolve?phone_number_id=...`

## Order
- Felder: `id`, `status`, `language`, `order_data`, `vehicle_json/vehicle`, `part_json/part`, `oem`, `total_price/totalPrice`, `currency`, `created_at/createdAt`, `updated_at/updatedAt`, `contact`
- Statuswerte (flexibel, Dashboard nutzt): `choose_language|collect_vehicle|collect_part|oem_lookup|show_offers|done|new|confirmed`

## Offer
- Felder (Dash): `id`, `orderId`, `supplier`, `supplierName/shopName`, `productName/product_name`, `productUrl/product_url`, `oemNumber`, `price/basePrice/finalPrice`, `currency`, `availability`, `deliveryTimeDays`, `tier`, `status`
- Statuswerte: `draft`, `published`

## Supplier
- Felder: `id`, `name`, `rating`, `api_type`, `meta_json`

## WwsConnection (Provider)
- Felder: `id`, `name`, `type (demo_wws|http_api|scraper)`, `baseUrl`, `isActive`, `authConfig`, `config`

## MerchantSettings
- Felder: `tenant`, `selected_shops`, `margin_percent`, `price_profiles[]`
- Endpoints: `/dashboard/merchant/settings/:id` GET/POST

## Invoice
- Felder: `id`, `invoice_number`, `status (DRAFT|ISSUED|SENT|PAID|CANCELED)`, `order`, `contact`, `issue_date`, `due_date`, `subtotal`, `tax_total`, `total`, `currency`, `billing_address_json`, `shipping_address_json`, `lines[]`, `created_at`
- InvoiceLine: `id`, `description`, `quantity`, `unit_price`, `tax_rate`, `line_total`
- Sequence: `InvoiceSequence` (`prefix`, `padding`, `next_number`, `yearly_reset`, `last_reset_year`)

## DealerSupplierSetting
- Felder: `supplier{id,name}`, `enabled`, `priority`, `is_default`
- Endpoint: `/api/dealers/:id/suppliers`

## Events / Audit
- OutboxEvent: `event_type` (`ORDER_CREATED`, `INVOICE_ISSUED`), `payload`, `status`
- AuditLog: `action`, `tenant`, `actor`, `metadata`, `created_at`

## Statusmaschinen (zentral)
- Orders: freie Strings, aber Confirm-Action setzt `confirmed`; keine offenen PATCH ohne Regel empfohlen.
- Invoices: feste States mit Aktionen `issue`, `send`, `mark-paid`, `cancel`; `invoice_number` nach Issue unveränderlich.
