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
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && pip install gunicorn psycopg2-binary redis invoke

# Copy project
COPY . .

# Create directory for static and media files
RUN mkdir -p $INVENTREE_STATIC $INVENTREE_MEDIA \
    && chown -R inventree:inventree /usr/src/app $INVENTREE_HOME

# Switch to non-root user
USER inventree

# Expose port (Gunicorn default)
EXPOSE 8000

# Entrypoint is handled by docker-compose commands (invoke server / invoke worker)
CMD ["gunicorn", "-b", "0.0.0.0:8000", "InvenTree.wsgi:application"]
