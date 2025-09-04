#!/bin/bash
# Second Brain - Production Entrypoint Script

set -e

echo "🚀 Starting Second Brain in $ENVIRONMENT mode"

# Apply database migrations
echo "📦 Applying database migrations..."
python migrate_db.py

# Run multi-tenant migration if needed
if [ "$MULTI_TENANT_MODE" = "true" ]; then
    echo "🏢 Applying multi-tenant migrations..."
    python -c "
from services.tenant_service import TenantService
import sqlite3
def get_conn():
    conn = sqlite3.connect('${DATABASE_URL:-/app/data/notes.db}'.replace('sqlite:///', ''))
    conn.row_factory = sqlite3.Row
    return conn
tenant_service = TenantService(get_conn)
print('✅ Multi-tenant setup complete')
"
fi

# Ensure directories exist
mkdir -p /app/data /app/vault /app/audio /app/uploads /app/screenshots

# Set proper file permissions
chmod 755 /app/data /app/vault /app/audio /app/uploads /app/screenshots

# Start the application
echo "🌟 Starting Second Brain application..."
exec python -m uvicorn app:app --host 0.0.0.0 --port 8082 --workers 1