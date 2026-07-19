#!/usr/bin/env bash
# Run the engine + API + dashboard locally on macOS/Linux (paper mode).
#   bash scripts/run_local.sh
# Loads .env if present; otherwise sets a minimal paper default.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -f .env ]; then
  set -a; . ./.env; set +a
elif [ -z "${TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1:-}" ]; then
  export TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1="local-paper-secret"
fi

export APP_PORT="${APP_PORT:-8000}"
echo "Starting Turtle Engine on http://localhost:${APP_PORT}  (dashboard at /, docs at /docs)"
exec python -m app.main
