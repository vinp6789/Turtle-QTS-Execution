"""Research-friendly, incrementally-rerunnable CSV storage for collected
historical observations.

ONE PLAIN CSV FILE per (metric, symbol, source) -- e.g.
"open_interest__BTC__binance.csv" -- rather than one combined file or a
new binary/database format: every research tool (pandas, a spreadsheet,
R, plain grep) reads this natively with zero new dependency, matching
this project's consistent "plain, stdlib-only, no new operational
surface" discipline (the same reasoning FileRegistryStorage's own
docstring gives for JSON-Lines). Columns: observed_at_utc, symbol,
value, source, source_detail, ingested_at_utc -- the exact fields of
FundingRateObservation/OpenInterestObservation (models.py), so a stored
row round-trips to the same typed object it came from.

INCREMENTAL / IDEMPOTENT BY DESIGN: merge_and_write() reads whatever
already exists at `path` (empty/missing is a valid starting state, not
an error), merges in the newly-fetched observations, and re-sorts the
union chronologically before writing -- so re-running the collection
pipeline over a date range that partially overlaps what is already on
disk is always safe: identical rows collapse silently, and a
genuinely-conflicting duplicate (same key, different value -- a source
republishing a corrected/different number for a date already recorded)
is treated as a data-quality anomaly, NOT silently overwritten: the
existing (first-seen) value is kept, and the conflict is reported back
to the caller to log, mirroring this project's "never silently
overwrite prior evidence" discipline (e.g. the Experiment Registry's
evidence-attaches-once rule).

Writes are atomic: to a temporary file in the same directory, then an
OS-level rename -- a crash mid-write can never leave a torn, half-written
CSV in place of a good one.
"""

import csv
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Tuple, Type, Union

from exchange_adapter import Symbol

from .errors import HistoricalDataError
from .models import FundingRateObservation, LiquidationObservation, OpenInterestObservation

_FIELDNAMES = ("observed_at_utc", "symbol", "value", "source", "source_detail", "ingested_at_utc")

# RD-10 Step 2, additive: a liquidation is irreducibly multi-field and cannot be
# expressed in the single-`value` shape above (see models.LiquidationObservation).
# This is a SECOND concrete row shape, not a generic schema mechanism -- the two
# shapes are enumerated explicitly below, exactly as this package already
# enumerates its concrete observation types rather than generalizing them.
_LIQUIDATION_FIELDNAMES = (
    "observed_at_utc", "symbol", "price", "size", "side", "direction", "method",
    "liquidated_user", "mark_price", "tid", "source", "source_detail", "ingested_at_utc",
)

ObservationType = Union[
    Type[FundingRateObservation], Type[OpenInterestObservation], Type[LiquidationObservation]
]


def _fieldnames_for(observation_type: ObservationType) -> Tuple[str, ...]:
    return _LIQUIDATION_FIELDNAMES if observation_type is LiquidationObservation else _FIELDNAMES


def _dedup_key(observation: Any) -> Tuple[str, ...]:
    """The identity of one row for merge purposes.

    (symbol, observed_at_utc) for the scalar series. For liquidations that
    key is NOT unique: the RD-10 Step 1 probe measured that one liquidation
    surfaces as TWO paired fills sharing a single `tid` and timestamp (the
    liquidator side and the liquidated side), so `tid` and `side` are part
    of the identity -- otherwise a merge would silently discard half of
    every liquidation."""
    if isinstance(observation, LiquidationObservation):
        return (
            observation.symbol.value, observation.observed_at_utc,
            str(observation.tid), observation.side,
        )
    return (observation.symbol.value, observation.observed_at_utc)


def series_filename(metric: str, symbol: Symbol, source: str) -> str:
    """Deterministic filename for one (metric, symbol, source) series --
    e.g. series_filename("open_interest", Symbol("BTC"), "binance") ->
    "open_interest__BTC__binance.csv"."""
    if not isinstance(metric, str) or not metric.strip():
        raise HistoricalDataError("metric must be a non-empty string")
    if not isinstance(symbol, Symbol):
        raise HistoricalDataError(f"symbol must be a Symbol, got {type(symbol).__name__}")
    if not isinstance(source, str) or not source.strip():
        raise HistoricalDataError("source must be a non-empty string")
    return f"{metric}__{symbol.value}__{source}.csv"


