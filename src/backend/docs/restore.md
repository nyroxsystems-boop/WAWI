# Restore Guide

## Inspect Backup

```bash
pg_restore --list backups/backup_YYYYMMDD_HHMMSS.dump | head
```

## Safe Restore (Staging)

1) Create a fresh staging database (do not overwrite production).
2) Set `DATABASE_URL` to the staging instance.
3) Restore:
   ```bash
   pg_restore --clean --if-exists --no-owner --dbname "$DATABASE_URL" backups/backup_YYYYMMDD_HHMMSS.dump
   ```
4) Verify application starts and data looks correct before any promotion.

Notes:
- Use `PGSSLMODE=require` if your DB enforces TLS.
- Do not run restores against production without a validated plan.***
