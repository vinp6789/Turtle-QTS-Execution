"""Verification tests for alpha_engine.historical.sources.binance.

No real network calls: every test injects a fake transport(url,
timeout_seconds) -> bytes, exactly mirroring
alpha_engine.data_sources.open_interest's own TransportFn-injection test
pattern, so these tests are fast, deterministic, and offline."""

import hashlib
import io
import unittest
import urllib.error
import zipfile
from datetime import date
from decimal import Decimal

from exchange_adapter import Symbol

from alpha_engine.historical import HistoricalDataError
from alpha_engine.historical.sources import binance

_CLOCK = lambda: "2024-06-01T00:00:00+00:00"


def _zip_bytes(filename: str, csv_text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(filename, csv_text)
    return buf.getvalue()


def _checksum_bytes(zip_bytes: bytes, filename: str) -> bytes:
    digest = hashlib.sha256(zip_bytes).hexdigest()
    return f"{digest}  {filename}\n".encode("utf-8")


class _FakeTransport:
    """Maps exact URLs to canned (bytes | HTTPError) responses."""

    def __init__(self):
        self._responses = {}

    def set(self, url, response):
        self._responses[url] = response

    def __call__(self, url, timeout_seconds):
        if url not in self._responses:
            raise AssertionError(f"unexpected URL requested: {url}")
        response = self._responses[url]
        if isinstance(response, Exception):
            raise response
        return response


class TestTimeoutTranslation(unittest.TestCase):
    """A stalled read on an already-open connection surfaces from
    urlopen as a bare TimeoutError, not urllib.error.URLError -- unlike
    a connection-establishment failure, it is NOT wrapped. Every
    fetch_* function must translate it into HistoricalDataError (like
    any other non-404 transport failure) so callers' HistoricalDataError-
    only retry loops (research/campaign_01_open_interest/collect_backfill.py,
    research/campaign_02_funding_rate/collect_backfill.py,
    research/deep_history_backfill/collect_backfill.py) actually catch
    and retry it, instead of the process crashing uncaught."""

    def test_zip_fetch_timeout_raises_historical_data_error_not_timeout_error(self):
        transport = _FakeTransport()
        base = "https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2021-01.zip"
        transport.set(base, TimeoutError("The read operation timed out"))

        with self.assertRaises(HistoricalDataError):
            binance.fetch_funding_rate_month(Symbol("BTC"), 2021, 1, transport=transport, clock=_CLOCK)

    def test_checksum_fetch_timeout_raises_historical_data_error_not_timeout_error(self):
        zip_bytes = _zip_bytes("x.csv", "calc_time,symbol,last_funding_rate,funding_interval_hours\n")
        transport = _FakeTransport()
        base = "https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2021-01.zip"
        transport.set(base, zip_bytes)
        transport.set(base + ".CHECKSUM", TimeoutError("The read operation timed out"))

        with self.assertRaises(HistoricalDataError):
            binance.fetch_funding_rate_month(Symbol("BTC"), 2021, 1, transport=transport, clock=_CLOCK)


class TestFetchOpenInterestDay(unittest.TestCase):
    def test_available_day_parses_rows(self):
        zip_name = "BTCUSDT-metrics-2024-01-15.zip"
        csv_text = (
            "create_time,symbol,sum_open_interest\n"
            "2024-01-15 00:00:00,BTCUSDT,77082.01800000\n"
            "2024-01-15 00:05:00,BTCUSDT,77234.08400000\n"
        )
        zip_bytes = _zip_bytes("BTCUSDT-metrics-2024-01-15.csv", csv_text)
        checksum = _checksum_bytes(zip_bytes, zip_name)

        transport = _FakeTransport()
        base = "https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2024-01-15.zip"
        transport.set(base, zip_bytes)
        transport.set(base + ".CHECKSUM", checksum)

        result = binance.fetch_open_interest_day(
            Symbol("BTC"), date(2024, 1, 15), transport=transport, clock=_CLOCK,
        )
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].value, Decimal("77082.01800000"))
        # canonical_utc() (B5) renders fixed microsecond precision.
        self.assertEqual(result[0].observed_at_utc, "2024-01-15T00:00:00.000000+00:00")
        self.assertEqual(result[0].source, "binance")
        self.assertEqual(result[0].source_detail, zip_name)
        self.assertEqual(result[0].ingested_at_utc, "2024-06-01T00:00:00+00:00")

    def test_unavailable_day_returns_none(self):
        transport = _FakeTransport()
        base = "https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2019-01-01.zip"
        transport.set(base, urllib.error.HTTPError(base, 404, "Not Found", None, None))

        result = binance.fetch_open_interest_day(
            Symbol("BTC"), date(2019, 1, 1), transport=transport, clock=_CLOCK,
        )
        self.assertIsNone(result)

    def test_checksum_mismatch_raises(self):
        zip_bytes = _zip_bytes("x.csv", "create_time,symbol,sum_open_interest\n2024-01-15 00:00:00,BTCUSDT,1\n")
        bad_checksum = ("0" * 64 + "  x\n").encode("utf-8")

        transport = _FakeTransport()
        base = "https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2024-01-15.zip"
        transport.set(base, zip_bytes)
        transport.set(base + ".CHECKSUM", bad_checksum)

        with self.assertRaises(HistoricalDataError):
            binance.fetch_open_interest_day(Symbol("BTC"), date(2024, 1, 15), transport=transport, clock=_CLOCK)

    def test_non_404_transport_error_raises(self):
        transport = _FakeTransport()
        base = "https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2024-01-15.zip"
        transport.set(base, urllib.error.HTTPError(base, 500, "Server Error", None, None))

        with self.assertRaises(HistoricalDataError):
            binance.fetch_open_interest_day(Symbol("BTC"), date(2024, 1, 15), transport=transport, clock=_CLOCK)

    def test_malformed_row_raises(self):
        zip_name = "BTCUSDT-metrics-2024-01-15.zip"
        csv_text = "create_time,symbol,sum_open_interest\n2024-01-15 00:00:00,BTCUSDT,NOT_A_NUMBER\n"
        zip_bytes = _zip_bytes("x.csv", csv_text)
        checksum = _checksum_bytes(zip_bytes, zip_name)

        transport = _FakeTransport()
        base = "https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2024-01-15.zip"
        transport.set(base, zip_bytes)
        transport.set(base + ".CHECKSUM", checksum)

        with self.assertRaises(HistoricalDataError):
            binance.fetch_open_interest_day(Symbol("BTC"), date(2024, 1, 15), transport=transport, clock=_CLOCK)

    def test_wrong_day_type_raises(self):
        with self.assertRaises(HistoricalDataError):
            binance.fetch_open_interest_day(Symbol("BTC"), "2024-01-15")


