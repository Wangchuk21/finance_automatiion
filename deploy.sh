#!/bin/bash
# ============================================================================
# Finance Automation — Production Deploy Script
# ============================================================================
# Usage:
#   ./deploy.sh           # Full deploy (build + migrate + start)
#   ./deploy.sh --quick   # Restart only (no rebuild)
# ============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "${CYAN}[STEP]${NC} $*"; }

COMPOSE_FILE="docker-compose.prod.yml"
TLS_COMPOSE_FILE="docker-compose.tls.yml"
ENV_FILE=".env.prod"
PROXY_CONTAINER="finance-proxy-prod"

# Parse KEY=VALUE lines without bash `source` so values containing characters
# like `<`, `>`, `&`, or spaces (e.g. SMTP_FROM) cannot break the script.
load_env_file() {
    local file="$1" line key value
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%$'\r'}"
        [[ "$line" =~ ^[[:space:]]*$ ]] && continue
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ "$line" != *=* ]] && continue

        key="${line%%=*}"
        value="${line#*=}"

        key="${key#"${key%%[![:space:]]*}"}"
        key="${key%"${key##*[![:space:]]}"}"
        [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue

        value="${value#"${value%%[![:space:]]*}"}"
        value="${value%"${value##*[![:space:]]}"}"
        if [[ ${#value} -ge 2 && ( "$value" == \"*\" || "$value" == \'*\' ) ]]; then
            value="${value:1:${#value}-2}"
        fi

        export "$key=$value"
    done < "$file"
}

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   Finance Automation — Production Deploy     ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════╝${NC}"
echo ""

# ── 1. Check env file ────────────────────────────────────────────────────────
log_step "Checking environment file..."
if [[ ! -f "$ENV_FILE" ]]; then
    log_error "Environment file $ENV_FILE not found!"
    log_info "Run: cp .env.prod.example .env.prod"
    log_info "Then edit .env.prod with your production values."
    exit 1
fi

# Compose file(s): the TLS proxy lives in its own file on the server.
COMPOSE_ARGS=(-f "$COMPOSE_FILE")
if [[ -f "$TLS_COMPOSE_FILE" ]]; then
    COMPOSE_ARGS+=(-f "$TLS_COMPOSE_FILE")
    log_info "Including $TLS_COMPOSE_FILE (TLS reverse proxy)"
else
    log_warn "$TLS_COMPOSE_FILE not found — deploying without the TLS proxy"
fi

# Load environment
load_env_file "$ENV_FILE"

# ── 2. Validate required variables ──────────────────────────────────────────
log_step "Validating configuration..."
REQUIRED_VARS=("SECRET_KEY" "ANONYMIZATION_SALT" "POSTGRES_PASSWORD" "DOMAIN" "TEMP_CONFIRM_CODE")
MISSING=()
for var in "${REQUIRED_VARS[@]}"; do
    val="${!var:-}"
    if [[ -z "$val" ]] || [[ "$val" == "CHANGE_ME" ]]; then
        MISSING+=("$var")
    fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
    log_error "The following variables are missing or still set to CHANGE_ME in $ENV_FILE:"
    for var in "${MISSING[@]}"; do
        echo "  - $var"
    done
    exit 1
fi

if [[ ${#SECRET_KEY} -lt 32 ]]; then
    log_error "SECRET_KEY must be at least 32 characters. Generate one: openssl rand -base64 32"
    exit 1
fi

log_info "Configuration OK ✓"

# ── 3. Create directories ───────────────────────────────────────────────────
log_step "Creating directories..."
mkdir -p uploads logs

# ── 4. Build & Deploy ────────────────────────────────────────────────────────
if [[ "${1:-}" == "--quick" ]]; then
    log_step "Quick restart (no rebuild)..."
    docker compose "${COMPOSE_ARGS[@]}" --env-file "$ENV_FILE" up -d
else
    log_step "Building application images..."
    docker compose "${COMPOSE_ARGS[@]}" --env-file "$ENV_FILE" build

    log_step "Starting services..."
    docker compose "${COMPOSE_ARGS[@]}" --env-file "$ENV_FILE" up -d
fi

# ── 4b. Restart reverse proxy ────────────────────────────────────────────────
# Recreated frontend/backend containers get new IPs and nginx caches upstream
# IPs at startup, which yields 502 Bad Gateway until it resolves them again.
log_step "Restarting reverse proxy (re-resolve upstream IPs)..."
if docker ps --format '{{.Names}}' | grep -qx "$PROXY_CONTAINER"; then
    if docker exec "$PROXY_CONTAINER" nginx -t >/dev/null 2>&1; then
        docker restart "$PROXY_CONTAINER" >/dev/null
        for _ in {1..10}; do
            [[ "$(docker inspect -f '{{.State.Running}}' "$PROXY_CONTAINER" 2>/dev/null)" == "true" ]] && break
            sleep 1
        done
        log_info "Proxy restarted ✓"
    else
        log_warn "Proxy config test failed — not restarting (run: docker exec $PROXY_CONTAINER nginx -t)"
    fi
else
    log_warn "Proxy container $PROXY_CONTAINER not running — skipping restart"
fi

# ── 5. Wait for health ──────────────────────────────────────────────────────
log_step "Waiting for services to become healthy..."
sleep 10

HEALTHY=true
for service in postgres backend frontend; do
    status=$(docker compose "${COMPOSE_ARGS[@]}" --env-file "$ENV_FILE" ps "$service" --format '{{.Health}}' 2>/dev/null || echo "unknown")
    if [[ "$status" == "healthy" ]]; then
        log_info "  $service: healthy ✓"
    else
        log_warn "  $service: $status (may still be starting)"
        HEALTHY=false
    fi
done

# ── 6. Final check ──────────────────────────────────────────────────────────
echo ""
if curl -sf "http://localhost:8000/health" >/dev/null 2>&1; then
    log_info "Backend health check: OK ✓"
else
    log_warn "Backend health check did not respond yet (may still be running migrations)"
fi

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Deployment complete!                       ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║                                              ║${NC}"
echo -e "${GREEN}║   Backend:  http://localhost:8000             ║${NC}"
echo -e "${GREEN}║   Frontend: http://localhost:3000             ║${NC}"
echo -e "${GREEN}║   Domain:   https://${DOMAIN:-localhost}                ║${NC}"
echo -e "${GREEN}║                                              ║${NC}"
echo -e "${GREEN}║   Logs:  docker compose ${COMPOSE_ARGS[*]} logs -f  ║${NC}"
echo -e "${GREEN}║                                              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""
