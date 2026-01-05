# Multi-Tenant (Subdomain) Skeleton

Subdomain → Tenant (`<slug>.euredomain.de`). Without Tenant: no access.

## Setup

```bash
python manage.py makemigrations
python manage.py migrate

# Tenant + Admin (owner)
python manage.py create_tenant --slug demo --name "Demo Tenant" --admin_email admin@demo.test --admin_password changeme

# Additional users
python manage.py create_user --tenant demo --email user@demo.test --password changeme --role staff
python manage.py create_user --tenant demo --email viewer@demo.test --password changeme --role readonly
```

## Local curl check
```bash
curl -H "Host: demo.euredomain.de" http://127.0.0.1:8000/
```
Erwartung: unbekannter Tenant → 404; geschützte Views ohne Tenant → 403 (require_tenant/require_role).

## Hosts / CSRF
- `ALLOWED_HOSTS` enthält `.euredomain.de`
- `CSRF_TRUSTED_ORIGINS` enthält `https://*.euredomain.de`
- Dev: `localhost` / `127.0.0.1` sind erlaubt

## Phase 2: WAWI Test-Flow
```bash
# WawiConfig setzen (per shell oder admin)
python manage.py shell -c "from wawitest.models import WawiConfig; from tenancy.models import Tenant; t=Tenant.objects.get(slug='demo'); WawiConfig.objects.update_or_create(tenant=t, defaults={'base_url':'http://localhost','api_token':'dummy','is_active':True})"

# Browser: http://127.0.0.1:8000/ mit Host: demo.euredomain.de
# Buttons (staff/owner): Beleg erstellen -> queued -> Run 1 queued job -> ready
```
