"""THE launcher. Every supported launch path arrives here.

Docker, run_local.ps1, run_local.sh and a developer shell all invoke this
module; they differ only in environment variables. There is no second
runtime tree, and `app.main` remains only as the ASGI object for process
managers that import one (uvicorn app.main:app) -- it builds the same
AppState through the same constructor.

    python -m scripts.run_platform
    EXECUTION_MODE=simulated python -m scripts.run_platform
    STRATEGY_CONFIG_PATH=config/strategies.toml python -m scripts.run_platform

CONSTRUCTION IS NOT DUPLICATED HERE. Every mode -- paper, simulated, live
-- is built by AppState.create(). This module chooses a transport and a
strategy set; it never assembles an engine. It previously carried a copy
of that constructor for the simulated path, and the copy silently lost
the durable emergency-stop restoration that AppState.create() performs.
That is why the transport_factory seam exists.

Every loaded plugin is logged with its kind and warning at startup, so an
operator can never be unaware that an engine-test plugin is emitting
orders.
"""

import logging
import os
import sys

import uvicorn

from app.api import create_app
from app.observability import configure_logging
from app.runtime import AppSettings, AppState

from alpha_engine.platform import StrategyLoadError, describe, load_strategies
from execution_sim import SimulatedTransport
from measurement import EquityLog, build_all, to_json

_log = logging.getLogger("turtle.platform")


def _load_env_file(path: str) -> int:
    """Populate os.environ from a KEY=VALUE file. EXPLICIT AND OPT-IN.

    NEVER AUTO-DISCOVERED, and this is a safety property rather than a
    preference. config/loader.py:81 applies TURTLE_EXEC_MODE as an
    UNCONDITIONAL override of the config file's mode, and this
    repository's .env sets it to "live". Auto-loading .env would
    therefore have silently converted every paper launch -- including
    Docker's default -- into a live Hyperliquid engine bound to the real
    venue. Loading happens only when ENV_FILE is set explicitly.

    A variable already present in the environment always wins, so an
    explicit `KEY=value python -m scripts.run_platform` can never be
    overridden by a file.

    This is not a configuration system. It populates os.environ, which
    AppSettings.from_env() and config.load_config already read; no value
    is interpreted here and no precedence is invented.
    """
    loaded = 0
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key in os.environ:          # explicit environment wins
                continue
            os.environ[key] = value.strip().strip('"').strip("'")
            loaded += 1
    return loaded


def _transport_factory():
    """The SimulatedTransport factory, or None for the real venue.

    Returning None is what every non-simulated launch does, and None is
    exactly what build_engine received before this seam existed -- so the
    paper and live paths are bit-for-bit what they always were.
    """
    if os.environ.get("EXECUTION_MODE", "").lower() != "simulated":
        return None

    def factory(base_url: str) -> SimulatedTransport:
        _log.warning("EXECUTION IS SIMULATED -- real market data, local deterministic fills")
        return SimulatedTransport(base_url=base_url)

    return factory


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


