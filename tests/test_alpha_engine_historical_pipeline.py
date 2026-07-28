"""Verification tests for alpha_engine.historical.pipeline (the
incremental collect_open_interest/collect_funding_rate orchestrators).

No real network calls: fake transports simulate the two sources.
"""

import tempfile
import unittest
import urllib.error
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from exchange_adapter import Symbol

from alpha_engine.historical import HistoricalDataError, load
from alpha_engine.historical.models import (
    FundingRateObservation,
    MarkPriceObservation,
    OpenInterestObservation,
)
from alpha_engine.historical.pipeline import (
    collect_funding_rate,
    collect_mark_price,
    collect_metrics,
    collect_open_interest,
)

_CLOCK = lambda: "2024-06-01T00:00:00+00:00"


def _oi_transport(available_dates):
    """Fake binance.TransportFn: returns a one-row zip for dates in
    `available_dates`, a 404 HTTPError otherwise."""
    import hashlib
    import io
    import zipfile

    def _zip_for(day_str):
        csv_text = f"create_time,symbol,sum_open_interest\n{day_str} 00:00:00,BTCUSDT,50000\n"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("x.csv", csv_text)
        return buf.getvalue()

    def transport(url, timeout_seconds):
        if url.endswith(".CHECKSUM"):
            zip_url = url[: -len(".CHECKSUM")]
            day_str = zip_url.rsplit("-metrics-", 1)[1].rsplit(".zip", 1)[0]
            if day_str not in available_dates:
                raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
            digest = hashlib.sha256(_zip_for(day_str)).hexdigest()
            return f"{digest}  x\n".encode("utf-8")
        day_str = url.rsplit("-metrics-", 1)[1].rsplit(".zip", 1)[0]
        if day_str not in available_dates:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return _zip_for(day_str)

    return transport


class TestCollectOpenInterest(unittest.TestCase):
    def test_unsupported_source_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(HistoricalDataError):
                collect_open_interest(
                    Symbol("BTC"), date(2024, 1, 1), date(2024, 1, 2), tmp, source="hyperliquid",
                )

    def test_collects_available_days_and_skips_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = _oi_transport({"2024-01-02"})
            result = collect_open_interest(
                Symbol("BTC"), date(2024, 1, 1), date(2024, 1, 3), tmp,
                transport=transport, clock=_CLOCK,
            )
            self.assertEqual(result.periods_requested, 3)
            self.assertEqual(result.periods_fetched, 3)
            self.assertEqual(result.periods_skipped, 0)
            self.assertEqual(result.periods_unavailable, 2)
            self.assertEqual(result.rows_added, 1)
            self.assertIsNotNone(result.quality_report)

    def test_incremental_rerun_skips_already_collected_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = _oi_transport({"2024-01-01", "2024-01-02"})
            collect_open_interest(
                Symbol("BTC"), date(2024, 1, 1), date(2024, 1, 2), tmp,
                transport=transport, clock=_CLOCK,
            )
            # Second call over an overlapping+extended range: the first
            # two days must be skipped (no network call), only the third
            # newly requested day is fetched.
            transport2 = _oi_transport({"2024-01-01", "2024-01-02", "2024-01-03"})
            result = collect_open_interest(
                Symbol("BTC"), date(2024, 1, 1), date(2024, 1, 3), tmp,
                transport=transport2, clock=_CLOCK,
            )
            self.assertEqual(result.periods_requested, 3)
            self.assertEqual(result.periods_skipped, 2)
            self.assertEqual(result.periods_fetched, 1)

    def test_force_refetches_already_collected_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = _oi_transport({"2024-01-01"})
            collect_open_interest(
                Symbol("BTC"), date(2024, 1, 1), date(2024, 1, 1), tmp,
                transport=transport, clock=_CLOCK,
            )
            result = collect_open_interest(
                Symbol("BTC"), date(2024, 1, 1), date(2024, 1, 1), tmp,
                source="binance", force=True, transport=transport, clock=_CLOCK,
            )
            self.assertEqual(result.periods_fetched, 1)
            self.assertEqual(result.periods_skipped, 0)

    def test_no_data_available_produces_none_quality_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = _oi_transport(set())
            result = collect_open_interest(
                Symbol("BTC"), date(2024, 1, 1), date(2024, 1, 1), tmp,
                transport=transport, clock=_CLOCK,
            )
            self.assertIsNone(result.quality_report)
            self.assertEqual(result.rows_added, 0)

    def test_invalid_date_range_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(HistoricalDataError):
                collect_open_interest(Symbol("BTC"), date(2024, 1, 2), date(2024, 1, 1), tmp)

    def test_stored_series_readable_via_public_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = _oi_transport({"2024-01-01"})
            result = collect_open_interest(
                Symbol("BTC"), date(2024, 1, 1), date(2024, 1, 1), tmp,
                transport=transport, clock=_CLOCK,
            )
            observations = load(Path(result.path), OpenInterestObservation)
            self.assertEqual(len(observations), 1)
            self.assertEqual(observations[0].value, Decimal("50000"))


