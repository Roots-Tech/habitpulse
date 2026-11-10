# ==========================================
# HabitPulse Production Dockerfile
# ==========================================
FROM python:3.10-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Install essential runtime and build tools for PostgreSQL & healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies in a separate layer for build caching
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Create a dedicated non-root user for container security
RUN addgroup --system habitgroup && adduser --system --group habituser

# Copy application source code
COPY . /app/

# Copy and setup entrypoint script
COPY scripts/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Create media, staticfiles, and backups directories with correct ownership
RUN mkdir -p /app/media /app/staticfiles /app/backups && \
    chown -R habituser:habitgroup /app

# Switch to non-root user
USER habituser

# Expose Django WSGI port
EXPOSE 8000

# Entrypoint manages database readiness, safe migrations, and static collection
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# Default start command: Production Gunicorn WSGI
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "2", "config.wsgi:application"]