class TestFetchMarkPriceDay(unittest.TestCase):
    def test_derives_price_from_value_over_oi(self):
        zip_name = "BTCUSDT-metrics-2024-01-15.zip"
        # value / oi = 3217372598.5128 / 77082.018 = 41739.6...
        csv_text = (
            "create_time,symbol,sum_open_interest,sum_open_interest_value\n"
            "2024-01-15 00:00:00,BTCUSDT,77082.01800000,3217372598.51280000\n"
        )
        zip_bytes = _zip_bytes("x.csv", csv_text)
        checksum = _checksum_bytes(zip_bytes, zip_name)
        transport = _FakeTransport()
        base = "https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2024-01-15.zip"
        transport.set(base, zip_bytes)
        transport.set(base + ".CHECKSUM", checksum)

        result = binance.fetch_mark_price_day(Symbol("BTC"), date(2024, 1, 15), transport=transport, clock=_CLOCK)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(float(result[0].value), 41739.6, places=0)
        self.assertGreater(result[0].value, 0)

    def test_zero_oi_row_skipped_not_fabricated(self):
        zip_name = "BTCUSDT-metrics-2024-01-15.zip"
        csv_text = (
            "create_time,symbol,sum_open_interest,sum_open_interest_value\n"
            "2024-01-15 00:00:00,BTCUSDT,0,0\n"
            "2024-01-15 00:05:00,BTCUSDT,100,4200000\n"
        )
        zip_bytes = _zip_bytes("x.csv", csv_text)
        checksum = _checksum_bytes(zip_bytes, zip_name)
        transport = _FakeTransport()
        base = "https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2024-01-15.zip"
        transport.set(base, zip_bytes)
        transport.set(base + ".CHECKSUM", checksum)

        result = binance.fetch_mark_price_day(Symbol("BTC"), date(2024, 1, 15), transport=transport, clock=_CLOCK)
        self.assertEqual(len(result), 1)  # zero-OI row skipped
        self.assertEqual(result[0].value, Decimal("42000"))

    def test_unavailable_day_returns_none(self):
        transport = _FakeTransport()
        base = "https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2019-01-01.zip"
        transport.set(base, urllib.error.HTTPError(base, 404, "Not Found", None, None))
        self.assertIsNone(binance.fetch_mark_price_day(Symbol("BTC"), date(2019, 1, 1), transport=transport, clock=_CLOCK))


class TestFetchFundingRateMonth(unittest.TestCase):
    def test_available_month_parses_rows(self):
        zip_name = "BTCUSDT-fundingRate-2024-01.zip"
        csv_text = (
            "calc_time,funding_interval_hours,last_funding_rate\n"
            "1704067200000,8,0.00037409\n"
            "1704096000000,8,0.00027213\n"
        )
        zip_bytes = _zip_bytes("x.csv", csv_text)
        checksum = _checksum_bytes(zip_bytes, zip_name)

        transport = _FakeTransport()
        base = "https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2024-01.zip"
        transport.set(base, zip_bytes)
        transport.set(base + ".CHECKSUM", checksum)

        result = binance.fetch_funding_rate_month(Symbol("BTC"), 2024, 1, transport=transport, clock=_CLOCK)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].value, Decimal("0.00037409"))
        self.assertEqual(result[0].source, "binance")

    def test_unavailable_month_returns_none(self):
        transport = _FakeTransport()
        base = "https://data.binance.vision/data/futures/um/monthly/fundingRate/SOLUSDT/SOLUSDT-fundingRate-2020-01.zip"
        transport.set(base, urllib.error.HTTPError(base, 404, "Not Found", None, None))

        result = binance.fetch_funding_rate_month(Symbol("SOL"), 2020, 1, transport=transport, clock=_CLOCK)
        self.assertIsNone(result)

    def test_invalid_month_raises(self):
        with self.assertRaises(HistoricalDataError):
            binance.fetch_funding_rate_month(Symbol("BTC"), 2024, 13)

    def test_invalid_year_type_raises(self):
        with self.assertRaises(HistoricalDataError):
            binance.fetch_funding_rate_month(Symbol("BTC"), "2024", 1)


if __name__ == "__main__":
    unittest.main()
