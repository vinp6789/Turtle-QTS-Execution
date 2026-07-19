# Deployment Guide

The Turtle Execution Engine ships as a single application that runs
**identically** on a Windows laptop, Docker, a VPS, or Railway. The only
thing that changes between environments is **environment variables** — no
code changes, no rebuilds.

```
Engine (Modules 1–10, frozen)
  → composition_root → orchestration → trading_system
    → app.runtime  (engine build + AppState + background cycle worker)
      → app.api    (FastAPI: REST + OpenAPI + dashboard + metrics)
      → app.telegram (bot + notifications)
```

The engine is never aware of HTTP/Telegram/Docker/Railway. `app/` is the
only layer that is.

---

## 1. Run locally (Windows)

```powershell
pip install -r requirements-app.txt
powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1
```

macOS/Linux:

```bash
pip install -r requirements-app.txt
bash scripts/run_local.sh
```

Then open:
- Dashboard (phone-friendly): http://localhost:8000/
- API docs (Swagger): http://localhost:8000/docs
- Health: http://localhost:8000/health

Defaults to **paper mode** (in-memory MockExchangeAdapter, no network, no
real orders). The only variable you must set is a signing secret; the run
scripts set a paper default if none is provided.

## 2. Run with Docker

```bash
cp .env.example .env      # edit as needed
docker compose up --build
```

State (the event store + logs) persists in the `turtle-data` volume.

## 3. Deploy on Railway

1. Push this repo to GitHub.
2. In Railway: **New Project → Deploy from GitHub repo**. Railway detects
   `Dockerfile` / `railway.json` and builds automatically.
3. Add a **Volume** mounted at `/app/data` (durable event store).
4. Set environment variables (Railway dashboard → Variables) — at minimum:
   - `TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1`
   - `API_KEY` (protects control endpoints — **set this in production**)
   - For live trading: `ENGINE_CONFIG_PATH=deploy/engine.live.toml`,
     `TURTLE_DEPLOYMENT_ACCOUNT_ADDRESS`,
     `TURTLE_SECRET_HYPERLIQUID_WALLET_KEY_V1`.
5. Railway injects `PORT` automatically; the app reads it. Health checks
   hit `/health`.

Open `https://<your-app>.up.railway.app/` on your phone to monitor.

## 4. Paper → Live

Live mode is entirely a configuration change:
1. Copy `deploy/engine.paper.toml` → `deploy/engine.live.toml`, set
   `[environment] mode = "live"` and the desired `network`.
2. Set `ENGINE_CONFIG_PATH=deploy/engine.live.toml`.
3. Provide `TURTLE_DEPLOYMENT_ACCOUNT_ADDRESS` and
   `TURTLE_SECRET_HYPERLIQUID_WALLET_KEY_V1`.
4. Run `python scripts/validate_env.py` — it fails fast if anything is
   missing or the signer/network is inconsistent.

> No strategy is bundled. With no strategy registered, the worker runs
> startup → synchronization → reconciliation each cycle but places **no
> orders**. This is the safe production default until a strategy is
> explicitly registered in `AppState.strategies`.

## 5. Environment variables

See [`.env.example`](../.env.example) for the full list with defaults.
Every setting has a safe default except the signing secret.