def _row_to_observation(row: Dict[str, str], observation_type: ObservationType) -> Any:
    if observation_type is LiquidationObservation:
        return LiquidationObservation(
            symbol=Symbol(row["symbol"]),
            observed_at_utc=row["observed_at_utc"],
            price=Decimal(row["price"]),
            size=Decimal(row["size"]),
            side=row["side"],
            direction=row["direction"],
            method=row["method"],
            liquidated_user=row["liquidated_user"],
            mark_price=Decimal(row["mark_price"]),
            tid=int(row["tid"]),
            source=row["source"],
            source_detail=row["source_detail"],
            ingested_at_utc=row["ingested_at_utc"],
        )
    return observation_type(
        symbol=Symbol(row["symbol"]),
        observed_at_utc=row["observed_at_utc"],
        value=Decimal(row["value"]),
        source=row["source"],
        source_detail=row["source_detail"],
        ingested_at_utc=row["ingested_at_utc"],
    )


def _observation_to_row(observation: Any) -> Dict[str, str]:
    if isinstance(observation, LiquidationObservation):
        return {
            "observed_at_utc": observation.observed_at_utc,
            "symbol": observation.symbol.value,
            "price": str(observation.price),
            "size": str(observation.size),
            "side": observation.side,
            "direction": observation.direction,
            "method": observation.method,
            "liquidated_user": observation.liquidated_user,
            "mark_price": str(observation.mark_price),
            "tid": str(observation.tid),
            "source": observation.source,
            "source_detail": observation.source_detail,
            "ingested_at_utc": observation.ingested_at_utc,
        }
    return {
        "observed_at_utc": observation.observed_at_utc,
        "symbol": observation.symbol.value,
        "value": str(observation.value),
        "source": observation.source,
        "source_detail": observation.source_detail,
        "ingested_at_utc": observation.ingested_at_utc,
    }


def load(path: Union[str, Path], observation_type: ObservationType) -> Tuple[Any, ...]:
    """Every observation currently on disk at `path`, reconstructed as
    `observation_type` instances. Returns an empty tuple if the file does
    not exist yet -- a fresh series is a normal starting state, not an
    error."""
    file_path = Path(path)
    if not file_path.is_file():
        return ()
    with open(file_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        expected = _fieldnames_for(observation_type)
        if reader.fieldnames is not None and tuple(reader.fieldnames) != expected:
            raise HistoricalDataError(
                f"{file_path}: unexpected CSV header {reader.fieldnames!r}, expected {expected!r}"
            )
        return tuple(_row_to_observation(row, observation_type) for row in reader)


@dataclass(frozen=True)
class MergeResult:
    """merge_and_write()'s outcome: how many rows were already present,
    how many genuinely new rows were added, and any conflicting-duplicate
    keys found (same (symbol, observed_at_utc), different value) -- the
    existing value is always kept for a conflict; this reports it rather
    than silently discarding the disagreement."""

    existing_count: int
    added_count: int
    conflict_keys: Tuple[Tuple[str, str], ...]

    def __post_init__(self) -> None:
        for field_name in ("existing_count", "added_count"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise HistoricalDataError(f"MergeResult.{field_name} must be a non-negative int")


def merge_and_write(
    path: Union[str, Path],
    observation_type: ObservationType,
    new_observations: Tuple[Any, ...],
) -> MergeResult:
    """Merges `new_observations` into whatever series already exists at
    `path`, deduplicating on (symbol, observed_at_utc), re-sorts
    chronologically, and writes atomically. Safe to call repeatedly with
    overlapping data (incremental reruns) -- identical rows collapse
    silently; a conflicting duplicate keeps the EXISTING value and is
    reported in the returned MergeResult, never silently overwritten."""
    if not isinstance(new_observations, tuple):
        raise HistoricalDataError("new_observations must be a tuple")

    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    existing = load(file_path, observation_type)

    by_key: Dict[Tuple[str, ...], Any] = {}
    for obs in existing:
        by_key[_dedup_key(obs)] = obs

    existing_count = len(by_key)
    added_count = 0
    conflicts = []
    for obs in new_observations:
        key = _dedup_key(obs)
        if key not in by_key:
            by_key[key] = obs
            added_count += 1
        elif by_key[key] != obs:
            conflicts.append(key)
        # identical existing row: silently coalesced, no-op

    merged = sorted(by_key.values(), key=lambda o: (o.observed_at_utc, o.symbol.value))

    tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_fieldnames_for(observation_type))
        writer.writeheader()
        for obs in merged:
            writer.writerow(_observation_to_row(obs))
    os.replace(tmp_path, file_path)

    return MergeResult(
        existing_count=existing_count,
        added_count=added_count,
        conflict_keys=tuple(sorted(conflicts)),
    )
