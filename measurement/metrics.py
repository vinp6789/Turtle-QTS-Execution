"""THE business-performance engine. The only one in Project Alpha.

Every strategy, paper run, testnet run and future live deployment obtains
business metrics from here. Dashboards, scoreboards, APIs, reports and
research must consume this component rather than implement their own
arithmetic -- a second implementation is a defect, not an optimisation.

WHAT IS REUSED, NOT REWRITTEN
  profit factor      -- alpha_engine.feasibility.profit_factor, already a
                        pure tested function over a payoff list. Imported,
                        not reimplemented.
  the VDA tax bar    -- alpha_engine.feasibility.MIN_GROSS_PROFIT_FACTOR
  trade records      -- position_manager's own PositionSnapshot fields
                        (realized_pnl, fees_paid, funding_paid,
                        created_at_utc, updated_at_utc). No trade is
                        reconstructed here; closed positions ARE the trades.
  equity history     -- measurement.EquityLog rows, which are themselves
                        copied verbatim from PortfolioSnapshot.

NO NEW PERSISTENCE. NO DUPLICATED ACCOUNTING. This module reads; it never
writes and never recomputes a figure the portfolio manager already owns.

KNOWN DUPLICATE, RECORDED NOT REFACTORED. alpha_engine/validation/
runner.py computes mean_win/mean_loss/gross_profit_factor inline over
SIGNAL samples. That is a different domain (signal validation, whose
outputs are sealed into evidence packages) and refactoring it would touch
the research path for no product benefit. It is noted here so a future
reader knows the overlap is deliberate, not an oversight.

FORMULAS. Every definition below is stated explicitly. Where more than
one industry convention exists, the adopted one is named and the
alternative is named too, so a reader never has to guess which was used.
"""

import math
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Sequence

from alpha_engine.feasibility import MIN_GROSS_PROFIT_FACTOR, profit_factor

# Cycles are not calendar periods, so annualisation uses elapsed wall time
# rather than an assumed bar count. 365 (not 252): crypto trades every day.
DAYS_PER_YEAR = Decimal("365")
# Below this, CAGR is not reported at all -- see cagr().
MIN_CAGR_DAYS = Decimal("30")
_SECONDS_PER_YEAR = 365.0 * 24 * 3600


