#!/bin/bash
set -e

echo "=== WaWi Startup ==="

# Run database migrations
echo "Running migrations..."
python manage.py migrate --noinput 2>&1 || echo "WARNING: Migrations failed (DB might not be ready yet)"

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput 2>&1 || echo "WARNING: collectstatic failed"

# Create superuser if env vars are set and user doesn't exist yet
if [ -n "$DJANGO_SUPERUSER_PASSWORD" ] && [ -n "$DJANGO_SUPERUSER_USERNAME" ]; then
    echo "Creating superuser '${DJANGO_SUPERUSER_USERNAME}'..."
    python manage.py createsuperuser \
        --noinput \
        --username "$DJANGO_SUPERUSER_USERNAME" \
        --email "${DJANGO_SUPERUSER_EMAIL:-admin@partsunion.de}" \
        2>&1 || echo "Superuser already exists or creation failed"
fi

echo "=== Starting Gunicorn ==="
exec gunicorn -b 0.0.0.0:8000 --workers 2 --timeout 120 InvenTree.wsgi:application
