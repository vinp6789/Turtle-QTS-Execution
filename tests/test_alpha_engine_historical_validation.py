"""Verification tests for alpha_engine.historical.validation
(assess_quality, verify_checksum)."""

import hashlib
import unittest
from decimal import Decimal

from exchange_adapter import Symbol

from alpha_engine.historical import HistoricalDataError
from alpha_engine.historical.models import OpenInterestObservation
from alpha_engine.historical.validation import assess_quality, verify_checksum


def _obs(hour: int, symbol="BTC", value="50000"):
    return OpenInterestObservation(
        symbol=Symbol(symbol),
        observed_at_utc=f"2024-01-01T{hour:02d}:00:00+00:00",
        value=Decimal(value),
        source="binance",
        source_detail="test",
        ingested_at_utc="2024-02-01T00:00:00+00:00",
    )


class TestAssessQuality(unittest.TestCase):
    def test_clean_series_reports_clean(self):
        series = tuple(_obs(h) for h in range(5))
        report = assess_quality(series, expected_interval_seconds=3600)
        self.assertTrue(report.clean)
        self.assertEqual(report.total_count, 5)
        self.assertEqual(report.unique_count, 5)
        self.assertEqual(report.duplicate_count, 0)
        self.assertTrue(report.is_monotonic)
        self.assertEqual(report.gap_count, 0)

    def test_duplicate_key_detected(self):
        series = (_obs(0), _obs(1), _obs(1))  # hour 1 duplicated
        report = assess_quality(series)
        self.assertFalse(report.clean)
        self.assertEqual(report.duplicate_count, 1)
        self.assertEqual(report.unique_count, 2)
        self.assertEqual(report.duplicate_keys, (("BTC", "2024-01-01T01:00:00+00:00"),))

    def test_out_of_order_detected(self):
        series = (_obs(2), _obs(0), _obs(1))  # not chronological in list order
        report = assess_quality(series)
        self.assertFalse(report.is_monotonic)
        self.assertFalse(report.clean)
        self.assertEqual(report.out_of_order_indices, (1,))  # index 1 (_obs(0)) < index 0 (_obs(2))

    def test_gap_detected(self):
        series = (_obs(0), _obs(1), _obs(10))  # big jump from hour 1 to hour 10
        report = assess_quality(series, expected_interval_seconds=3600, gap_tolerance_factor=Decimal("1.5"))
        self.assertFalse(report.clean)
        self.assertEqual(report.gap_count, 1)
        self.assertEqual(report.gaps[0][0], "2024-01-01T01:00:00+00:00")
        self.assertEqual(report.gaps[0][1], "2024-01-01T10:00:00+00:00")

    def test_no_gap_check_when_interval_not_supplied(self):
        series = (_obs(0), _obs(10))
        report = assess_quality(series)  # no expected_interval_seconds
        self.assertEqual(report.gap_count, 0)
        self.assertTrue(report.clean)  # nothing else wrong

    def test_empty_sequence_raises(self):
        with self.assertRaises(HistoricalDataError):
            assess_quality(())

    def test_wrong_type_raises(self):
        with self.assertRaises(HistoricalDataError):
            assess_quality("not-a-sequence")

    def test_invalid_expected_interval_raises(self):
        with self.assertRaises(HistoricalDataError):
            assess_quality((_obs(0),), expected_interval_seconds=-5)

    def test_multiple_symbols_do_not_collide_as_duplicates(self):
        series = (_obs(0, symbol="BTC"), _obs(0, symbol="ETH"))
        report = assess_quality(series)
        self.assertTrue(report.clean)
        self.assertEqual(report.unique_count, 2)


class TestVerifyChecksum(unittest.TestCase):
    def test_matching_checksum_true(self):
        data = b"hello world"
        digest = hashlib.sha256(data).hexdigest()
        self.assertTrue(verify_checksum(data, digest))

    def test_case_insensitive(self):
        data = b"hello world"
        digest = hashlib.sha256(data).hexdigest().upper()
        self.assertTrue(verify_checksum(data, digest))

    def test_mismatched_checksum_false(self):
        data = b"hello world"
        self.assertFalse(verify_checksum(data, "0" * 64))

    def test_non_bytes_raises(self):
        with self.assertRaises(HistoricalDataError):
            verify_checksum("not-bytes", "0" * 64)

    def test_empty_expected_raises(self):
        with self.assertRaises(HistoricalDataError):
            verify_checksum(b"data", "")


if __name__ == "__main__":
    unittest.main()
