# Run the engine + API + dashboard locally on Windows (PAPER mode).
#   powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1
#
# PAPER IS FORCED AND CANNOT BE OVERRIDDEN BY .env.
# This script used to parse .env directly, and a .env containing
# TURTLE_EXEC_MODE=live silently turned this "paper mode" launcher into a
# real HyperliquidAdapter bound to the live venue. Two protections now
# make that impossible:
#   1. TURTLE_EXEC_MODE=paper is set BEFORE the file is read, and the
#      canonical loader never overwrites an already-set variable.
#   2. config/loader.py fails closed if the file and the variable disagree.
# To trade live, use an explicitly live configuration -- never this script.

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

# Asserted first so nothing loaded afterwards can change it.
$env:TURTLE_EXEC_MODE = "paper"

if (Test-Path ".env") {
  # Loaded by the canonical launcher through the single opt-in path, so
  # credentials arrive without a second parser. Credentials do not imply
  # live trading: the mode above still governs.
  $env:ENV_FILE = ".env"
} elseif (-not $env:TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1) {
  $env:TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1 = "local-paper-secret"
}

if (-not $env:APP_PORT) { $env:APP_PORT = "8000" }
Write-Host "Starting Turtle Engine (PAPER: MockExchangeAdapter, no venue writes)"
Write-Host "  http://localhost:$env:APP_PORT   dashboard at /, docs at /docs"
python -m scripts.run_platform
