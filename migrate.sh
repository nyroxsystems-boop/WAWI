#!/bin/bash
set -e

echo "==> Running InvenTree Migrations..."

cd InvenTree-master/src/backend/InvenTree

# Set Django settings
export DJANGO_SETTINGS_MODULE="InvenTree.settings_render"
export PYTHONPATH="$(pwd)"

# Run migrations
echo "==> Applying database migrations..."
python manage.py migrate --noinput

# Collect static files
echo "==> Collecting static files..."
python manage.py collectstatic --noinput

# Create superuser if needed (optional)
# python manage.py createsuperuser --noinput --email admin@example.com || true

echo "==> Migrations completed successfully!"
