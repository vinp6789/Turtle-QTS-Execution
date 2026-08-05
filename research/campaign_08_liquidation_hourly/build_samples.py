"""Point-in-time sample construction for Research Campaign 08.

Turns the Hyperliquid liquidation archive + the venue's own 1h candles
into ValidationSamples. Every methodological guarantee the campaign
claims lives here:

  - NO LOOK-AHEAD. The feature at hour T is the count of liquidation
    events observed WITHIN hour T; the outcome is the return from the
    close of hour T to the close of hour T+1. outcome_observed_at_utc is
    strictly after the feature's computed_at_utc, so the platform's own
    causality audit can verify it independently.
  - NON-OVERLAPPING BY CONSTRUCTION. Samples are hourly and the outcome
    window is exactly one hour, so consecutive outcome windows abut and
    never overlap. (CAMP-01/07 had to enforce this with a spacing
    assertion; here it is structural.)
  - RD-14 APPLIED AT HOURLY GRANULARITY. Inside the covered window an
    hour with no rows is a VERIFIED ZERO-EVENT hour, materialized as 0 --
    licensed by the whole-window coverage audit, which found 24/24
    hourly archive objects on every day except the RD-15 partial day.
  - RD-15 APPLIED. 2025-07-27 is excluded entirely (16/24 archive
    hours); its partial hours would otherwise read as quiet hours.
  - NEVER FABRICATE. An hour without both endpoint prices is SKIPPED and
    counted in diagnostics, never filled.
  - DETERMINISTIC. Pure function of the inputs; no wall clock, no
    randomness.
"""

import csv
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from exchange_adapter import Symbol

from alpha_engine.features import LiquidationDensityFeature
from alpha_engine.validation import ValidationSample

_ROOT = Path("data/alpha_engine_historical")
_EXCLUDED_DAY = "2025-07-27"          # RD-15
_LIQ_START = datetime(2025, 7, 28, tzinfo=timezone.utc)
_LIQ_END = datetime(2026, 7, 28, 23, tzinfo=timezone.utc)


@dataclass
class CampaignSamples:
    samples: Tuple[ValidationSample, ...]
    diagnostics: Dict[str, int] = field(default_factory=dict)
    hourly_counts: Dict[str, Dict[datetime, int]] = field(default_factory=dict)
    scale: Dict[str, Decimal] = field(default_factory=dict)


def _hour(ts: str) -> datetime:
    return datetime(int(ts[0:4]), int(ts[5:7]), int(ts[8:10]), int(ts[11:13]),
                    tzinfo=timezone.utc)


