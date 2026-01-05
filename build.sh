#!/bin/bash
set -e

echo "==> Upgrading pip..."
pip install --upgrade pip

echo "==> Installing InvenTree dependencies..."

cd src/backend

# Install main requirements
# Note: We use the lockfile with hashes.
pip install -r requirements.txt

# Install Render-specific dependencies (Bypassing hash check)
# These are required for the Render environment but not strictly pinned in requirements.txt
echo "==> Installing Render adapters..."
pip install psycopg2-binary dj-database-url django-money

echo "==> Running migrations..."
cd InvenTree
python manage.py migrate --noinput

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

echo "==> Setup completed successfully!"

