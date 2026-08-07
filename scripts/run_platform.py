"""Run the trading platform WITH strategies loaded from configuration.

WHY THIS EXISTS ALONGSIDE app.main. `app.main` builds AppState with no
strategies, so the engine runs cycles and trades nothing -- which is what
it did for every run before P1. Both seams needed to fix that already
existed and had simply never been used:

    AppState.create(settings, strategies=...)   accepts them
    create_app(state=...)                       accepts a prebuilt state

So this entry point touches NO frozen module. It reads
config/strategies.toml, builds the enabled plugins through
alpha_engine.platform, and hands the result to the frozen engine.

    python -m scripts.run_platform
    STRATEGY_CONFIG_PATH=config/strategies.toml python -m scripts.run_platform

Every loaded plugin is logged with its kind and warning at startup, so an
operator can never be unaware that an engine-test plugin is emitting
orders.
"""

import logging
import os
import sys

import uvicorn

from app.api import create_app
from app.runtime import AppSettings, AppState
from app.observability import configure_logging

from alpha_engine.platform import StrategyLoadError, describe, load_strategies

_log = logging.getLogger("turtle.platform")


def main() -> int:
    settings = AppSettings.from_env()
    configure_logging(settings.log_level, settings.log_format)

    path = os.environ.get("STRATEGY_CONFIG_PATH", "config/strategies.toml")
    try:
        strategies, entries = load_strategies(path)
    except StrategyLoadError as exc:
        # Fail closed: a misconfigured strategy set must never boot into a
        # partially-loaded book.
        _log.error("strategy configuration rejected: %s", exc)
        return 2

    _log.info("loaded %d strategy plugin(s) from %s", len(strategies), path)
    for line in describe(entries).splitlines():
        _log.info("%s", line)
    for entry in entries:
        if entry.warning:
            _log.warning("%s", entry.warning)

    state = AppState.create(settings, strategies=strategies)
    app = create_app(state=state)
    uvicorn.run(app, host=settings.host, port=settings.port, log_config=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
