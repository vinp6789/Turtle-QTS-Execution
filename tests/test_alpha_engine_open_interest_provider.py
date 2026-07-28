"""Verification tests for the Open Interest Provider (Alpha Engine
Milestone 1.2).

Uses an INJECTED fake transport (a plain function matching
OpenInterestProvider's transport parameter shape) rather than a real
network call -- OpenInterestProvider was designed specifically for this
seam, mirroring the dependency-injection pattern this repository already
uses elsewhere (hyperliquid_adapter.transport.TransportFn,
MockExchangeAdapter.fail_next/set_funding_rate). No real HTTP request is
made in this file.
"""

import unittest
from decimal import Decimal

from exchange_adapter import Symbol

from alpha_engine.data_sources import DataSourceError, OpenInterestProvider, OpenInterestReading

_WELL_FORMED_RESPONSE = [
    {"universe": [{"name": "BTC", "szDecimals": 5}, {"name": "ETH", "szDecimals": 4}]},
    [{"openInterest": "12345.6789"}, {"openInterest": "987.65"}],
]


def _fake_transport(response, call_log=None):
    def _transport(url, payload, timeout_seconds):
        if call_log is not None:
            call_log.append((url, payload, timeout_seconds))
        return response
    return _transport


def _raising_transport(exc):
    def _transport(url, payload, timeout_seconds):
        raise exc
    return _transport


class TestOpenInterestReadingValidation(unittest.TestCase):
    def test_available_without_value_raises(self):
        with self.assertRaises(DataSourceError):
            OpenInterestReading(
                symbol=Symbol("BTC"), fetched_at_utc="2026-01-01T00:00:00+00:00",
                available=True, value=None, observed_at_utc=None,
            )

    def test_available_with_reason_raises(self):
        with self.assertRaises(DataSourceError):
            OpenInterestReading(
                symbol=Symbol("BTC"), fetched_at_utc="2026-01-01T00:00:00+00:00",
                available=True, value=Decimal("100"), observed_at_utc="2026-01-01T00:00:00+00:00",
                reason="should not be set",
            )

    def test_unavailable_with_value_raises(self):
        with self.assertRaises(DataSourceError):
            OpenInterestReading(
                symbol=Symbol("BTC"), fetched_at_utc="2026-01-01T00:00:00+00:00",
                available=False, value=Decimal("100"), reason="whatever",
            )

    def test_unavailable_without_reason_raises(self):
        with self.assertRaises(DataSourceError):
            OpenInterestReading(
                symbol=Symbol("BTC"), fetched_at_utc="2026-01-01T00:00:00+00:00",
                available=False, reason=None,
            )


class TestConstructorValidation(unittest.TestCase):
    def test_rejects_blank_base_url(self):
        with self.assertRaises(DataSourceError):
            OpenInterestProvider(base_url="  ")

    def test_rejects_non_callable_transport(self):
        with self.assertRaises(DataSourceError):
            OpenInterestProvider(transport="not-callable")

    def test_rejects_non_positive_timeout(self):
        with self.assertRaises(DataSourceError):
            OpenInterestProvider(timeout_seconds=0)
        with self.assertRaises(DataSourceError):
            OpenInterestProvider(timeout_seconds=-5)


class TestFetchSuccess(unittest.TestCase):
    def test_fetch_returns_available_reading_for_well_formed_response(self):
        provider = OpenInterestProvider(transport=_fake_transport(_WELL_FORMED_RESPONSE), clock=lambda: "2026-01-01T00:00:00+00:00")
        reading = provider.fetch(Symbol("BTC"))
        self.assertTrue(reading.available)
        self.assertEqual(reading.value, Decimal("12345.6789"))
        self.assertEqual(reading.symbol, Symbol("BTC"))
        self.assertIsNone(reading.reason)

    def test_observed_at_equals_fetched_at(self):
        provider = OpenInterestProvider(transport=_fake_transport(_WELL_FORMED_RESPONSE), clock=lambda: "2026-03-01T12:00:00+00:00")
        reading = provider.fetch(Symbol("BTC"))
        self.assertEqual(reading.observed_at_utc, reading.fetched_at_utc)
        self.assertEqual(reading.fetched_at_utc, "2026-03-01T12:00:00+00:00")

    def test_second_asset_in_universe_parsed_correctly(self):
        provider = OpenInterestProvider(transport=_fake_transport(_WELL_FORMED_RESPONSE))
        reading = provider.fetch(Symbol("ETH"))
        self.assertEqual(reading.value, Decimal("987.65"))

    def test_fetch_never_raises_for_valid_input(self):
        provider = OpenInterestProvider(transport=_fake_transport(_WELL_FORMED_RESPONSE))
        try:
            provider.fetch(Symbol("BTC"))
        except Exception as exc:  # noqa: BLE001
            self.fail(f"fetch() raised unexpectedly for well-formed data: {exc!r}")


