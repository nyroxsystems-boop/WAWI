#!/bin/bash
set -e

echo "=== WaWi Startup ==="

# Generate any missing migration files (for new models)
echo "Generating migrations..."
python manage.py makemigrations --noinput 2>&1 || echo "WARNING: makemigrations failed"

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

    # Generate/refresh DRF API token for the superuser
    echo "Generating API token for '${DJANGO_SUPERUSER_USERNAME}'..."
    python manage.py drf_create_token "$DJANGO_SUPERUSER_USERNAME" 2>&1 || echo "Token generation failed (may already exist)"
fi

echo "=== Starting Gunicorn ==="
exec gunicorn -b 0.0.0.0:8000 --workers 2 --timeout 120 InvenTree.wsgi:application
