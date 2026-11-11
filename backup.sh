#!/bin/bash
# ============================================================================
# Finance Automation — Database & Uploads Backup Script
# ============================================================================
# Usage:
#   ./backup.sh              # Run backup
#   crontab -e               # Add: 0 2 * * * /opt/finance-automation/backup.sh >> /var/log/finance-backup.log 2>&1
# ============================================================================

set -euo pipefail

# Configuration — adjust these if your paths differ
BACKUP_DIR="${BACKUP_DIR:-/opt/finance-automation/backups}"
RETENTION_DAYS=30
DATE=$(date +%Y%m%d_%H%M%S)
DB_CONTAINER="finance-db-prod"

# Load env to get DB credentials
ENV_FILE="$(dirname "$0")/.env.prod"
if [[ -f "$ENV_FILE" ]]; then
    set -a; source "$ENV_FILE"; set +a
fi
DB_USER="${POSTGRES_USER:-finance}"
DB_NAME="${POSTGRES_DB:-finance}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*"; }

mkdir -p "$BACKUP_DIR"

log_info "Starting backup..."

# Database backup
BACKUP_FILE="${BACKUP_DIR}/finance_${DATE}.sql.gz"
log_info "Creating database backup: $BACKUP_FILE"

if docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_FILE"; then
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    log_info "Database backup completed: $BACKUP_FILE ($SIZE)"
else
    log_error "Database backup failed"
    exit 1
fi

# Uploads backup
APP_DIR="$(dirname "$0")"
UPLOADS_DIR="${APP_DIR}/uploads"
if [[ -d "$UPLOADS_DIR" ]] && [[ "$(ls -A "$UPLOADS_DIR" 2>/dev/null)" ]]; then
    UPLOADS_BACKUP="${BACKUP_DIR}/uploads_${DATE}.tar.gz"
    log_info "Creating uploads backup: $UPLOADS_BACKUP"
    if tar -czf "$UPLOADS_BACKUP" -C "$APP_DIR" uploads 2>/dev/null; then
        SIZE=$(du -h "$UPLOADS_BACKUP" | cut -f1)
        log_info "Uploads backup completed: $UPLOADS_BACKUP ($SIZE)"
    else
        log_warn "Uploads backup failed"
    fi
else
    log_info "No uploads to back up"
fi

# Cleanup old backups
log_info "Cleaning up backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "finance_*.sql.gz" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true
find "$BACKUP_DIR" -name "uploads_*.tar.gz" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true

# Summary
TOTAL_BACKUPS=$(ls -1 "$BACKUP_DIR"/*.gz 2>/dev/null | wc -l)
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)
log_info "Backup completed. Total: $TOTAL_BACKUPS files, $TOTAL_SIZE"
