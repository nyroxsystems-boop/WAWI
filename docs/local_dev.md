## Lokale Entwicklung (Postgres + Django)

### Voraussetzungen
- Docker / Docker Compose
- Python 3.10+

### Setup
1. Kopiere `.env.example` nach `.env.local` und passe Werte an (DB, SECRET_KEY, MEDIA_ROOT).
2. Starte Postgres:
   ```sh
   make up
   ```
3. Führe Migrations aus:
   ```sh
   make migrate
   ```
4. Seed Demo-Daten:
   ```sh
   make seed
   ```
   Ausgabe enthält Tenant-ID und Service Token für den Bot.

### Wichtige ENV Variablen
- `INVENTREE_DB_ENGINE` (z.B. `postgresql`)
- `INVENTREE_DB_NAME`, `INVENTREE_DB_USER`, `INVENTREE_DB_PASSWORD`, `INVENTREE_DB_HOST`, `INVENTREE_DB_PORT`
- `SECRET_KEY` (JWT/Signing)
- `MEDIA_ROOT` (Speicherort für PDF-Rechnungen)

### Nützliche Befehle
- `make test` – führt Tests für tenancy, channels, wws, billing aus
- `python3 src/backend/InvenTree/manage.py runserver` – startet Backend (nutzt `.env.local`)

### Compose
`docker-compose.yml` stellt Postgres, optional Redis und ein einfaches Backend-Container-Setup bereit. Für lokale Entwicklung kannst du auch außerhalb des Containers `python3 src/backend/InvenTree/manage.py runserver` nutzen.
