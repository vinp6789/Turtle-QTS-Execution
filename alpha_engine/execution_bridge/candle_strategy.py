"""ApprovedCandleAlphaStrategy: the generic candle-derived execution bridge.

A SIBLING of ApprovedFundingAlphaStrategy, not a replacement and not a
generalisation of it. The funding bridge is the only code path in this
repository that has ever been cleared to place live orders; widening it
to dispatch by family would put that path at regression risk for no
benefit. Constitution Section 5 -- "New capability is a new module,
package, or function -- never a rewrite" -- points at exactly this
choice. `strategy.py` is untouched by this file.

WHY THIS CLASS CAN EXIST AT ALL. strategy.py's docstring explains that
the bridge served the funding family only because Open Interest was not
on the sanctioned StrategyContext surface and fetching it inside a
Strategy would break purity. The D6 context extension put OHLCV candles
ON that surface (MarketDataView.get_candles), so a candle-derived family
is now reachable through exactly the same purity contract: every input
comes from `context`, no I/O of our own, no hidden state.

ONE EXIT POLICY FOR ALL CANDLE FAMILIES. Every family served here is
volatility-normalised by construction, so ATR-multiple exits are the
shared policy rather than a per-family choice. A future family needing
genuinely different exit geometry is a different acquisition pattern and
belongs in its own bridge, not in a branch here.

ATR-BASED EXITS, AND WHY THEY ARE STILL "DECLARED, NEVER FABRICATED".
The funding bridge derives stop/T1/T2 from FIXED fractions of mark. This
strategy's feature is ATR-normalised, so a fixed percentage stop would
re-introduce the scale dependence the feature exists to remove: 2% is a
wide stop on BTC and a tight one on SOL. Exits are therefore fixed
MULTIPLES OF ATR, pre-registered in the specification exactly as the
fractions are:

    atr_stop_mult   (required)   stop distance = atr_stop_mult * ATR
    atr_t1_mult     (optional)   T1 distance   = atr_t1_mult   * ATR
    atr_t2_mult     (optional)   T2 distance   = atr_t2_mult   * ATR

The multiples come from the frozen specification and the ATR comes from
the same candles the signal was computed on. Nothing is invented here.
Distances are converted to an effective fraction of mark and run through
the SAME geometry and the SAME degenerate-geometry refusal the funding
bridge uses -- an extreme ATR refuses the intent rather than clamping it.

DIAGNOSTICS ARE OBSERVED, NEVER CONSULTED. Every evaluation logs the
feature value, ATR, and the resulting stop/TP distances. That record
exists for later analysis only: no branch in this file reads any of it. The trading decision is a pure function of
(feature value, threshold, direction_convention) and the exit geometry a
pure function of (ATR, pre-registered multiples, mark).
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

from exchange_adapter import CandleInterval, OrderSide, OrderType, TimeInForce
from trading_system.strategy import Strategy, StrategyContext, TradeIntent

from .._time import parse_utc
from ..candidates import CandidateSpecification, SignalDirection, get_candidate_type
from ..features import ATR_PERIOD, atr_from_candles
from ..portfolio import select_signals
from ..registry import ExperimentRegistry
from ..watchlist import Watchlist
from .errors import ExecutionBridgeError

_logger = logging.getLogger(__name__)

STRATEGY_NAME = "alpha_engine_approved_candle_v1"

# The bar size the feature is calibrated on. Not a parameter: changing it
# changes what the feature measures, which is a new feature version.
CANDLE_INTERVAL = CandleInterval.H1


def _multiple(spec: CandidateSpecification, key: str, *, required: bool) -> Optional[Decimal]:
    """Same discipline as strategy.py's _fraction: a risk level is read
    from the pre-registered specification or refused -- never defaulted."""
    raw = spec.parameters.get(key)
    if raw is None:
        if required:
            raise ExecutionBridgeError(
                f"specification {spec.name!r} v{spec.version} is missing parameters[{key!r}] -- "
                "the bridge never fabricates a risk level; declare it in the pre-registered "
                "specification"
            )
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise ExecutionBridgeError(
            f"parameters[{key!r}] must be a string-encoded decimal, got {raw!r}"
        )
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ExecutionBridgeError(f"parameters[{key!r}] {raw!r} is not a valid decimal") from exc
    if value <= 0:
        raise ExecutionBridgeError(f"parameters[{key!r}] must be > 0, got {value}")
    return value


class ApprovedCandleAlphaStrategy(Strategy):
    """Evaluates governance-APPROVED CANDLE-DERIVED specifications live,
    entirely through the sanctioned StrategyContext surface.

    Family-agnostic by construction: it imports no feature, no candidate
    and no family name. Everything is resolved through the candidate
    catalog, so a new candle strategy needs only a feature, a candidate,
    a catalog entry and a specification -- never a change to this file."""

    def __init__(
        self,
        specifications: Tuple[CandidateSpecification, ...],
        registry: Optional[ExperimentRegistry] = None,
        watchlist: Optional[Watchlist] = None,
    ):
        if not isinstance(specifications, tuple) or not specifications:
            raise ExecutionBridgeError("specifications must be a non-empty tuple")
        if watchlist is not None and not isinstance(watchlist, Watchlist):
            raise ExecutionBridgeError(
                f"watchlist must be a Watchlist or None, got {type(watchlist).__name__}"
            )
        for spec in specifications:
            if not isinstance(spec, CandidateSpecification):
                raise ExecutionBridgeError(
                    f"every specification must be a CandidateSpecification, "
                    f"got {type(spec).__name__}"
                )
            entry = get_candidate_type(spec.name)
            if entry.feature_fn is None:
                raise ExecutionBridgeError(
                    f"specification {spec.name!r} is not a candle-derived family -- its "
                    "catalog entry declares no feature_fn. This bridge serves only families "
                    "whose feature is computed from candles; single-reading families "
                    "(funding, open interest) have their own bridge."
                )
            # Validate risk levels at CONSTRUCTION, so a malformed
            # specification fails loudly at wiring time rather than
            # silently producing no intents in production.
            _multiple(spec, "atr_stop_mult", required=True)
            _multiple(spec, "atr_t1_mult", required=False)
            _multiple(spec, "atr_t2_mult", required=False)
            if watchlist is not None:
                outside = [s.value for s in spec.universe if s not in watchlist]
                if outside:
                    raise ExecutionBridgeError(
                        f"specification {spec.name!r} v{spec.version} reaches outside the "
                        f"watchlist: {outside}"
                    )
        self._specifications = specifications
        self._registry = registry
        self._watchlist = watchlist
        self._last_evaluated_at: Dict[Tuple[str, str], str] = {}

    @property
    def name(self) -> str:
        """Stable across restarts for the same configuration -- the
        execution layer uses it to attribute an order back to the
        strategy that proposed it. A PROPERTY, matching the ABC."""
        return STRATEGY_NAME

    def _live_specifications(self) -> Tuple[CandidateSpecification, ...]:
        """A1, same semantics as the funding bridge: with a registry, only
        specifications matching a CURRENTLY APPROVED/SHAKEDOWN/
        FULL_PRODUCTION experiment survive, re-derived every cycle."""
        if self._registry is None:
            return self._specifications
        from ..governance import approved_experiments  # local: avoids import cycle

        live_dicts = [dict(r.specification) for r in approved_experiments(self._registry)]
        live = tuple(
            spec for spec in self._specifications
            if spec.to_specification_dict() in live_dicts
        )
        for spec in self._specifications:
            if spec not in live:
                _logger.info(
                    "specification no longer live-approved, skipping this cycle: "
                    "name=%s version=%s", spec.name, spec.version,
                )
        return live

    def _is_due(self, spec: CandidateSpecification, evaluated_at_utc: str) -> bool:
        last = self._last_evaluated_at.get((spec.name, spec.version))
        if last is None:
            return True
        elapsed = (parse_utc(evaluated_at_utc) - parse_utc(last)).total_seconds()
        return elapsed >= spec.cadence_seconds

    def generate_intents(self, context: StrategyContext) -> Tuple[TradeIntent, ...]:
        context_symbols = {s.value for s in context.universe}

        signals = []
        signal_spec: Dict[int, CandidateSpecification] = {}
        signal_atr: Dict[int, Decimal] = {}

        for spec in self._live_specifications():
            if not self._is_due(spec, context.evaluated_at_utc):
                _logger.debug(
                    "%s v%s skipped this cycle: cadence not yet due (cadence_seconds=%d)",
                    spec.name, spec.version, spec.cadence_seconds,
                )
                continue
            entry = get_candidate_type(spec.name)
            evaluate_fn = entry.evaluate_fn
            feature_fn = entry.feature_fn
            warmup = entry.warmup_periods
            for symbol in spec.universe:
                if symbol.value not in context_symbols:
                    continue  # never trade outside the context universe
                try:
                    candles = context.market_data.get_candles(
                        symbol, CANDLE_INTERVAL, warmup
                    )
                except Exception as exc:  # noqa: BLE001 -- fail-safe: no history, no signal
                    _logger.warning(
                        "no candles for %s, skipping this cycle: %s", symbol.value, exc
                    )
                    continue
                feature = feature_fn(symbol, context.evaluated_at_utc, candles)
                signal = evaluate_fn(feature, spec)
                signals.append(signal)
                signal_spec[id(signal)] = spec
                if feature.available:
                    atr = atr_from_candles(candles, ATR_PERIOD)
                    if atr is not None and atr > 0:
                        signal_atr[id(signal)] = atr
                self._log_diagnostics(spec, symbol, feature, signal_atr.get(id(signal)))
            self._last_evaluated_at[(spec.name, spec.version)] = context.evaluated_at_utc

        intents: List[TradeIntent] = []
        for signal in select_signals(tuple(signals)):
            spec = signal_spec[id(signal)]
            atr = signal_atr.get(id(signal))
            if atr is None:
                # No usable volatility scale -> no derivable exit geometry.
                # Refuse rather than fall back to a fixed percentage, which
                # would silently re-introduce scale dependence.
                _logger.warning(
                    "no ATR for %s this cycle -- refusing the intent rather than "
                    "substituting a fixed-percentage stop", signal.symbol.value,
                )
                continue
            try:
                mark = context.market_data.get_mark_price(signal.symbol).price
            except Exception:  # noqa: BLE001 -- no usable mark -> no intent
                continue
            if mark <= 0:
                continue

            stop_mult = _multiple(spec, "atr_stop_mult", required=True)
            t1_mult = _multiple(spec, "atr_t1_mult", required=False)
            t2_mult = _multiple(spec, "atr_t2_mult", required=False)

            stop_distance = stop_mult * atr
            t1_distance = t1_mult * atr if t1_mult is not None else None
            t2_distance = t2_mult * atr if t2_mult is not None else None

            if signal.direction is SignalDirection.LONG:
                side = OrderSide.BUY
                stop = mark - stop_distance
                t1 = mark + t1_distance if t1_distance is not None else None
                t2 = mark + t2_distance if t2_distance is not None else None
            else:
                side = OrderSide.SELL
                stop = mark + stop_distance
                t1 = mark - t1_distance if t1_distance is not None else None
                t2 = mark - t2_distance if t2_distance is not None else None

            # Same refusal the funding bridge applies: an extreme ATR
            # relative to mark yields degenerate geometry -- refuse, never clamp.
            if stop <= 0 or (t1 is not None and t1 <= 0) or (t2 is not None and t2 <= 0):
                _logger.warning(
                    "degenerate exit geometry for %s (mark=%s atr=%s) -- refusing intent",
                    signal.symbol.value, mark, atr,
                )
                continue

            intents.append(TradeIntent(
                symbol=signal.symbol,
                side=side,
                order_type=OrderType.LIMIT,
                time_in_force=TimeInForce.GTC,
                reduce_only=False,
                stop_price=stop,
                limit_price=mark,
                t1_price=t1,
                t2_price=t2,
            ))
        return tuple(intents)

    @staticmethod
    def _log_diagnostics(spec, symbol, feature, atr) -> None:
        """Observation only. NOTHING in generate_intents reads this.

        Deliberately family-agnostic: it records the feature's own scalar
        and the shared exit inputs, never a family's internal indicator
        components. A family that wants richer diagnostics logs them from
        its own feature module, where it owns the meaning."""
        if not feature.available:
            _logger.info(
                "signal_diagnostics symbol=%s spec=%s/%s feature=%s available=false reason=%s",
                symbol.value, spec.name, spec.version, feature.feature_name, feature.reason,
            )
            return
        stop_mult = spec.parameters.get("atr_stop_mult")
        t1_mult = spec.parameters.get("atr_t1_mult")
        _logger.info(
            "signal_diagnostics symbol=%s spec=%s/%s feature=%s feature_value=%s "
            "atr=%s atr_stop_distance=%s atr_tp_distance=%s",
            symbol.value, spec.name, spec.version, feature.feature_name, feature.value, atr,
            (Decimal(stop_mult) * atr) if (stop_mult and atr) else None,
            (Decimal(t1_mult) * atr) if (t1_mult and atr) else None,
        )
