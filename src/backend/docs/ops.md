# Ops Notes (Render)

## Cron Alert Check

Run every 5 minutes (Render Cron):

```bash
python manage.py check_alerts --stuck-minutes 10
```

- Exit 0: keine Alerts
- Exit 2: Alerts gefunden (Failed Jobs oder stuck Documents)
- Logs: `wawitest.alert` mit jobs_failed und docs_stuck_creating

## Health

- `/healthz` für Liveness
- `/readyz` für Readiness (DB + einfache Zählungen)
