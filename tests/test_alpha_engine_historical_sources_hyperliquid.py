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


def _candle_row(t_ms, close, coin="BTC"):
    return {"t": t_ms, "T": t_ms + 86399999, "s": coin, "i": "1d",
            "o": close, "c": close, "h": close, "l": close, "v": "123.45", "n": 100}


class TestFetchDailyCandles(unittest.TestCase):
    """Backlog 1.4. No real network calls -- same fake-transport pattern
    as TestFetchFundingRateRange above."""

    def test_parses_rows_using_close_price(self):
        transport = _FakeTransport([[
            _candle_row(1704067200000, "42000.5"), _candle_row(1704153600000, "43100.0"),
        ]])
        result = hyperliquid.fetch_daily_candles(
            Symbol("BTC"), 1704067200000, 1704240000000, transport=transport, clock=_CLOCK,
        )
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].value, Decimal("42000.5"))
        self.assertEqual(result[0].source, "hyperliquid")
        self.assertEqual(len(transport.calls), 1)

    def test_request_shape_matches_live_verified_endpoint(self):
        transport = _FakeTransport([[]])
        hyperliquid.fetch_daily_candles(
            Symbol("ETH"), 1704067200000, 1704153600000, transport=transport, clock=_CLOCK,
        )
        url, payload, _ = transport.calls[0]
        self.assertEqual(url, hyperliquid._INFO_URL)
        self.assertEqual(payload, {
            "type": "candleSnapshot",
            "req": {"coin": "ETH", "interval": "1d", "startTime": 1704067200000, "endTime": 1704153600000},
        })

    def test_no_pagination_loop_single_call_regardless_of_row_count(self):
        # Live-verified (module docstring): candleSnapshot has no per-call
        # cap, unlike fundingHistory's 500-record page size -- this locks
        # in that fetch_daily_candles never loops/paginates.
        many_rows = [_candle_row(1704067200000 + i * 86400000, "42000.0") for i in range(400)]
        transport = _FakeTransport([many_rows])
        result = hyperliquid.fetch_daily_candles(
            Symbol("BTC"), 1704067200000, 1704067200000 + 400 * 86400000, transport=transport, clock=_CLOCK,
        )
        self.assertEqual(len(result), 400)
        self.assertEqual(len(transport.calls), 1)

    def test_empty_response_returns_empty_tuple(self):
        transport = _FakeTransport([[]])
        result = hyperliquid.fetch_daily_candles(
            Symbol("BTC"), 1577836800000, 1577840400000, transport=transport, clock=_CLOCK,
        )
        self.assertEqual(result, ())

    def test_non_list_response_raises(self):
        transport = _FakeTransport([{"unexpected": "shape"}])
        with self.assertRaises(HistoricalDataError):
            hyperliquid.fetch_daily_candles(
                Symbol("BTC"), 1704067200000, 1704074400000, transport=transport, clock=_CLOCK,
            )

    def test_malformed_row_raises(self):
        transport = _FakeTransport([[{"t": 1704067200000}]])  # missing "c"
        with self.assertRaises(HistoricalDataError):
            hyperliquid.fetch_daily_candles(
                Symbol("BTC"), 1704067200000, 1704074400000, transport=transport, clock=_CLOCK,
            )

    def test_http_error_raises(self):
        transport = _FakeTransport([urllib.error.HTTPError("url", 500, "Server Error", None, None)])
        with self.assertRaises(HistoricalDataError):
            hyperliquid.fetch_daily_candles(
                Symbol("BTC"), 1704067200000, 1704074400000, transport=transport, clock=_CLOCK,
            )

    def test_invalid_range_raises(self):
        with self.assertRaises(HistoricalDataError):
            hyperliquid.fetch_daily_candles(Symbol("BTC"), 100, 50)  # end < start

    def test_wrong_symbol_type_raises(self):
        with self.assertRaises(HistoricalDataError):
            hyperliquid.fetch_daily_candles("BTC", 0, 100)


if __name__ == "__main__":
    unittest.main()
