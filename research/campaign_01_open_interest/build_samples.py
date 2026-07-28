"""Point-in-time sample construction for Research Campaign 01.

This is the single most correctness-critical piece of the campaign: it
turns raw historical OI + mark-price series into the ValidationSamples the
frozen validation platform scores. Every methodological guarantee the
campaign claims lives here and is unit-tested (see
tests/test_alpha_engine_historical_*.py analogues for the platform;
tests/test_research_campaign_01_build_samples.py for this):

  - NO LOOK-AHEAD. The extremeness feature at time T uses only OI observed
    STRICTLY BEFORE T (a trailing window); the current OI is the latest
    observation at-or-before T; the forward return uses mark prices
    at-or-before T and at-or-before T+horizon (never a future print).
    outcome_observed_at_utc = T+horizon is strictly after the feature's
    computed_at_utc = T, so the platform's own causality audit can verify
    this independently.
  - NON-OVERLAPPING OUTCOMES. Samples are spaced at least `horizon_hours`
    apart, so consecutive 24h outcome windows do not overlap — the
    mitigation for the autocorrelation that would otherwise fake
    statistical significance. Enforced by assertion, not just convention.
  - NEVER FABRICATE. If any required datum is missing at a sample time
    (a data gap: no OI at T, too few window points, no mark at T or
    T+horizon within tolerance, a degenerate normalization), that sample
    is SKIPPED and counted in diagnostics — never filled with a guess.
  - DETERMINISTIC. Pure function of the input series and parameters; no
    wall clock, no randomness.

Two sample sets are produced from the SAME sample times and the SAME
realized outcomes, differing only in the normalization stamped on each
FeatureValue: percentile-rank (primary) and z-score (robustness). Reusing
identical outcomes isolates the effect of the normalization choice.
"""

from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from alpha_engine._time import canonical_utc, parse_utc
from alpha_engine.features import (
    PCTRANK_NAME,
    PCTRANK_VERSION,
    ZSCORE_NAME,
    ZSCORE_VERSION,
    FeatureValue,
    percentile_rank_centered,
    zscore,
)
from alpha_engine.validation import ValidationSample
from exchange_adapter import Symbol

_DEFAULT_TOLERANCE_MS = 10 * 60 * 1000  # 10 min — generous vs. 5-min native resolution


def _to_sorted_pairs(observations: Sequence) -> Tuple[List[int], List[Decimal]]:
    """(epoch_ms list, value list), sorted ascending by time. Parses each
    observed_at_utc via the platform's canonical parser (no raw-string
    ordering)."""
    rows = sorted(
        ((int(parse_utc(o.observed_at_utc).timestamp() * 1000), o.value) for o in observations),
        key=lambda p: p[0],
    )
    times = [t for t, _ in rows]
    values = [v for _, v in rows]
    return times, values


def _latest_at_or_before(times: List[int], values: List[Decimal], t_ms: int,
                         tolerance_ms: int) -> Optional[Decimal]:
    """The value of the latest observation with time <= t_ms, but only if
    that observation is within tolerance_ms of t_ms (else the point is a
    stale straggler across a data gap -> None, skip)."""
    idx = bisect_right(times, t_ms) - 1
    if idx < 0:
        return None
    if t_ms - times[idx] > tolerance_ms:
        return None
    return values[idx]


def _window_values(times: List[int], values: List[Decimal], start_ms: int, end_ms: int) -> List[Decimal]:
    """All values with start_ms <= time < end_ms (a trailing window,
    end-exclusive so the current point is never inside its own window)."""
    lo = bisect_right(times, start_ms - 1)
    hi = bisect_right(times, end_ms - 1)
    return values[lo:hi]


def make_regime_labeler(
    btc_mark_observations: Sequence,
    *,
    lookback_days: int = 30,
    threshold: Decimal = Decimal("0.05"),
    tolerance_ms: int = _DEFAULT_TOLERANCE_MS,
) -> Callable[[int], str]:
    """A regime labeler independent of Open Interest: bull/bear/chop from
    BTC's trailing `lookback_days` mark-price return (> threshold = bull,
    < -threshold = bear, else chop; 'unknown' if BTC price is unavailable
    at either endpoint). Deliberately computed from PRICE, not OI, so
    regime stratification is not circular with the signal under test."""
    times, values = _to_sorted_pairs(btc_mark_observations)
    lookback_ms = lookback_days * 24 * 3600 * 1000

    def label(t_ms: int) -> str:
        now = _latest_at_or_before(times, values, t_ms, tolerance_ms)
        past = _latest_at_or_before(times, values, t_ms - lookback_ms, tolerance_ms)
        if now is None or past is None or past == 0:
            return "unknown"
        ret = now / past - Decimal(1)
        if ret > threshold:
            return "bull"
        if ret < -threshold:
            return "bear"
        return "chop"

    return label


@dataclass
class CampaignSamples:
    pctrank_samples: Tuple[ValidationSample, ...]
    zscore_samples: Tuple[ValidationSample, ...]
    diagnostics: Dict[str, int] = field(default_factory=dict)


