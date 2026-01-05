#!/usr/bin/env bash
source "/Users/xaaronvx/Desktop/Nyrox Systems/autoteile-assistent/InvenTree-master/.venv/bin/activate"
set -a
source .env
set +a
export INVENTREE_DB_ENGINE=django.db.backends.sqlite3
export INVENTREE_DB_NAME="$(pwd)/data/db.sqlite3"
export INVENTREE_DB_USER=
export INVENTREE_DB_PASSWORD=
export INVENTREE_DB_HOST=
export INVENTREE_DB_PORT=
python manage.py run_worker
