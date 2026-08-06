"""TrendMomentumFeature: ATR-normalised MACD histogram, gated by EMA trend.

The first feature computed from OHLCV candles (D6 context extension)
rather than from a single provider reading.

WHAT IT MEASURES, in one scalar:

    value = MACD_histogram / ATR      signed, scale-free
            ...zeroed when the EMA trend disagrees with the histogram's sign

Three canonical indicators, one number:
  - **MACD(12, 26, 9)** histogram -- momentum, the magnitude and sign.
  - **ATR(14)** -- the divisor. Dividing by ATR makes the value
    scale-free, so one threshold is comparable across BTC, ETH and SOL
    whose absolute price scales differ by ~1000x. This satisfies
    Constitution Section 6's instrument-relative requirement WITHOUT a
    per-symbol threshold table.
  - **EMA(12) vs EMA(26)** -- the trend gate. When the faster EMA is
    above the slower, only positive histograms survive; when below, only
    negative ones. A histogram fighting its own trend is zeroed, which
    reads as FLAT downstream.

PERIODS ARE CONSTANTS, NOT PARAMETERS. 12/26/9 and 14 are the canonical
published settings and are baked into this module deliberately: they are
not tunable, not searched, not optimised, and not passed by the caller.
Changing any of them is a NEW FEATURE VERSION -- which forces a new
pre-registration and a new evidence package rather than a silent refit.
That is the whole point.

PURE FUNCTION. compute() reads no clock, holds no state, and touches no
candle outside the tuple it is handed. Two calls with identical inputs
always produce identical output -- the same discipline
FundingRateFeature and LiquidationDensityFeature state for themselves.

NEVER FABRICATES. Too few candles, a non-positive ATR (a perfectly flat
window), or any malformed input yields an UNAVAILABLE FeatureValue with
a stated reason. It never pads, never extrapolates, and never falls back
to a shorter window -- a short window would silently change the
indicator's meaning.

NO LIVE PROVIDER EXISTS, deliberately. Candles arrive through the
sanctioned MarketDataView.get_candles() seam; compute() takes the
already-fetched tuple. Constitution Section 5 forbids building a provider
ahead of a concrete need.
"""

import logging
from decimal import Decimal
from typing import List, Optional, Sequence

from exchange_adapter import Candle, Symbol

from .atr import ATR_PERIOD, atr_from_candles
from .errors import FeatureError
from .models import FeatureMetadata, FeatureValue

NAME = "ema_macd_atr_norm"
VERSION = "v1"

# Canonical, frozen. See module docstring -- these are not parameters.
EMA_FAST = 12
EMA_SLOW = 26
MACD_SIGNAL = 9
# ATR_PERIOD is imported from .atr -- one implementation shared with the
# execution bridge, so a signal's volatility scale and its exit sizing can
# never diverge.

# Enough history for the slow EMA and the signal line to be meaningful.
# EMA is an infinite-response filter, so "enough" is a judgement, not an
# exact number; 200 is the conventional comfortable margin and is what
# every specification using this feature must supply.
WARMUP_PERIODS = 200

_logger = logging.getLogger(__name__)


def _ema(values: Sequence[Decimal], period: int) -> List[Decimal]:
    """Deterministic EMA. Seeded with the simple average of the first
    `period` values (the standard seeding), then the usual recursion.
    Returns one EMA value per input from index `period-1` onward."""
    if len(values) < period:
        return []
    multiplier = Decimal(2) / Decimal(period + 1)
    seed = sum(values[:period]) / Decimal(period)
    out = [seed]
    for value in values[period:]:
        out.append((value - out[-1]) * multiplier + out[-1])
    return out


