"""Verification tests for alpha_engine.historical.sources.hyperliquid.

No real network calls: every test injects a fake transport(url, payload,
timeout_seconds) -> Any, mirroring alpha_engine.data_sources.
open_interest's own TransportFn-injection test pattern."""

import unittest
import urllib.error
from decimal import Decimal

from exchange_adapter import Symbol

from alpha_engine.historical import HistoricalDataError
from alpha_engine.historical.sources import hyperliquid

_CLOCK = lambda: "2024-06-01T00:00:00+00:00"


class _FakeTransport:
    """Records every call and returns responses from a queue keyed by
    call order (fundingHistory pagination calls the same URL repeatedly
    with different payloads)."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, url, payload, timeout_seconds):
        self.calls.append((url, payload, timeout_seconds))
        if not self._responses:
            raise AssertionError("no more fake responses queued")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _row(time_ms, rate):
    return {"coin": "BTC", "fundingRate": rate, "premium": "0.0001", "time": time_ms}


class TestFetchFundingRateRange(unittest.TestCase):
    def test_single_page_parses_rows(self):
        transport = _FakeTransport([[_row(1704067200000, "0.0001"), _row(1704070800000, "0.0002")]])
        result = hyperliquid.fetch_funding_rate_range(
            Symbol("BTC"), 1704067200000, 1704074400000, transport=transport, clock=_CLOCK,
        )
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].value, Decimal("0.0001"))
        self.assertEqual(result[0].source, "hyperliquid")
        self.assertEqual(len(transport.calls), 1)

    def test_paginates_past_500_cap(self):
        page1 = [_row(1704067200000 + i * 3600000, "0.0001") for i in range(500)]
        page2 = [_row(page1[-1]["time"] + 3600000, "0.0002")]
        transport = _FakeTransport([page1, page2])

        result = hyperliquid.fetch_funding_rate_range(
            Symbol("BTC"), 1704067200000, page1[-1]["time"] + 7200000,
            transport=transport, clock=_CLOCK,
        )
        self.assertEqual(len(result), 501)
        self.assertEqual(len(transport.calls), 2)
        # Second call's startTime resumes exactly one ms after the last record of page 1.
        self.assertEqual(transport.calls[1][1]["startTime"], page1[-1]["time"] + 1)

    def test_empty_response_returns_empty_tuple(self):
        transport = _FakeTransport([[]])
        result = hyperliquid.fetch_funding_rate_range(
            Symbol("BTC"), 1577836800000, 1577840400000, transport=transport, clock=_CLOCK,
        )
        self.assertEqual(result, ())

    def test_non_list_response_raises(self):
        transport = _FakeTransport([{"unexpected": "shape"}])
        with self.assertRaises(HistoricalDataError):
            hyperliquid.fetch_funding_rate_range(
                Symbol("BTC"), 1704067200000, 1704074400000, transport=transport, clock=_CLOCK,
            )

    def test_malformed_row_raises(self):
        transport = _FakeTransport([[{"coin": "BTC", "time": 1704067200000}]])  # missing fundingRate
        with self.assertRaises(HistoricalDataError):
            hyperliquid.fetch_funding_rate_range(
                Symbol("BTC"), 1704067200000, 1704074400000, transport=transport, clock=_CLOCK,
            )

    def test_http_error_raises(self):
        transport = _FakeTransport([urllib.error.HTTPError("url", 500, "Server Error", None, None)])
        with self.assertRaises(HistoricalDataError):
            hyperliquid.fetch_funding_rate_range(
                Symbol("BTC"), 1704067200000, 1704074400000, transport=transport, clock=_CLOCK,
            )

    def test_invalid_range_raises(self):
        with self.assertRaises(HistoricalDataError):
            hyperliquid.fetch_funding_rate_range(Symbol("BTC"), 100, 50)  # end < start

    def test_wrong_symbol_type_raises(self):
        with self.assertRaises(HistoricalDataError):
            hyperliquid.fetch_funding_rate_range("BTC", 0, 100)


if __name__ == "__main__":
    unittest.main()