def _attach_attribution(state, entries):
    """Persist WHY each cycle decided what it decided.

    Wraps run_one_cycle at the SAME seam the equity log already uses --
    no new execution path, and the trading path never depends on this.
    Every value written is already on the CycleResult that run_cycle
    returns and would otherwise discard, including the vetoed intents.

    FAILURE IS VISIBLE, NEVER SILENT. Execution must not depend on
    attribution persistence, so a failure is caught -- but it then emits
    a HEALTH_ALERT naming the cycle and sets attribution_degraded, so the
    cycle can never be presented as fully auditable.
    """
    from event_store import EventType

    from alpha_engine.platform.attributed_strategy import AttributedStrategy, StrategyIdentity
    from measurement import attribution

    by_name = {e.name: e for e in entries}
    wrapped = []
    for s in state.strategies:
        entry = by_name.get(s.name)
        if entry is None:
            # Fall back on the plugin list positionally only when a name
            # does not match; kind is still registry-sourced, never guessed.
            entry = list(by_name.values())[len(wrapped)] if len(wrapped) < len(by_name) else None
        identity = StrategyIdentity(
            strategy_id=entry.name if entry else s.name,
            strategy_version=str(getattr(s, "version", "")),
            strategy_kind=entry.kind.value if entry else "UNKNOWN",
        )
        wrapped.append(AttributedStrategy(s, identity))
    state.strategies = tuple(wrapped)

    inner = state.run_one_cycle

    def wrapped_cycle():
        result = inner()
        try:
            thesis = {}
            features = {}
            for s in state.strategies:
                target = s.inner if isinstance(s, AttributedStrategy) else s
                t = getattr(target, "thesis", None)
                if t:
                    thesis[s.identity.strategy_id if isinstance(s, AttributedStrategy) else s.name] = t
                features.update(getattr(target, "features_by_intent", {}) or {})
            failure = attribution.record(
                state.engine.event_store, result, state.strategies,
                thesis_by_strategy=thesis, features_by_intent=features)
        except Exception as exc:                       # noqa: BLE001
            failure = f"{type(exc).__name__}: {exc}"
        if failure:
            state.attribution_degraded = True
            _log.error("ATTRIBUTION DEGRADED for cycle %s: %s",
                       getattr(result, "evaluated_at_utc", "?"), failure)
            try:
                state.engine.event_store.append(EventType.HEALTH_ALERT, {
                    "source": "attribution", "severity": "DEGRADED",
                    "cycle_evaluated_at_utc": getattr(result, "evaluated_at_utc", None),
                    "error": failure,
                })
            except Exception:                          # noqa: BLE001
                pass                                   # never fail a cycle
        return result

    state.run_one_cycle = wrapped_cycle
    state.attribution_degraded = False
    _log.info("attribution -> TRADE_ATTRIBUTION events in the engine event store")
    return state


def _attach_scoreboard_api(app, state, entries):
    """GET /scoreboard -- the business report, as JSON.

    ADDITIVE: a router added to the already-built app; app/api is frozen
    and untouched. The endpoint CALCULATES NOTHING -- it calls
    measurement.build_all() and serialises. Every value, status and
    reason originates in the metrics engine.
    """
    from fastapi import APIRouter

    router = APIRouter()

    @router.get("/scoreboard", tags=["monitoring"])
    def scoreboard():
        return to_json(build_all(
            strategies=state.strategies, equity_log=state.equity_log,
            store=state.engine.event_store,
            position_manager=state.engine.position_manager, entries=entries))

    @router.get("/attribution/health", tags=["monitoring"])
    def attribution_health():
        """Whether every cycle so far is fully auditable. ADDITIVE: the
        frozen /health is untouched. A consumer must not treat cycles as
        auditable while degraded is true."""
        degraded = bool(getattr(state, "attribution_degraded", False))
        return {"attribution_degraded": degraded,
                "fully_auditable": not degraded,
                "cycles_run": state.cycles_run}

    app.include_router(router)
    _log.info("scoreboard API -> GET /scoreboard")
    return app


def main() -> int:
    # Before AppSettings.from_env(), because that is what reads the result.
    env_file = os.environ.get("ENV_FILE")
    if env_file:
        count = _load_env_file(env_file)

    settings = AppSettings.from_env()
    configure_logging(settings.log_level, settings.log_format)
    if env_file:
        _log.warning("loaded %d variable(s) from %s -- note that TURTLE_EXEC_MODE "
                     "in such a file OVERRIDES the config file's mode", count, env_file)

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

    # ONE construction path for every mode. The transport is the only
    # thing that varies, and it varies through a parameter -- not a branch
    # into a second constructor.
    state = AppState.create(
        settings, strategies=strategies, transport_factory=_transport_factory())
    _attach_attribution(state, entries)
    _attach_equity_log(state, os.environ.get("EQUITY_LOG_PATH", "data/measurement/equity.jsonl"))
    app = create_app(state=state)
    _attach_scoreboard_api(app, state, entries)
    uvicorn.run(app, host=settings.host, port=settings.port, log_config=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