def _metrics_transport(available_dates):
    """Fake binance.TransportFn returning a metrics zip WITH the value
    column, for mark-price collection."""
    import hashlib
    import io
    import zipfile

    def _zip_for(day_str):
        csv_text = (
            "create_time,symbol,sum_open_interest,sum_open_interest_value\n"
            f"{day_str} 00:00:00,BTCUSDT,100,4200000\n"
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("x.csv", csv_text)
        return buf.getvalue()

    def transport(url, timeout_seconds):
        day_str = url.rsplit("-metrics-", 1)[1].rsplit(".zip", 1)[0].replace(".CHECKSUM", "")
        if day_str not in available_dates:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        if url.endswith(".CHECKSUM"):
            digest = hashlib.sha256(_zip_for(day_str)).hexdigest()
            return f"{digest}  x\n".encode("utf-8")
        return _zip_for(day_str)

    return transport


class TestCollectMarkPrice(unittest.TestCase):
    def test_collects_and_derives_price(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = _metrics_transport({"2024-01-01"})
            result = collect_mark_price(
                Symbol("BTC"), date(2024, 1, 1), date(2024, 1, 1), tmp,
                transport=transport, clock=_CLOCK,
            )
            self.assertEqual(result.rows_added, 1)
            obs = load(Path(result.path), MarkPriceObservation)
            self.assertEqual(obs[0].value, Decimal("42000"))  # 4200000 / 100

    def test_unsupported_source_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(HistoricalDataError):
                collect_mark_price(Symbol("BTC"), date(2024, 1, 1), date(2024, 1, 1), tmp, source="hyperliquid")

    def test_incremental_rerun_skips_covered_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = _metrics_transport({"2024-01-01", "2024-01-02"})
            collect_mark_price(Symbol("BTC"), date(2024, 1, 1), date(2024, 1, 1), tmp, transport=transport, clock=_CLOCK)
            result = collect_mark_price(
                Symbol("BTC"), date(2024, 1, 1), date(2024, 1, 2), tmp, transport=transport, clock=_CLOCK,
            )
            self.assertEqual(result.periods_skipped, 1)
            self.assertEqual(result.periods_fetched, 1)


class TestCollectMetrics(unittest.TestCase):
    def test_single_pass_writes_both_series(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = _metrics_transport({"2024-01-01"})
            oi_result, mark_result = collect_metrics(
                Symbol("BTC"), date(2024, 1, 1), date(2024, 1, 1), tmp, transport=transport, clock=_CLOCK,
            )
            self.assertEqual(oi_result.rows_added, 1)
            self.assertEqual(mark_result.rows_added, 1)
            oi = load(Path(oi_result.path), OpenInterestObservation)
            mark = load(Path(mark_result.path), MarkPriceObservation)
            self.assertEqual(oi[0].value, Decimal("100"))
            self.assertEqual(mark[0].value, Decimal("42000"))  # 4200000 / 100

    def test_incremental_rerun_skips_covered_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = _metrics_transport({"2024-01-01", "2024-01-02"})
            collect_metrics(Symbol("BTC"), date(2024, 1, 1), date(2024, 1, 1), tmp, transport=transport, clock=_CLOCK)
            oi_result, _ = collect_metrics(
                Symbol("BTC"), date(2024, 1, 1), date(2024, 1, 2), tmp, transport=transport, clock=_CLOCK,
            )
            self.assertEqual(oi_result.periods_skipped, 1)
            self.assertEqual(oi_result.periods_fetched, 1)


def _funding_transport_binance(available_months):
    import hashlib
    import io
    import zipfile

    def _zip_for(month_str):
        csv_text = "calc_time,funding_interval_hours,last_funding_rate\n1704067200000,8,0.0001\n"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("x.csv", csv_text)
        return buf.getvalue()

    def transport(url, timeout_seconds):
        if url.endswith(".CHECKSUM"):
            zip_url = url[: -len(".CHECKSUM")]
            month_str = zip_url.rsplit("-fundingRate-", 1)[1].rsplit(".zip", 1)[0]
            if month_str not in available_months:
                raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
            digest = hashlib.sha256(_zip_for(month_str)).hexdigest()
            return f"{digest}  x\n".encode("utf-8")
        month_str = url.rsplit("-fundingRate-", 1)[1].rsplit(".zip", 1)[0]
        if month_str not in available_months:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return _zip_for(month_str)

    return transport


class TestCollectFundingRateBinance(unittest.TestCase):
    def test_collects_available_months(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = _funding_transport_binance({"2024-01"})
            result = collect_funding_rate(
                Symbol("BTC"), date(2024, 1, 1), date(2024, 1, 31), tmp,
                source="binance", transport=transport, clock=_CLOCK,
            )
            self.assertEqual(result.periods_requested, 1)
            self.assertEqual(result.rows_added, 1)

    def test_incremental_rerun_skips_covered_months(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = _funding_transport_binance({"2024-01", "2024-02"})
            collect_funding_rate(
                Symbol("BTC"), date(2024, 1, 1), date(2024, 1, 31), tmp,
                source="binance", transport=transport, clock=_CLOCK,
            )
            result = collect_funding_rate(
                Symbol("BTC"), date(2024, 1, 1), date(2024, 2, 28), tmp,
                source="binance", transport=transport, clock=_CLOCK,
            )
            self.assertEqual(result.periods_requested, 2)
            self.assertEqual(result.periods_skipped, 1)
            self.assertEqual(result.periods_fetched, 1)


class TestCollectFundingRateHyperliquid(unittest.TestCase):
    def test_collects_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []

            def transport(url, payload, timeout_seconds):
                calls.append(payload)
                return [{"coin": "BTC", "fundingRate": "0.0001", "time": payload["startTime"]}]

            result = collect_funding_rate(
                Symbol("BTC"), date(2024, 1, 1), date(2024, 1, 1), tmp,
                source="hyperliquid", transport=transport, clock=_CLOCK,
            )
            self.assertEqual(result.rows_added, 1)
            self.assertEqual(len(calls), 1)

    def test_incremental_rerun_resumes_from_high_water_mark(self):
        with tempfile.TemporaryDirectory() as tmp:
            first_time_ms = 1704067200000  # 2024-01-01T00:00:00Z

            def transport1(url, payload, timeout_seconds):
                return [{"coin": "BTC", "fundingRate": "0.0001", "time": first_time_ms}]

            collect_funding_rate(
                Symbol("BTC"), date(2024, 1, 1), date(2024, 1, 2), tmp,
                source="hyperliquid", transport=transport1, clock=_CLOCK,
            )

            seen_start_times = []

            def transport2(url, payload, timeout_seconds):
                seen_start_times.append(payload["startTime"])
                return []

            collect_funding_rate(
                Symbol("BTC"), date(2024, 1, 1), date(2024, 1, 2), tmp,
                source="hyperliquid", transport=transport2, clock=_CLOCK,
            )
            self.assertEqual(seen_start_times, [first_time_ms + 1])

    def test_force_refetches_full_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            first_time_ms = 1704067200000

            def transport1(url, payload, timeout_seconds):
                return [{"coin": "BTC", "fundingRate": "0.0001", "time": first_time_ms}]

            collect_funding_rate(
                Symbol("BTC"), date(2024, 1, 1), date(2024, 1, 2), tmp,
                source="hyperliquid", transport=transport1, clock=_CLOCK,
            )

            seen_start_times = []

            def transport2(url, payload, timeout_seconds):
                seen_start_times.append(payload["startTime"])
                return [{"coin": "BTC", "fundingRate": "0.0001", "time": first_time_ms}]

            collect_funding_rate(
                Symbol("BTC"), date(2024, 1, 1), date(2024, 1, 2), tmp,
                source="hyperliquid", force=True, transport=transport2, clock=_CLOCK,
            )
            expected_start_ms = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
            self.assertEqual(seen_start_times, [expected_start_ms])


if __name__ == "__main__":
    unittest.main()
