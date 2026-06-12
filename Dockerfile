FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    INVENTREE_HOME="/home/inventree" \
    INVENTREE_MEDIA="/home/inventree/media" \
    INVENTREE_STATIC="/home/inventree/static" \
    INVENTREE_STATIC_ROOT="/home/inventree/static" \
    INVENTREE_MEDIA_ROOT="/home/inventree/media" \
    INVENTREE_BACKUP_DIR="/home/inventree/backup" \
    INVENTREE_LOG_DIR="/home/inventree/logs" \
    INVENTREE_PLUGIN_DIR="/usr/src/app/InvenTree/plugins" \
    INVENTREE_WEB_ROOT="/usr/src/app/InvenTree/InvenTree/web"

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
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libcairo2 \
    libffi-dev \
    shared-mime-info \
    libglib2.0-0 \
    fonts-dejavu-core \
    curl \
    procps \
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
    && if [ -f InvenTree/config_template.yaml ]; then \
    cp InvenTree/config_template.yaml /usr/config/config.yaml; \
    echo "Copied config_template.yaml to /usr/config/config.yaml"; \
    else \
    echo "WARNING: config_template.yaml not found, creating empty config"; \
    touch /usr/config/config.yaml; \
    fi

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/src/app/docker-entrypoint.sh
RUN chmod +x /usr/src/app/docker-entrypoint.sh

# Create ALL directories InvenTree needs + fix ownership
RUN mkdir -p $INVENTREE_STATIC $INVENTREE_MEDIA $INVENTREE_BACKUP_DIR $INVENTREE_LOG_DIR \
    && mkdir -p /usr/src/app/InvenTree/plugins \
    && chown -R inventree:inventree /usr/src/app $INVENTREE_HOME /usr/config

# Switch to non-root user
USER inventree

# Set working directory to InvenTree Django project
WORKDIR /usr/src/app/InvenTree

# Expose port
EXPOSE 8000

# Run entrypoint: migrate → collectstatic → create admin → gunicorn
CMD ["/usr/src/app/docker-entrypoint.sh"]
