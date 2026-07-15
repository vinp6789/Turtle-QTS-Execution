"""Risk Manager: a pure approval/veto module. It never generates signals,
computes conviction, calculates indicators, sizes positions, or submits
orders -- it only determines whether an already-fully-specified proposed
trade is permitted, given already-computed inputs from other frozen
modules. No filesystem access, no network access, no randomness, no
wall-clock access inside decision logic (the caller supplies
`evaluated_at_utc` explicitly), no global mutable state, no persistence.

Decision precedence (capital protection first):
  1. BLOCKED   -- kill switch active or engine stopped. Never overridden.
  2. FAIL_SAFE -- any required input is missing, stale, or nonsensical.
                  Unknown equals unsafe; never approved on incomplete data.
  3. REJECTED  -- every applicable business-rule violation is collected
                  and reported, not just the first one found.
  4. APPROVED  -- only if every check that could run, ran, and passed.
"""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from typing import Optional, Tuple

from config import RiskProfileParams
from exchange_adapter import ExchangeCapabilities, OrderType, TimeInForce
from execution_state_machine import State
from position_manager import PositionSnapshot
from portfolio_manager import PortfolioSnapshot

from .errors import RiskManagerConfigurationError
from .models import (
    CORRELATION_THRESHOLD,
    CorrelationInfo,
    Decision,
    FundingInfo,
    ReasonCode,
    RiskDecision,
    RiskManagerLimits,
    TradeRequest,
)

_BLOCKING_STATES = {
    State.SOFT_KILL: ReasonCode.KILL_SWITCH_SOFT,
    State.HARD_KILL: ReasonCode.KILL_SWITCH_HARD,
    State.EMERGENCY_KILL: ReasonCode.KILL_SWITCH_EMERGENCY,
    State.STOPPED: ReasonCode.ENGINE_STOPPED,
}


def _parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _age_seconds(evaluated_at_utc: str, data_at_utc: str) -> float:
    """Pure comparison of two given ISO timestamps -- never touches the
    real wall clock. A negative result (data timestamped after the
    evaluation moment) is itself treated as suspicious by the caller."""
    return (_parse_utc(evaluated_at_utc) - _parse_utc(data_at_utc)).total_seconds()


