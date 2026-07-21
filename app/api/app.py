"""FastAPI application factory.

create_app() wires the runtime (AppState + CycleWorker) to HTTP. The engine
is built once and shared; the worker (if enabled) runs cycles on a timer;
the API only reads/serializes state and offers two protected control
actions. FastAPI auto-generates OpenAPI at /openapi.json and Swagger UI at
/docs.

Lifespan:
  startup  -> optional initial cycle (so /health is meaningful immediately),
              then start the CycleWorker if enabled.
  shutdown -> stop the worker, then release the engine (adapter disconnect +
              EventStore lock).
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.observability import configure_logging, log_event
from app.runtime import AppSettings, AppState, CycleWorker
from app.telegram import TelegramBot

_DASHBOARD_DIR = Path(__file__).resolve().parents[2] / "dashboard"

_DESCRIPTION = (
    "Interface layer for the Turtle Execution Engine. Read-only monitoring "
    "(/health, /status, /portfolio, /reports, /metrics) plus two protected "
    "control actions (/cycle/run, /control/emergency-stop). The trading "
    "engine itself is fully independent of HTTP."
)


def create_app(
    state: Optional[AppState] = None,
    worker: Optional[CycleWorker] = None,
    *,
    settings: Optional[AppSettings] = None,
    start_worker: bool = True,
    run_startup_cycle: bool = True,
) -> FastAPI:
    if state is None:
        settings = settings or AppSettings.from_env()
        configure_logging(settings.log_level, settings.log_format)
        state = AppState.create(settings)
    if worker is None:
        worker = CycleWorker(state)

    logger = logging.getLogger("turtle.app")
    if not (state.settings.api_key and state.settings.api_key.strip()):
        logger.warning(
            "API_KEY is not set: control endpoints (/cycle/run, /control/emergency-stop) are "
            "DISABLED (fail-closed, HTTP 503). Set API_KEY to enable them. Read-only monitoring is unaffected."
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.run_startup_cycle:
            try:
                app.state.app_state.run_one_cycle()
                log_event(logger, logging.INFO, "startup cycle completed",
                          cycles_run=app.state.app_state.cycles_run)
            except BaseException as exc:  # noqa: BLE001 -- never block startup on a first-cycle failure
                log_event(logger, logging.ERROR, "startup cycle failed", error=f"{type(exc).__name__}: {exc}")
        if app.state.start_worker and app.state.app_state.settings.worker_enabled:
            app.state.worker.start()
            log_event(logger, logging.INFO, "cycle worker started",
                      interval_seconds=app.state.app_state.settings.cycle_interval_seconds)
        # H5: start the Telegram polling bot when Telegram is enabled. The
        # bot's own _enabled guard makes this a no-op otherwise; config was
        # already validated fail-clear at settings load. Bot lifecycle is
        # tied to this lifespan: started here, stopped in finally.
        if app.state.telegram_bot is not None:
            app.state.telegram_bot.start()
            if app.state.telegram_bot.is_running:
                log_event(logger, logging.INFO, "telegram bot started")
        try:
            yield
        finally:
            if app.state.telegram_bot is not None:
                app.state.telegram_bot.stop()
            app.state.worker.stop()
            app.state.app_state.shutdown()
            log_event(logger, logging.INFO, "engine shut down")

    app = FastAPI(title="Turtle Execution Engine", version="1.0.0",
                  description=_DESCRIPTION, lifespan=lifespan)
    app.state.app_state = state
    app.state.worker = worker
    app.state.start_worker = start_worker
    app.state.run_startup_cycle = run_startup_cycle
    # H5: construct the bot once (cheap; no network until start()). Its own
    # _enabled guard means a disabled Telegram never polls. None only when
    # the whole feature is off, so the lifespan can skip it entirely.
    app.state.telegram_bot = (
        TelegramBot(state, state.settings) if state.settings.telegram_enabled else None
    )

    app.include_router(router)

    if state.settings.dashboard_enabled and _DASHBOARD_DIR.is_dir():
        assets = _DASHBOARD_DIR / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

        @app.get("/", include_in_schema=False)
        def dashboard_index():
            index = _DASHBOARD_DIR / "index.html"
            if index.is_file():
                return FileResponse(str(index))
            return {"message": "dashboard not built; API is at /docs"}

    return app
