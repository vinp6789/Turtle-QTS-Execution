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

\* **Fail-closed (H1):** these two endpoints are **disabled (HTTP 503)**
whenever `API_KEY` is unset or whitespace — no unauthenticated caller can
run a cycle or trigger the one-way emergency stop. Setting `API_KEY`
**enables** them and requires it (constant-time compared) via `X-API-Key:
<key>` or `Authorization: Bearer <key>`; a missing/empty/wrong key then
returns 401. **Always set `API_KEY` in production.** The dashboard stores
it in the browser's localStorage. Read-only endpoints are always open.

## Monitoring from your phone

Open `/` on the deployed URL. The dashboard auto-refreshes every 5s and
shows engine/kill-switch state, portfolio, reconciliation, and reports,
plus **Run cycle** and **Emergency stop** buttons (enter the API key once).

## Emergency stop

`POST /control/emergency-stop` (or `/stop` in Telegram, or the dashboard
button) executes in fail-safe order: **(1) best-effort cancel of all
resting venue orders while signing is still valid** (H2 fix — revocation
is one-way, so anything not cancelled first would rest at the venue,
fillable but unmanageable, forever; the response reports the
venue-confirmed cancel count, and a cancel failure is surfaced but never
delays step 2), **(2) revoke all signing** via the frozen
`SigningBoundary.revoke_all()` and the wallet signer's `revoke()`, then
**(3) durably record** the stop by driving the Execution State Machine
into `EMERGENCY_KILL` (M1 fix). Consequences, all deliberate:

- Every subsequent risk evaluation returns `BLOCKED` and every cycle
  attempt is refused (`EmergencyStopActive`) — no orphan order records.
- Monitoring/dashboard/`/health` show the kill switch **active**.
- The stop **survives restart**: the kill state replays from the event
  store, so a restarted process stays stopped (previously a restart
  silently resumed trading). Read-only monitoring and fill booking keep
  working.

Resuming requires a **fresh deployment state**: a new `ENGINE_STORE_PATH`
(archive the old event log first — `scripts/backup_eventstore.py`) plus
signing configuration, matching the frozen design's "an emergency kill is
a one-way trip requiring a fresh process" (`EMERGENCY_KILL`'s only exit is
`SHUTDOWN`).

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
