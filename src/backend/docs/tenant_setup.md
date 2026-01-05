# Tenant Setup & WAWI Test Flow

## Migration & Basics

```bash
python manage.py makemigrations
python manage.py migrate
```

Tenants über Subdomain `<slug>.euredomain.de`. Ohne Subdomain greifen die Dashboard-Actions nicht (require_tenant/role).

## Tenant + User anlegen

```bash
python manage.py create_tenant --slug demo --name "Demo GmbH" --admin_email admin@example.com --admin_password pass1234
python manage.py create_user --tenant demo --email staff@example.com --password pass1234 --role staff
```

## WAWI Config setzen (per Shell)

```bash
python manage.py shell <<'PY'
from wawitest.models import WawiConfig
from tenancy.models import Tenant
t = Tenant.objects.get(slug='demo')
WawiConfig.objects.update_or_create(tenant=t, defaults={'base_url': 'https://example.com', 'api_token': 'token', 'is_active': True})
PY
```

## Phase 2 Smoke-Test (Buttons)

- Browser: `https://<tenant>.euredomain.de/`
  - Buttons „Beleg erstellen (queue)“, „Retry“, „Force FAIL“, „Run one queued job“ sind für Staff/Owner sichtbar.
  - Status: creating → ready nach „Run one“.
  - last_error sichtbar bei Fehlern.

## Phase 3 Reparatur & Readiness

- Stuck reparieren (z.B. >60 Minuten):
  ```bash
  python manage.py repair_jobs --stuck-minutes 60 --mode requeue
  # oder
  python manage.py repair_jobs --stuck-minutes 60 --mode fail
  ```
- Health/Ready:
  ```bash
  curl -sS https://wawi-new.onrender.com/healthz
  curl -sS https://wawi-new.onrender.com/readyz
  ```
  Erwartung: `{"status":"ready","db":"ok"}` + optionale Zählungen.