class RiskManager:
    """Immutable after construction. evaluate() is a pure function of its
    arguments: no shared mutable state exists to race on, so no lock is
    needed for thread-safety -- concurrent calls simply cannot interfere
    with each other."""

    def __init__(self, limits: RiskManagerLimits):
        if not isinstance(limits, RiskManagerLimits):
            raise RiskManagerConfigurationError(f"limits must be a RiskManagerLimits, got {type(limits).__name__}")
        self._limits = limits
        self._initialized = True

    def __setattr__(self, name, value):
        if getattr(self, "_initialized", False):
            raise AttributeError("RiskManager is immutable after initialization")
        object.__setattr__(self, name, value)

    @property
    def limits(self) -> RiskManagerLimits:
        return self._limits

    def evaluate(
        self,
        *,
        trade_request: TradeRequest,
        risk_profile: RiskProfileParams,
        evaluated_at_utc: str,
        kill_switch_state: Optional[State] = None,
        portfolio_snapshot: Optional[PortfolioSnapshot] = None,
        open_positions: Optional[Tuple[PositionSnapshot, ...]] = None,
        capabilities: Optional[ExchangeCapabilities] = None,
        funding_info: Optional[FundingInfo] = None,
        correlation_info: Optional[CorrelationInfo] = None,
    ) -> RiskDecision:
        if not isinstance(trade_request, TradeRequest):
            raise RiskManagerConfigurationError(f"trade_request must be a TradeRequest, got {type(trade_request).__name__}")
        if not isinstance(risk_profile, RiskProfileParams):
            raise RiskManagerConfigurationError(f"risk_profile must be a RiskProfileParams, got {type(risk_profile).__name__}")
        if risk_profile.risk_pct_per_trade <= 0 or risk_profile.heat_cap <= 0 or risk_profile.max_positions <= 0:
            raise RiskManagerConfigurationError(
                f"risk_profile has non-positive fields (risk_pct_per_trade={risk_profile.risk_pct_per_trade}, "
                f"heat_cap={risk_profile.heat_cap}, max_positions={risk_profile.max_positions}) -- "
                "RiskProfileParams has no validation of its own (Module 1 validates only its own config-file "
                "loading path), so Risk Manager must not trust an arbitrary instance blindly"
            )
        if not isinstance(evaluated_at_utc, str) or not evaluated_at_utc.strip():
            raise RiskManagerConfigurationError("evaluated_at_utc must be a non-empty ISO 8601 string")

        # --- Precedence 1: kill switch / stopped engine -- never overridden ---
        if kill_switch_state is not None and kill_switch_state in _BLOCKING_STATES:
            reason = _BLOCKING_STATES[kill_switch_state]
            return self._decision(
                Decision.BLOCKED, (reason,), (reason.value,), evaluated_at_utc,
                calculated_exposure=None, calculated_heat=None, leverage=None,
                liquidation_buffer=None, funding_estimate=None,
                audit_metadata={"kill_switch_state": kill_switch_state.value},
            )

        # --- Precedence 2: missing / stale / nonsensical required data ---
        missing_reasons = []
        violated = []
        if kill_switch_state is None:
            missing_reasons.append(ReasonCode.MISSING_REQUIRED_DATA)
            violated.append("kill_switch_state:missing")
        if portfolio_snapshot is None:
            missing_reasons.append(ReasonCode.MISSING_REQUIRED_DATA)
            violated.append("portfolio_snapshot:missing")
        if open_positions is None:
            missing_reasons.append(ReasonCode.MISSING_REQUIRED_DATA)
            violated.append("open_positions:missing")
        if capabilities is None:
            missing_reasons.append(ReasonCode.MISSING_REQUIRED_DATA)
            violated.append("capabilities:missing")
        if funding_info is None:
            missing_reasons.append(ReasonCode.MISSING_REQUIRED_DATA)
            violated.append("funding_info:missing")
        if correlation_info is None:
            missing_reasons.append(ReasonCode.MISSING_REQUIRED_DATA)
            violated.append("correlation_info:missing")
        if trade_request.estimated_liquidation_price is None:
            missing_reasons.append(ReasonCode.MISSING_REQUIRED_DATA)
            violated.append("trade_request.estimated_liquidation_price:missing")

        for label, ts in self._timestamps_to_check(portfolio_snapshot, open_positions, funding_info, correlation_info):
            age = _age_seconds(evaluated_at_utc, ts)
            if age < 0 or age > self._limits.max_stale_data_seconds:
                missing_reasons.append(ReasonCode.STALE_DATA)
                violated.append(f"{label}:stale(age={age}s)")

        if portfolio_snapshot is not None and portfolio_snapshot.equity <= 0:
            missing_reasons.append(ReasonCode.NON_POSITIVE_EQUITY)
            violated.append("portfolio_snapshot.equity:non_positive")

        if missing_reasons:
            return self._decision(
                Decision.FAIL_SAFE, tuple(missing_reasons), tuple(violated), evaluated_at_utc,
                calculated_exposure=None, calculated_heat=None, leverage=trade_request.leverage,
                liquidation_buffer=None, funding_estimate=None,
                audit_metadata={"stage": "data_verification"},
            )

        # --- Precedence 3: business-rule checks, ALL collected, none short-circuited ---
        # Pinned to a fixed precision/rounding, immune to any ambient
        # decimal.getcontext() mutation elsewhere in a larger process --
        # this function's output must depend only on its arguments.
        with localcontext() as ctx:
            ctx.prec = 28
            ctx.rounding = ROUND_HALF_EVEN

            reasons = []
            violated_limits = []

            heat_contribution = trade_request.proposed_risk_amount / portfolio_snapshot.equity
            calculated_heat = portfolio_snapshot.heat + heat_contribution
            calculated_exposure = portfolio_snapshot.exposure + trade_request.proposed_notional

            if heat_contribution > risk_profile.risk_pct_per_trade:
                reasons.append(ReasonCode.RISK_PER_TRADE_EXCEEDED)
                violated_limits.append(
                    f"risk_pct_per_trade: {heat_contribution} > {risk_profile.risk_pct_per_trade}"
                )
            if calculated_heat > risk_profile.heat_cap:
                reasons.append(ReasonCode.PORTFOLIO_HEAT_EXCEEDED)
                violated_limits.append(f"heat_cap: {calculated_heat} > {risk_profile.heat_cap}")
            if len(open_positions) >= risk_profile.max_positions:
                reasons.append(ReasonCode.MAX_POSITIONS_EXCEEDED)
                violated_limits.append(f"max_positions: {len(open_positions)} >= {risk_profile.max_positions}")
            if trade_request.proposed_margin_required > portfolio_snapshot.available_cash:
                reasons.append(ReasonCode.INSUFFICIENT_MARGIN)
                violated_limits.append(
                    f"available_cash: {trade_request.proposed_margin_required} > {portfolio_snapshot.available_cash}"
                )
            if trade_request.leverage > self._limits.max_leverage:
                reasons.append(ReasonCode.LEVERAGE_EXCEEDED)
                violated_limits.append(f"max_leverage: {trade_request.leverage} > {self._limits.max_leverage}")

            liquidation_buffer = self._liquidation_buffer(trade_request)
            stop_distance = abs(trade_request.entry_price - trade_request.stop_price)
            min_required_buffer = self._limits.min_liquidation_buffer_pct * stop_distance
            if liquidation_buffer is None or liquidation_buffer < min_required_buffer:
                reasons.append(ReasonCode.LIQUIDATION_TOO_CLOSE)
                violated_limits.append(f"liquidation_buffer: {liquidation_buffer} < {min_required_buffer}")

            # Signed cost to the PROPOSED side, not raw magnitude: standard
            # perpetual convention is funding_rate > 0 means longs pay
            # shorts. A short with a large positive rate is receiving
            # income, not paying it, and must not be rejected as "too
            # expensive" -- only an actual cost above the limit should be.
            funding_cost_rate = funding_info.funding_rate if trade_request.side.value == "BUY" else -funding_info.funding_rate
            funding_estimate = funding_cost_rate * trade_request.proposed_notional
            if funding_cost_rate > self._limits.max_funding_rate_abs:
                reasons.append(ReasonCode.FUNDING_RATE_TOO_HIGH)
                violated_limits.append(
                    f"max_funding_rate_abs: {funding_cost_rate} > {self._limits.max_funding_rate_abs}"
                )

            correlated_count = sum(
                1 for entry in correlation_info.entries if abs(entry.correlation) >= CORRELATION_THRESHOLD
            )
            if correlated_count > self._limits.max_correlated_positions:
                reasons.append(ReasonCode.CORRELATION_LIMIT_EXCEEDED)
                violated_limits.append(
                    f"max_correlated_positions: {correlated_count} > {self._limits.max_correlated_positions}"
                )

            capability_violation = self._capability_violation(trade_request, capabilities)
            if capability_violation is not None:
                reasons.append(ReasonCode.EXCHANGE_CAPABILITY_UNSUPPORTED)
                violated_limits.append(capability_violation)

            if reasons:
                return self._decision(
                    Decision.REJECTED, tuple(reasons), tuple(violated_limits), evaluated_at_utc,
                    calculated_exposure=calculated_exposure, calculated_heat=calculated_heat,
                    leverage=trade_request.leverage, liquidation_buffer=liquidation_buffer,
                    funding_estimate=funding_estimate, audit_metadata={"stage": "business_rules"},
                )

            # --- Precedence 4: approved ---
            return self._decision(
                Decision.APPROVED, (ReasonCode.OK,), (), evaluated_at_utc,
                calculated_exposure=calculated_exposure, calculated_heat=calculated_heat,
                leverage=trade_request.leverage, liquidation_buffer=liquidation_buffer,
                funding_estimate=funding_estimate, audit_metadata={"stage": "approved"},
            )

    # -- helpers --

    @staticmethod
    def _timestamps_to_check(portfolio_snapshot, open_positions, funding_info, correlation_info):
        pairs = []
        if portfolio_snapshot is not None:
            pairs.append(("portfolio_snapshot", portfolio_snapshot.updated_at_utc))
        if open_positions is not None:
            for pos in open_positions:
                pairs.append((f"position:{pos.position_id}", pos.updated_at_utc))
        if funding_info is not None:
            pairs.append(("funding_info", funding_info.as_of_utc))
        if correlation_info is not None:
            pairs.append(("correlation_info", correlation_info.as_of_utc))
        return pairs

    @staticmethod
    def _liquidation_buffer(trade_request: TradeRequest) -> Optional[Decimal]:
        if trade_request.estimated_liquidation_price is None:
            return None
        # Long: liquidation must sit beyond the stop (further from entry).
        # Short: liquidation must sit beyond the stop on the other side.
        if trade_request.side.value == "BUY":
            return trade_request.stop_price - trade_request.estimated_liquidation_price
        return trade_request.estimated_liquidation_price - trade_request.stop_price

    @staticmethod
    def _capability_violation(trade_request: TradeRequest, capabilities: ExchangeCapabilities) -> Optional[str]:
        if trade_request.order_type is OrderType.MARKET and not capabilities.supports_market_orders:
            return "order_type:MARKET not supported"
        if trade_request.order_type is OrderType.LIMIT and not capabilities.supports_limit_orders:
            return "order_type:LIMIT not supported"
        if trade_request.reduce_only and not capabilities.supports_reduce_only:
            return "reduce_only not supported"
        if trade_request.time_in_force is TimeInForce.IOC and not capabilities.supports_ioc:
            return "time_in_force:IOC not supported"
        if trade_request.time_in_force is TimeInForce.FOK and not capabilities.supports_fok:
            return "time_in_force:FOK not supported"
        if trade_request.time_in_force is TimeInForce.POST_ONLY and not capabilities.supports_post_only:
            return "time_in_force:POST_ONLY not supported"
        return None

    def _decision(
        self, decision, reason_codes, violated_limits, evaluated_at_utc,
        *, calculated_exposure, calculated_heat, leverage, liquidation_buffer, funding_estimate, audit_metadata,
    ) -> RiskDecision:
        return RiskDecision(
            decision=decision,
            reason_codes=reason_codes,
            violated_limits=violated_limits,
            calculated_exposure=calculated_exposure,
            calculated_heat=calculated_heat,
            leverage=leverage,
            liquidation_buffer=liquidation_buffer,
            funding_estimate=funding_estimate,
            timestamp_utc=evaluated_at_utc,
            audit_metadata=audit_metadata,
        )

    def __repr__(self) -> str:
        return f"RiskManager(limits={self._limits!r})"

    __str__ = __repr__