class TrendMomentumFeature:
    """Stateless; compute() is a staticmethod, mirroring
    FundingRateFeature and LiquidationDensityFeature exactly."""

    NAME = NAME
    VERSION = VERSION
    WARMUP_PERIODS = WARMUP_PERIODS
    INPUT_DATA_SOURCES = ("candles",)

    EMA_FAST = EMA_FAST
    EMA_SLOW = EMA_SLOW
    MACD_SIGNAL = MACD_SIGNAL
    ATR_PERIOD = ATR_PERIOD

    @classmethod
    def metadata(cls) -> FeatureMetadata:
        return FeatureMetadata(
            name=cls.NAME,
            version=cls.VERSION,
            warmup_periods=cls.WARMUP_PERIODS,
            input_data_sources=cls.INPUT_DATA_SOURCES,
        )

    @staticmethod
    def compute(
        symbol: Symbol,
        computed_at_utc: str,
        candles: Sequence[Candle],
        *,
        unavailable_reason: Optional[str] = None,
    ) -> FeatureValue:
        """ATR-normalised, EMA-gated MACD histogram for the LAST candle.

        `candles` must be CLOSED, ordered oldest -> newest, and at least
        WARMUP_PERIODS long. Fewer yields an unavailable FeatureValue --
        never a value computed from a shorter window.

        Raises FeatureError only for a caller's programming error (wrong
        types, unordered candles, symbol mismatch). A genuine data
        condition degrades to unavailable, never to a crash and never to
        a fabricated number.
        """
        if not isinstance(symbol, Symbol):
            raise FeatureError(f"symbol must be a Symbol, got {type(symbol).__name__}")
        if not isinstance(computed_at_utc, str) or not computed_at_utc.strip():
            raise FeatureError("computed_at_utc must be a non-empty string")

        if candles is None:
            if not unavailable_reason or not unavailable_reason.strip():
                raise FeatureError(
                    "unavailable_reason is required when candles is None -- a missing "
                    "history must say why, never degrade silently into a flat signal"
                )
            return FeatureValue(
                feature_name=NAME, feature_version=VERSION, symbol=symbol,
                computed_at_utc=computed_at_utc, available=False, reason=unavailable_reason,
            )

        if not isinstance(candles, (tuple, list)):
            raise FeatureError(f"candles must be a tuple or list, got {type(candles).__name__}")
        for candle in candles:
            if not isinstance(candle, Candle):
                raise FeatureError(f"candles must contain only Candle, got {type(candle).__name__}")
            if candle.symbol != symbol:
                raise FeatureError(
                    f"candle for {candle.symbol.value} does not match requested symbol {symbol.value}"
                )
        times = [c.open_time_utc for c in candles]
        if times != sorted(times):
            raise FeatureError("candles must be ordered oldest -> newest by open_time_utc")
        if len(set(times)) != len(times):
            raise FeatureError("candles must not contain duplicate open_time_utc")

        if len(candles) < WARMUP_PERIODS:
            return FeatureValue(
                feature_name=NAME, feature_version=VERSION, symbol=symbol,
                computed_at_utc=computed_at_utc, available=False,
                reason=(
                    f"insufficient history: {len(candles)} candles, "
                    f"{WARMUP_PERIODS} required -- refusing to compute on a short window"
                ),
            )

        closes = [c.close for c in candles]
        fast = _ema(closes, EMA_FAST)
        slow = _ema(closes, EMA_SLOW)
        # Align: the slow series starts (EMA_SLOW - EMA_FAST) entries later.
        offset = EMA_SLOW - EMA_FAST
        macd_line = [fast[i + offset] - slow[i] for i in range(len(slow))]
        signal_line = _ema(macd_line, MACD_SIGNAL)
        if not signal_line:
            return FeatureValue(
                feature_name=NAME, feature_version=VERSION, symbol=symbol,
                computed_at_utc=computed_at_utc, available=False,
                reason="MACD signal line unavailable on this window",
            )
        histogram = macd_line[-1] - signal_line[-1]

        atr = atr_from_candles(candles, ATR_PERIOD)
        if atr is None or atr <= 0:
            return FeatureValue(
                feature_name=NAME, feature_version=VERSION, symbol=symbol,
                computed_at_utc=computed_at_utc, available=False,
                reason=(
                    "ATR is zero or undefined on this window -- a flat market has no "
                    "volatility scale, so a normalised momentum value would be meaningless"
                ),
            )

        # EMA trend gate: a histogram fighting its own trend is zeroed.
        trend_up = fast[-1] > slow[-1]
        if (histogram > 0 and not trend_up) or (histogram < 0 and trend_up):
            value = Decimal(0)
        else:
            value = histogram / atr

        _logger.debug(
            "%s: symbol=%s hist=%s atr=%s trend_up=%s value=%s",
            NAME, symbol.value, histogram, atr, trend_up, value,
        )
        return FeatureValue(
            feature_name=NAME, feature_version=VERSION, symbol=symbol,
            computed_at_utc=computed_at_utc, available=True, value=value,
        )
