#!/bin/bash
# Production Entrypoint Script

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# Required environment variables
REQUIRED_VARS=(
    "SECRET_KEY"
    "ANONYMIZATION_SALT"
    "POSTGRES_PASSWORD"
    "DATABASE_URL"
)

log_info "Starting Finance Automation Backend"
log_info "Environment: ${APP_ENV:-dev}"

# Validate required environment variables
for var in "${REQUIRED_VARS[@]}"; do
    if [[ -z "${!var:-}" ]]; then
        log_error "Required environment variable $var is not set"
        exit 1
    fi
done

# Validate SECRET_KEY length
if [[ ${#SECRET_KEY} -lt 32 ]]; then
    log_error "SECRET_KEY must be at least 32 characters"
    exit 1
fi

# Production-specific checks
if [[ "${APP_ENV:-dev}" == "production" ]]; then
    log_info "Running production checks..."
    if [[ "$SECRET_KEY" == *"change"* ]] || [[ "$SECRET_KEY" == *"dev-"* ]]; then
        log_error "SECRET_KEY contains default/dev value. Generate a proper secret: openssl rand -base64 32"
        exit 1
    fi
    if [[ "$ANONYMIZATION_SALT" == *"change"* ]] || [[ "$ANONYMIZATION_SALT" == *"dev-"* ]]; then
        log_error "ANONYMIZATION_SALT contains default/dev value. Generate a proper salt: openssl rand -base64 32"
        exit 1
    fi
    if [[ "${DEBUG:-false}" == "true" ]]; then
        log_warn "DEBUG=true in production! Overriding to false."
        export DEBUG=false
    fi
fi

# Wait for database
log_info "Waiting for database..."
max_retries=30
retry=0
until pg_isready -h postgres -U "${POSTGRES_USER:-finance}" -d "${POSTGRES_DB:-finance}" >/dev/null 2>&1; do
    retry=$((retry + 1))
    if [[ $retry -ge $max_retries ]]; then
        log_error "Database not ready after $max_retries attempts"
        exit 1
    fi
    log_info "Database not ready, waiting... (attempt $retry/$max_retries)"
    sleep 2
done
log_info "Database is ready"

# Run migrations
log_info "Running database migrations..."
cd /app
alembic upgrade head

# Create upload directory
mkdir -p /app/uploads 2>/dev/null || true
chmod 755 /app/uploads 2>/dev/null || true

# Create logs directory
mkdir -p /app/logs 2>/dev/null || true
chmod 755 /app/logs 2>/dev/null || true

# Determine worker count: use WEB_CONCURRENCY env var, or 4 for prod, 1 for dev
WORKERS="${WEB_CONCURRENCY:-4}"
if [[ "${APP_ENV:-dev}" != "production" ]]; then
    WORKERS="${WEB_CONCURRENCY:-1}"
fi

# Lowercase log level for uvicorn
LOG_LEVEL_LOWER="${LOG_LEVEL,,}"
LOG_LEVEL_LOWER="${LOG_LEVEL_LOWER:-info}"

# Start application
log_info "Starting application server (workers=$WORKERS, log_level=$LOG_LEVEL_LOWER)..."
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers "$WORKERS" \
    --loop uvloop \
    --http httptools \
    --access-log \
    --log-level "$LOG_LEVEL_LOWER" \
    --proxy-headers \
    --forwarded-allow-ips="*"
