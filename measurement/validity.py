"""Metric validity: does this number mean anything yet?

A metric can be computable and still be meaningless. The scoreboard's
first run reported a Sharpe of 340.39 from ten cycles spanning two
minutes -- arithmetically correct, and pure noise. This module makes that
condition explicit on EVERY metric instead of leaving a reader to notice.

NOT A SECOND SCOREBOARD, AND NOT A SECOND METRICS ENGINE. No formula
lives here. Validity is decided from the SHAPE of the data (how many
observations, how much elapsed time, how many wins and losses), never
from a metric's value.

WHY NOT REUSE CriterionOutcome. alpha_engine.validation.CriterionOutcome
(PASS/FAIL/NOT_EVALUATED) answers a different question -- "did this
metric clear its pre-registered bar?" -- and is sealed into evidence
packages. A metric can be VALID and fail its bar, or INSUFFICIENT_DATA in
which case pass/fail is meaningless. Reusing that enum would couple
research evidence to product presentation for a superficial similarity.
The PATTERN (enum + explicit reason) is reused; the object is not.

ONE DECLARATIVE TABLE, NOT PER-METRIC LOGIC. REQUIREMENTS below states
each metric's minimum data once. Adding a metric means adding a row, not
writing another branch.
"""

from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, NamedTuple, Optional


class MetricStatus(Enum):
    VALID = "VALID"
    """Enough data for the number to mean what it says."""

    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    """Computable in principle; not enough observations yet. This is NOT
    a failure -- 'we cannot tell' and 'it lost money' are different
    answers, and conflating them is a documented past error of this
    project."""

    NOT_APPLICABLE = "NOT_APPLICABLE"
    """Undefined for this data by construction -- e.g. a profit factor
    with no losing trade has no denominator. Not a shortage of data; more
    data of the same kind would not help."""


class Metric(NamedTuple):
    """One reported metric: the value, whether it means anything, and why."""

    value: Any
    status: MetricStatus
    reason: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "value": str(self.value) if isinstance(self.value, Decimal) else self.value,
            "status": self.status.value,
            "reason": self.reason,
        }


# ---------------------------------------------------------- thresholds
# Stated once, here. Every one is a judgement about when a statistic
# stops being noise, not a formula.

MIN_OBSERVATIONS_FOR_RETURN = 2      # a return needs two equity points
MIN_RETURNS_FOR_SHARPE = 30          # a std estimate from <30 points is unstable
MIN_DAYS_FOR_SHARPE = Decimal("7")   # annualising a sub-week sample is noise
MIN_DAYS_FOR_CAGR = Decimal("30")    # 10% over 2 days annualises to +35,823,253%
MIN_TRADES_FOR_TRADE_STATS = 1


class _Shape(NamedTuple):
    """What the data looks like. Never what the metrics say."""

    observations: int
    elapsed_days: Optional[Decimal]
    return_count: int
    trade_count: int
    win_count: int
    loss_count: int


def _shape(metrics: Dict[str, Any], return_count: int,
           elapsed_days: Optional[Decimal]) -> _Shape:
    return _Shape(
        observations=int(metrics.get("observations") or 0),
        elapsed_days=elapsed_days,
        return_count=return_count,
        trade_count=int(metrics.get("trade_count") or 0),
        win_count=int(metrics.get("win_count") or 0),
        loss_count=int(metrics.get("loss_count") or 0),
    )


def _needs_returns(s: _Shape) -> Optional[str]:
    if s.observations < MIN_OBSERVATIONS_FOR_RETURN:
        return f"insufficient observations ({s.observations} < {MIN_OBSERVATIONS_FOR_RETURN})"
    if s.return_count < 1:
        return "no computable returns (non-positive opening equity)"
    return None


