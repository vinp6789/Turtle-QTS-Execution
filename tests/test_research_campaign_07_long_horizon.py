"""Pre-registration integrity + longer-horizon correctness tests for
Research Campaign 07 (research.campaign_07_oi_long_horizon).

Synthetic in-memory series only -- no network, no real data.

Two distinct jobs:

  1. GUARD THE PRE-REGISTRATION. Campaign 07's constants ARE the
     pre-registration (docs/RESEARCH_CAMPAIGN_07_oi_long_horizon.md).
     RD-11 B makes them immutable once locked, so a test asserts each
     literal value: any silent post-hoc edit fails the suite.

  2. GUARD THE ONE THING THIS CAMPAIGN CHANGES -- the horizon. The
     non-overlap guarantee is what makes a longer horizon statistically
     honest; at 72h/120h a regression to overlapping windows would
     silently manufacture significance.
"""

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from exchange_adapter import Symbol

from alpha_engine._time import parse_utc
from alpha_engine.historical.models import MarkPriceObservation, OpenInterestObservation
from research.campaign_01_open_interest.build_samples import build_samples
from research.campaign_07_oi_long_horizon import run_campaign as c07

_START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _oi(symbol, n_hours):
    return tuple(OpenInterestObservation(
        symbol=symbol, observed_at_utc=(_START + timedelta(hours=h)).isoformat(),
        value=Decimal("1000") + Decimal(h), source="binance",
        source_detail="synthetic", ingested_at_utc=_START.isoformat(),
    ) for h in range(n_hours))


def _mark(symbol, n_hours):
    return tuple(MarkPriceObservation(
        symbol=symbol, observed_at_utc=(_START + timedelta(hours=h)).isoformat(),
        value=Decimal("100") + Decimal(h % 7), source="binance",
        source_detail="synthetic", ingested_at_utc=_START.isoformat(),
    ) for h in range(n_hours))


class TestPreRegistrationIsImmutable(unittest.TestCase):
    """RD-11 B: every locked constant is asserted literally. If a future
    edit changes one after results are observed, this fails loudly."""

    def test_acceptance_criteria_match_the_campaign_document(self):
        self.assertEqual(c07.MIN_HIT_RATE, 0.55)
        self.assertEqual(c07.MIN_SIGNALED_SAMPLES, 100)

    def test_validation_parameters_match_the_campaign_document(self):
        self.assertEqual(c07.N_FOLDS, 3)
        self.assertEqual(c07.N_RESAMPLES, 1000)
        self.assertEqual(c07.SEED, 7)
        self.assertEqual(c07.WINDOW_DAYS, 30)

    def test_registered_configurations_are_exactly_the_three_that_passed_feasibility(self):
        self.assertEqual(c07.CONFIGURATIONS, (
            (72, "0.40", "PRIMARY"),
            (72, "0.25", "robustness-threshold"),
            (120, "0.40", "robustness-horizon"),
        ))

    def test_exactly_one_configuration_is_primary(self):
        primaries = [c for c in c07.CONFIGURATIONS if c[2] == "PRIMARY"]
        self.assertEqual(len(primaries), 1)
        self.assertEqual(primaries[0][:2], (72, "0.40"))

    def test_both_directions_registered_separately(self):
        """Constitution Section 6 forbids one tunable candidate where a
        human could pick the direction that happened to work."""
        self.assertEqual(c07.DIRECTIONS, ("contrarian", "momentum"))

    def test_168h_is_not_registered(self):
        """168h measured worst-fold 66 against a floor of 100 and was
        excluded at feasibility. It must not reappear."""
        self.assertNotIn(168, [h for h, _, _ in c07.CONFIGURATIONS])

    def test_six_experiments_are_produced(self):
        self.assertEqual(len(c07.CONFIGURATIONS) * len(c07.DIRECTIONS), 6)

    def test_defer_ceiling_is_declared_in_known_limitations(self):
        joined = " ".join(c07._KNOWN_LIMITATIONS).lower()
        self.assertIn("defer-ceiling", joined)
        self.assertIn("not promotion-eligible", joined)

    def test_shared_upstream_field_limitation_is_declared(self):
        joined = " ".join(c07._KNOWN_LIMITATIONS).lower()
        self.assertIn("sum_open_interest_value / sum_open_interest", joined)
        self.assertIn("independent", joined)

    def test_survivorship_and_nonstationarity_declared(self):
        joined = " ".join(c07._KNOWN_LIMITATIONS).lower()
        self.assertIn("survivorship", joined)
        self.assertIn("non-stationarity", joined)