def _dec(value, default="0") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _ts(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------- returns

def period_returns(equity_rows: Sequence[Dict[str, Any]]) -> List[Decimal]:
    """Simple returns between consecutive equity observations, NET OF
    CAPITAL FLOWS.

        r_t = (E_t - E_{t-1} - net_flow_t) / E_{t-1}

    where net_flow_t is the change in (deposits - withdrawals) over the
    period. Subtracting flows is not optional: a deposit raises equity
    without being a return, and every return-based metric below would be
    wrong the first time capital moved. This is why EquityLog records the
    cumulative flow fields.

    Periods with a non-positive opening equity are skipped -- a return is
    undefined there, and fabricating one would corrupt every downstream
    statistic.
    """
    out: List[Decimal] = []
    for prev, cur in zip(equity_rows, equity_rows[1:]):
        e0 = _dec(prev.get("equity"))
        if e0 <= 0:
            continue
        flow = ((_dec(cur.get("deposits_cumulative")) - _dec(prev.get("deposits_cumulative")))
                - (_dec(cur.get("withdrawals_cumulative")) - _dec(prev.get("withdrawals_cumulative"))))
        out.append((_dec(cur.get("equity")) - e0 - flow) / e0)
    return out


def total_return(equity_rows: Sequence[Dict[str, Any]]) -> Optional[Decimal]:
    """Cumulative time-weighted return: prod(1 + r_t) - 1.

    ADOPTED: time-weighted (TWR), chain-linked over the period returns
    above. NOT money-weighted (IRR/MWR). TWR measures the STRATEGY;
    money-weighted measures the investor's timing of deposits, which is
    not what a strategy scoreboard should reward or punish.
    """
    rs = period_returns(equity_rows)
    if not rs:
        return None
    acc = Decimal("1")
    for r in rs:
        acc *= (Decimal("1") + r)
    return acc - Decimal("1")


def cagr(equity_rows: Sequence[Dict[str, Any]]) -> Optional[Decimal]:
    """Compound annual growth rate from the time-weighted total return.

        CAGR = (1 + total_return)^(365 / elapsed_days) - 1

    Uses ELAPSED WALL TIME between the first and last observation, not a
    cycle count, because cycles are not calendar periods.

    REFUSES TO ANNUALISE A SHORT WINDOW. Returns None below
    MIN_CAGR_DAYS (30). A 10% gain over two days annualises to
    +35,823,253% -- arithmetically correct, and exactly the number that
    gets screenshotted and believed. Refusing is the honest answer; the
    caller can report total_return, which is always defined.
    """
    tr = total_return(equity_rows)
    if tr is None or len(equity_rows) < 2:
        return None
    t0, t1 = _ts(equity_rows[0].get("observed_at_utc")), _ts(equity_rows[-1].get("observed_at_utc"))
    if t0 is None or t1 is None:
        return None
    days = Decimal(str((t1 - t0).total_seconds() / 86400.0))
    if days < MIN_CAGR_DAYS:
        return None
    growth = Decimal("1") + tr
    if growth <= 0:
        return Decimal("-1")           # total loss; the power is undefined
    return Decimal(str(float(growth) ** float(DAYS_PER_YEAR / days))) - Decimal("1")


def sharpe(equity_rows: Sequence[Dict[str, Any]],
           risk_free_rate_annual: Decimal = Decimal("0")) -> Optional[Decimal]:
    """Annualised Sharpe ratio of the per-cycle return series.

        Sharpe = (mean(r) - rf_per_period) / stdev(r) * sqrt(periods/year)

    ADOPTED: SAMPLE standard deviation (ddof=1) -- the returns are a
    sample, not a population. Annualisation uses the OBSERVED mean period
    length in wall time, so an irregular cycle cadence does not silently
    mis-scale the result.

    Default risk-free rate is ZERO, deliberately: the project's real
    benchmark is the HLP vault (see MECHANISMS.md), and a Sharpe against
    an assumed rate would invite comparing it to numbers computed against
    a different one.

    Returns None with fewer than two returns or zero variance -- a Sharpe
    with no dispersion is a division by zero, not infinity.
    """
    rs = period_returns(equity_rows)
    if len(rs) < 2:
        return None
    t0, t1 = _ts(equity_rows[0].get("observed_at_utc")), _ts(equity_rows[-1].get("observed_at_utc"))
    if t0 is None or t1 is None:
        return None
    elapsed = (t1 - t0).total_seconds()
    if elapsed <= 0:
        return None
    periods_per_year = _SECONDS_PER_YEAR / (elapsed / len(rs))

    n = Decimal(len(rs))
    mean = sum(rs) / n
    var = sum((r - mean) ** 2 for r in rs) / (n - Decimal("1"))
    if var <= 0:
        return None
    excess = mean - (risk_free_rate_annual / Decimal(str(periods_per_year)))
    return (excess / Decimal(str(math.sqrt(float(var))))) * Decimal(str(math.sqrt(periods_per_year)))


def max_drawdown(equity_rows: Sequence[Dict[str, Any]]) -> Optional[Decimal]:
    """Largest peak-to-trough decline, as a POSITIVE fraction.

        MDD = max over t of (peak_so_far - E_t) / peak_so_far

    ADOPTED: computed on the raw equity path, NOT net of capital flows.
    A drawdown is what an operator actually experienced in the account;
    flow-adjusting it would report a decline that nobody lived through.
    This deliberately differs from the return series above, which IS
    flow-adjusted -- the two answer different questions.
    """
    if not equity_rows:
        return None
    peak = None
    worst = Decimal("0")
    for row in equity_rows:
        e = _dec(row.get("equity"))
        if peak is None or e > peak:
            peak = e
        if peak and peak > 0:
            dd = (peak - e) / peak
            if dd > worst:
                worst = dd
    return worst


def rolling_returns(equity_rows: Sequence[Dict[str, Any]], window: int) -> List[Decimal]:
    """Chain-linked return over each rolling window of `window` periods.

    Supported directly by the equity log: it is a windowed application of
    period_returns, needing no additional stored field.
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    rs = period_returns(equity_rows)
    out: List[Decimal] = []
    for i in range(len(rs) - window + 1):
        acc = Decimal("1")
        for r in rs[i:i + window]:
            acc *= (Decimal("1") + r)
        out.append(acc - Decimal("1"))
    return out


# ---------------------------------------------------------------- trades

def trade_metrics(trades: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Trade-level statistics from CLOSED positions.

    A "trade" is one closed position, taken straight from the position
    manager's own record: realized_pnl, fees_paid, funding_paid,
    created_at_utc, updated_at_utc. Nothing is reconstructed here.

    NET vs GROSS, stated explicitly because the two are routinely
    confused:
      realized_pnl is NET of fees (position_manager books the fee into it)
      gross_pnl    = realized_pnl + fees_paid + funding_paid

    profit_factor       -- on NET pnl:   what the account actually kept
    gross_profit_factor -- on GROSS pnl: what the signal produced before
                           costs. The VDA tax gate is assessed on the
                           GROSS figure, because Indian VDA tax is levied
                           on gross gains (MIN_GROSS_PROFIT_FACTOR).

    Both call alpha_engine.feasibility.profit_factor; the formula is not
    reimplemented here.
    """
    net = [_dec(t.get("realized_pnl")) for t in trades]
    fees = [_dec(t.get("fees_paid")) for t in trades]
    funding = [_dec(t.get("funding_paid")) for t in trades]
    gross = [n + f + g for n, f, g in zip(net, fees, funding)]

    wins = [p for p in net if p > 0]
    losses = [-p for p in net if p < 0]      # positive magnitudes

    n = len(net)
    avg_win = (sum(wins) / Decimal(len(wins))) if wins else None
    avg_loss = (sum(losses) / Decimal(len(losses))) if losses else None

    # Win rate: wins / ALL closed trades. A break-even trade counts in the
    # denominator and not the numerator -- it is not a win.
    win_rate = (Decimal(len(wins)) / Decimal(n)) if n else None

    # Payoff ratio = average win / average loss. None when either leg is
    # absent: a ratio with no denominator is undefined, not infinite.
    payoff = (avg_win / avg_loss) if (avg_win is not None and avg_loss and avg_loss > 0) else None

    # Expectancy = mean net PnL per trade. Equivalent to
    # win_rate*avg_win - (1-win_rate)*avg_loss, computed directly so a
    # rounding difference cannot make the two disagree.
    expectancy = (sum(net) / Decimal(n)) if n else None

    holds = []
    for t in trades:
        a, b = _ts(t.get("created_at_utc")), _ts(t.get("updated_at_utc"))
        if a and b and b >= a:
            holds.append((b - a).total_seconds())
    avg_hold = (sum(holds) / len(holds)) if holds else None

    pf_net = profit_factor([float(p) for p in net]) if net else None
    pf_gross = profit_factor([float(p) for p in gross]) if gross else None

    return {
        "trade_count": n,
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": win_rate,
        "average_win": avg_win,
        "average_loss": avg_loss,
        "payoff_ratio": payoff,
        "expectancy": expectancy,
        "profit_factor": Decimal(str(pf_net)) if pf_net is not None else None,
        "gross_profit_factor": Decimal(str(pf_gross)) if pf_gross is not None else None,
        "total_net_pnl": sum(net) if net else Decimal("0"),
        "total_gross_pnl": sum(gross) if gross else Decimal("0"),
        "fees_paid": sum(fees) if fees else Decimal("0"),
        "funding_paid": sum(funding) if funding else Decimal("0"),
        "average_holding_seconds": avg_hold,
    }


def cost_attribution(trade_stats: Dict[str, Any]) -> Dict[str, Any]:
    """Where the gross result went.

        cost_total   = fees + funding
        cost_ratio   = cost_total / |gross_pnl|   (None when gross is 0)

    Reported as a SHARE OF THE GROSS RESULT rather than of equity,
    because the question this answers is "how much of what the signal
    produced did execution consume?".
    """
    fees = _dec(trade_stats.get("fees_paid"))
    funding = _dec(trade_stats.get("funding_paid"))
    gross = _dec(trade_stats.get("total_gross_pnl"))
    total = fees + funding
    return {
        "fees_paid": fees,
        "funding_paid": funding,
        "cost_total": total,
        "cost_ratio_of_gross": (total / abs(gross)) if gross != 0 else None,
    }


# ------------------------------------------------------------- aggregate

def compute(equity_rows: Sequence[Dict[str, Any]],
            trades: Sequence[Dict[str, Any]] = (),
            *, rolling_window: Optional[int] = None) -> Dict[str, Any]:
    """The single entry point. Everything a scoreboard or API needs.

    Returns Decimals and None -- never floats, never fabricated values.
    A metric that cannot be computed from the data provided is None, and
    the caller decides how to present that.
    """
    stats = trade_metrics(trades)
    out: Dict[str, Any] = {
        "observations": len(equity_rows),
        "first_observed_at_utc": equity_rows[0].get("observed_at_utc") if equity_rows else None,
        "last_observed_at_utc": equity_rows[-1].get("observed_at_utc") if equity_rows else None,
        "starting_equity": _dec(equity_rows[0].get("equity")) if equity_rows else None,
        "ending_equity": _dec(equity_rows[-1].get("equity")) if equity_rows else None,
        "total_return": total_return(equity_rows),
        "cagr": cagr(equity_rows),
        "sharpe": sharpe(equity_rows),
        "max_drawdown": max_drawdown(equity_rows),
    }
    out.update(stats)
    out["cost_attribution"] = cost_attribution(stats)
    gpf = stats.get("gross_profit_factor")
    out["survives_vda_tax"] = (gpf > Decimal(str(MIN_GROSS_PROFIT_FACTOR))) if gpf is not None else None
    if rolling_window:
        out[f"rolling_return_{rolling_window}"] = rolling_returns(equity_rows, rolling_window)
    return out


def to_jsonable(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Decimals -> strings, for the same reason every other Decimal in
    this repository is serialised as a string: never through a float."""
    def conv(v):
        if isinstance(v, Decimal):
            return str(v)
        if isinstance(v, dict):
            return {k: conv(x) for k, x in v.items()}
        if isinstance(v, list):
            return [conv(x) for x in v]
        return v
    return {k: conv(v) for k, v in metrics.items()}
