"""Verification tests for historical observation value types
(alpha_engine.historical.models)."""

import unittest
from decimal import Decimal

from exchange_adapter import Symbol

from alpha_engine.historical import HistoricalDataError
from alpha_engine.historical.models import (
    FundingRateObservation,
    MarkPriceObservation,
    OpenInterestObservation,
)

_OK_KWARGS = dict(
    symbol=Symbol("BTC"),
    observed_at_utc="2024-01-15T00:00:00+00:00",
    value=Decimal("0.0001"),
    source="binance",
    source_detail="BTCUSDT-fundingRate-2024-01.zip",
    ingested_at_utc="2024-02-01T00:00:00+00:00",
)


class TestFundingRateObservation(unittest.TestCase):
    def test_valid_construction(self):
        obs = FundingRateObservation(**_OK_KWARGS)
        self.assertEqual(obs.symbol, Symbol("BTC"))
        self.assertEqual(obs.value, Decimal("0.0001"))

    def test_negative_value_allowed(self):
        # Funding rate is signed -- negative is a valid, common value.
        obs = FundingRateObservation(**{**_OK_KWARGS, "value": Decimal("-0.0005")})
        self.assertEqual(obs.value, Decimal("-0.0005"))

    def test_wrong_symbol_type_raises(self):
        with self.assertRaises(HistoricalDataError):
            FundingRateObservation(**{**_OK_KWARGS, "symbol": "BTC"})

    def test_non_decimal_value_raises(self):
        with self.assertRaises(HistoricalDataError):
            FundingRateObservation(**{**_OK_KWARGS, "value": 0.0001})

    def test_empty_source_raises(self):
        with self.assertRaises(HistoricalDataError):
            FundingRateObservation(**{**_OK_KWARGS, "source": ""})

    def test_empty_source_detail_raises(self):
        with self.assertRaises(HistoricalDataError):
            FundingRateObservation(**{**_OK_KWARGS, "source_detail": ""})

    def test_unparseable_observed_at_utc_raises(self):
        with self.assertRaises(HistoricalDataError):
            FundingRateObservation(**{**_OK_KWARGS, "observed_at_utc": "not-a-timestamp"})

    def test_unparseable_ingested_at_utc_raises(self):
        with self.assertRaises(HistoricalDataError):
            FundingRateObservation(**{**_OK_KWARGS, "ingested_at_utc": "not-a-timestamp"})

    def test_empty_observed_at_utc_raises(self):
        with self.assertRaises(HistoricalDataError):
            FundingRateObservation(**{**_OK_KWARGS, "observed_at_utc": ""})


class TestOpenInterestObservation(unittest.TestCase):
    def _kwargs(self, **overrides):
        return {**_OK_KWARGS, "value": Decimal("50000"), **overrides}

    def test_valid_construction(self):
        obs = OpenInterestObservation(**self._kwargs())
        self.assertEqual(obs.value, Decimal("50000"))

    def test_zero_value_allowed(self):
        obs = OpenInterestObservation(**self._kwargs(value=Decimal("0")))
        self.assertEqual(obs.value, Decimal("0"))

    def test_negative_value_raises(self):
        # Open interest is an unsigned magnitude -- mirrors
        # data_sources.open_interest.OpenInterestReading's own domain
        # constraint.
        with self.assertRaises(HistoricalDataError):
            OpenInterestObservation(**self._kwargs(value=Decimal("-1")))

    def test_wrong_symbol_type_raises(self):
        with self.assertRaises(HistoricalDataError):
            OpenInterestObservation(**self._kwargs(symbol="BTC"))


class TestMarkPriceObservation(unittest.TestCase):
    def _kwargs(self, **overrides):
        return {**_OK_KWARGS, "value": Decimal("42000.5"), **overrides}

    def test_valid_construction(self):
        obs = MarkPriceObservation(**self._kwargs())
        self.assertEqual(obs.value, Decimal("42000.5"))

    def test_zero_value_raises(self):
        with self.assertRaises(HistoricalDataError):
            MarkPriceObservation(**self._kwargs(value=Decimal("0")))

    def test_negative_value_raises(self):
        with self.assertRaises(HistoricalDataError):
            MarkPriceObservation(**self._kwargs(value=Decimal("-1")))

    def test_wrong_symbol_type_raises(self):
        with self.assertRaises(HistoricalDataError):
            MarkPriceObservation(**self._kwargs(symbol="BTC"))


if __name__ == "__main__":
    unittest.main()
