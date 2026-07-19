# Production Readiness Checklist

## Before first deploy
- [ ] `python -m unittest discover -s tests` is green.
- [ ] `python scripts/validate_env.py` passes with production env.
- [ ] `python scripts/smoke_test.py` passes.
- [ ] `API_KEY` is set to a strong secret (control endpoints protected).
- [ ] `TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1` set from a secret store,
      never committed.
- [ ] Durable volume mounted at the `ENGINE_STORE_PATH` parent (Railway
      volume at `/app/data`).
- [ ] One engine process per venue account, one process per event store.

## Before enabling LIVE trading
- [ ] `ENGINE_CONFIG_PATH` points at a `mode = "live"` config.
- [ ] `TURTLE_DEPLOYMENT_ACCOUNT_ADDRESS` set (public wallet address).
- [ ] `TURTLE_SECRET_HYPERLIQUID_WALLET_KEY_V1` set (EIP-712 signing key).
- [ ] `network` in the config matches the wallet's network (validated at
      build; mismatch fails fast).
- [ ] Risk limits reviewed: `RISK_MAX_LEVERAGE`, `RISK_MIN_LIQ_BUFFER_PCT`,
      `RISK_MAX_FUNDING_RATE_ABS`, `RISK_MAX_CORRELATED_POSITIONS`,
      `RISK_MAX_STALE_DATA_SECONDS`.
- [ ] `CYCLE_MAINTENANCE_MARGIN_RATE` / `CYCLE_TARGET_LEVERAGE` reviewed.
- [ ] A strategy has been registered (else the engine reconciles but never
      trades — intentional safe default).
- [ ] Emergency stop tested (dashboard button / `POST /control/emergency-stop`
      / Telegram `/stop`).

## Observability
- [ ] `/metrics` scraped by Prometheus (or Railway metrics).
- [ ] Logs shipped (`LOG_FORMAT=json`).
- [ ] Telegram alerts configured (optional) and `/health` reachable from
      phone.

## Ongoing
- [ ] Scheduled `scripts/backup_eventstore.py`.
- [ ] Watch `turtle_reconciliation_matches` = 1 and
      `turtle_kill_switch_active` = 0.
- [ ] Restart policy in place (`railway.json` / compose `restart:
      unless-stopped`).

## Safety invariants (enforced by the engine, not the app)
- Mutations are `UNSAFE_NEVER_AUTO_RETRY` — the worker never re-submits.
- Persist-before-transmit — order mappings are fsync-durable before an
  order can reach the venue.
- Emergency stop is one-way for the running process.
- Reconciliation runs every cycle before any new decision.
