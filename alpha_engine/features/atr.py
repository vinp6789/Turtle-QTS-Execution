"""Average True Range -- a shared primitive, not a feature.

ATR is used in two structurally different places and must be identical in
both, so it lives here rather than inside either caller:

  1. TrendMomentumFeature divides the MACD histogram by ATR to make the
     feature scale-free across instruments.
  2. The candle execution bridge multiplies ATR by pre-registered
     multiples to derive stop/T1/T2 distances.

If these two ever computed ATR differently, a signal calibrated on one
volatility scale would be sized against another -- a silent, capital-
affecting inconsistency that no test of either module alone would catch.
One implementation makes that divergence impossible.

Wilder's smoothing is the canonical ATR and is what both callers assume.
Pure functions: no clock, no state, no I/O.
"""

from decimal import Decimal
from typing import List, Optional, Sequence

from exchange_adapter import Candle

# Wilder's original period. A constant, not a parameter -- see the
# feature and bridge docstrings on why periods are frozen.
ATR_PERIOD = 14


def true_ranges(candles: Sequence[Candle]) -> List[Decimal]:
    """TR = max(high-low, |high-prev_close|, |low-prev_close|).

    The first candle has no previous close and contributes high-low."""
    if not candles:
        return []
    ranges = [candles[0].high - candles[0].low]
    for i in range(1, len(candles)):
        prev_close = candles[i - 1].close
        ranges.append(
            max(
                candles[i].high - candles[i].low,
                abs(candles[i].high - prev_close),
                abs(candles[i].low - prev_close),
            )
        )
    return ranges


def wilder_atr(ranges: Sequence[Decimal], period: int = ATR_PERIOD) -> Optional[Decimal]:
    """Latest Wilder-smoothed ATR, or None when the window is too short.

    Returns None rather than a partial value: a caller must decide what to
    do with missing volatility, and a short-window ATR would silently mean
    something different from a full one."""
    if len(ranges) < period:
        return None
    atr = sum(ranges[:period]) / Decimal(period)
    for tr in ranges[period:]:
        atr = (atr * Decimal(period - 1) + tr) / Decimal(period)
    return atr


def atr_from_candles(
    candles: Sequence[Candle], period: int = ATR_PERIOD
) -> Optional[Decimal]:
    """Convenience: true_ranges + wilder_atr in one call."""
    return wilder_atr(true_ranges(candles), period)
