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
from pathlib import Path

import uvicorn

from app.api import create_app
from app.observability import configure_logging
from app.runtime import AppSettings, AppState
from app.runtime.accounting import AccountingSync
from app.runtime.engine_builder import _risk_limits, build_engine_from_settings

from composition_root import build_engine
from composition_root.deployment import load_deployment_settings
from config import load_config
from exchange_adapter import Symbol
from hyperliquid_adapter.transport import MAINNET_BASE_URL, TESTNET_BASE_URL

from alpha_engine.platform import StrategyLoadError, describe, load_strategies
from execution_sim import SimulatedTransport
from measurement import EquityLog

_log = logging.getLogger("turtle.platform")


def _simulated_state(settings, strategies):
    """Build the engine with SimulatedTransport injected.

    Replicates build_engine_from_settings, differing in exactly one
    argument -- transport= -- because that function does not expose the
    seam and is frozen. The adapter, order lifecycle, position tracking,
    event store and accounting are the REAL ones; only the venue's
    answers are simulated.
    """
    env = os.environ
    config = load_config(settings.engine_config_path, env=env)
    deployment = load_deployment_settings(env)
    store_path = Path(settings.event_store_path)
    store_path.parent.mkdir(parents=True, exist_ok=True)

    base_url = MAINNET_BASE_URL if config.exchange.network == "mainnet" else TESTNET_BASE_URL
    transport = SimulatedTransport(base_url=base_url)
    _log.warning("EXECUTION IS SIMULATED -- real market data, local deterministic fills")

    engine = build_engine(
        config=config, deployment=deployment, risk_limits=_risk_limits(settings),
        event_store_path=store_path, env=env, transport=transport,
    )
    if settings.initial_deposit > 0:
        engine.portfolio_manager.deposit(
            settings.initial_deposit, request_id="app_accounting:initial-deposit:v1")
    state = AppState(
        settings=settings, engine=engine,
        universe=tuple(Symbol(s) for s in config.universe.symbols),
        risk_profile=config.risk.active_profile_params,
        strategies=tuple(strategies),
        accounting=AccountingSync(engine, target_leverage=settings.target_leverage),
    )
    state.simulated_transport = transport      # for equity persistence
    return state


def _attach_equity_log(state, path):
    """Record one measurement row per cycle.

    Wraps run_one_cycle rather than modifying it: AppState is frozen, and
    the recording is a pure read of the snapshot AccountingSync has
    already refreshed. A failure to RECORD must never fail a CYCLE -- the
    trading path does not depend on measurement.
    """
    log = EquityLog(path)
    inner = state.run_one_cycle
    names = tuple(s.name for s in state.strategies)

    def wrapped():
        result = inner()
        try:
            log.record(state.engine.portfolio_manager.get_snapshot(),
                       cycle_seq=state.cycles_run, strategy_names=names)
        except Exception as exc:                      # noqa: BLE001
            _log.error("equity row not recorded: %s: %s", type(exc).__name__, exc)
        return result

    state.run_one_cycle = wrapped
    state.equity_log = log
    _log.info("equity history -> %s (resuming at cycle_seq %d)", log.path, log.last_cycle_seq)
    return state


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

    if os.environ.get("EXECUTION_MODE", "").lower() == "simulated":
        state = _simulated_state(settings, strategies)
    else:
        state = AppState.create(settings, strategies=strategies)
    _attach_equity_log(state, os.environ.get("EQUITY_LOG_PATH", "data/measurement/equity.jsonl"))
    app = create_app(state=state)
    uvicorn.run(app, host=settings.host, port=settings.port, log_config=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
