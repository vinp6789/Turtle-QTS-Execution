"""Point-in-time sample construction for Campaign 04 (Funding Delta).

Mirrors Campaign 02/03's PIT/non-overlapping discipline exactly; the ONLY
difference is the feature value: instead of the raw funding rate, the
feature is `funding_delta` = the change between consecutive funding
settlements, taken at the latest settlement at-or-before the sample time.

Correctness guarantees (identical intent to Campaign 02/03):
  - NO LOOK-AHEAD: the delta at time T is funding[s] - funding[s-1] for
    the latest settlement s <= T (both s and s-1 are <= T by construction).
    The forward return uses mark prices at-or-before T and T+horizon only.
  - NON-OVERLAPPING OUTCOMES: samples spaced >= horizon_hours apart.
  - NEVER FABRICATE: a missing datum (no prior settlement to difference,
    or missing mark) skips that sample, never fills a guess.
  - DETERMINISTIC: pure function of input series and parameters.

The feature identity is the string "funding_delta"/"v1" -- a genuinely
new feature (distinct from funding_rate_raw), stamped on both the
FeatureValue here and the CandidateSpecification.feature_name in
run_campaign, so the candidate's evaluate() sees a matched pair.
"""

from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from alpha_engine._time import canonical_utc, parse_utc
from alpha_engine.features import FeatureValue
from alpha_engine.validation import ValidationSample
from exchange_adapter import Symbol

from research.campaign_02_funding_rate.build_samples import (
    make_regime_labeler,
    _DEFAULT_TOLERANCE_MS,
    _to_sorted_pairs,
    _latest_at_or_before,
)

FEATURE_NAME = "funding_delta"
FEATURE_VERSION = "v1"


def _delta_pairs(times: List[int], values: List[Decimal]) -> Tuple[List[int], List[Decimal]]:
    """(time, delta) for each settlement i>=1: value[i]-value[i-1], keyed
    at time[i] (the settlement at which the change is observed)."""
    dt = times[1:]
    dv = [values[i] - values[i - 1] for i in range(1, len(values))]
    return dt, dv


@dataclass
class CampaignSamples:
    samples: Tuple[ValidationSample, ...]
    diagnostics: Dict[str, int] = field(default_factory=dict)


def build_samples(
    funding_by_symbol: Dict[Symbol, Sequence],
    mark_by_symbol: Dict[Symbol, Sequence],
    *,
    horizon_hours: int = 24,
    sample_spacing_hours: int = 24,
    regime_labeler: Optional[Callable[[int], str]] = None,
    tolerance_ms: int = _DEFAULT_TOLERANCE_MS,
) -> CampaignSamples:
    """Builds the pooled ValidationSample set for Campaign 04 (delta
    feature). See module docstring for correctness guarantees.

    Raises ValueError if sample_spacing_hours < horizon_hours."""
    if sample_spacing_hours < horizon_hours:
        raise ValueError(
            f"sample_spacing_hours ({sample_spacing_hours}) must be >= horizon_hours ({horizon_hours})"
        )

    horizon_ms = horizon_hours * 3600 * 1000
    spacing_ms = sample_spacing_hours * 3600 * 1000

    samples: List[ValidationSample] = []
    diag = {
        "symbols": 0, "grid_points": 0, "built": 0,
        "skip_no_delta": 0, "skip_no_mark_t": 0, "skip_no_mark_forward": 0,
    }

    for symbol in sorted(funding_by_symbol, key=lambda s: s.value):
        funding_obs = funding_by_symbol.get(symbol) or ()
        mark_obs = mark_by_symbol.get(symbol) or ()
        if not funding_obs or not mark_obs:
            continue
        diag["symbols"] += 1
        fr_t, fr_v = _to_sorted_pairs(funding_obs)
        if len(fr_t) < 2:
            continue
        d_t, d_v = _delta_pairs(fr_t, fr_v)  # delta series (one shorter)
        mk_t, mk_v = _to_sorted_pairs(mark_obs)

        first_ms = d_t[0]
        last_ms = min(d_t[-1], mk_t[-1] - horizon_ms)
        if last_ms <= first_ms:
            continue
        start_dt = datetime.fromtimestamp(first_ms / 1000, tz=timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        t_ms = int(start_dt.timestamp() * 1000)

        while t_ms <= last_ms:
            diag["grid_points"] += 1
            current_delta = _latest_at_or_before(d_t, d_v, t_ms, tolerance_ms)
            if current_delta is None:
                diag["skip_no_delta"] += 1
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

            feature_value = FeatureValue(
                feature_name=FEATURE_NAME, feature_version=FEATURE_VERSION, symbol=symbol,
                computed_at_utc=computed_at, available=True, value=current_delta,
            )
            samples.append(ValidationSample(
                feature_value=feature_value,
                realized_outcome=realized, outcome_observed_at_utc=outcome_at, regime_label=regime,
            ))
            diag["built"] += 1
            t_ms += spacing_ms

    return CampaignSamples(samples=tuple(samples), diagnostics=diag)


__all__ = ["build_samples", "make_regime_labeler", "CampaignSamples", "FEATURE_NAME", "FEATURE_VERSION"]
