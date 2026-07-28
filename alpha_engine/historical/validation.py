"""Data-quality checks for a collected historical series (duplicates,
chronological ordering, gaps) plus source-file checksum verification.

Mirrors alpha_engine.validation.causality_audit's own discipline exactly:
assess_quality() NEVER raises for a data condition -- a duplicate, an
out-of-order pair, or a gap are all normal, evidence-bearing findings,
counted and reported, never silently dropped and never a crash. It DOES
raise (HistoricalDataError) for a genuine caller error: an empty/wrong-
type sequence.

verify_checksum() is a separate, pure predicate -- checksum failure IS a
genuine integrity error (the downloaded bytes are not what the source
published), and the caller (historical.sources.binance) is the one that
decides to raise on a False result, matching this project's "the
boundary layer decides fail-loud vs. fail-safe" pattern.

Deliberately duck-typed over `.symbol.value` / `.observed_at_utc` rather
than requiring a shared base class or Protocol: works identically for
FundingRateObservation and OpenInterestObservation today, and for any
future historical observation type with the same two attributes,
without inventing an ABC ahead of a third concrete need (the same
restraint already applied to Feature/Candidate elsewhere in this
codebase).
"""

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional, Sequence, Tuple

from .._time import parse_utc
from .errors import HistoricalDataError

_DEFAULT_GAP_TOLERANCE_FACTOR = Decimal("1.5")


@dataclass(frozen=True)
class DataQualityReport:
    """One assess_quality() call's outcome. `clean` is True iff there are
    zero duplicates, the series is fully chronologically sorted, and (when
    an expected interval was supplied) zero gaps exceed tolerance."""

    total_count: int
    unique_count: int
    duplicate_count: int
    duplicate_keys: Tuple[Tuple[str, str], ...]  # (symbol_value, observed_at_utc)
    is_monotonic: bool
    out_of_order_indices: Tuple[int, ...]
    gap_count: int
    gaps: Tuple[Tuple[str, str, Decimal], ...]  # (prev_observed_at_utc, next_observed_at_utc, gap_seconds)
    clean: bool

    def __post_init__(self) -> None:
        for field_name in ("total_count", "unique_count", "duplicate_count", "gap_count"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise HistoricalDataError(f"DataQualityReport.{field_name} must be a non-negative int")
        if not isinstance(self.is_monotonic, bool):
            raise HistoricalDataError("DataQualityReport.is_monotonic must be a bool")
        if not isinstance(self.clean, bool):
            raise HistoricalDataError("DataQualityReport.clean must be a bool")
        expected_clean = (
            self.duplicate_count == 0 and self.is_monotonic and self.gap_count == 0
        )
        if self.clean != expected_clean:
            raise HistoricalDataError(
                "DataQualityReport.clean is inconsistent -- must be True iff there are zero "
                "duplicates, the series is monotonic, and zero gaps exceed tolerance"
            )


def assess_quality(
    observations: Sequence[Any],
    expected_interval_seconds: Optional[float] = None,
    gap_tolerance_factor: Decimal = _DEFAULT_GAP_TOLERANCE_FACTOR,
) -> DataQualityReport:
    """Scores a collected series for duplicate (symbol, observed_at_utc)
    keys, chronological ordering (by parsed timestamp, never raw string --
    B5), and -- when `expected_interval_seconds` is given -- gaps wider
    than `expected_interval_seconds * gap_tolerance_factor`.

    Raises HistoricalDataError for a caller error (empty/wrong-type
    sequence, or an unparseable timestamp -- a structurally malformed row
    should already have failed at construction in models.py, so reaching
    here unparseable indicates a caller bypassed that validation).
    Never raises merely because duplicates/gaps/ordering issues were
    found -- those are the normal, counted outcome this function exists
    to report.
    """
    if not isinstance(observations, (list, tuple)) or len(observations) == 0:
        raise HistoricalDataError("observations must be a non-empty list or tuple")
    if expected_interval_seconds is not None and (
        not isinstance(expected_interval_seconds, (int, float)) or isinstance(expected_interval_seconds, bool)
        or expected_interval_seconds <= 0
    ):
        raise HistoricalDataError("expected_interval_seconds must be a positive number or None")

    total = len(observations)
    seen_keys = {}
    duplicate_keys = []
    for obs in observations:
        try:
            key = (obs.symbol.value, obs.observed_at_utc)
        except AttributeError as exc:
            raise HistoricalDataError(
                f"observations must expose .symbol.value and .observed_at_utc: {exc}"
            ) from exc
        seen_keys[key] = seen_keys.get(key, 0) + 1
    for key, count in seen_keys.items():
        if count > 1:
            duplicate_keys.append(key)
    duplicate_keys = tuple(sorted(duplicate_keys))
    duplicate_count = sum(count - 1 for count in seen_keys.values() if count > 1)
    unique_count = len(seen_keys)

    try:
        parsed_times = [parse_utc(obs.observed_at_utc) for obs in observations]
    except ValueError as exc:
        raise HistoricalDataError(f"unparseable observed_at_utc in series: {exc}") from exc

    out_of_order_indices = tuple(
        i for i in range(1, len(parsed_times)) if parsed_times[i] < parsed_times[i - 1]
    )
    is_monotonic = len(out_of_order_indices) == 0

    gaps = []
    if expected_interval_seconds is not None:
        tolerance_seconds = Decimal(str(expected_interval_seconds)) * gap_tolerance_factor
        sorted_pairs = sorted(zip(parsed_times, observations), key=lambda p: p[0])
        for (prev_time, prev_obs), (next_time, next_obs) in zip(sorted_pairs, sorted_pairs[1:]):
            gap_seconds = Decimal(str((next_time - prev_time).total_seconds()))
            if gap_seconds > tolerance_seconds:
                gaps.append((prev_obs.observed_at_utc, next_obs.observed_at_utc, gap_seconds))
    gaps = tuple(gaps)

    return DataQualityReport(
        total_count=total,
        unique_count=unique_count,
        duplicate_count=duplicate_count,
        duplicate_keys=duplicate_keys,
        is_monotonic=is_monotonic,
        out_of_order_indices=out_of_order_indices,
        gap_count=len(gaps),
        gaps=gaps,
        clean=(duplicate_count == 0 and is_monotonic and len(gaps) == 0),
    )


def verify_checksum(data: bytes, expected_sha256_hex: str) -> bool:
    """True iff sha256(data) matches expected_sha256_hex (case-
    insensitive). Pure predicate -- never raises for a mismatch; the
    caller (a source-fetching function) decides whether a mismatch is
    fatal."""
    if not isinstance(data, (bytes, bytearray)):
        raise HistoricalDataError(f"data must be bytes, got {type(data).__name__}")
    if not isinstance(expected_sha256_hex, str) or not expected_sha256_hex.strip():
        raise HistoricalDataError("expected_sha256_hex must be a non-empty string")
    actual = hashlib.sha256(data).hexdigest()
    return actual.lower() == expected_sha256_hex.strip().lower()
