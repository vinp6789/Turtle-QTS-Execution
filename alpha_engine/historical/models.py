"""Value types for historical (backfilled) observations.

Two separate frozen dataclasses -- FundingRateObservation and
OpenInterestObservation -- mirroring the same "two concrete, near-
identical types rather than one generic shape" discipline
alpha_engine.data_sources already established for FundingRateReading/
OpenInterestReading, rather than inventing a third, more-generic
"HistoricalObservation" ahead of a real need. A future third historical
metric (e.g. stablecoin flows) gets its own type the same way, not a
forced fit into these two.

DELIBERATELY NOT the same shape as FundingRateReading/OpenInterestReading
(alpha_engine.data_sources): those types carry `available`/`reason`
because a LIVE fetch can fail in a way that must still produce a
well-formed answer for that exact instant. A historical BACKFILL point is
different -- a day/month either has a published source file or it
doesn't; when it doesn't, it is simply absent from the collected series
(logged and skipped upstream in historical.sources.*), never represented
as a typed "unavailable" row. There is nothing to carry a `reason` for at
the level of one row.

Every timestamp field is validated through alpha_engine._time.parse_utc
(B5's canonical timestamp handling) -- a malformed timestamp from a
source file is a configuration/parsing error, not a data condition, and
must raise immediately rather than silently sorting wrong later.
"""

from dataclasses import dataclass
from decimal import Decimal

from exchange_adapter import Symbol

from .._time import parse_utc
from .errors import HistoricalDataError


def _validate_common(
    class_name: str, symbol: Symbol, observed_at_utc: str, value: Decimal,
    source: str, source_detail: str, ingested_at_utc: str,
) -> None:
    if not isinstance(symbol, Symbol):
        raise HistoricalDataError(f"{class_name}.symbol must be a Symbol, got {type(symbol).__name__}")
    if not isinstance(observed_at_utc, str) or not observed_at_utc.strip():
        raise HistoricalDataError(f"{class_name}.observed_at_utc must be a non-empty string")
    try:
        parse_utc(observed_at_utc)
    except ValueError as exc:
        raise HistoricalDataError(f"{class_name}.observed_at_utc is not a parseable timestamp: {exc}") from exc
    if not isinstance(value, Decimal):
        raise HistoricalDataError(f"{class_name}.value must be a Decimal, got {type(value).__name__}")
    if not isinstance(source, str) or not source.strip():
        raise HistoricalDataError(f"{class_name}.source must be a non-empty string")
    if not isinstance(source_detail, str) or not source_detail.strip():
        raise HistoricalDataError(f"{class_name}.source_detail must be a non-empty string")
    if not isinstance(ingested_at_utc, str) or not ingested_at_utc.strip():
        raise HistoricalDataError(f"{class_name}.ingested_at_utc must be a non-empty string")
    try:
        parse_utc(ingested_at_utc)
    except ValueError as exc:
        raise HistoricalDataError(f"{class_name}.ingested_at_utc is not a parseable timestamp: {exc}") from exc


@dataclass(frozen=True)
class FundingRateObservation:
    """One historical funding-rate settlement for one symbol, from one
    named source (e.g. "binance", "hyperliquid"). `source_detail` records
    exactly which file/endpoint call produced this row (e.g. a bulk
    archive filename or an API request range) -- provenance a research
    conclusion can be traced back to, per this project's evidence-
    fingerprinting discipline elsewhere."""

    symbol: Symbol
    observed_at_utc: str
    value: Decimal
    source: str
    source_detail: str
    ingested_at_utc: str

    def __post_init__(self) -> None:
        _validate_common(
            "FundingRateObservation", self.symbol, self.observed_at_utc, self.value,
            self.source, self.source_detail, self.ingested_at_utc,
        )


@dataclass(frozen=True)
class MarkPriceObservation:
    """One historical mark-price sample for one symbol, from one named
    source. For the Binance metrics source this is derived as
    sum_open_interest_value / sum_open_interest -- the open-interest units
    cancel, leaving the venue's own mark price (empirically verified to
    match spot to the dollar; see docs/RESEARCH_CAMPAIGN_01_open_interest.md).
    For the Hyperliquid source (Backlog 1.4, `sources.hyperliquid.
    fetch_daily_candles`) this is a DAILY CANDLE CLOSE, not a point-in-time
    mark price -- reused as the same type because it is structurally
    identical (one Decimal value per symbol per timestamp), not because
    the two quantities mean the same thing; see that function's own
    derivation-scope note (RD-11 A).
    Kept as its OWN series/type rather than a field on OpenInterestObservation
    because a mark price is a distinct metric with distinct downstream use
    (forward-return outcomes), and mixing two metrics in one row would
    couple them where they should stay independently queryable -- the same
    "two concrete types, not one generic shape" discipline this module
    already applies to funding vs. open interest.

    A price is a strictly positive magnitude: zero or negative is a
    parse/configuration error, not a value to store."""

    symbol: Symbol
    observed_at_utc: str
    value: Decimal
    source: str
    source_detail: str
    ingested_at_utc: str

    def __post_init__(self) -> None:
        _validate_common(
            "MarkPriceObservation", self.symbol, self.observed_at_utc, self.value,
            self.source, self.source_detail, self.ingested_at_utc,
        )
        if self.value <= 0:
            raise HistoricalDataError(
                f"MarkPriceObservation.value must be strictly positive, got {self.value}"
            )