def load_hourly_counts(symbols: Sequence[Symbol], root: Path = _ROOT):
    """Unique liquidation events (distinct tid) per (symbol, hour)."""
    out = {}
    for symbol in symbols:
        tids: Dict[datetime, set] = {}
        with open(root / f"liquidation__{symbol.value}__hyperliquid_s3.csv",
                  newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                ts = row["observed_at_utc"]
                if ts[:10] == _EXCLUDED_DAY:        # RD-15
                    continue
                tids.setdefault(_hour(ts), set()).add(row["tid"])
        out[symbol.value] = {h: len(s) for h, s in tids.items()}
    return out


def load_hourly_prices(symbols: Sequence[Symbol], root: Path = _ROOT):
    """Hyperliquid 1h candle closes, keyed by hour (Backlog 3.6)."""
    out = {}
    for symbol in symbols:
        prices: Dict[datetime, Decimal] = {}
        with open(root / f"mark_price__{symbol.value}__hyperliquid_1h.csv",
                  newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                prices[_hour(row["observed_at_utc"])] = Decimal(row["value"])
        out[symbol.value] = prices
    return out


def make_regime_labeler(btc_prices: Dict[datetime, Decimal], lookback_hours: int = 24 * 7,
                        threshold: Decimal = Decimal("0.05")):
    """BTC trailing-return regime, price-derived and independent of the
    liquidation feature -- the CAMP-01 convention at hourly resolution."""
    def label(hour: datetime) -> str:
        past = hour - timedelta(hours=lookback_hours)
        if hour not in btc_prices or past not in btc_prices:
            return "unknown"
        prior = btc_prices[past]
        if prior <= 0:
            return "unknown"
        ret = (btc_prices[hour] - prior) / prior
        if ret > threshold:
            return "bull"
        if ret < -threshold:
            return "bear"
        return "chop"
    return label


def build_samples(
    symbols: Sequence[Symbol],
    *,
    root: Path = _ROOT,
    horizon_hours: int = 1,
    percentile_threshold: int = 75,
    regime_labeler: Optional[Callable[[datetime], str]] = None,
) -> CampaignSamples:
    """The pre-registered rule is `count >= that symbol's own p75`
    (Constitution Section 6 -- instrument-relative, never one absolute
    count across symbols whose medians differ ~15x). The validation
    platform applies ONE threshold to every sample, so the per-symbol
    normalization is carried in the VALUE rather than the threshold:

        feature value := count / p75(symbol),  threshold := 1.0

    which is exactly equivalent to `count >= p75(symbol)` and, unlike a
    percentile-rank transform, is tie-safe -- material here because
    51-65% of hours are zero-count. The feature IDENTITY remains
    liquidation_density_hourly, so provenance is unaffected.

    Thresholds are derived from exactly the in-window samples the
    campaign scores (full-sample scope, declared under RD-11 A in the
    campaign document)."""
    counts = load_hourly_counts(symbols, root)
    prices = load_hourly_prices(symbols, root)

    diag = {"grid_hours": 0, "built": 0, "skip_no_price_t": 0,
            "skip_no_price_forward": 0, "skip_outside_liq_window": 0}
    samples: List[ValidationSample] = []

    # First pass: the in-window count population per symbol, so the
    # per-symbol threshold is derived from exactly what gets scored.
    in_window: Dict[str, List[int]] = {s.value: [] for s in symbols}
    for symbol in symbols:
        sym_prices, sym_counts = prices[symbol.value], counts[symbol.value]
        for hour in sym_prices:
            if (_LIQ_START <= hour <= _LIQ_END
                    and (hour + timedelta(hours=horizon_hours)) in sym_prices
                    and sym_prices[hour] > 0):
                in_window[symbol.value].append(sym_counts.get(hour, 0))
    scale: Dict[str, Decimal] = {}
    for sym, vals in in_window.items():
        p = percentile(sorted(vals), percentile_threshold)
        if p <= 0:
            raise ValueError(
                f"{sym}: p{percentile_threshold} of the hourly count distribution is {p}; "
                "normalization would divide by zero -- the threshold must sit above the "
                "zero mass for the rule to be well defined"
            )
        scale[sym] = p
    diag["threshold_p"] = percentile_threshold

    for symbol in sorted(symbols, key=lambda s: s.value):
        sym_prices = prices[symbol.value]
        sym_counts = counts[symbol.value]
        for hour in sorted(sym_prices):
            forward = hour + timedelta(hours=horizon_hours)
            diag["grid_hours"] += 1
            if not (_LIQ_START <= hour <= _LIQ_END):
                diag["skip_outside_liq_window"] += 1
                continue
            if hour not in sym_prices:
                diag["skip_no_price_t"] += 1
                continue
            if forward not in sym_prices:
                diag["skip_no_price_forward"] += 1
                continue
            p0, p1 = sym_prices[hour], sym_prices[forward]
            if p0 <= 0:
                diag["skip_no_price_t"] += 1
                continue
            # RD-14: an hour absent from the archive inside the covered
            # window is a measured zero, not missing data.
            raw_count = sym_counts.get(hour, 0)
            feature_value = LiquidationDensityFeature.compute(
                symbol, hour.isoformat(), raw_count)
            # Carry the instrument-relative normalization in the value.
            feature_value = replace(
                feature_value, value=Decimal(raw_count) / scale[symbol.value])
            samples.append(ValidationSample(
                feature_value=feature_value,
                realized_outcome=(p1 - p0) / p0,
                outcome_observed_at_utc=forward.isoformat(),
                regime_label=(regime_labeler(hour) if regime_labeler else None),
            ))
            diag["built"] += 1

    return CampaignSamples(samples=tuple(samples), diagnostics=diag,
                           hourly_counts=counts, scale=scale)


def percentile(sorted_vals, p):
    import math
    k = (len(sorted_vals) - 1) * (p / 100.0)
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return Decimal(str(sorted_vals[int(k)]))
    return Decimal(str(sorted_vals[lo] * (hi - k) + sorted_vals[hi] * (k - lo)))


def per_symbol_thresholds(built: CampaignSamples, symbols, p: int) -> Dict[str, Decimal]:
    """p-th percentile of each symbol's OWN hourly count distribution,
    computed over exactly the samples the campaign will score
    (Constitution Section 6; full-sample scope declared in the campaign
    document under RD-11 A)."""
    by_symbol: Dict[str, List[int]] = {s.value: [] for s in symbols}
    for sample in built.samples:
        by_symbol[sample.feature_value.symbol.value].append(int(sample.feature_value.value))
    return {sym: percentile(sorted(vals), p) for sym, vals in by_symbol.items()}
