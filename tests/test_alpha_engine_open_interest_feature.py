"""Verification tests for the Open Interest Feature (Alpha Engine
Milestone 2.2).

Mirrors test_alpha_engine_funding_rate_feature.py exactly -- same
structure, same test intent, applied to the second data source.
"""

import unittest
from decimal import Decimal

from exchange_adapter import Symbol

from alpha_engine.data_sources import OpenInterestReading
from alpha_engine.features import FeatureError, OpenInterestFeature


def _available_reading(symbol=None, value=Decimal("12345.6789"), fetched_at="2026-01-01T00:00:00+00:00",
                        observed_at="2026-01-01T00:00:00+00:00"):
    return OpenInterestReading(
        symbol=symbol or Symbol("BTC"), fetched_at_utc=fetched_at, available=True,
        value=value, observed_at_utc=observed_at,
    )


def _unavailable_reading(symbol=None, fetched_at="2026-01-01T00:00:00+00:00", reason="simulated failure"):
    return OpenInterestReading(
        symbol=symbol or Symbol("BTC"), fetched_at_utc=fetched_at, available=False, reason=reason,
    )


class TestOpenInterestFeatureMetadata(unittest.TestCase):
    def test_metadata_reports_name_version_warmup_and_inputs(self):
        meta = OpenInterestFeature.metadata()
        self.assertEqual(meta.name, "open_interest_raw")
        self.assertEqual(meta.version, "v1")
        self.assertEqual(meta.warmup_periods, 0)
        self.assertEqual(meta.input_data_sources, ("open_interest",))


class TestComputeAvailable(unittest.TestCase):
    def test_available_reading_passes_through_the_exact_value(self):
        reading = _available_reading(value=Decimal("98765.4321"))
        result = OpenInterestFeature.compute(reading)
        self.assertTrue(result.available)
        self.assertEqual(result.value, Decimal("98765.4321"))
        self.assertEqual(result.feature_name, "open_interest_raw")
        self.assertEqual(result.feature_version, "v1")
        self.assertIsNone(result.reason)

    def test_symbol_and_timestamp_carried_through(self):
        reading = _available_reading(symbol=Symbol("ETH"), fetched_at="2026-03-01T12:00:00+00:00")
        result = OpenInterestFeature.compute(reading)
        self.assertEqual(result.symbol, Symbol("ETH"))
        self.assertEqual(result.computed_at_utc, "2026-03-01T12:00:00+00:00")


class TestComputeUnavailable(unittest.TestCase):
    def test_unavailable_reading_yields_unavailable_feature(self):
        reading = _unavailable_reading(reason="ConnectionError: simulated outage")
        result = OpenInterestFeature.compute(reading)
        self.assertFalse(result.available)
        self.assertIsNone(result.value)
        self.assertIn("ConnectionError", result.reason)

    def test_unavailable_never_raises(self):
        reading = _unavailable_reading(reason="symbol 'DOGE' not found in venue universe")
        try:
            result = OpenInterestFeature.compute(reading)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"compute() must never raise for an unavailable input reading, raised {exc!r}")
        self.assertFalse(result.available)


class TestComputeInputValidation(unittest.TestCase):
    def test_rejects_non_reading_argument(self):
        with self.assertRaises(FeatureError):
            OpenInterestFeature.compute("not-a-reading")

    def test_rejects_none(self):
        with self.assertRaises(FeatureError):
            OpenInterestFeature.compute(None)

    def test_rejects_a_funding_rate_reading(self):
        # A different provider's reading type must not be silently accepted.
        from alpha_engine.data_sources import FundingRateReading
        wrong_type = FundingRateReading(
            symbol=Symbol("BTC"), fetched_at_utc="2026-01-01T00:00:00+00:00",
            available=True, value=Decimal("0.0001"), observed_at_utc="2026-01-01T00:00:00+00:00",
        )
        with self.assertRaises(FeatureError):
            OpenInterestFeature.compute(wrong_type)


class TestPurityAndDeterminism(unittest.TestCase):
    def test_repeated_calls_with_identical_input_yield_identical_output(self):
        reading = _available_reading(value=Decimal("500.5"))
        first = OpenInterestFeature.compute(reading)
        second = OpenInterestFeature.compute(reading)
        self.assertEqual(first, second)

    def test_a_call_with_a_different_reading_does_not_affect_a_later_identical_call(self):
        reading_a = _available_reading(symbol=Symbol("BTC"), value=Decimal("100"))
        reading_b = _available_reading(symbol=Symbol("ETH"), value=Decimal("200"))

        result_a1 = OpenInterestFeature.compute(reading_a)
        OpenInterestFeature.compute(reading_b)  # unrelated intervening call
        result_a2 = OpenInterestFeature.compute(reading_a)

        self.assertEqual(result_a1, result_a2)

    def test_two_separate_instances_compute_identically(self):
        reading = _available_reading(value=Decimal("300"))
        instance_1 = OpenInterestFeature()
        instance_2 = OpenInterestFeature()
        self.assertEqual(instance_1.compute(reading), instance_2.compute(reading))

    def test_class_level_and_instance_level_calls_agree(self):
        reading = _available_reading(value=Decimal("300"))
        self.assertEqual(OpenInterestFeature.compute(reading), OpenInterestFeature().compute(reading))


if __name__ == "__main__":
    unittest.main()
