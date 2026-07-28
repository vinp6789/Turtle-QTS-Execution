"""Point-in-time correctness tests for Research Campaign 02 sample
construction (research.campaign_02_funding_rate.build_samples).

Synthetic in-memory series only — no network, no real data. Mirrors
tests/test_research_campaign_01_build_samples.py's guarantees, adapted
for funding rate's simpler (no-normalization) feature."""

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from exchange_adapter import Symbol

from alpha_engine._time import parse_utc
from alpha_engine.historical.models import FundingRateObservation, MarkPriceObservation
from research.campaign_02_funding_rate.build_samples import build_samples, make_regime_labeler

_START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _funding_series(symbol, n_settlements, base=Decimal("0.0001"), step=Decimal("0.00001"), interval_hours=8):
    out = []
    for i in range(n_settlements):
        t = _START + timedelta(hours=interval_hours * i)
        out.append(FundingRateObservation(
            symbol=symbol, observed_at_utc=t.isoformat(), value=base + step * Decimal(i),
            source="binance", source_detail="synthetic", ingested_at_utc=_START.isoformat(),
        ))
    return tuple(out)


def _mark_series(symbol, n_hours, base=Decimal("100"), step=Decimal("0.1")):
    out = []
    for h in range(n_hours):
        t = _START + timedelta(hours=h)
        out.append(MarkPriceObservation(
            symbol=symbol, observed_at_utc=t.isoformat(), value=base + step * Decimal(h),
            source="binance", source_detail="synthetic", ingested_at_utc=_START.isoformat(),
        ))
    return tuple(out)


class TestBuildSamples(unittest.TestCase):
    def setUp(self):
        self.btc = Symbol("BTC")
        self.hours = 24 * 15
        self.funding = {self.btc: _funding_series(self.btc, n_settlements=(self.hours // 8))}
        self.mark = {self.btc: _mark_series(self.btc, self.hours)}
        self.kwargs = dict(horizon_hours=24, sample_spacing_hours=24, tolerance_ms=5 * 3600 * 1000)

    def test_builds_samples(self):
        result = build_samples(self.funding, self.mark, **self.kwargs)
        self.assertGreater(len(result.samples), 0)

    def test_no_lookahead_outcome_strictly_after_feature(self):
        result = build_samples(self.funding, self.mark, **self.kwargs)
        for s in result.samples:
            self.assertLess(
                parse_utc(s.feature_value.computed_at_utc),
                parse_utc(s.outcome_observed_at_utc),
            )

    def test_non_overlapping_outcomes_enforced(self):
        with self.assertRaises(ValueError):
            build_samples(self.funding, self.mark, horizon_hours=24, sample_spacing_hours=12)

    def test_feature_value_is_raw_funding_rate_no_normalization(self):
        # Unlike Campaign 01, the feature value must be the RAW funding
        # rate at T -- no rolling/percentile/z-score transform.
        result = build_samples(self.funding, self.mark, **self.kwargs)
        fr_t = [(parse_utc(o.observed_at_utc), o.value) for o in self.funding[self.btc]]
        for s in result.samples:
            t = parse_utc(s.feature_value.computed_at_utc)
            candidates = [v for (ft, v) in fr_t if ft <= t]  # latest funding at or before t
            self.assertTrue(candidates)
            self.assertEqual(s.feature_value.value, candidates[-1])

    def test_feature_identity_matches_live_feature_metadata(self):
        from alpha_engine.features import FundingRateFeature
        result = build_samples(self.funding, self.mark, **self.kwargs)
        meta = FundingRateFeature.metadata()
        for s in result.samples:
            self.assertEqual(s.feature_value.feature_name, meta.name)
            self.assertEqual(s.feature_value.feature_version, meta.version)

    def test_realized_outcome_matches_forward_return(self):
        result = build_samples(self.funding, self.mark, **self.kwargs)
        s = result.samples[0]
        t = parse_utc(s.feature_value.computed_at_utc)
        t_fwd = parse_utc(s.outcome_observed_at_utc)
        h0 = int((t - _START).total_seconds() // 3600)
        h1 = int((t_fwd - _START).total_seconds() // 3600)
        mark0 = Decimal("100") + Decimal("0.1") * Decimal(h0)
        mark1 = Decimal("100") + Decimal("0.1") * Decimal(h1)
        expected = mark1 / mark0 - Decimal(1)
        self.assertAlmostEqual(float(s.realized_outcome), float(expected), places=8)

    def test_gap_in_funding_skips_sample_not_fabricated(self):
        full_funding = list(_funding_series(self.btc, n_settlements=(self.hours // 8)))
        kept = [f for f in full_funding
                if not (_START + timedelta(days=6) <= parse_utc(f.observed_at_utc) < _START + timedelta(days=7))]
        result = build_samples({self.btc: tuple(kept)}, self.mark, **self.kwargs)
        self.assertGreater(result.diagnostics["skip_no_funding"], 0)

    def test_deterministic(self):
        a = build_samples(self.funding, self.mark, **self.kwargs)
        b = build_samples(self.funding, self.mark, **self.kwargs)
        self.assertEqual(
            [s.realized_outcome for s in a.samples],
            [s.realized_outcome for s in b.samples],
        )

    def test_regime_labeler_is_price_based(self):
        labeler = make_regime_labeler(self.mark[self.btc], lookback_days=2, threshold=Decimal("0.001"))
        result = build_samples(self.funding, self.mark, regime_labeler=labeler, **self.kwargs)
        labels = {s.regime_label for s in result.samples}
        self.assertIn("bull", labels)


if __name__ == "__main__":
    unittest.main()