@dataclass(frozen=True)
class LiquidationObservation:
    """One historical liquidation-bearing fill for one symbol, from one
    named source (RD-10 Step 2).

    A THIRD concrete type, not a generalization of the other two -- the
    same discipline this module's own docstring already states. It cannot
    reuse their shape: those carry a single scalar `value`, whereas a
    liquidation is irreducibly multi-field (price AND size AND side AND
    method AND the liquidated account), and collapsing that into one
    `value` would discard exactly the information the metric exists to
    carry.

    Field semantics are taken verbatim from the measured archive schema
    (RD-10 Step 1 probe of node_fills_by_block): a fill event carries an
    optional `liquidation` sub-object, and 100% of observed occurrences
    were non-null. `tid` is the venue's own trade id; it is retained
    because the probe measured that ONE liquidation surfaces as TWO
    paired fills sharing a single `tid` (liquidator side and liquidated
    side), so (symbol, observed_at_utc) alone does NOT uniquely identify
    a row -- see storage._dedup_key.

    `direction` is the venue's own `dir` string (e.g. "Close Long"), kept
    because it is what distinguishes the liquidated side of the pair from
    the liquidator side. Interpreting it is research's job, not this
    type's: no derived/classified field is stored here."""

    symbol: Symbol
    observed_at_utc: str
    price: Decimal
    size: Decimal
    side: str
    direction: str
    method: str
    liquidated_user: str
    mark_price: Decimal
    tid: int
    source: str
    source_detail: str
    ingested_at_utc: str

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, Symbol):
            raise HistoricalDataError(
                f"LiquidationObservation.symbol must be a Symbol, got {type(self.symbol).__name__}"
            )
        for name in ("observed_at_utc", "ingested_at_utc"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise HistoricalDataError(
                    f"LiquidationObservation.{name} must be a non-empty string"
                )
            try:
                parse_utc(value)
            except ValueError as exc:
                raise HistoricalDataError(
                    f"LiquidationObservation.{name} is not a parseable timestamp: {exc}"
                ) from exc
        for name in ("side", "direction", "method", "liquidated_user", "source", "source_detail"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise HistoricalDataError(
                    f"LiquidationObservation.{name} must be a non-empty string"
                )
        for name in ("price", "size", "mark_price"):
            value = getattr(self, name)
            if not isinstance(value, Decimal):
                raise HistoricalDataError(
                    f"LiquidationObservation.{name} must be a Decimal, got {type(value).__name__}"
                )
        if self.size <= 0:
            raise HistoricalDataError(
                f"LiquidationObservation.size must be positive, got {self.size}"
            )
        if self.price <= 0 or self.mark_price <= 0:
            raise HistoricalDataError(
                "LiquidationObservation.price and .mark_price must be strictly positive"
            )
        if not isinstance(self.tid, int) or isinstance(self.tid, bool):
            raise HistoricalDataError(
                f"LiquidationObservation.tid must be an int, got {type(self.tid).__name__}"
            )


@dataclass(frozen=True)
class OpenInterestObservation:
    """One historical open-interest sample for one symbol, from one named
    source. Mirrors OpenInterestReading's own domain constraint: value is
    a non-negative magnitude, never signed -- an unsigned count of open
    contracts/base-asset units cannot be negative."""

    symbol: Symbol
    observed_at_utc: str
    value: Decimal
    source: str
    source_detail: str
    ingested_at_utc: str

    def __post_init__(self) -> None:
        _validate_common(
            "OpenInterestObservation", self.symbol, self.observed_at_utc, self.value,
            self.source, self.source_detail, self.ingested_at_utc,
        )
        if self.value < 0:
            raise HistoricalDataError(
                f"OpenInterestObservation.value must be non-negative, got {self.value}"
            )
