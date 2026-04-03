#!/bin/bash
set -e

echo "=== WaWi Startup ==="

# Run database migrations (migrations should be committed to git, not auto-generated)
echo "Running migrations..."
python manage.py migrate --noinput 2>&1 || {
    echo "ERROR: Migrations failed. Retrying in 5 seconds..."
    sleep 5
    python manage.py migrate --noinput 2>&1 || echo "WARNING: Migrations failed after retry"
}

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

# Generate API token for bot-service (auto-finds first superuser)
echo "============================================"
echo "=== Generating API Token (bot-service)   ==="
echo "============================================"
python manage.py create_api_token --name bot-service --days 3650 2>&1 || echo "WARNING: Token generation failed"
echo "============================================"

echo "=== Starting Gunicorn ==="
exec gunicorn -b 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-8}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --access-logfile - \
    --error-logfile - \
    InvenTree.wsgi:application
