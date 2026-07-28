"""FundingRateFeature: the first Feature Engineering transform (Alpha
Engine Milestone 2.1; Architecture v0.2 SS4).

The simplest possible feature over alpha_engine.data_sources.
FundingRateProvider's output: a deterministic, stateless pass-through of
the current funding rate. Deliberately minimal, per project direction to
reach the first complete vertical slice (Provider -> Feature -> Candidate
-> Validation -> Evidence Package) before building anything more
elaborate:

  - No historical windowing (no rolling mean, no z-score): the Alpha
    Engine has no time-series storage yet, so any such transform would
    either be fabricated or would require infrastructure not yet
    justified by a second use case. WARMUP_PERIODS is therefore 0: this
    feature is valid from the very first available reading, no history
    required.
  - No Feature ABC/registry: see models.py's docstring for why.

Causality, adapted to what this system actually has today: Architecture
v0.2 SS3's causality requirement is normally checked against historical
indices ("a feature's value at index i must not change if future data is
altered") -- that check does not directly apply yet, since there is no
time series. Instead, compute() is a PURE function of exactly the single
FundingRateReading passed to it: no wall-clock read, no hidden state, no
access to any other reading past, present, or future. Two calls with the
same input always produce identical output, and a call with one reading
never affects the result of a call with a different reading. This is
causality-safety BY CONSTRUCTION rather than by an after-the-fact
historical audit -- proven in
tests/test_alpha_engine_funding_rate_feature.py. Once real historical
windowing exists (a later milestone), the index-based causality audit the
roadmap originally envisioned becomes meaningful and should be added
then, not simulated now.
"""

import logging

from ..data_sources import FundingRateReading
from .errors import FeatureError
from .models import FeatureMetadata, FeatureValue

NAME = "funding_rate_raw"
VERSION = "v1"

_logger = logging.getLogger(__name__)


class FundingRateFeature:
    """Stateless; every instance (and the class itself) behaves
    identically. compute() is a staticmethod precisely because there is
    nothing instance-specific to hold -- call
    FundingRateFeature.compute(...) directly, or instantiate freely."""

    NAME = NAME
    VERSION = VERSION
    WARMUP_PERIODS = 0
    INPUT_DATA_SOURCES = ("funding_rate",)

    @classmethod
    def metadata(cls) -> FeatureMetadata:
        return FeatureMetadata(
            name=cls.NAME, version=cls.VERSION, warmup_periods=cls.WARMUP_PERIODS,
            input_data_sources=cls.INPUT_DATA_SOURCES,
        )

    @staticmethod
    def compute(reading: FundingRateReading) -> FeatureValue:
        """Pure pass-through: the feature value IS the funding rate, when
        available. Never raises for an unavailable reading -- mirrors the
        provider's own fail-safe discipline (Architecture v0.2 SS8): an
        unavailable input becomes an unavailable feature, with the
        underlying reason carried through for observability, never a
        fabricated value and never a crash. Still raises FeatureError for
        a caller's own programming error (wrong argument type)."""
        if not isinstance(reading, FundingRateReading):
            raise FeatureError(f"reading must be a FundingRateReading, got {type(reading).__name__}")

        if not reading.available:
            # B4: DEBUG (not WARNING) -- the provider already logged the
            # underlying condition at its own layer; this is a downstream
            # pass-through trace, not a new event.
            _logger.debug(
                "funding_rate_raw compute degraded to unavailable: symbol=%s reason=%s",
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
