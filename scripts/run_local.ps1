# Run the engine + API + dashboard locally on Windows (paper mode).
#   powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1
# Loads .env if present; otherwise sets a minimal paper default.

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (Test-Path ".env") {
  Get-Content ".env" | ForEach-Object {
    if ($_ -match '^\s*([^#=]+)\s*=\s*(.*)\s*$') {
      [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim())
    }
  }
} elseif (-not $env:TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1) {
  $env:TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1 = "local-paper-secret"
}

if (-not $env:APP_PORT) { $env:APP_PORT = "8000" }
Write-Host "Starting Turtle Engine on http://localhost:$env:APP_PORT  (dashboard at /, docs at /docs)"
python -m app.main
