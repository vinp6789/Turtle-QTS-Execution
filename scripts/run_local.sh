#!/usr/bin/env bash
# Run the engine + API + dashboard locally on macOS/Linux (PAPER mode).
#   bash scripts/run_local.sh
#
# PAPER IS FORCED AND CANNOT BE OVERRIDDEN BY .env.
# This script used to `. ./.env` directly, and a .env containing
# TURTLE_EXEC_MODE=live silently turned this "paper mode" launcher into a
# real HyperliquidAdapter bound to the live venue. Two protections now
# make that impossible:
#   1. TURTLE_EXEC_MODE=paper is exported BEFORE the file is read, and the
#      canonical loader never overwrites an already-set variable.
#   2. config/loader.py fails closed if the file and the variable disagree.
# To trade live, use an explicitly live configuration -- never this script.
set -euo pipefail
cd "$(dirname "$0")/.."

# Asserted first so nothing loaded afterwards can change it.
export TURTLE_EXEC_MODE=paper

if [ -f .env ]; then
  # Loaded by the canonical launcher through the single opt-in path, so
  # credentials arrive without a second parser. Credentials do not imply
  # live trading: the mode above still governs.
  export ENV_FILE=.env
elif [ -z "${TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1:-}" ]; then
  export TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1="local-paper-secret"
fi

export APP_PORT="${APP_PORT:-8000}"
echo "Starting Turtle Engine (PAPER: MockExchangeAdapter, no venue writes)"
echo "  http://localhost:${APP_PORT}   dashboard at /, docs at /docs"
exec python -m scripts.run_platform