def build_samples(
    oi_by_symbol: Dict[Symbol, Sequence],
    mark_by_symbol: Dict[Symbol, Sequence],
    *,
    window_days: int = 30,
    horizon_hours: int = 24,
    sample_spacing_hours: int = 24,
    regime_labeler: Optional[Callable[[int], str]] = None,
    tolerance_ms: int = _DEFAULT_TOLERANCE_MS,
) -> CampaignSamples:
    """Builds the pctrank and zscore ValidationSample sets, pooled across
    all symbols. See module docstring for the correctness guarantees.

    Raises ValueError if sample_spacing_hours < horizon_hours (that would
    permit overlapping outcome windows — the campaign's cardinal sin)."""
    if sample_spacing_hours < horizon_hours:
        raise ValueError(
            f"sample_spacing_hours ({sample_spacing_hours}) must be >= horizon_hours ({horizon_hours}) "
            "to keep outcome windows non-overlapping"
        )

    window_ms = window_days * 24 * 3600 * 1000
    horizon_ms = horizon_hours * 3600 * 1000
    spacing_ms = sample_spacing_hours * 3600 * 1000

    pct_samples: List[ValidationSample] = []
    z_samples: List[ValidationSample] = []
    diag = {
        "symbols": 0, "grid_points": 0, "built": 0,
        "skip_no_oi": 0, "skip_thin_window": 0, "skip_no_mark_t": 0,
        "skip_no_mark_forward": 0, "skip_norm_pct_none": 0, "skip_norm_z_none": 0,
    }

    for symbol in sorted(oi_by_symbol, key=lambda s: s.value):
        oi_obs = oi_by_symbol.get(symbol) or ()
        mark_obs = mark_by_symbol.get(symbol) or ()
        if not oi_obs or not mark_obs:
            continue
        diag["symbols"] += 1
        oi_t, oi_v = _to_sorted_pairs(oi_obs)
        mk_t, mk_v = _to_sorted_pairs(mark_obs)

        # Sample grid: aligned to UTC midnight, from first feasible time
        # (enough trailing window) to last feasible (a forward mark exists).
        first_ms = oi_t[0] + window_ms
        last_ms = min(oi_t[-1], mk_t[-1] - horizon_ms)
        if last_ms <= first_ms:
            continue
        start_dt = datetime.fromtimestamp(first_ms / 1000, tz=timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        t_ms = int(start_dt.timestamp() * 1000)

        while t_ms <= last_ms:
            diag["grid_points"] += 1
            current_oi = _latest_at_or_before(oi_t, oi_v, t_ms, tolerance_ms)
            if current_oi is None:
                diag["skip_no_oi"] += 1
                t_ms += spacing_ms
                continue
            window = _window_values(oi_t, oi_v, t_ms - window_ms, t_ms)
            if len(window) < 2:
                diag["skip_thin_window"] += 1
                t_ms += spacing_ms
                continue
            mark_t = _latest_at_or_before(mk_t, mk_v, t_ms, tolerance_ms)
            if mark_t is None or mark_t == 0:
                diag["skip_no_mark_t"] += 1
                t_ms += spacing_ms
                continue
            mark_fwd = _latest_at_or_before(mk_t, mk_v, t_ms + horizon_ms, tolerance_ms)
            if mark_fwd is None:
                diag["skip_no_mark_forward"] += 1
                t_ms += spacing_ms
                continue

            realized = mark_fwd / mark_t - Decimal(1)
            computed_at = canonical_utc(datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).isoformat())
            outcome_at = canonical_utc(
                datetime.fromtimestamp((t_ms + horizon_ms) / 1000, tz=timezone.utc).isoformat()
            )
            regime = regime_labeler(t_ms) if regime_labeler is not None else None

            pct = percentile_rank_centered(window, current_oi)
            z = zscore(window, current_oi)

            if pct is not None:
                pct_samples.append(ValidationSample(
                    feature_value=FeatureValue(
                        feature_name=PCTRANK_NAME, feature_version=PCTRANK_VERSION, symbol=symbol,
                        computed_at_utc=computed_at, available=True, value=pct,
                    ),
                    realized_outcome=realized, outcome_observed_at_utc=outcome_at, regime_label=regime,
                ))
            else:
                diag["skip_norm_pct_none"] += 1

            if z is not None:
                z_samples.append(ValidationSample(
                    feature_value=FeatureValue(
                        feature_name=ZSCORE_NAME, feature_version=ZSCORE_VERSION, symbol=symbol,
                        computed_at_utc=computed_at, available=True, value=z,
                    ),
                    realized_outcome=realized, outcome_observed_at_utc=outcome_at, regime_label=regime,
                ))
            else:
                diag["skip_norm_z_none"] += 1

            diag["built"] += 1
            t_ms += spacing_ms

    return CampaignSamples(
        pctrank_samples=tuple(pct_samples),
        zscore_samples=tuple(z_samples),
        diagnostics=diag,
    )
