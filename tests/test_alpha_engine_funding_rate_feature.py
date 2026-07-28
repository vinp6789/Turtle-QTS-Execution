"""Verification tests for the Funding Rate Feature (Alpha Engine
Milestone 2.1).

Tests the feature layer in isolation from the provider: a
FundingRateReading is constructed directly here (no real Engine/adapter
needed), since FundingRateFeature.compute() is a pure function of exactly
that one argument. This mirrors the layering itself -- the provider
(Milestone 1.1) is tested against a real adapter fixture; the feature is
tested against the provider's output type alone.
"""

import unittest
from decimal import Decimal

from exchange_adapter import Symbol

from alpha_engine.data_sources import FundingRateReading
from alpha_engine.features import FeatureError, FeatureMetadata, FeatureValue, FundingRateFeature


def _available_reading(symbol=None, value=Decimal("0.0001"), fetched_at="2026-01-01T00:00:00+00:00",
                        observed_at="2026-01-01T00:00:00+00:00"):
    return FundingRateReading(
        symbol=symbol or Symbol("BTC"), fetched_at_utc=fetched_at, available=True,
        value=value, observed_at_utc=observed_at,
    )


def _unavailable_reading(symbol=None, fetched_at="2026-01-01T00:00:00+00:00", reason="simulated failure"):
    return FundingRateReading(
        symbol=symbol or Symbol("BTC"), fetched_at_utc=fetched_at, available=False, reason=reason,
    )


class TestFeatureMetadataValidation(unittest.TestCase):
    def test_blank_name_raises(self):
        with self.assertRaises(FeatureError):
            FeatureMetadata(name="  ", version="v1", warmup_periods=0, input_data_sources=("x",))

    def test_blank_version_raises(self):
        with self.assertRaises(FeatureError):
            FeatureMetadata(name="x", version=" ", warmup_periods=0, input_data_sources=("x",))

    def test_negative_warmup_raises(self):
        with self.assertRaises(FeatureError):
            FeatureMetadata(name="x", version="v1", warmup_periods=-1, input_data_sources=("x",))

    def test_non_tuple_input_data_sources_raises(self):
        with self.assertRaises(FeatureError):
            FeatureMetadata(name="x", version="v1", warmup_periods=0, input_data_sources=["x"])

    def test_valid_metadata_constructs(self):
        meta = FeatureMetadata(name="x", version="v1", warmup_periods=0, input_data_sources=("funding_rate",))
        self.assertEqual(meta.name, "x")


class TestFeatureValueValidation(unittest.TestCase):
    def test_available_without_value_raises(self):
        with self.assertRaises(FeatureError):
            FeatureValue(
                feature_name="f", feature_version="v1", symbol=Symbol("BTC"),
                computed_at_utc="2026-01-01T00:00:00+00:00", available=True, value=None,
            )

    def test_available_with_reason_raises(self):
        with self.assertRaises(FeatureError):
            FeatureValue(
                feature_name="f", feature_version="v1", symbol=Symbol("BTC"),
                computed_at_utc="2026-01-01T00:00:00+00:00", available=True,
                value=Decimal("1"), reason="should not be set",
            )

    def test_unavailable_with_value_raises(self):
        with self.assertRaises(FeatureError):
            FeatureValue(
                feature_name="f", feature_version="v1", symbol=Symbol("BTC"),
                computed_at_utc="2026-01-01T00:00:00+00:00", available=False,
                value=Decimal("1"), reason="x",
            )

    def test_unavailable_without_reason_raises(self):
        with self.assertRaises(FeatureError):
            FeatureValue(
                feature_name="f", feature_version="v1", symbol=Symbol("BTC"),
                computed_at_utc="2026-01-01T00:00:00+00:00", available=False, reason=None,
            )


class TestFundingRateFeatureMetadata(unittest.TestCase):
    def test_metadata_reports_name_version_warmup_and_inputs(self):
        meta = FundingRateFeature.metadata()
        self.assertEqual(meta.name, "funding_rate_raw")
        self.assertEqual(meta.version, "v1")
        self.assertEqual(meta.warmup_periods, 0)
        self.assertEqual(meta.input_data_sources, ("funding_rate",))


