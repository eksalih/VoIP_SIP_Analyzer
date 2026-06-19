#!/usr/bin/env bash
#
# One-command setup for VoIP SIP Analyzer.
# Checks prerequisites, prepares config, builds, and starts the stack.
#
# Usage: ./setup.sh
#
set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
RESET='\033[0m'

info()  { echo -e "${BOLD}==>${RESET} $1"; }
ok()    { echo -e "${GREEN}✓${RESET} $1"; }
warn()  { echo -e "${YELLOW}!${RESET} $1"; }
fail()  { echo -e "${RED}✗${RESET} $1"; exit 1; }

echo ""
echo -e "${BOLD}VoIP SIP Analyzer — Setup${RESET}"
echo "================================================"
echo ""

# ── 1. Check Docker ─────────────────────────────────────────────────────
info "Checking for Docker..."
if ! command -v docker &> /dev/null; then
    fail "Docker is not installed. Install it from https://docs.docker.com/get-docker/ and re-run this script."
fi
ok "Docker found ($(docker --version))"

if ! docker info &> /dev/null; then
    fail "Docker is installed but not running. Start Docker and re-run this script."
fi
ok "Docker daemon is running"

# ── 2. Check docker compose ─────────────────────────────────────────────
info "Checking for Docker Compose..."
if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    fail "Docker Compose not found. It ships with modern Docker Desktop installs — try updating Docker."
fi
ok "Docker Compose found ($COMPOSE_CMD)"

# ── 3. Prepare .env ──────────────────────────────────────────────────────
info "Preparing configuration..."
if [ ! -f backend/.env ]; then
    cp backend/.env.example backend/.env
    ok "Created backend/.env from template (edit this to customize settings)"
else
    ok "backend/.env already exists, leaving it as-is"
fi

if [ ! -f .env ]; then
    cp .env.example .env
    ok "Created .env from template (controls docker-compose build settings like VITE_API_URL)"
else
    ok ".env already exists, leaving it as-is"
fi

# ── 4. Prepare data directory ───────────────────────────────────────────
mkdir -p data
ok "Data directory ready at ./data (this is where your call history persists)"

# ── 5. Build and start ──────────────────────────────────────────────────
info "Building and starting containers (this may take a few minutes on first run)..."
$COMPOSE_CMD up --build -d

# ── 6. Wait for backend health check ────────────────────────────────────
info "Waiting for backend to become healthy..."
ATTEMPTS=0
MAX_ATTEMPTS=30
until curl -sf http://localhost:8000/health > /dev/null 2>&1; do
    ATTEMPTS=$((ATTEMPTS + 1))
    if [ "$ATTEMPTS" -ge "$MAX_ATTEMPTS" ]; then
        warn "Backend did not become healthy within 60s."
        warn "Check logs with: $COMPOSE_CMD logs backend"
        exit 1
    fi
    sleep 2
done
ok "Backend is healthy"

echo ""
echo "================================================"
echo -e "${GREEN}${BOLD}Setup complete!${RESET}"
echo ""
echo "  Frontend:  http://localhost:3000"
echo "  Backend:   http://localhost:8000"
echo "  API docs:  http://localhost:8000/docs"
echo ""
echo "  Stop:      $COMPOSE_CMD down"
echo "  Logs:      $COMPOSE_CMD logs -f"
echo "  Restart:   $COMPOSE_CMD restart"
echo ""

# Try to open the browser automatically (best-effort, ignore failures)
if command -v open &> /dev/null; then
    open http://localhost:3000 2>/dev/null || true
elif command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:3000 2>/dev/null || true
fi
