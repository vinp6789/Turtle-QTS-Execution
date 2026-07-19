# Operations Runbook

## Endpoints (all under the app base URL)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | open | Liveness/readiness (cheap; container + Railway health check) |
| GET | `/status` | open | Full status: portfolio, positions, reconciliation, last cycle |
| GET | `/portfolio` | open | Portfolio figures |
| GET | `/reports` | open | Five human-readable summaries |
| GET | `/metrics` | open | Prometheus text exposition |
| GET | `/docs` | open | Swagger UI / OpenAPI |
| GET | `/` | open | Mobile dashboard |
| POST | `/cycle/run` | API key* | Run one trading cycle now |
| POST | `/control/emergency-stop` | API key* | Revoke all signing (Emergency Kill) |

\* Protected only when `API_KEY` is set. **Always set `API_KEY` in
production.** Present it as `X-API-Key: <key>` or `Authorization: Bearer
<key>`. The dashboard stores it in the browser's localStorage.

## Monitoring from your phone

Open `/` on the deployed URL. The dashboard auto-refreshes every 5s and
shows engine/kill-switch state, portfolio, reconciliation, and reports,
plus **Run cycle** and **Emergency stop** buttons (enter the API key once).

## Emergency stop

`POST /control/emergency-stop` (or `/stop` in Telegram, or the dashboard
button) revokes **all** signing capability via the frozen
`SigningBoundary.revoke_all()` and the wallet signer's `revoke()`. This is
**one-way** for the running process — no further order can be authorized.
To resume trading, redeploy/restart with fresh signing config.

## Telegram

Set `TELEGRAM_ENABLED=true`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
Commands: `/status /portfolio /risk /reconcile /health /cycle /stop /help`.
Only messages from the configured chat id are honored, and `/stop` acts
only from that chat.

## Metrics

Point Prometheus at `/metrics`. Key series: `turtle_engine_up`,
`turtle_kill_switch_active`, `turtle_emergency_stopped`,
`turtle_cycles_run_total`, `turtle_equity`, `turtle_unrealized_pnl`,
`turtle_exposure`, `turtle_heat`, `turtle_reconciliation_matches`.

## Logs

Structured JSON to stdout (`LOG_FORMAT=json`). Railway/Docker capture it.
Set `LOG_FORMAT=text` for readable local logs.

## Backups

The event store is the single source of truth. Back it up:

```bash
python scripts/backup_eventstore.py            # -> data/backups/events-<ts>.log
```

Safe to run while the engine is live (append-only log; read-only copy).
Restore by stopping the process and copying a backup to `ENGINE_STORE_PATH`.

## Pre-deploy validation

```bash
python scripts/validate_env.py     # fails fast on bad config/secrets/network
python scripts/smoke_test.py       # in-process end-to-end check
```

## Common issues

- **`SecretsStartupError` on boot** — `TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1`
  is unset.
- **`MissingDeploymentSettingError`** — live mode without
  `TURTLE_DEPLOYMENT_ACCOUNT_ADDRESS`.
- **`EventStoreLockError`** — two processes share one `ENGINE_STORE_PATH`.
  Run one engine per store (and one engine per venue account).
- **Control endpoints return 401** — `API_KEY` is set; supply it.
- **Control endpoints open (warning in logs)** — `API_KEY` is unset; set it.