def _needs_sharpe(s: _Shape) -> Optional[str]:
    if (r := _needs_returns(s)):
        return r
    if s.return_count < MIN_RETURNS_FOR_SHARPE:
        return f"insufficient observations ({s.return_count} returns < {MIN_RETURNS_FOR_SHARPE})"
    if s.elapsed_days is None or s.elapsed_days < MIN_DAYS_FOR_SHARPE:
        got = "unknown" if s.elapsed_days is None else f"{s.elapsed_days:.2f}d"
        return f"insufficient elapsed time ({got} < {MIN_DAYS_FOR_SHARPE}d)"
    return None


def _needs_cagr(s: _Shape) -> Optional[str]:
    if (r := _needs_returns(s)):
        return r
    if s.elapsed_days is None or s.elapsed_days < MIN_DAYS_FOR_CAGR:
        got = "unknown" if s.elapsed_days is None else f"{s.elapsed_days:.2f}d"
        return f"insufficient elapsed time ({got} < {MIN_DAYS_FOR_CAGR}d)"
    return None


def _needs_trades(s: _Shape) -> Optional[str]:
    if s.trade_count < MIN_TRADES_FOR_TRADE_STATS:
        return "no closed trades"
    return None


def _needs_wins(s: _Shape) -> Optional[str]:
    if (r := _needs_trades(s)):
        return r
    if s.win_count < 1:
        return "insufficient wins (no winning trade)"
    return None


def _needs_losses(s: _Shape) -> Optional[str]:
    if (r := _needs_trades(s)):
        return r
    if s.loss_count < 1:
        return "insufficient losses (no losing trade -- ratio has no denominator)"
    return None


def _needs_both_legs(s: _Shape) -> Optional[str]:
    return _needs_wins(s) or _needs_losses(s)


# THE DECLARATIVE TABLE. metric name -> (requirement check, is a missing
# requirement NOT_APPLICABLE rather than INSUFFICIENT_DATA?).
#
# NOT_APPLICABLE is used where more data OF THE SAME KIND would not help:
# a profit factor with zero losing trades is undefined, not under-sampled.
REQUIREMENTS: Dict[str, tuple] = {
    "total_return":        (_needs_returns, False),
    "cagr":                (_needs_cagr, False),
    "sharpe":              (_needs_sharpe, False),
    "max_drawdown":        (_needs_returns, False),
    "trade_count":         (lambda s: None, False),      # a count is always valid
    "win_rate":            (_needs_trades, False),
    "expectancy":          (_needs_trades, False),
    "average_win":         (_needs_wins, True),
    "average_loss":        (_needs_losses, True),
    "payoff_ratio":        (_needs_both_legs, True),
    "profit_factor":       (_needs_losses, True),
    "gross_profit_factor": (_needs_losses, True),
    "average_holding_seconds": (_needs_trades, False),
    "fees_paid":           (lambda s: None, False),
    "funding_paid":        (lambda s: None, False),
}


def classify(metrics: Dict[str, Any], *, return_count: int,
             elapsed_days: Optional[Decimal]) -> Dict[str, Metric]:
    """Wrap each metric with its validity. Values are passed through
    untouched -- this never recomputes, rounds or adjusts a number.

    A metric absent from REQUIREMENTS is returned VALID: the table states
    what needs a minimum, and silence means "always meaningful".
    """
    s = _shape(metrics, return_count, elapsed_days)
    out: Dict[str, Metric] = {}
    for name, value in metrics.items():
        check, na = REQUIREMENTS.get(name, (None, False))
        if check is None:
            out[name] = Metric(value, MetricStatus.VALID)
            continue
        reason = check(s)
        if reason is None:
            out[name] = Metric(value, MetricStatus.VALID)
        else:
            status = MetricStatus.NOT_APPLICABLE if na else MetricStatus.INSUFFICIENT_DATA
            out[name] = Metric(value, status, reason)
    return out


def as_dict(classified: Dict[str, Metric]) -> Dict[str, Any]:
    """{name: {value, status, reason}} -- the API's shape."""
    return {k: v.as_dict() for k, v in classified.items()}