class TestComputeAvailable(unittest.TestCase):
    def test_available_reading_passes_through_the_exact_value(self):
        reading = _available_reading(value=Decimal("0.00037"))
        result = FundingRateFeature.compute(reading)
        self.assertTrue(result.available)
        self.assertEqual(result.value, Decimal("0.00037"))
        self.assertEqual(result.feature_name, "funding_rate_raw")
        self.assertEqual(result.feature_version, "v1")
        self.assertIsNone(result.reason)

    def test_negative_rate_sign_is_preserved(self):
        reading = _available_reading(value=Decimal("-0.0002"))
        result = FundingRateFeature.compute(reading)
        self.assertEqual(result.value, Decimal("-0.0002"))

    def test_symbol_and_timestamp_carried_through(self):
        reading = _available_reading(symbol=Symbol("ETH"), fetched_at="2026-03-01T12:00:00+00:00")
        result = FundingRateFeature.compute(reading)
        self.assertEqual(result.symbol, Symbol("ETH"))
        self.assertEqual(result.computed_at_utc, "2026-03-01T12:00:00+00:00")


class TestComputeUnavailable(unittest.TestCase):
    def test_unavailable_reading_yields_unavailable_feature(self):
        reading = _unavailable_reading(reason="stale: too old")
        result = FundingRateFeature.compute(reading)
        self.assertFalse(result.available)
        self.assertIsNone(result.value)
        self.assertIn("stale: too old", result.reason)

    def test_unavailable_never_raises(self):
        reading = _unavailable_reading(reason="ExchangeConnectionError: simulated outage")
        try:
            result = FundingRateFeature.compute(reading)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"compute() must never raise for an unavailable input reading, raised {exc!r}")
        self.assertFalse(result.available)


class TestComputeInputValidation(unittest.TestCase):
    def test_rejects_non_reading_argument(self):
        with self.assertRaises(FeatureError):
            FundingRateFeature.compute("not-a-reading")

    def test_rejects_none(self):
        with self.assertRaises(FeatureError):
            FundingRateFeature.compute(None)


class TestPurityAndDeterminism(unittest.TestCase):
    """The 'causality, adapted' proof this milestone's docstrings
    describe: with no historical time series to index into, causality
    reduces to compute() being a pure function of exactly its one
    argument -- proven here by repeatability and non-interference across
    calls, rather than by a historical-index audit that would not
    correspond to any real capability of this system yet."""

    def test_repeated_calls_with_identical_input_yield_identical_output(self):
        reading = _available_reading(value=Decimal("0.0001"))
        first = FundingRateFeature.compute(reading)
        second = FundingRateFeature.compute(reading)
        self.assertEqual(first, second)

    def test_a_call_with_a_different_reading_does_not_affect_a_later_identical_call(self):
        reading_a = _available_reading(symbol=Symbol("BTC"), value=Decimal("0.0001"))
        reading_b = _available_reading(symbol=Symbol("ETH"), value=Decimal("0.0009"))

        result_a1 = FundingRateFeature.compute(reading_a)
        FundingRateFeature.compute(reading_b)  # unrelated intervening call
        result_a2 = FundingRateFeature.compute(reading_a)

        self.assertEqual(result_a1, result_a2)

    def test_two_separate_instances_compute_identically(self):
        reading = _available_reading(value=Decimal("0.0005"))
        instance_1 = FundingRateFeature()
        instance_2 = FundingRateFeature()
        self.assertEqual(instance_1.compute(reading), instance_2.compute(reading))

    def test_class_level_and_instance_level_calls_agree(self):
        reading = _available_reading(value=Decimal("0.0005"))
        self.assertEqual(FundingRateFeature.compute(reading), FundingRateFeature().compute(reading))


if __name__ == "__main__":
    unittest.main()