class TestNonOverlapAtLongerHorizons(unittest.TestCase):
    """The guarantee that makes a longer horizon honest."""

    def test_samples_are_spaced_at_least_the_horizon_apart(self):
        sym = Symbol("BTC")
        n = 24 * 200
        for horizon in (72, 120):
            with self.subTest(horizon=horizon):
                built = build_samples(
                    {sym: _oi(sym, n)}, {sym: _mark(sym, n)},
                    window_days=30, horizon_hours=horizon, sample_spacing_hours=horizon,
                )
                times = sorted(parse_utc(s.feature_value.computed_at_utc)
                               for s in built.pctrank_samples)
                self.assertGreater(len(times), 2)
                gaps = [(b - a).total_seconds() / 3600 for a, b in zip(times, times[1:])]
                self.assertGreaterEqual(min(gaps), horizon)

    def test_overlapping_spacing_is_refused(self):
        """Spacing < horizon would overlap outcome windows -- the
        campaign's cardinal sin. build_samples must refuse it."""
        sym = Symbol("BTC")
        for horizon in (72, 120):
            with self.subTest(horizon=horizon):
                with self.assertRaises(ValueError):
                    build_samples({sym: _oi(sym, 2000)}, {sym: _mark(sym, 2000)},
                                  window_days=30, horizon_hours=horizon,
                                  sample_spacing_hours=24)

    def test_outcome_timestamp_is_strictly_after_the_feature_timestamp(self):
        """No look-ahead: the label must be observed after the feature."""
        sym = Symbol("BTC")
        built = build_samples({sym: _oi(sym, 24 * 200)}, {sym: _mark(sym, 24 * 200)},
                              window_days=30, horizon_hours=72, sample_spacing_hours=72)
        self.assertTrue(built.pctrank_samples)
        for s in built.pctrank_samples:
            self.assertGreater(parse_utc(s.outcome_observed_at_utc),
                               parse_utc(s.feature_value.computed_at_utc))

    def test_longer_horizon_yields_proportionally_fewer_samples(self):
        """Non-overlapping sampling divides N by the horizon -- the cost
        that made 168h infeasible."""
        sym = Symbol("BTC")
        n = 24 * 300
        counts = {}
        for horizon in (72, 120):
            built = build_samples({sym: _oi(sym, n)}, {sym: _mark(sym, n)},
                                  window_days=30, horizon_hours=horizon,
                                  sample_spacing_hours=horizon)
            counts[horizon] = len(built.pctrank_samples)
        self.assertGreater(counts[72], counts[120])
        ratio = counts[72] / max(counts[120], 1)
        self.assertGreater(ratio, 1.3)  # ~120/72 = 1.67, allow grid slack


class TestSignalledCensus(unittest.TestCase):
    """The census is outcome-blind and must partition folds exactly."""

    def _built(self, horizon=72):
        sym = Symbol("BTC")
        n = 24 * 300
        return build_samples({sym: _oi(sym, n)}, {sym: _mark(sym, n)},
                             window_days=30, horizon_hours=horizon,
                             sample_spacing_hours=horizon).pctrank_samples

    def test_census_returns_one_count_per_fold(self):
        counts = c07.signalled_census(self._built(), "0.40", n_folds=3)
        self.assertEqual(len(counts), 3)
        self.assertTrue(all(isinstance(c, int) for c in counts))

    def test_lower_threshold_signals_at_least_as_often(self):
        loose = sum(c07.signalled_census(self._built(), "0.25"))
        tight = sum(c07.signalled_census(self._built(), "0.40"))
        self.assertGreaterEqual(loose, tight)

    def test_census_never_exceeds_total_samples(self):
        built = self._built()
        self.assertLessEqual(sum(c07.signalled_census(built, "0.25")), len(built))


class TestSpecConstruction(unittest.TestCase):
    def test_spec_carries_the_locked_acceptance_criteria(self):
        spec = c07._spec(72, "0.40", "contrarian", (Symbol("BTC"),))
        self.assertEqual(spec.acceptance_criteria["min_hit_rate"], 0.55)
        self.assertEqual(spec.acceptance_criteria["min_signaled_samples"], 100)

    def test_spec_cadence_matches_the_horizon(self):
        for horizon in (72, 120):
            spec = c07._spec(horizon, "0.40", "contrarian", (Symbol("BTC"),))
            self.assertEqual(spec.cadence_seconds, horizon * 3600)

    def test_spec_threshold_and_direction_are_recorded(self):
        spec = c07._spec(120, "0.25", "momentum", (Symbol("BTC"),))
        self.assertEqual(spec.parameters["threshold"], "0.25")
        self.assertEqual(spec.parameters["direction_convention"], "momentum")


if __name__ == "__main__":
    unittest.main()
