"""Execution bridge (Alpha Engine R6): the one component that touches
the Execution Engine's public Strategy seam.

ApprovedFundingAlphaStrategy is a concrete trading_system.strategy.
Strategy whose generate_intents() evaluates governance-APPROVED
funding-rate-family specifications live, entirely through the sanctioned
StrategyContext surface:

  - funding rate via context.market_data.get_funding_rate (wrapped in
    the existing FundingRateProvider, with the provider's clock pinned
    to context.evaluated_at_utc -- no wall-clock read, so the strategy
    stays a deterministic function of its context);
  - mark price via context.market_data.get_mark_price (needed to place
    the stop/T1/T2 levels TradeIntent requires).

LIVENESS (audit finding A1): the specifications tuple passed at
construction was previously captured once, forever -- if governance
later froze or retired one of them, this strategy kept emitting intents
for it until the whole process restarted, silently trading a hypothesis
governance no longer stands behind. An OPTIONAL `registry` constructor
argument closes this: when supplied, every generate_intents() call
re-derives the currently live-approved subset of held specifications
fresh from the registry (the same APPROVED/SHAKEDOWN/FULL_PRODUCTION set
alpha_engine.governance.approved_experiments() already defines) before
evaluating anything that cycle. `registry` is optional and defaults to
None -- omitting it preserves the exact prior behavior (the held
specifications are trusted for the strategy's lifetime), which remains
appropriate for tests and for any deployment that reconstructs the
strategy on its own approval-refresh schedule.

CADENCE (audit finding A2): CandidateSpecification.cadence_seconds was
declared but never enforced -- every spec was evaluated on every single
generate_intents() call regardless of its own pre-registered cadence.
Each spec's due-ness is now tracked via an internal, monotonic map from
(name, version) to the last context.evaluated_at_utc at which it WAS
evaluated -- compared using alpha_engine._time.parse_utc (never a raw
string comparison, never the wall clock) against the CURRENT
context.evaluated_at_utc. A spec seen for the first time is always due.
This is instance-local mutable state, not a violation of the Strategy
purity contract (no I/O beyond context) -- it is exactly the same
"replay the same context SEQUENCE, get the same result sequence" notion
of determinism every other stateful manager in this codebase already
relies on, not "any single call is independently idempotent forever."

CANDIDATE DISPATCH (audit finding C3): evaluate_fn is now resolved via
alpha_engine.candidates.get_candidate_type() (the catalog's own lookup)
rather than a hardcoded import of FundingRateThresholdRuleCandidate --
the catalog, not this file, is the single source of truth for "which
callable evaluates the funding_rate_threshold_rule family," matching
every other catalog-driven consumer in this codebase.

WATCHLIST ENFORCEMENT (audit finding C4): alpha_engine.watchlist.Watchlist
existed but was never actually checked anywhere -- "generate alpha only
from a configurable watchlist" was a stated system objective with no
enforcement. An OPTIONAL `watchlist` constructor argument closes this
gate here (see alpha_engine.research.run_research_cycle for the other,
independent gate at research time): when supplied, every symbol in every
held specification's universe must already be a watchlist member, or
construction fails loudly. Optional and defaults to None, preserving
prior behavior for callers not yet wiring a watchlist.

WHY FUNDING-FAMILY ONLY (documented limitation, not an oversight): the
Strategy contract requires generate_intents to be a pure function of its
context, with no I/O beyond what context.market_data provides. Funding
rate IS on that sanctioned surface; Open Interest is NOT (its provider
performs its own independent HTTP fetch -- impure inside a strategy).
Emitting OI-family intents live therefore requires either an Execution
Engine context extension (a change to non-frozen-but-stable
trading_system code this project has chosen not to make without a
correctness reason) or an injected pre-fetched snapshot (hidden state
relative to the context, violating the purity contract). Until one of
those is consciously chosen, OI candidates can be researched, validated,
and approved -- but not traded live. Stated here and in the final
documentation, not silently worked around.

RISK LEVELS ARE DECLARED, NEVER FABRICATED: TradeIntent requires a
stop_price; a candidate signal carries only a direction. The bridge
derives stop/T1/T2 from the CURRENT MARK and per-specification fractions
that must be pre-registered in CandidateSpecification.parameters:
  - "stop_fraction"  (required; string decimal, 0 < f < 1)
  - "t1_fraction", "t2_fraction" (optional; string decimal > 0)
For a BUY:  stop = mark*(1-stop_fraction), t1 = mark*(1+t1_fraction), ...
For a SELL: stop = mark*(1+stop_fraction), t1 = mark*(1-t1_fraction), ...
These fractions are part of the pre-registered, governance-reviewed
hypothesis -- the bridge validates their presence and range AT
CONSTRUCTION (fail-loud configuration error), never invents defaults.

Sizing does not happen here: the Execution Engine's frozen RiskManager /
portfolio-construction stack sizes, approves, and quantizes every intent
downstream, unchanged.
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

from exchange_adapter import OrderSide, OrderType, TimeInForce
from trading_system.strategy import Strategy, StrategyContext, TradeIntent

from .._time import parse_utc
from ..candidates import (
    CandidateSpecification,
    SignalDirection,
    get_candidate_type,
)
from ..data_sources import FundingRateProvider
from ..features import FundingRateFeature
from ..portfolio import select_signals
from ..registry import ExperimentRegistry
from ..watchlist import Watchlist
from .errors import ExecutionBridgeError

_logger = logging.getLogger(__name__)

_FUNDING_FAMILY = "funding_rate_threshold_rule"
STRATEGY_NAME = "alpha_engine_approved_funding_v1"


def _fraction(spec: CandidateSpecification, key: str, *, required: bool, upper_exclusive=None):
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
        raise ExecutionBridgeError(f"parameters[{key!r}] must be a string-encoded decimal, got {raw!r}")
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ExecutionBridgeError(f"parameters[{key!r}] {raw!r} is not a valid decimal") from exc
    if value <= 0 or (upper_exclusive is not None and value >= upper_exclusive):
        bound = f" and < {upper_exclusive}" if upper_exclusive is not None else ""
        raise ExecutionBridgeError(f"parameters[{key!r}] must be > 0{bound}, got {value}")
    return value


class ApprovedFundingAlphaStrategy(Strategy):
    """Constructed with the (already governance-approved) funding-family
    specifications it may act on. Construction is fail-loud on any
    configuration problem; generate_intents() is fail-safe on any market
    data problem.

    `registry` (optional, A1): when supplied, every generate_intents()
    call re-verifies each held specification is still live-approved
    before evaluating it; when omitted (the default), the held
    specifications are trusted for the strategy's lifetime -- the exact
    prior behavior."""

    def __init__(
        self,
        specifications: Tuple[CandidateSpecification, ...],
        registry: Optional[ExperimentRegistry] = None,
        watchlist: Optional[Watchlist] = None,
    ):
        if not isinstance(specifications, tuple) or len(specifications) == 0:
            raise ExecutionBridgeError("specifications must be a non-empty tuple")
        if watchlist is not None and not isinstance(watchlist, Watchlist):
            raise ExecutionBridgeError(
                f"watchlist must be a Watchlist or None, got {type(watchlist).__name__}"
            )
        for spec in specifications:
            if not isinstance(spec, CandidateSpecification):
                raise ExecutionBridgeError(
                    f"every specification must be a CandidateSpecification, got {type(spec).__name__}"
                )
            if spec.name != _FUNDING_FAMILY:
                raise ExecutionBridgeError(
                    f"specification {spec.name!r} is not the funding-rate family -- this bridge "
                    f"serves {_FUNDING_FAMILY!r} only (see module docstring on why)"
                )
            _fraction(spec, "stop_fraction", required=True, upper_exclusive=Decimal("1"))
            _fraction(spec, "t1_fraction", required=False)
            _fraction(spec, "t2_fraction", required=False)
            if watchlist is not None:
                # C4: the Watchlist type existed but was never enforced --
                # a live-trading bridge is the second, independent gate
                # (alongside run_research_cycle) that must refuse a
                # specification reaching outside the configured watchlist.
                outside = [symbol.value for symbol in spec.universe if symbol not in watchlist]
                if outside:
                    raise ExecutionBridgeError(
                        f"specification {spec.name!r} v{spec.version} universe includes symbol(s) "
                        f"{sorted(outside)} outside watchlist {watchlist.name!r}"
                    )
        if registry is not None and not isinstance(registry, ExperimentRegistry):
            raise ExecutionBridgeError(
                f"registry must be an ExperimentRegistry or None, got {type(registry).__name__}"
            )
        self._specifications = specifications
        self._registry = registry
        self._last_evaluated_at: Dict[Tuple[str, str], str] = {}

    @property
    def name(self) -> str:
        return STRATEGY_NAME

    def _live_specifications(self) -> Tuple[CandidateSpecification, ...]:
        """A1: with no registry, every held specification is trusted (the
        prior, unconditional behavior). With a registry, only
        specifications matching a CURRENTLY APPROVED/SHAKEDOWN/
        FULL_PRODUCTION experiment's content survive -- a specification
        governance has since frozen, retired, or otherwise moved out of
        that set silently stops trading THIS cycle, no restart needed."""
        if self._registry is None:
            return self._specifications
        from ..governance import approved_experiments  # local import: avoids import cycle at package load

        live_specification_dicts = [dict(record.specification) for record in approved_experiments(self._registry)]
        live = tuple(
            spec for spec in self._specifications
            if spec.to_specification_dict() in live_specification_dicts
        )
        for spec in self._specifications:
            if spec not in live:
                _logger.info(
                    "specification no longer live-approved, skipping this cycle: name=%s version=%s",
                    spec.name, spec.version,
                )
        return live

    def _is_due(self, spec: CandidateSpecification, evaluated_at_utc: str) -> bool:
        """A2: enforces spec.cadence_seconds against context.evaluated_at_utc
        only -- never the wall clock. A specification evaluated for the
        first time is always due."""
        last = self._last_evaluated_at.get((spec.name, spec.version))
        if last is None:
            return True
        elapsed_seconds = (parse_utc(evaluated_at_utc) - parse_utc(last)).total_seconds()
        return elapsed_seconds >= spec.cadence_seconds

    def generate_intents(self, context: StrategyContext) -> Tuple[TradeIntent, ...]:
        provider = FundingRateProvider(
            context.market_data, clock=lambda: context.evaluated_at_utc,
        )
        context_symbols = {s.value for s in context.universe}
        evaluate_fn = get_candidate_type(_FUNDING_FAMILY).evaluate_fn

        signals = []
        signal_spec = {}
        for spec in self._live_specifications():
            if not self._is_due(spec, context.evaluated_at_utc):
                _logger.debug(
                    "%s v%s skipped this cycle: cadence not yet due (cadence_seconds=%d)",
                    spec.name, spec.version, spec.cadence_seconds,
                )
                continue
            for symbol in spec.universe:
                if symbol.value not in context_symbols:
                    continue  # watchlist/universe intersection: never trade outside context
                reading = provider.fetch(symbol)  # fail-safe: never raises for data problems
                feature = FundingRateFeature.compute(reading)
                signal = evaluate_fn(feature, spec)
                signals.append(signal)
                signal_spec[id(signal)] = spec
            self._last_evaluated_at[(spec.name, spec.version)] = context.evaluated_at_utc

        intents: List[TradeIntent] = []
        for signal in select_signals(tuple(signals)):
            spec = signal_spec[id(signal)]
            try:
                mark = context.market_data.get_mark_price(signal.symbol).price
            except Exception:  # noqa: BLE001 -- no usable mark -> no intent for this symbol
                continue
            if mark <= 0:
                continue
            stop_fraction = _fraction(spec, "stop_fraction", required=True, upper_exclusive=Decimal("1"))
            t1_fraction = _fraction(spec, "t1_fraction", required=False)
            t2_fraction = _fraction(spec, "t2_fraction", required=False)

            if signal.direction is SignalDirection.LONG:
                side = OrderSide.BUY
                stop = mark * (Decimal("1") - stop_fraction)
                t1 = mark * (Decimal("1") + t1_fraction) if t1_fraction is not None else None
                t2 = mark * (Decimal("1") + t2_fraction) if t2_fraction is not None else None
            else:
                side = OrderSide.SELL
                stop = mark * (Decimal("1") + stop_fraction)
                t1 = mark * (Decimal("1") - t1_fraction) if t1_fraction is not None else None
                t2 = mark * (Decimal("1") - t2_fraction) if t2_fraction is not None else None
            if stop <= 0 or (t1 is not None and t1 <= 0) or (t2 is not None and t2 <= 0):
                continue  # degenerate geometry from an extreme fraction/mark -- refuse, don't clamp

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


def load_approved_specifications(registry: ExperimentRegistry) -> Tuple[CandidateSpecification, ...]:
    """Reconstructs typed specifications for every experiment currently
    holding governance approval (APPROVED / SHAKEDOWN / FULL_PRODUCTION)
    whose family this bridge can serve (funding-rate). Deterministic
    order (governance's own created_at/id ordering). Approved
    experiments of OTHER families are skipped here -- they remain
    approved research, just not live-tradeable through this bridge (see
    module docstring)."""
    from ..governance import approved_experiments  # local import: avoids import cycle at package load

    if not isinstance(registry, ExperimentRegistry):
        raise ExecutionBridgeError(f"registry must be an ExperimentRegistry, got {type(registry).__name__}")
    specs = []
    for record in approved_experiments(registry):
        spec_dict = dict(record.specification)
        if spec_dict.get("candidate_name") != _FUNDING_FAMILY:
            continue
        specs.append(CandidateSpecification.from_specification_dict(spec_dict))
    return tuple(specs)
