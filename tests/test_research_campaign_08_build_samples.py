"""Point-in-time correctness + pre-registration integrity tests for
Research Campaign 08 (hourly liquidation density).

Synthetic in-memory series only -- no network, no real data.

Guards the campaign's methodological claims (no look-ahead,
non-overlapping outcomes, RD-14 zeros, RD-15 exclusion, skip-never-
fabricate, determinism) and the immutability of the locked
pre-registration constants (RD-11 B).
"""

import csv
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from exchange_adapter import Symbol

from research.campaign_08_liquidation_hourly import build_samples as bs
from research.campaign_08_liquidation_hourly import run_campaign as c08

_SYMS = (Symbol("BTC"), Symbol("ETH"), Symbol("SOL"))
_T0 = datetime(2026, 1, 10, 0, tzinfo=timezone.utc)


def _write(root, symbol, liq_rows, price_hours):
    with open(Path(root) / f"liquidation__{symbol}__hyperliquid_s3.csv", "w",
              newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["observed_at_utc", "symbol", "price", "size", "side", "direction",
                    "method", "liquidated_user", "mark_price", "tid", "source",
                    "source_detail", "ingested_at_utc"])
        for hour, tid in liq_rows:
            w.writerow([hour.isoformat(), symbol, "1", "1", "A", "Open Short", "market",
                        "0x0", "1", tid, "hyperliquid_s3", "x", _T0.isoformat()])
    with open(Path(root) / f"mark_price__{symbol}__hyperliquid_1h.csv", "w",
              newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["observed_at_utc", "symbol", "value", "source", "source_detail",
                    "ingested_at_utc"])
        for i, hour in enumerate(price_hours):
            w.writerow([hour.isoformat(), symbol, str(100 + i), "hyperliquid_1h", "x",
                        _T0.isoformat()])


def _fixture(root, n_hours=200, liq_every=2, events_per_hour=3):
    hours = [_T0 + timedelta(hours=i) for i in range(n_hours)]
    for sym in ("BTC", "ETH", "SOL"):
        rows = []
        for i, h in enumerate(hours):
            if i % liq_every == 0:
                for j in range(events_per_hour + (i % 5)):
                    rows.append((h, f"{sym}-{i}-{j}"))
        _write(root, sym, rows, hours)
    return hours


class TestPreRegistrationIsImmutable(unittest.TestCase):
    """RD-11 B: locked constants asserted literally."""

    def test_locked_constants(self):
        self.assertEqual(c08.PERCENTILE, 75)
        self.assertEqual(c08.THRESHOLD, "1.0")
        self.assertEqual(c08.HORIZON_HOURS, 1)
        self.assertEqual(c08.MIN_HIT_RATE, 0.55)
        self.assertEqual(c08.MIN_SIGNALED_SAMPLES, 100)
        self.assertEqual(c08.N_FOLDS, (3, 5))
        self.assertEqual(c08.N_RESAMPLES, 1000)
        self.assertEqual(c08.SEED, 7)
        self.assertEqual(c08.DIRECTIONS, ("contrarian", "momentum"))

    def test_p90_and_p99_are_not_registered(self):
        """Both were excluded on measurement (effective 85 and 6 vs a
        floor of 100). They must not reappear."""
        self.assertNotIn(c08.PERCENTILE, (90, 99))

    def test_four_experiments(self):
        self.assertEqual(len(c08.N_FOLDS) * len(c08.DIRECTIONS), 4)

    def test_uses_the_liquidation_family_never_the_funding_one(self):
        spec = c08._spec(3, "contrarian", _SYMS)
        self.assertEqual(spec.name, "liquidation_density_rule")
        self.assertEqual(spec.feature_name, "liquidation_density_hourly")
        self.assertNotIn("funding", spec.feature_name)

    def test_known_limitations_declare_the_binding_constraints(self):
        joined = " ".join(c08._KNOWN_LIMITATIONS).lower()
        for expected in ("zero-inflation", "venue retention", "cross-symbol", "rd-11 a"):
            self.assertIn(expected, joined)


