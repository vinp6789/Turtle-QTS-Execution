"""LiquidationDensityFeature: hourly liquidation-event density
(Research Campaign 08, Backlog 3.7 option (b)).

Exists for one reason: **correct provenance**. Campaigns 04 and 05 tested
new features (`funding_delta`, `oi_velocity`) by reusing
`funding_rate_threshold_rule`, whose specification factory reads
feature_name/feature_version from `FundingRateFeature.metadata()` and
never from the caller. Their evidence packages are therefore stamped
`feature_name="funding_rate_raw"` while testing something else, and
`ALPHA_LIBRARY.md`'s "(feature `oi_velocity`)" annotations are human
notes papering over that. Campaign 08 is the first campaign whose result
could be promotion-eligible, so its evidence must say what it actually
measured.

WHAT THE FEATURE IS: the count of DISTINCT liquidation events (unique
`tid`) for one symbol in one UTC hour. Non-negative and unbounded above.

NO LIVE PROVIDER EXISTS, deliberately. The historical source is the
Hyperliquid S3 fill archive (`historical.sources.hyperliquid_s3`), and
forward accumulation comes from the Live Recorder (RD-18). There is no
`LiquidationDensityProvider` because nothing needs one today, and
Constitution §5 forbids building one ahead of a concrete need. compute()
therefore takes the already-counted value directly rather than a
provider Reading -- the one structural difference from
FundingRateFeature, and the honest one.

Causality, on the same terms FundingRateFeature states: compute() is a
PURE function of its arguments -- no wall-clock read, no hidden state, no
access to any other hour past or future. Two calls with identical inputs
always produce identical output.

ZERO IS A REAL VALUE, NOT MISSING DATA. Per RD-14 an absent
(symbol, hour) inside the covered window is a VERIFIED ZERO-EVENT hour.
A count of 0 is therefore `available=True` with value 0 -- never
unavailable, never fabricated. Only a genuinely unknown hour (outside
coverage) should be passed as unavailable, and that is the caller's
judgement, not this feature's.
"""

import logging
from decimal import Decimal
from typing import Optional

from exchange_adapter import Symbol

from .errors import FeatureError
from .models import FeatureMetadata, FeatureValue

NAME = "liquidation_density_hourly"
VERSION = "v1"

_logger = logging.getLogger(__name__)


class LiquidationDensityFeature:
    """Stateless; compute() is a staticmethod, mirroring
    FundingRateFeature's shape exactly."""

    NAME = NAME
    VERSION = VERSION
    WARMUP_PERIODS = 0
    INPUT_DATA_SOURCES = ("liquidation",)

    @classmethod
    def metadata(cls) -> FeatureMetadata:
        return FeatureMetadata(
            name=cls.NAME, version=cls.VERSION, warmup_periods=cls.WARMUP_PERIODS,
            input_data_sources=cls.INPUT_DATA_SOURCES,
        )

    @staticmethod
    def compute(
        symbol: Symbol,
        computed_at_utc: str,
        event_count: Optional[int],
        *,
        unavailable_reason: Optional[str] = None,
    ) -> FeatureValue:
        """The feature value IS the hourly unique-event count.

        `event_count=None` yields an unavailable FeatureValue and REQUIRES
        `unavailable_reason` -- an hour outside coverage is genuinely
        unknown and must never be silently read as quiet. A count of 0 is
        available (RD-14). Raises FeatureError for a caller's own
        programming error (wrong types, negative count, missing reason)."""
        if not isinstance(symbol, Symbol):
            raise FeatureError(f"symbol must be a Symbol, got {type(symbol).__name__}")
        if not isinstance(computed_at_utc, str) or not computed_at_utc.strip():
            raise FeatureError("computed_at_utc must be a non-empty string")

        if event_count is None:
            if not unavailable_reason or not unavailable_reason.strip():
                raise FeatureError(
                    "unavailable_reason is required when event_count is None -- an hour outside "
                    "coverage must say why, never degrade silently into a quiet hour (RD-14)"
                )
            return FeatureValue(
                feature_name=NAME, feature_version=VERSION, symbol=symbol,
                computed_at_utc=computed_at_utc, available=False, reason=unavailable_reason,
            )

        if isinstance(event_count, bool) or not isinstance(event_count, int):
            raise FeatureError(f"event_count must be an int or None, got {type(event_count).__name__}")
        if event_count < 0:
            raise FeatureError(f"event_count must be non-negative, got {event_count}")

        return FeatureValue(
            feature_name=NAME, feature_version=VERSION, symbol=symbol,
            computed_at_utc=computed_at_utc, available=True, value=Decimal(event_count),
        )
