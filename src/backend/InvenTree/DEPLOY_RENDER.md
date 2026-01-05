# Render Deploy (wawi-new / WWS)

Ziel: `/api/ext/...` Dokumente müssen live zuverlässig von `creating` → `ready` wechseln. Dafür braucht es:
- einen dauerhaft laufenden Worker (`python manage.py run_jobs`)
- funktionierende WeasyPrint Runtime (inkl. System-Libs für Cairo/Pango)

## 1) Render Services

### 1.1 Web Service (Gunicorn)
- **Root Directory:** `InvenTree-master/src/backend/InvenTree`
- **Build Command:** `./render-build.sh`
- **Start Command:** `gunicorn InvenTree.wsgi:application -c gunicorn.conf.py`
- **Health Check Path:** `/healthz`

### 1.2 Worker Service (Background Worker)
- **Root Directory:** `InvenTree-master/src/backend/InvenTree`
- **Build Command:** `./render-build.sh`
- **Start Command:** `python manage.py run_jobs`

Wichtig: Der Worker braucht **die gleichen ENV Vars / DB Config** wie der Web-Service.

## 2) WeasyPrint System Dependencies

WeasyPrint benötigt systemweite Libraries. In diesem Repo installiert `render-build.sh` u.a.:
- `libcairo2`
- `libpango-1.0-0`
- `libpangocairo-1.0-0`
- `libgdk-pixbuf-2.0-0`
- `libffi-dev`
- `fonts-dejavu-core`

Wenn PDF-Jobs trotz Worker direkt fehlschlagen, prüfe im Worker-Log nach:
- `WeasyPrint is not available…`
- `WeasyPrint failed to render PDF…`

## 3) ENV Vars (Minimum)

**Pflicht / empfohlen:**
- `INVENTREE_SITE_URL=https://wawi-new.onrender.com`
- `INVENTREE_ALLOWED_HOSTS=wawi-new.onrender.com`
- `INVENTREE_TRUSTED_ORIGINS=https://wawi-new.onrender.com,https://autoteile-dashboard.onrender.com`
- `DATABASE_URL=postgres://...` (oder die bestehenden `INVENTREE_DB_*` Variablen)
- `INVENTREE_STATIC_ROOT=/var/data/static` (oder Render Default)
- `INVENTREE_MEDIA_ROOT=/var/data/media` (oder Render Default)
- **Admin aktivieren:** `INVENTREE_ADMIN_ENABLED=true`
- **Optional Admin Pfad:** `INVENTREE_ADMIN_URL=admin/` (ohne führenden Slash; trailing Slash egal, wird bereinigt)
- (Nur falls nötig) `DJANGO_SETTINGS_MODULE=InvenTree.settings_render`

Hinweis: Render-Dateisystem ist i.d.R. **ephemeral**. Für langlebige PDFs sollte MEDIA auf ein dauerhaftes Storage zeigen (z.B. S3 via `django-storages`), sonst können Downloads nach Deploy/Restart verschwinden.

## 4) Live Checks (curl)

Health:
```bash
curl -sS https://wawi-new.onrender.com/healthz
curl -sS https://wawi-new.onrender.com/api/health/
curl -sS https://wawi-new.onrender.com/__whoami__
curl -I https://wawi-new.onrender.com/admin/   # erwartet 200 oder 302, kein 404
```

Job Status (requires Bearer token):
```bash
curl -sS \
  -H "Authorization: Bearer $WAWI_TOKEN" \
  https://wawi-new.onrender.com/api/ext/jobs/<job_id>/
```

Dokument-Flow (short):
1) Upsert order (PUT `/api/ext/orders/<id>/` mit `Idempotency-Key`)
2) Document anstoßen (POST `/api/ext/orders/<id>/documents/`)
3) Poll `GET /api/ext/orders/<id>/` bis `documents[].status == ready|failed`
