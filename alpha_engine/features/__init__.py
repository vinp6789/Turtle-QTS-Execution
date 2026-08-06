"""Feature Engineering (Architecture v0.2 SS4; Alpha Engine Milestone
2.1: FundingRateFeature -- the first feature; Milestone 2.2:
OpenInterestFeature -- the second, built as an exact mirror of the
first).

Public API:
    FundingRateFeature   -- pure, stateless pass-through of the current
                            funding rate (no historical windowing yet --
                            see its own module docstring for why)
    OpenInterestFeature  -- pure, stateless pass-through of the current
                            open interest figure (same shape, same
                            reasoning as FundingRateFeature)
    FeatureValue         -- one compute() call's outcome
    FeatureMetadata      -- a feature's self-description (name, version,
                            warmup, input data sources)
    FeatureError         -- this sub-package's error base

Now that two features share an identical shape (NAME/VERSION/
WARMUP_PERIODS/INPUT_DATA_SOURCES/metadata()/compute()), a shared Feature
ABC is closer to justified than after the first alone -- but still
deferred until a third feature or an actual caller needing polymorphism
over Feature demonstrates what is genuinely common, rather than guessing
a contract from a sample of two (see open_interest_feature.py's
docstring).
"""

from .errors import FeatureError
from .funding_rate_feature import FundingRateFeature
from .liquidation_density_feature import LiquidationDensityFeature
from .atr import ATR_PERIOD, atr_from_candles, true_ranges, wilder_atr
from .trend_momentum_feature import TrendMomentumFeature
from .models import FeatureMetadata, FeatureValue
from .open_interest_feature import OpenInterestFeature
from .open_interest_rolling import (
    PCTRANK_NAME,
    PCTRANK_VERSION,
    ZSCORE_NAME,
    ZSCORE_VERSION,
    percentile_rank_centered,
    zscore,
)

__all__ = [
    "FundingRateFeature",
    "LiquidationDensityFeature",
    "TrendMomentumFeature",
    "atr_from_candles",
    "true_ranges",
    "wilder_atr",
    "ATR_PERIOD",
    "OpenInterestFeature",
    "FeatureValue",
    "FeatureMetadata",
    "FeatureError",
    # Rolling OI extremeness transforms (Research Campaign 01)
    "percentile_rank_centered",
    "zscore",
    "PCTRANK_NAME",
    "PCTRANK_VERSION",
    "ZSCORE_NAME",
    "ZSCORE_VERSION",
]
