"""Application / interface layer for the Turtle Execution Engine.

Everything under `app/` is the PRODUCTIZATION boundary: HTTP (FastAPI),
Telegram, dashboard serving, background worker, logging, metrics,
environment/config loading, and deployment glue. It sits strictly ABOVE
the frozen engine (Modules 1-10), composition_root, orchestration, and
trading_system, and depends on them only through their public APIs.

Directional rule (never violated): nothing under app/ is imported by any
frozen module or by trading_system -- the engine has no knowledge of HTTP,
Telegram, HTML, Railway, or Docker. This package is the ONLY place those
concerns live.

Sub-packages:
    app.runtime        -- env/config loading, engine construction, shared
                          AppState, background cycle worker
    app.observability  -- structured logging, Prometheus-format metrics
    app.api            -- FastAPI application, routers, schemas, service
                          layer, dashboard/static serving
    app.telegram       -- command router + notification service (bot is a
                          thin polling adapter over a pure command core)
"""
