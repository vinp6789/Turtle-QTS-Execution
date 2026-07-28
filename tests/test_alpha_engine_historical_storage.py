"""Verification tests for alpha_engine.historical.storage (CSV load/
merge/incremental rerun/atomic write)."""

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from exchange_adapter import Symbol

from alpha_engine.historical import HistoricalDataError
from alpha_engine.historical.models import FundingRateObservation, OpenInterestObservation
from alpha_engine.historical.storage import MergeResult, load, merge_and_write, series_filename


def _obs(hour, value="50000", symbol="BTC", source="binance"):
    return OpenInterestObservation(
        symbol=Symbol(symbol),
        observed_at_utc=f"2024-01-01T{hour:02d}:00:00+00:00",
        value=Decimal(value),
        source=source,
        source_detail="test-file",
        ingested_at_utc="2024-02-01T00:00:00+00:00",
    )


class TestSeriesFilename(unittest.TestCase):
    def test_deterministic_name(self):
        name = series_filename("open_interest", Symbol("BTC"), "binance")
        self.assertEqual(name, "open_interest__BTC__binance.csv")

    def test_wrong_symbol_type_raises(self):
        with self.assertRaises(HistoricalDataError):
            series_filename("open_interest", "BTC", "binance")

    def test_empty_metric_raises(self):
        with self.assertRaises(HistoricalDataError):
            series_filename("", Symbol("BTC"), "binance")


class TestLoad(unittest.TestCase):
    def test_missing_file_returns_empty_tuple(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "does_not_exist.csv"
            self.assertEqual(load(path, OpenInterestObservation), ())

    def test_round_trips_through_merge_and_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "series.csv"
            observations = (_obs(0), _obs(1))
            merge_and_write(path, OpenInterestObservation, observations)
            loaded = load(path, OpenInterestObservation)
            self.assertEqual(set(loaded), set(observations))


class TestMergeAndWrite(unittest.TestCase):
    def test_creates_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a" / "b" / "series.csv"
            merge_and_write(path, OpenInterestObservation, (_obs(0),))
            self.assertTrue(path.is_file())

    def test_first_write_reports_zero_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "series.csv"
            result = merge_and_write(path, OpenInterestObservation, (_obs(0), _obs(1)))
            self.assertIsInstance(result, MergeResult)
            self.assertEqual(result.existing_count, 0)
            self.assertEqual(result.added_count, 2)
            self.assertEqual(result.conflict_keys, ())

    def test_incremental_rerun_only_adds_new_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "series.csv"
            merge_and_write(path, OpenInterestObservation, (_obs(0), _obs(1)))
            # Re-run with an overlapping + one genuinely new row.
            result = merge_and_write(path, OpenInterestObservation, (_obs(0), _obs(1), _obs(2)))
            self.assertEqual(result.existing_count, 2)
            self.assertEqual(result.added_count, 1)
            self.assertEqual(len(load(path, OpenInterestObservation)), 3)

    def test_conflicting_duplicate_keeps_existing_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "series.csv"
            merge_and_write(path, OpenInterestObservation, (_obs(0, value="50000"),))
            result = merge_and_write(path, OpenInterestObservation, (_obs(0, value="99999"),))
            self.assertEqual(len(result.conflict_keys), 1)
            self.assertEqual(result.added_count, 0)
            loaded = load(path, OpenInterestObservation)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].value, Decimal("50000"))  # existing kept, not overwritten

    def test_identical_duplicate_is_silent_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "series.csv"
            merge_and_write(path, OpenInterestObservation, (_obs(0),))
            result = merge_and_write(path, OpenInterestObservation, (_obs(0),))
            self.assertEqual(result.conflict_keys, ())
            self.assertEqual(result.added_count, 0)
            self.assertEqual(len(load(path, OpenInterestObservation)), 1)

    def test_output_is_sorted_chronologically_regardless_of_input_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "series.csv"
            merge_and_write(path, OpenInterestObservation, (_obs(2), _obs(0), _obs(1)))
            loaded = load(path, OpenInterestObservation)
            self.assertEqual([o.observed_at_utc for o in loaded], [
                "2024-01-01T00:00:00+00:00", "2024-01-01T01:00:00+00:00", "2024-01-01T02:00:00+00:00",
            ])

    def test_supports_funding_rate_observation_type_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "funding.csv"
            obs = FundingRateObservation(
                symbol=Symbol("BTC"), observed_at_utc="2024-01-01T00:00:00+00:00",
                value=Decimal("-0.0002"), source="hyperliquid", source_detail="test",
                ingested_at_utc="2024-02-01T00:00:00+00:00",
            )
            merge_and_write(path, FundingRateObservation, (obs,))
            loaded = load(path, FundingRateObservation)
            self.assertEqual(loaded, (obs,))

    def test_wrong_new_observations_type_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "series.csv"
            with self.assertRaises(HistoricalDataError):
                merge_and_write(path, OpenInterestObservation, [_obs(0)])  # list, not tuple

    def test_unexpected_csv_header_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "series.csv"
            path.write_text("wrong,header\n1,2\n", encoding="utf-8")
            with self.assertRaises(HistoricalDataError):
                load(path, OpenInterestObservation)


if __name__ == "__main__":
    unittest.main()
