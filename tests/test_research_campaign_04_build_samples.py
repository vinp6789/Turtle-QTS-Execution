"""Campaign 04 (Funding Delta) sample-construction unit tests.

Verifies the delta feature's PIT correctness, non-overlap, feature
identity, determinism, and the no-fabrication skip behavior — mirroring
the Campaign 02 test discipline, adapted to the first-difference feature.
"""
from decimal import Decimal

import pytest

from exchange_adapter import Symbol
from alpha_engine.candidates import CandidateSignal, SignalDirection
from alpha_engine.candidates.funding_rate_candidate import FundingRateThresholdRuleCandidate
from research.campaign_04_funding_delta.build_samples import (
    build_samples, FEATURE_NAME, FEATURE_VERSION,
)
from research.campaign_04_funding_delta.run_campaign import _spec


class _FR:
    def __init__(self, ts, value):
        self.observed_at_utc = ts
        self.value = Decimal(value)


class _MK:
    def __init__(self, ts, value):
        self.observed_at_utc = ts
        self.value = Decimal(value)


from datetime import datetime, timedelta, timezone

_BASE = datetime(2023, 7, 1, tzinfo=timezone.utc)


def _funding_series(symbol, values):
    # 8-hourly settlements starting 2023-07-01, len(values) settlements
    out = []
    for i, v in enumerate(values):
        ts = (_BASE + timedelta(hours=8 * i)).isoformat()
        out.append(_FR(ts, v))
    return out


def _mark_series(days=400):
    # daily mark prices, gently rising, for outcomes/regime
    out = []
    price = Decimal("100")
    for d in range(days):
        ts = (_BASE + timedelta(days=d)).isoformat()
        out.append(_MK(ts, price))
        price += Decimal("1")
    return out


def test_builds_delta_samples():
    sym = Symbol("BTC")
    # alternating funding so deltas are clearly nonzero
    values = ["0.0001", "0.0003", "0.0000", "0.0002"] * 30
    funding = {sym: _funding_series(sym, values)}
    mark = {sym: _mark_series(40)}
    res = build_samples(funding, mark)
    assert res.diagnostics["built"] > 0
    assert all(s.feature_value.feature_name == FEATURE_NAME for s in res.samples)
    assert all(s.feature_value.feature_version == FEATURE_VERSION for s in res.samples)


def test_feature_value_is_first_difference():
    sym = Symbol("BTC")
    values = ["0.0001", "0.0004", "0.0002", "0.0005"] * 30
    funding = {sym: _funding_series(sym, values)}
    mark = {sym: _mark_series(40)}
    res = build_samples(funding, mark)
    # every feature value must equal some funding[i]-funding[i-1] from the series
    fr = funding[sym]
    valid_deltas = {fr[i].value - fr[i - 1].value for i in range(1, len(fr))}
    for s in res.samples:
        assert s.feature_value.value in valid_deltas


def test_no_lookahead_outcome_after_feature():
    from alpha_engine._time import parse_utc
    sym = Symbol("BTC")
    values = ["0.0001", "0.0003"] * 60
    res = build_samples({sym: _funding_series(sym, values)}, {sym: _mark_series(40)})
    for s in res.samples:
        assert parse_utc(s.outcome_observed_at_utc) > parse_utc(s.feature_value.computed_at_utc)


def test_non_overlapping_outcomes():
    from alpha_engine._time import parse_utc
    sym = Symbol("BTC")
    values = ["0.0001", "0.0003"] * 60
    res = build_samples({sym: _funding_series(sym, values)}, {sym: _mark_series(40)},
                        horizon_hours=24, sample_spacing_hours=24)
    times = sorted(parse_utc(s.feature_value.computed_at_utc) for s in res.samples)
    for a, b in zip(times, times[1:]):
        assert (b - a).total_seconds() >= 24 * 3600 - 1


def test_spacing_must_cover_horizon():
    sym = Symbol("BTC")
    with pytest.raises(ValueError):
        build_samples({sym: _funding_series(sym, ["0.0001", "0.0002"] * 30)},
                      {sym: _mark_series(40)}, horizon_hours=24, sample_spacing_hours=12)


def test_deterministic():
    sym = Symbol("BTC")
    values = ["0.0001", "0.0003", "0.0000", "0.0002"] * 30
    a = build_samples({sym: _funding_series(sym, values)}, {sym: _mark_series(40)})
    b = build_samples({sym: _funding_series(sym, values)}, {sym: _mark_series(40)})
    va = [(s.feature_value.value, s.realized_outcome) for s in a.samples]
    vb = [(s.feature_value.value, s.realized_outcome) for s in b.samples]
    assert va == vb


def test_series_shorter_than_two_skipped():
    sym = Symbol("BTC")
    # single settlement -> no delta possible -> no samples, not an error
    res = build_samples({sym: _funding_series(sym, ["0.0001"])}, {sym: _mark_series(40)})
    assert res.diagnostics["built"] == 0


def test_feature_identity_matches_candidate_spec():
    # the constructed spec's feature identity must match the sample feature identity,
    # so the reused funding_rate_threshold_rule mechanism accepts the pair.
    spec = _spec("contrarian", "binance", (Symbol("BTC"),))
    assert spec.feature_name == FEATURE_NAME
    assert spec.feature_version == FEATURE_VERSION
    assert spec.name == "funding_rate_threshold_rule"


def test_candidate_evaluates_delta_feature():
    # a large positive delta above the Binance threshold must produce a directional signal
    sym = Symbol("BTC")
    values = ["0.0001", "0.0010"]  # delta = +0.0009 > 0.00005239 threshold
    res = build_samples({sym: _funding_series(sym, values * 40)}, {sym: _mark_series(50)})
    spec = _spec("contrarian", "binance", (sym,))
    signaled = 0
    for s in res.samples:
        sig = FundingRateThresholdRuleCandidate.evaluate(s.feature_value, spec)
        assert isinstance(sig, CandidateSignal)
        if sig.available and sig.direction is not SignalDirection.FLAT:
            signaled += 1
    assert signaled > 0  # the +0.0009 deltas must signal at the p75 threshold
