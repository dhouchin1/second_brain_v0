# Second Brain - Multi-Tenant Production Dockerfile
FROM python:3.11-slim as base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    sqlite3 \
    nginx \
    supervisor \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN useradd -m -u 1000 app && \
    mkdir -p /app /app/data /app/vault /app/audio && \
    chown -R app:app /app

WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p \
    /app/data \
    /app/vault \
    /app/audio \
    /app/uploads \
    /app/screenshots \
    /app/static \
    /app/templates \
    && chown -R app:app /app

# Copy supervisor config
COPY deployment/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Set proper permissions
RUN chmod +x deployment/entrypoint.sh && \
    chown app:app /app -R

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8082/health || exit 1

# Switch to app user
USER app

# Expose port
EXPOSE 8082

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=production

# Entry point
CMD ["./deployment/entrypoint.sh"]