class TestSampleConstruction(unittest.TestCase):
    def test_no_look_ahead_outcome_is_after_the_feature(self):
        with tempfile.TemporaryDirectory() as tmp:
            _fixture(tmp)
            built = bs.build_samples(_SYMS, root=Path(tmp))
            self.assertTrue(built.samples)
            for s in built.samples:
                self.assertGreater(
                    datetime.fromisoformat(s.outcome_observed_at_utc),
                    datetime.fromisoformat(s.feature_value.computed_at_utc))

    def test_outcome_window_is_exactly_one_hour(self):
        """Non-overlapping by construction: windows abut, never overlap."""
        with tempfile.TemporaryDirectory() as tmp:
            _fixture(tmp)
            built = bs.build_samples(_SYMS, root=Path(tmp))
            for s in built.samples:
                delta = (datetime.fromisoformat(s.outcome_observed_at_utc)
                         - datetime.fromisoformat(s.feature_value.computed_at_utc))
                self.assertEqual(delta, timedelta(hours=1))

    def test_rd14_absent_hours_become_zero_not_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            _fixture(tmp, liq_every=2)   # half the hours have no rows at all
            built = bs.build_samples(_SYMS, root=Path(tmp))
            zeros = [s for s in built.samples if s.feature_value.value == 0]
            self.assertTrue(zeros, "absent hours must materialize as zero")
            for s in zeros:
                self.assertTrue(s.feature_value.available)
                self.assertIsNone(s.feature_value.reason)

    def test_rd15_excluded_day_never_enters(self):
        with tempfile.TemporaryDirectory() as tmp:
            hours = [datetime(2025, 7, 27, h, tzinfo=timezone.utc) for h in range(8, 24)]
            hours += [datetime(2025, 7, 28, h, tzinfo=timezone.utc) for h in range(24)]
            for sym in ("BTC", "ETH", "SOL"):
                _write(tmp, sym, [(h, f"{sym}-{i}") for i, h in enumerate(hours)], hours)
            built = bs.build_samples(_SYMS, root=Path(tmp))
            days = {s.feature_value.computed_at_utc[:10] for s in built.samples}
            self.assertNotIn("2025-07-27", days)

    def test_missing_forward_price_is_skipped_never_fabricated(self):
        with tempfile.TemporaryDirectory() as tmp:
            hours = [_T0 + timedelta(hours=i) for i in range(50)]
            for sym in ("BTC", "ETH", "SOL"):
                # drop the final price so the last hour has no forward point
                _write(tmp, sym, [(h, f"{sym}-{i}") for i, h in enumerate(hours)], hours)
            built = bs.build_samples(_SYMS, root=Path(tmp))
            self.assertEqual(built.diagnostics["skip_no_price_forward"], 3)

    def test_normalization_is_exactly_count_ge_per_symbol_p75(self):
        with tempfile.TemporaryDirectory() as tmp:
            _fixture(tmp)
            built = bs.build_samples(_SYMS, root=Path(tmp))
            counts = built.hourly_counts
            for s in built.samples:
                sym = s.feature_value.symbol.value
                hour = datetime.fromisoformat(s.feature_value.computed_at_utc)
                raw = counts[sym].get(hour, 0)
                signalled_by_value = s.feature_value.value >= 1
                signalled_by_rule = Decimal(raw) >= built.scale[sym]
                self.assertEqual(signalled_by_value, signalled_by_rule)

    def test_threshold_derived_per_symbol_not_pooled(self):
        with tempfile.TemporaryDirectory() as tmp:
            _fixture(tmp)
            built = bs.build_samples(_SYMS, root=Path(tmp))
            self.assertEqual(set(built.scale), {"BTC", "ETH", "SOL"})
            for v in built.scale.values():
                self.assertGreater(v, 0)

    def test_all_zero_distribution_refuses_rather_than_dividing_by_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            hours = [_T0 + timedelta(hours=i) for i in range(60)]
            for sym in ("BTC", "ETH", "SOL"):
                _write(tmp, sym, [], hours)   # no liquidations at all
            with self.assertRaises(ValueError):
                bs.build_samples(_SYMS, root=Path(tmp))

    def test_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            _fixture(tmp)
            a = bs.build_samples(_SYMS, root=Path(tmp))
            b = bs.build_samples(_SYMS, root=Path(tmp))
            self.assertEqual(len(a.samples), len(b.samples))
            self.assertEqual([s.feature_value.value for s in a.samples],
                             [s.feature_value.value for s in b.samples])
            self.assertEqual(a.scale, b.scale)

    def test_regime_labeler_is_price_derived_and_optional(self):
        with tempfile.TemporaryDirectory() as tmp:
            _fixture(tmp, n_hours=400)
            prices = bs.load_hourly_prices(_SYMS, Path(tmp))
            labeler = bs.make_regime_labeler(prices["BTC"])
            built = bs.build_samples(_SYMS, root=Path(tmp), regime_labeler=labeler)
            labels = {s.regime_label for s in built.samples}
            self.assertTrue(labels <= {"bull", "bear", "chop", "unknown"})


if __name__ == "__main__":
    unittest.main()
