#!/usr/bin/env bash
set -euo pipefail

echo "[render-build] Installing system deps for WeasyPrint (cairo/pango)…"
apt-get update
apt-get install -y --no-install-recommends \
  libcairo2 \
  libpango-1.0-0 \
  libpangocairo-1.0-0 \
  libgdk-pixbuf-2.0-0 \
  libffi-dev \
  fonts-dejavu-core \
  shared-mime-info
rm -rf /var/lib/apt/lists/*

echo "[render-build] Installing Python dependencies…"
python -m pip install --upgrade pip
python -m pip install -r ../requirements.txt

echo "[render-build] Collecting static files…"
python manage.py collectstatic --noinput

echo "[render-build] Done."
