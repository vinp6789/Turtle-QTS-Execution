"""Point-in-time sample construction for Campaign 05 (Open Interest Velocity).

Mirrors Campaign 02/03/04's PIT / non-overlapping discipline exactly; the
only differences are the feature and one locked data-validity rule:

  - FEATURE: `oi_velocity[T] = OI(latest <= T) / OI(latest <= T-24h) - 1`
    -- the 24h FRACTIONAL change of Open Interest. Fractional (scale-free)
    is required, not optional: Campaign 01 established empirically that
    raw OI is strongly non-stationary (~3.4x secular growth over the
    sample), so a raw delta would inherit that non-stationarity. The
    fractional form measures rate-of-change independent of the level.

  - LOCKED DATA-VALIDITY RULE (docs/RESEARCH_CAMPAIGN_05_oi_velocity.md
    section 1a; permanent, no future OI campaign may modify it): a sample
    is constructed ONLY IF both endpoint OI observations are strictly
    positive (> 0). Investigation of the |velocity| ~ 1.0 outliers showed
    every one is a single OI = 0.0 archive snapshot surrounded by normal
    values (e.g. BTC 2024-07-14: 85453 -> 0.0 -> 85645) -- an impossible
    value (OI cannot be zero while the instrument trades), i.e. a
    missing-data artifact, NOT a genuine market event, rollover, or
    exchange-methodology change. Non-positive endpoints are SKIPPED
    (never fabricated, never clamped) and counted as
    `skip_nonpositive_oi`. The rule filters on DATA VALIDITY, not on
    velocity magnitude, so it removes exactly the impossible values while
    retaining every genuine move (the next-largest velocities, <= 0.24,
    have smooth neighbourhoods and are kept).

Correctness guarantees (identical intent to Campaigns 02/03/04):
  - NO LOOK-AHEAD: the feature at time T uses only OI observations at or
    before T (both endpoints: latest <= T and latest <= T-24h). The
    forward return uses mark prices at-or-before T and at-or-before
    T+horizon only. outcome_observed_at_utc = T+horizon is strictly after
    computed_at_utc = T.
  - NON-OVERLAPPING OUTCOMES: samples spaced >= horizon_hours apart.
  - NEVER FABRICATE: any missing or invalid datum skips that sample.
  - DETERMINISTIC: pure function of input series and parameters.

WARMUP AND TOLERANCE REPRODUCE THE LOCKED FEASIBILITY CONDITIONS: the
pre-registration's locked threshold (0.037901) and per-fold counts
([169, 113, 108]) were measured with a 30-day grid warmup and a 6h
lookup tolerance. Both are fixed here as module constants so the
executed campaign reproduces the sample set the locked parameters were
derived from; changing either would invalidate the locked per-fold
adequacy check.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Sequence

from alpha_engine._time import canonical_utc
from alpha_engine.features import FeatureValue
from alpha_engine.validation import ValidationSample
from exchange_adapter import Symbol

from research.campaign_02_funding_rate.build_samples import (
    make_regime_labeler,
    _to_sorted_pairs,
    _latest_at_or_before,
)

FEATURE_NAME = "oi_velocity"
FEATURE_VERSION = "v1"

# Locked to the feasibility measurement conditions (see module docstring).
_OI_TOLERANCE_MS = 6 * 3600 * 1000   # OI is 5-minute resolution; 6h lookup tolerance
_WARMUP_DAYS = 30                    # grid starts 30 days after the series' first observation


@dataclass
class CampaignSamples:
    samples: tuple
    diagnostics: Dict[str, int] = field(default_factory=dict)


def build_samples(
    oi_by_symbol: Dict[Symbol, Sequence],
    mark_by_symbol: Dict[Symbol, Sequence],
    *,
    horizon_hours: int = 24,
    sample_spacing_hours: int = 24,
    lookback_hours: int = 24,
    regime_labeler: Optional[Callable[[int], str]] = None,
    tolerance_ms: int = _OI_TOLERANCE_MS,
    warmup_days: int = _WARMUP_DAYS,
) -> CampaignSamples:
    """Builds the pooled ValidationSample set for Campaign 05 (oi_velocity
    feature). See module docstring for correctness guarantees and for the
    locked OI>0 data-validity rule.

    Raises ValueError if sample_spacing_hours < horizon_hours (would permit
    overlapping outcome windows)."""
    if sample_spacing_hours < horizon_hours:
        raise ValueError(
            f"sample_spacing_hours ({sample_spacing_hours}) must be >= horizon_hours ({horizon_hours}) "
            "to keep outcome windows non-overlapping"
        )

    horizon_ms = horizon_hours * 3600 * 1000
    spacing_ms = sample_spacing_hours * 3600 * 1000
    lookback_ms = lookback_hours * 3600 * 1000

    samples: List[ValidationSample] = []
    diag = {
        "symbols": 0, "grid_points": 0, "built": 0,
        "skip_no_oi": 0, "skip_nonpositive_oi": 0,
        "skip_no_mark_t": 0, "skip_no_mark_forward": 0,
    }

    for symbol in sorted(oi_by_symbol, key=lambda s: s.value):
        oi_obs = oi_by_symbol.get(symbol) or ()
        mark_obs = mark_by_symbol.get(symbol) or ()
        if not oi_obs or not mark_obs:
            continue
        diag["symbols"] += 1
        oi_t, oi_v = _to_sorted_pairs(oi_obs)
        mk_t, mk_v = _to_sorted_pairs(mark_obs)

        first_ms = oi_t[0]
        last_ms = min(oi_t[-1], mk_t[-1] - horizon_ms)
        if last_ms <= first_ms:
            continue
        start_dt = datetime.fromtimestamp(first_ms / 1000, tz=timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=warmup_days)
        t_ms = int(start_dt.timestamp() * 1000)

        while t_ms <= last_ms:
            diag["grid_points"] += 1
            oi_now = _latest_at_or_before(oi_t, oi_v, t_ms, tolerance_ms)
            oi_prev = _latest_at_or_before(oi_t, oi_v, t_ms - lookback_ms, tolerance_ms)
            if oi_now is None or oi_prev is None:
                diag["skip_no_oi"] += 1
                t_ms += spacing_ms
                continue
            # LOCKED DATA-VALIDITY RULE (pre-registration section 1a): both
            # endpoints must be strictly positive. OI cannot be zero while the
            # instrument trades; a non-positive reading is an impossible value
            # (missing-data artifact), never a genuine market event.
            if oi_now <= 0 or oi_prev <= 0:
                diag["skip_nonpositive_oi"] += 1
                t_ms += spacing_ms
                continue

            velocity = oi_now / oi_prev - Decimal(1)

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

            feature_value = FeatureValue(
                feature_name=FEATURE_NAME, feature_version=FEATURE_VERSION, symbol=symbol,
                computed_at_utc=computed_at, available=True, value=velocity,
            )
            samples.append(ValidationSample(
                feature_value=feature_value,
                realized_outcome=realized, outcome_observed_at_utc=outcome_at, regime_label=regime,
            ))
            diag["built"] += 1
            t_ms += spacing_ms

    return CampaignSamples(samples=tuple(samples), diagnostics=diag)


__all__ = ["build_samples", "make_regime_labeler", "CampaignSamples", "FEATURE_NAME", "FEATURE_VERSION"]