class TestFetchFailureModes(unittest.TestCase):
    def test_unknown_symbol_degrades_to_unavailable(self):
        provider = OpenInterestProvider(transport=_fake_transport(_WELL_FORMED_RESPONSE))
        reading = provider.fetch(Symbol("DOGE"))
        self.assertFalse(reading.available)
        self.assertIn("not found", reading.reason)

    def test_transport_exception_degrades_to_unavailable(self):
        provider = OpenInterestProvider(transport=_raising_transport(ConnectionError("simulated outage")))
        reading = provider.fetch(Symbol("BTC"))
        self.assertFalse(reading.available)
        self.assertIn("ConnectionError", reading.reason)

    def test_non_list_response_degrades_to_unavailable(self):
        provider = OpenInterestProvider(transport=_fake_transport({"not": "a list"}))
        reading = provider.fetch(Symbol("BTC"))
        self.assertFalse(reading.available)

    def test_short_response_degrades_to_unavailable(self):
        provider = OpenInterestProvider(transport=_fake_transport([{"universe": []}]))  # only 1 element
        reading = provider.fetch(Symbol("BTC"))
        self.assertFalse(reading.available)

    def test_missing_universe_degrades_to_unavailable(self):
        provider = OpenInterestProvider(transport=_fake_transport([{}, []]))
        reading = provider.fetch(Symbol("BTC"))
        self.assertFalse(reading.available)

    def test_missing_asset_ctxs_degrades_to_unavailable(self):
        provider = OpenInterestProvider(transport=_fake_transport([{"universe": [{"name": "BTC"}]}, "not-a-list"]))
        reading = provider.fetch(Symbol("BTC"))
        self.assertFalse(reading.available)

    def test_non_string_open_interest_degrades_to_unavailable(self):
        response = [{"universe": [{"name": "BTC"}]}, [{"openInterest": 12345}]]  # int, not str
        provider = OpenInterestProvider(transport=_fake_transport(response))
        reading = provider.fetch(Symbol("BTC"))
        self.assertFalse(reading.available)

    def test_invalid_decimal_string_degrades_to_unavailable(self):
        response = [{"universe": [{"name": "BTC"}]}, [{"openInterest": "not-a-number"}]]
        provider = OpenInterestProvider(transport=_fake_transport(response))
        reading = provider.fetch(Symbol("BTC"))
        self.assertFalse(reading.available)

    def test_asset_ctxs_shorter_than_universe_degrades_to_unavailable(self):
        response = [{"universe": [{"name": "BTC"}, {"name": "ETH"}]}, [{"openInterest": "1.0"}]]  # only 1 ctx for 2 assets
        provider = OpenInterestProvider(transport=_fake_transport(response))
        reading = provider.fetch(Symbol("ETH"))
        self.assertFalse(reading.available)

    def test_fetch_never_raises_for_any_failure_mode(self):
        provider = OpenInterestProvider(transport=_raising_transport(TimeoutError("simulated timeout")))
        try:
            reading = provider.fetch(Symbol("BTC"))
        except Exception as exc:  # noqa: BLE001
            self.fail(f"fetch() must never raise for a data-source failure, raised {exc!r}")
        self.assertFalse(reading.available)


class TestFetchInputValidation(unittest.TestCase):
    def test_rejects_non_symbol_argument(self):
        provider = OpenInterestProvider(transport=_fake_transport(_WELL_FORMED_RESPONSE))
        with self.assertRaises(DataSourceError):
            provider.fetch("BTC")


class TestProviderIsStateless(unittest.TestCase):
    def test_every_fetch_calls_transport_fresh_no_caching(self):
        call_log = []
        provider = OpenInterestProvider(transport=_fake_transport(_WELL_FORMED_RESPONSE, call_log=call_log))
        provider.fetch(Symbol("BTC"))
        provider.fetch(Symbol("BTC"))
        provider.fetch(Symbol("ETH"))
        self.assertEqual(len(call_log), 3)

    def test_a_failed_fetch_does_not_affect_the_next_successful_fetch(self):
        calls = {"n": 0}

        def _flaky_transport(url, payload, timeout_seconds):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectionError("transient")
            return _WELL_FORMED_RESPONSE

        provider = OpenInterestProvider(transport=_flaky_transport)
        first = provider.fetch(Symbol("BTC"))
        self.assertFalse(first.available)
        second = provider.fetch(Symbol("BTC"))
        self.assertTrue(second.available)
        self.assertEqual(second.value, Decimal("12345.6789"))


class TestNoExecutionEngineCoupling(unittest.TestCase):
    """A direct, explicit companion to the automated scaffold-level check
    (test_alpha_engine_scaffold.py's TestNoFrozenModuleCoupling) --
    proves the specific architectural claim this milestone's docstrings
    make: OpenInterestProvider works with zero Execution Engine object of
    any kind, using only a plain injected function."""

    def test_provider_never_touches_market_data_view_or_engine(self):
        provider = OpenInterestProvider(transport=_fake_transport(_WELL_FORMED_RESPONSE))
        reading = provider.fetch(Symbol("BTC"))
        self.assertTrue(reading.available)  # constructed and used with no Engine/MarketDataView anywhere


if __name__ == "__main__":
    unittest.main()
