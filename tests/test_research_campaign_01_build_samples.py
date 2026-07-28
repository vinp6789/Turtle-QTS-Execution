"""Point-in-time correctness tests for Research Campaign 01 sample
construction (research.campaign_01_open_interest.build_samples).

Synthetic in-memory series only — no network, no real data. These tests
guard the campaign's core methodological claims: no look-ahead,
non-overlapping outcomes, skip-never-fabricate, deterministic."""

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from exchange_adapter import Symbol

from alpha_engine._time import parse_utc
from alpha_engine.historical.models import MarkPriceObservation, OpenInterestObservation
from research.campaign_01_open_interest.build_samples import build_samples, make_regime_labeler

_START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _oi_series(symbol, n_hours, base=Decimal("1000"), step=Decimal("1")):
    """Hourly OI, monotonically increasing (so the latest value is an
    upper-tail extreme vs. its trailing window)."""
    out = []
    for h in range(n_hours):
        t = _START + timedelta(hours=h)
        out.append(OpenInterestObservation(
            symbol=symbol, observed_at_utc=t.isoformat(), value=base + step * Decimal(h),
            source="binance", source_detail="synthetic", ingested_at_utc=_START.isoformat(),
        ))
    return tuple(out)


def _mark_series(symbol, n_hours, base=Decimal("100"), step=Decimal("0.1")):
    """Hourly mark, monotonically increasing (so forward returns are
    positive and computable)."""
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
        # 15 days hourly, window 2d, horizon 24h, spacing 24h, tolerance 90 min.
        self.hours = 24 * 15
        self.oi = {self.btc: _oi_series(self.btc, self.hours)}
        self.mark = {self.btc: _mark_series(self.btc, self.hours)}
        self.kwargs = dict(window_days=2, horizon_hours=24, sample_spacing_hours=24,
                           tolerance_ms=90 * 60 * 1000)

    def test_builds_samples(self):
        result = build_samples(self.oi, self.mark, **self.kwargs)
        self.assertGreater(len(result.pctrank_samples), 0)
        self.assertEqual(len(result.pctrank_samples), len(result.zscore_samples))

    def test_no_lookahead_outcome_strictly_after_feature(self):
        result = build_samples(self.oi, self.mark, **self.kwargs)
        for s in result.pctrank_samples:
            self.assertLess(
                parse_utc(s.feature_value.computed_at_utc),
                parse_utc(s.outcome_observed_at_utc),
            )

    def test_non_overlapping_outcomes_enforced(self):
        with self.assertRaises(ValueError):
            build_samples(self.oi, self.mark, window_days=2, horizon_hours=24, sample_spacing_hours=12)

    def test_realized_outcome_matches_forward_return(self):
        result = build_samples(self.oi, self.mark, **self.kwargs)
        s = result.pctrank_samples[0]
        t = parse_utc(s.feature_value.computed_at_utc)
        t_fwd = parse_utc(s.outcome_observed_at_utc)
        # mark(t) and mark(t+24h) from the deterministic hourly series.
        h0 = int((t - _START).total_seconds() // 3600)
        h1 = int((t_fwd - _START).total_seconds() // 3600)
        mark0 = Decimal("100") + Decimal("0.1") * Decimal(h0)
        mark1 = Decimal("100") + Decimal("0.1") * Decimal(h1)
        expected = mark1 / mark0 - Decimal(1)
        self.assertAlmostEqual(float(s.realized_outcome), float(expected), places=8)

    def test_rising_oi_gives_positive_pctrank(self):
        # Monotone-rising OI => current is the max of its trailing window
        # => upper-tail => centered percentile ~ +0.5.
        result = build_samples(self.oi, self.mark, **self.kwargs)
        for s in result.pctrank_samples:
            self.assertGreater(s.feature_value.value, Decimal("0.4"))

    def test_gap_in_mark_skips_sample_not_fabricated(self):
        # Remove all mark observations around one forward point; that
        # sample must be skipped, not fabricated.
        full_mark = list(_mark_series(self.btc, self.hours))
        # Drop a >tolerance hole straddling a forward-outcome midnight
        # (day-6 00:00 is the +24h point of the day-5 sample), so no mark
        # exists within tolerance of it.
        hole_start = _START + timedelta(days=6) - timedelta(hours=2)
        hole_end = _START + timedelta(days=6) + timedelta(hours=2)
        kept = [m for m in full_mark
                if not (hole_start <= parse_utc(m.observed_at_utc) <= hole_end)]
        result = build_samples({self.btc: self.oi[self.btc]}, {self.btc: tuple(kept)}, **self.kwargs)
        self.assertGreater(result.diagnostics["skip_no_mark_forward"]
                           + result.diagnostics["skip_no_mark_t"], 0)

    def test_deterministic(self):
        a = build_samples(self.oi, self.mark, **self.kwargs)
        b = build_samples(self.oi, self.mark, **self.kwargs)
        self.assertEqual(
            [s.realized_outcome for s in a.pctrank_samples],
            [s.realized_outcome for s in b.pctrank_samples],
        )

    def test_regime_labeler_is_price_based_and_independent_of_oi(self):
        labeler = make_regime_labeler(self.mark[self.btc], lookback_days=2, threshold=Decimal("0.001"))
        result = build_samples(self.oi, self.mark, regime_labeler=labeler, **self.kwargs)
        labels = {s.regime_label for s in result.pctrank_samples}
        # Rising mark over the window => 'bull' regime should appear.
        self.assertIn("bull", labels)


if __name__ == "__main__":
    unittest.main()
