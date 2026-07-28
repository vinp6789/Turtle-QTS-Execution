"""Campaign 05 (Open Interest Velocity) sample-construction unit tests.

Verifies the oi_velocity feature's PIT correctness, non-overlap,
fractional-change arithmetic, the LOCKED OI>0 data-validity rule and its
`skip_nonpositive_oi` diagnostic, determinism, spacing guard, and feature
identity — mirroring the Campaign 04 test discipline, adapted to the
fractional-change feature.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from exchange_adapter import Symbol
from alpha_engine._time import parse_utc
from research.campaign_05_oi_velocity.build_samples import (
    build_samples,
    FEATURE_NAME,
    FEATURE_VERSION,
    _OI_TOLERANCE_MS,
    _WARMUP_DAYS,
)

_BASE = datetime(2023, 7, 1, tzinfo=timezone.utc)
_SYM = Symbol("BTC")


class _OI:
    def __init__(self, ts, value):
        self.observed_at_utc = ts
        self.value = Decimal(value)


class _MK:
    def __init__(self, ts, value):
        self.observed_at_utc = ts
        self.value = Decimal(value)


def _oi_series(values, step_hours=24):
    """Daily OI observations starting 2023-07-01T00:00Z."""
    return [_OI((_BASE + timedelta(hours=step_hours * i)).isoformat(), v) for i, v in enumerate(values)]


def _mark_series(days=12):
    """Daily mark prices, +1 per day from 100 — outcomes are exactly computable."""
    out = []
    price = Decimal("100")
    for d in range(days):
        out.append(_MK((_BASE + timedelta(days=d)).isoformat(), price))
        price += Decimal("1")
    return out


def _build(oi_values, *, days_mark=12, **kwargs):
    kwargs.setdefault("warmup_days", 1)
    return build_samples({_SYM: _oi_series(oi_values)}, {_SYM: _mark_series(days_mark)}, **kwargs)


# --------------------------------------------------------------------------
# feature identity
# --------------------------------------------------------------------------

def test_feature_identity_is_oi_velocity_v1():
    assert FEATURE_NAME == "oi_velocity"
    assert FEATURE_VERSION == "v1"
    res = _build(["100", "110", "121", "133"])
    assert res.samples
    assert all(s.feature_value.feature_name == FEATURE_NAME for s in res.samples)
    assert all(s.feature_value.feature_version == FEATURE_VERSION for s in res.samples)


def test_locked_warmup_and_tolerance_constants():
    """Locked to the feasibility measurement conditions that produced the
    pre-registered threshold and per-fold counts."""
    assert _WARMUP_DAYS == 30
    assert _OI_TOLERANCE_MS == 6 * 3600 * 1000


# --------------------------------------------------------------------------
# fractional velocity arithmetic
# --------------------------------------------------------------------------

def test_velocity_is_fractional_change_not_raw_delta():
    # 100 -> 110 is +10% regardless of scale; a raw delta would be +10.
    res = _build(["100", "110", "121"])
    first = res.samples[0]
    assert first.feature_value.value == Decimal("110") / Decimal("100") - Decimal(1)
    assert first.feature_value.value == Decimal("0.1")


def test_velocity_scale_free_same_pct_different_levels():
    """The same percentage move at a 1000x larger OI level yields the same
    feature value — the property that makes the feature stationary."""
    small = _build(["100", "110"])
    large = _build(["100000", "110000"])
    assert small.samples[0].feature_value.value == large.samples[0].feature_value.value


def test_negative_velocity_on_unwind():
    res = _build(["200", "150"])
    assert res.samples[0].feature_value.value == Decimal("150") / Decimal("200") - Decimal(1)
    assert res.samples[0].feature_value.value < 0


# --------------------------------------------------------------------------
# LOCKED OI>0 data-validity rule + diagnostic
# --------------------------------------------------------------------------

def test_zero_oi_is_skipped_not_fabricated():
    """A zero OI snapshot is an impossible value: it must skip BOTH the grid
    point where it is the current reading and the next one where it is the
    lookback reading — never produce a fabricated +/-100% velocity."""
    res = _build(["100", "110", "0", "130", "140"])
    assert res.diagnostics["skip_nonpositive_oi"] == 2
    assert res.diagnostics["built"] == 2
    # no sample may carry the -1.0 (or huge) velocity a zero endpoint would create
    assert all(abs(s.feature_value.value) < Decimal("1") for s in res.samples)


def test_negative_oi_is_skipped_guard_is_le_zero():
    """The guard is `<= 0`, not `== 0` — a negative reading is equally
    impossible and must be skipped."""
    res = _build(["100", "110", "-5", "130", "140"])
    assert res.diagnostics["skip_nonpositive_oi"] == 2
    assert res.diagnostics["built"] == 2


def test_diagnostic_zero_when_all_oi_valid():
    res = _build(["100", "110", "121", "133"])
    assert res.diagnostics["skip_nonpositive_oi"] == 0
    assert res.diagnostics["built"] == res.diagnostics["grid_points"]


def test_diagnostics_account_for_every_grid_point():
    res = _build(["100", "110", "0", "130", "140"])
    d = res.diagnostics
    accounted = (d["built"] + d["skip_no_oi"] + d["skip_nonpositive_oi"]
                 + d["skip_no_mark_t"] + d["skip_no_mark_forward"])
    assert accounted == d["grid_points"]


# --------------------------------------------------------------------------
# point-in-time correctness
# --------------------------------------------------------------------------

def test_no_lookahead_feature_ignores_future_observations():
    """The feature at T must use only OI at-or-before T. A huge later value
    must not affect an earlier sample."""
    res = _build(["100", "110", "999999"])
    assert res.samples[0].feature_value.value == Decimal("0.1")


def test_no_lookahead_outcome_strictly_after_feature():
    res = _build(["100", "110", "121", "133"])
    for s in res.samples:
        assert parse_utc(s.outcome_observed_at_utc) > parse_utc(s.feature_value.computed_at_utc)


def test_realized_outcome_matches_forward_mark_return():
    res = _build(["100", "110", "121"])
    s = res.samples[0]
    t = parse_utc(s.feature_value.computed_at_utc)
    day_index = (t - _BASE).days
    mark_now = Decimal(100 + day_index)
    mark_fwd = Decimal(100 + day_index + 1)
    assert s.realized_outcome == mark_fwd / mark_now - Decimal(1)


def test_non_overlapping_outcomes_enforced():
    res = _build(["100", "110", "121", "133", "146"], horizon_hours=24, sample_spacing_hours=24)
    times = sorted(parse_utc(s.feature_value.computed_at_utc) for s in res.samples)
    for a, b in zip(times, times[1:]):
        assert (b - a).total_seconds() >= 24 * 3600 - 1


def test_spacing_shorter_than_horizon_rejected():
    with pytest.raises(ValueError):
        _build(["100", "110", "121"], horizon_hours=24, sample_spacing_hours=12)


# --------------------------------------------------------------------------
# determinism
# --------------------------------------------------------------------------

def test_deterministic():
    values = ["100", "110", "0", "130", "140", "155"]
    a = _build(values)
    b = _build(values)
    assert [(s.feature_value.value, s.realized_outcome) for s in a.samples] == \
           [(s.feature_value.value, s.realized_outcome) for s in b.samples]
    assert a.diagnostics == b.diagnostics


# --------------------------------------------------------------------------
# degenerate inputs are skipped, never fabricated
# --------------------------------------------------------------------------

def test_single_observation_yields_no_samples():
    res = _build(["100"])
    assert res.diagnostics["built"] == 0


def test_missing_mark_series_yields_no_samples():
    res = build_samples({_SYM: _oi_series(["100", "110", "121"])}, {_SYM: []}, warmup_days=1)
    assert res.samples == ()
    assert res.diagnostics["built"] == 0
