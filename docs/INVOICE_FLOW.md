# Invoice Flow (Draft → Issue → PDF → Send → Paid/Cancel)

Kurzübersicht, wie Rechnungen im System durchlaufen werden.

## Modelle
- `InvoiceSequence`: Nummernkreis pro Tenant (`prefix`, `padding`, `next_number`, `yearly_reset`, `last_reset_year`)
- `Invoice`: status `DRAFT|ISSUED|SENT|PAID|CANCELED`, `invoice_number` (per Tenant unique, erst bei Issue), `order`, `contact`, `subtotal/tax_total/total`, `currency`, `pdf_file`
- `InvoiceLine`: `description`, `quantity`, `unit_price`, `tax_rate`, `line_total` (auto)

## Status-Übergänge
- `DRAFT` (default)
- `issue` → `ISSUED` (vergibt Nummer atomar, setzt `issue_date`, recalculates totals, generiert PDF)
- `send` → `SENT` (falls noch Draft, wird vorher issued)
- `mark-paid` → `PAID` (nicht erlaubt, wenn `CANCELED`)
- `cancel` → `CANCELED` (nicht erlaubt, wenn `PAID`)
- `invoice_number` ist nach Issue unveränderlich.

## Endpoints
- `GET /api/invoices` (list)
- `POST /api/invoices` (draft anlegen, optional lines)
- `GET /api/invoices/:id`
- `POST /api/invoices/:id/issue`
- `POST /api/invoices/:id/send`
- `POST /api/invoices/:id/mark-paid`
- `POST /api/invoices/:id/cancel`
- `GET /api/invoices/:id/pdf` (Download/Stream, generiert bei Bedarf)
- `GET /api/reports/invoices/export?from=&to=` (CSV Export)
- `POST /api/orders/:id/create-invoice` (Draft aus Order/Offers erzeugen)

## Nummernvergabe (atomar)
```python
seq = InvoiceSequence.objects.select_for_update().get_or_create(tenant=tenant)
if seq.yearly_reset and seq.last_reset_year != year: seq.next_number = 1; seq.last_reset_year = year
number = f"{seq.prefix}{year}-{seq.next_number:0{seq.padding}d}"
seq.next_number += 1; seq.save()
invoice.invoice_number = number; invoice.issue_date = today
```

## PDF
- Generator: WeasyPrint (fällt zurück auf HTML-Bytes, falls Lib fehlt)
- Template minimal aus Model- und BillingSettings-Daten (Seller-Info, Beträge).

## Tenant-Scoping
- Alle Modelle erben `TenantScopedModel`; API filtert per `request.tenant`.
- Owner kann via `X-Tenant-Override` (Role `OWNER_ADMIN`) umschalten (Audit-Log).

## Beispiel-Flow (API)
```bash
# Draft anlegen
curl -X POST "$API/api/invoices" -H "Authorization: Bearer $TOKEN" -d '{"currency":"EUR","lines":[{"description":"Demo","quantity":1,"unit_price":99,"tax_rate":19}]}'

# Issue
curl -X POST "$API/api/invoices/1/issue" -H "Authorization: Bearer $TOKEN"

# PDF
curl -L "$API/api/invoices/1/pdf" -H "Authorization: Bearer $TOKEN" -o invoice.pdf
```
