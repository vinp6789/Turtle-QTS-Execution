"""Point-in-time sample construction for Research Campaign 02 (Funding Rate).

Lighter than Campaign 01's equivalent: funding_rate_threshold_rule
consumes the RAW funding rate value directly (no rolling normalization --
see docs/RESEARCH_CAMPAIGN_02_funding_rate.md §2 on why funding needs
none, unlike Open Interest). The point-in-time / non-overlapping-outcome
scaffolding is otherwise the same discipline Campaign 01 established,
duplicated here (not imported across campaign packages) at small,
bounded cost, matching this project's own established precedent for
keeping each campaign's harness independently reviewable
(alpha_engine.historical.sources.hyperliquid's own post_json is the
precedent for this exact tradeoff).

Correctness guarantees (identical intent to Campaign 01's build_samples.py):
  - NO LOOK-AHEAD: the feature at time T is the latest funding-rate
    settlement observed at-or-before T; the forward return uses mark
    prices at-or-before T and at-or-before T+horizon only.
    outcome_observed_at_utc = T+horizon is strictly after
    computed_at_utc = T.
  - NON-OVERLAPPING OUTCOMES: samples spaced >= horizon_hours apart.
  - NEVER FABRICATE: a missing datum at sample time skips that sample
    (counted in diagnostics), never fills a guess.
  - DETERMINISTIC: pure function of input series and parameters.
"""

from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from alpha_engine._time import canonical_utc, parse_utc
from alpha_engine.features import FeatureValue, FundingRateFeature
from alpha_engine.validation import ValidationSample
from exchange_adapter import Symbol

_DEFAULT_TOLERANCE_MS = 4 * 3600 * 1000  # 4h -- generous vs. 8h historical Binance cadence


def _to_sorted_pairs(observations: Sequence) -> Tuple[List[int], List[Decimal]]:
    rows = sorted(
        ((int(parse_utc(o.observed_at_utc).timestamp() * 1000), o.value) for o in observations),
        key=lambda p: p[0],
    )
    return [t for t, _ in rows], [v for _, v in rows]


def _latest_at_or_before(times: List[int], values: List[Decimal], t_ms: int,
                         tolerance_ms: int) -> Optional[Decimal]:
    idx = bisect_right(times, t_ms) - 1
    if idx < 0:
        return None
    if t_ms - times[idx] > tolerance_ms:
        return None
    return values[idx]


def make_regime_labeler(
    btc_mark_observations: Sequence,
    *,
    lookback_days: int = 30,
    threshold: Decimal = Decimal("0.05"),
    tolerance_ms: int = _DEFAULT_TOLERANCE_MS,
) -> Callable[[int], str]:
    """Identical in mechanism to Campaign 01's regime labeler: bull/bear/
    chop from BTC's own trailing mark-price return, independent of
    funding rate (never circular with the signal under test)."""
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
    """Builds the pooled ValidationSample set for Campaign 02. See module
    docstring for correctness guarantees.

    Raises ValueError if sample_spacing_hours < horizon_hours (would
    permit overlapping outcome windows)."""
    if sample_spacing_hours < horizon_hours:
        raise ValueError(
            f"sample_spacing_hours ({sample_spacing_hours}) must be >= horizon_hours ({horizon_hours}) "
            "to keep outcome windows non-overlapping"
        )

    horizon_ms = horizon_hours * 3600 * 1000
    spacing_ms = sample_spacing_hours * 3600 * 1000
    meta = FundingRateFeature.metadata()

    samples: List[ValidationSample] = []
    diag = {
        "symbols": 0, "grid_points": 0, "built": 0,
        "skip_no_funding": 0, "skip_no_mark_t": 0, "skip_no_mark_forward": 0,
    }

    for symbol in sorted(funding_by_symbol, key=lambda s: s.value):
        funding_obs = funding_by_symbol.get(symbol) or ()
        mark_obs = mark_by_symbol.get(symbol) or ()
        if not funding_obs or not mark_obs:
            continue
        diag["symbols"] += 1
        fr_t, fr_v = _to_sorted_pairs(funding_obs)
        mk_t, mk_v = _to_sorted_pairs(mark_obs)

        first_ms = fr_t[0]
        last_ms = min(fr_t[-1], mk_t[-1] - horizon_ms)
        if last_ms <= first_ms:
            continue
        start_dt = datetime.fromtimestamp(first_ms / 1000, tz=timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        t_ms = int(start_dt.timestamp() * 1000)

        while t_ms <= last_ms:
            diag["grid_points"] += 1
            current_funding = _latest_at_or_before(fr_t, fr_v, t_ms, tolerance_ms)
            if current_funding is None:
                diag["skip_no_funding"] += 1
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

            # Constructed directly (not via FundingRateFeature.compute(), which
            # requires a LIVE data_sources.FundingRateReading) -- this is
            # historical backfill data, not a live fetch. Uses the feature's
            # own NAME/VERSION identity so the fingerprint/validation layers
            # see exactly the same feature identity a live run would produce.
            # Identical pattern to Campaign 01's build_samples.py.
            feature_value = FeatureValue(
                feature_name=meta.name, feature_version=meta.version, symbol=symbol,
                computed_at_utc=computed_at, available=True, value=current_funding,
            )
            samples.append(ValidationSample(
                feature_value=feature_value,
                realized_outcome=realized, outcome_observed_at_utc=outcome_at, regime_label=regime,
            ))
            diag["built"] += 1
            t_ms += spacing_ms

    return CampaignSamples(samples=tuple(samples), diagnostics=diag)
