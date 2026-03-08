FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    INVENTREE_HOME="/home/inventree" \
    INVENTREE_MEDIA="/home/inventree/media" \
    INVENTREE_STATIC="/home/inventree/static"

# Create a user to run the application
RUN groupadd -r inventree && useradd -r -g inventree inventree

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    build-essential \
    gettext \
    libjpeg-dev \
    zlib1g-dev \
    git \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /usr/src/app

# Install Python dependencies
COPY src/backend/requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && pip install gunicorn psycopg2-binary redis invoke dj-database-url

# Copy backend project
COPY src/backend/ .

# Create config directory that InvenTree expects (resolves to /usr/config at runtime)
# Also create writable config dir at /usr/src/app/InvenTree/config for the WORKDIR
RUN mkdir -p /usr/config /usr/src/app/config /usr/src/app/InvenTree/config \
    && if [ -f InvenTree/InvenTree/config_template.yaml ]; then \
    cp InvenTree/InvenTree/config_template.yaml /usr/config/config.yaml; \
    else \
    touch /usr/config/config.yaml; \
    fi

# Create directory for static and media files + fix all ownership
RUN mkdir -p $INVENTREE_STATIC $INVENTREE_MEDIA \
    && chown -R inventree:inventree /usr/src/app $INVENTREE_HOME /usr/config

# Switch to non-root user
USER inventree

# Set working directory to InvenTree Django project
# Structure: src/backend/InvenTree/InvenTree/wsgi.py
# After COPY, this is at /usr/src/app/InvenTree/InvenTree/wsgi.py
WORKDIR /usr/src/app/InvenTree

# Expose port (Gunicorn default)
EXPOSE 8000

# Run gunicorn — env vars (DATABASE_URL, SECRET_KEY etc.) provided by Railway
CMD ["gunicorn", "-b", "0.0.0.0:8000", "InvenTree.wsgi:application"]
