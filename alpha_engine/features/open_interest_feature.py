"""OpenInterestFeature: the second Feature Engineering transform (Alpha
Engine Milestone 2.2; Architecture v0.2 SS4).

Mirrors FundingRateFeature (Milestone 2.1) exactly, reusing the identical
shape and reasoning for the identical reasons -- this is the second
orthogonal data source's vertical slice, following the same pattern
proven with funding rate rather than inventing a new one:

  - No historical windowing (no rolling mean, no z-score): the Alpha
    Engine still has no time-series storage. WARMUP_PERIODS is 0: this
    feature is valid from the very first available reading.
  - No Feature ABC/registry: see models.py's docstring for why -- with
    two features now sharing this identical NAME/VERSION/WARMUP_PERIODS/
    INPUT_DATA_SOURCES/metadata()/compute() shape, a shared contract is
    closer to justified than it was after the first one alone, but
    extracting it is still deferred until a THIRD feature (or an actual
    caller needing polymorphism over Feature) demonstrates what would
    genuinely be shared beyond what two examples already show -- avoiding
    guessing the contract from a sample of two.

Causality: identical reasoning to FundingRateFeature -- compute() is a
PURE function of exactly the single OpenInterestReading passed to it, no
wall-clock read, no hidden state. Causality-safety by construction, not
an after-the-fact historical audit; proven in
tests/test_alpha_engine_open_interest_feature.py.
"""

import logging

from ..data_sources import OpenInterestReading
from .errors import FeatureError
from .models import FeatureMetadata, FeatureValue

NAME = "open_interest_raw"
VERSION = "v1"

_logger = logging.getLogger(__name__)


class OpenInterestFeature:
    """Stateless; every instance (and the class itself) behaves
    identically. compute() is a staticmethod precisely because there is
    nothing instance-specific to hold -- call
    OpenInterestFeature.compute(...) directly, or instantiate freely."""

    NAME = NAME
    VERSION = VERSION
    WARMUP_PERIODS = 0
    INPUT_DATA_SOURCES = ("open_interest",)

    @classmethod
    def metadata(cls) -> FeatureMetadata:
        return FeatureMetadata(
            name=cls.NAME, version=cls.VERSION, warmup_periods=cls.WARMUP_PERIODS,
            input_data_sources=cls.INPUT_DATA_SOURCES,
        )

    @staticmethod
    def compute(reading: OpenInterestReading) -> FeatureValue:
        """Pure pass-through: the feature value IS the open interest
        figure, when available. Never raises for an unavailable reading
        -- mirrors the provider's own fail-safe discipline (Architecture
        v0.2 SS8): an unavailable input becomes an unavailable feature,
        with the underlying reason carried through for observability,
        never a fabricated value and never a crash. Still raises
        FeatureError for a caller's own programming error (wrong
        argument type)."""
        if not isinstance(reading, OpenInterestReading):
            raise FeatureError(f"reading must be an OpenInterestReading, got {type(reading).__name__}")

        if not reading.available:
            # B4: DEBUG (not WARNING) -- the provider already logged the
            # underlying condition at its own layer; this is a downstream
            # pass-through trace, not a new event.
            _logger.debug(
                "open_interest_raw compute degraded to unavailable: symbol=%s reason=%s",
                reading.symbol.value, reading.reason,
            )
            return FeatureValue(
                feature_name=NAME, feature_version=VERSION, symbol=reading.symbol,
                computed_at_utc=reading.fetched_at_utc, available=False,
                reason=f"input reading unavailable: {reading.reason}",
            )
        return FeatureValue(
            feature_name=NAME, feature_version=VERSION, symbol=reading.symbol,
            computed_at_utc=reading.fetched_at_utc, available=True, value=reading.value,
        )
