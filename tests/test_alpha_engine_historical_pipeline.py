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
    LiquidationObservation,
    MarkPriceObservation,
    OpenInterestObservation,
)
from alpha_engine.historical.pipeline import (
    collect_funding_rate,
    collect_liquidations,
    collect_mark_price,
    collect_metrics,
    collect_open_interest,
)
from alpha_engine.historical.sources import hyperliquid_s3

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


def _fake_liquidation_obs(symbol_value, hour_key, tid, side="B"):
    """One synthetic fill row, matching models.LiquidationObservation's
    real field shape. A real liquidation is TWO rows sharing one `tid`
    with OPPOSITE sides (see sources/hyperliquid_s3.py's module docstring)
    -- callers simulating a pair must pass side="B" and side="A"."""
    from decimal import Decimal as _D
    return LiquidationObservation(
        symbol=Symbol(symbol_value),
        observed_at_utc="2026-06-01T00:00:00+00:00",
        price=_D("50000"), size=_D("0.1"), side=side, direction="Close Long",
        method="market", liquidated_user="0xabc", mark_price=_D("50001"),
        tid=tid, source=hyperliquid_s3.SOURCE_NAME, source_detail=hour_key,
        ingested_at_utc="2026-06-01T00:00:01+00:00",
    )


class TestCollectLiquidations(unittest.TestCase):
    """No real AWS calls: hyperliquid_s3.list_hour_keys/fetch_hour are
    monkeypatched, mirroring the manual-monkeypatch style already used in
    tests/test_historical_hyperliquid_s3.py and
    tests/test_alpha_engine_historical_storage.py."""

    def setUp(self):
        self._real_list_hour_keys = hyperliquid_s3.list_hour_keys
        self._real_fetch_hour = hyperliquid_s3.fetch_hour
        self._real_client = hyperliquid_s3._client

    def tearDown(self):
        hyperliquid_s3.list_hour_keys = self._real_list_hour_keys
        hyperliquid_s3.fetch_hour = self._real_fetch_hour
        hyperliquid_s3._client = self._real_client

    def _patch_source(self, hours_by_date, obs_by_key):
        def fake_list_hour_keys(*, date, bucket, prefix, region, client=None):
            return hours_by_date.get(date, ())

        def fake_fetch_hour(key, *, bucket, region, symbols=None, client=None):
            wanted = {s.value for s in symbols} if symbols else None
            rows = obs_by_key.get(key, ())
            if wanted is None:
                return rows
            return tuple(o for o in rows if o.symbol.value in wanted)

        hyperliquid_s3.list_hour_keys = fake_list_hour_keys
        hyperliquid_s3.fetch_hour = fake_fetch_hour

    def test_collects_and_writes_one_series_per_symbol(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = "node_fills_by_block/hourly/20260601/0.lz4"
            self._patch_source(
                hours_by_date={"20260601": (key,)},
                obs_by_key={key: (
                    _fake_liquidation_obs("BTC", key, 1, "B"), _fake_liquidation_obs("BTC", key, 1, "A"),
                    _fake_liquidation_obs("ETH", key, 2, "B"), _fake_liquidation_obs("ETH", key, 2, "A"),
                )},
            )
            results = collect_liquidations(
                (Symbol("BTC"), Symbol("ETH")), date(2026, 6, 1), date(2026, 6, 1), tmp, clock=_CLOCK,
            )
            self.assertEqual(len(results), 2)
            btc_result, eth_result = results
            self.assertEqual(btc_result.symbol_value, "BTC")
            self.assertEqual(btc_result.rows_added, 2)
            self.assertEqual(eth_result.symbol_value, "ETH")
            self.assertEqual(eth_result.rows_added, 2)
            self.assertEqual(len(load(Path(tmp) / "liquidation__BTC__hyperliquid_s3.csv", LiquidationObservation)), 2)
            self.assertEqual(len(load(Path(tmp) / "liquidation__ETH__hyperliquid_s3.csv", LiquidationObservation)), 2)

    def test_checkpoint_is_written_and_resume_skips_processed_hours(self):
        with tempfile.TemporaryDirectory() as tmp:
            key0 = "node_fills_by_block/hourly/20260601/0.lz4"
            key1 = "node_fills_by_block/hourly/20260601/1.lz4"
            self._patch_source(
                hours_by_date={"20260601": (key0, key1)},
                obs_by_key={
                    key0: (_fake_liquidation_obs("BTC", key0, 1, "B"), _fake_liquidation_obs("BTC", key0, 1, "A")),
                    key1: (_fake_liquidation_obs("BTC", key1, 2, "B"), _fake_liquidation_obs("BTC", key1, 2, "A")),
                },
            )
            first = collect_liquidations((Symbol("BTC"),), date(2026, 6, 1), date(2026, 6, 1), tmp, clock=_CLOCK)
            self.assertEqual(first[0].periods_fetched, 2)
            self.assertEqual(first[0].periods_skipped, 0)
            self.assertEqual(first[0].rows_added, 4)
            self.assertEqual(hyperliquid_s3.read_checkpoint(Path(tmp) / ".liquidation_checkpoint.json"), key1)

            second = collect_liquidations((Symbol("BTC"),), date(2026, 6, 1), date(2026, 6, 1), tmp, clock=_CLOCK)
            self.assertEqual(second[0].periods_fetched, 0)
            self.assertEqual(second[0].periods_skipped, 2)
            self.assertEqual(second[0].rows_added, 0)  # already merged, idempotent

    def test_force_ignores_checkpoint_without_duplicating_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = "node_fills_by_block/hourly/20260601/0.lz4"
            self._patch_source(
                hours_by_date={"20260601": (key,)},
                obs_by_key={key: (_fake_liquidation_obs("BTC", key, 1, "B"), _fake_liquidation_obs("BTC", key, 1, "A"))},
            )
            collect_liquidations((Symbol("BTC"),), date(2026, 6, 1), date(2026, 6, 1), tmp, clock=_CLOCK)
            forced = collect_liquidations(
                (Symbol("BTC"),), date(2026, 6, 1), date(2026, 6, 1), tmp, force=True, clock=_CLOCK,
            )
            self.assertEqual(forced[0].periods_fetched, 1)  # re-fetched, ignoring checkpoint
            self.assertEqual(forced[0].rows_added, 0)  # storage dedup: no new rows
            self.assertEqual(len(load(Path(tmp) / "liquidation__BTC__hyperliquid_s3.csv", LiquidationObservation)), 2)

    def test_day_with_no_objects_counts_as_unavailable_not_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._patch_source(hours_by_date={}, obs_by_key={})
            result = collect_liquidations(
                (Symbol("BTC"),), date(2026, 6, 1), date(2026, 6, 1), tmp, clock=_CLOCK,
            )[0]
            self.assertEqual(result.periods_requested, 0)
            self.assertEqual(result.periods_fetched, 0)
            self.assertEqual(result.periods_unavailable, 1)
            self.assertEqual(result.rows_added, 0)

    def test_already_processed_days_survive_a_failure_on_a_later_day(self):
        """Locks in the durability fix: rows are flushed to disk per DAY,
        not once at the end of the whole requested range. A failure while
        fetching a LATER day's hour must not lose an EARLIER day's
        already-checkpointed, already-decoded rows -- if it did, the
        checkpoint would sit durably ahead of what was ever persisted to
        the CSV, and resume would skip those hours forever."""
        with tempfile.TemporaryDirectory() as tmp:
            day1_key = "node_fills_by_block/hourly/20260601/0.lz4"
            day2_key = "node_fills_by_block/hourly/20260602/0.lz4"

            def fake_list_hour_keys(*, date, bucket, prefix, region, client=None):
                return {"20260601": (day1_key,), "20260602": (day2_key,)}.get(date, ())

            def fake_fetch_hour(key, *, bucket, region, symbols=None, client=None):
                if key == day2_key:
                    raise HistoricalDataError("simulated network failure fetching day 2")
                return (
                    _fake_liquidation_obs("BTC", key, 1, "B"),
                    _fake_liquidation_obs("BTC", key, 1, "A"),
                )

            hyperliquid_s3.list_hour_keys = fake_list_hour_keys
            hyperliquid_s3.fetch_hour = fake_fetch_hour

            with self.assertRaises(HistoricalDataError):
                collect_liquidations((Symbol("BTC"),), date(2026, 6, 1), date(2026, 6, 2), tmp, clock=_CLOCK)

            # Day 1's rows must already be on disk, and the checkpoint
            # must not have advanced past day 1's key.
            series = load(Path(tmp) / "liquidation__BTC__hyperliquid_s3.csv", LiquidationObservation)
            self.assertEqual(len(series), 2)
            self.assertEqual(
                hyperliquid_s3.read_checkpoint(Path(tmp) / ".liquidation_checkpoint.json"), day1_key,
            )

    def test_mid_day_interruption_does_not_advance_checkpoint_past_unpersisted_rows(self):
        """H1 (independent QA audit finding, High severity): the checkpoint
        must never point past data that is not yet durably on disk. This
        reproduces the exact scenario the earlier implementation got
        wrong -- a failure PARTWAY THROUGH a single day's hours, not
        between two days (test_already_processed_days_survive_a_failure_
        on_a_later_day above covers only the between-days case, which
        already worked; this is the case that didn't).

        Before the fix: the checkpoint advanced per successfully-fetched
        hour while the flush to disk was batched to once per day, so a
        crash after hour 2 of a 5-hour day left the checkpoint at hour 2
        with ZERO rows ever written -- and because keys_after_checkpoint
        treats hour <= checkpoint as done, resume skipped hours 0-2
        forever. After the fix: the checkpoint only advances after that
        day's flush succeeds, so a crash partway through a day leaves the
        checkpoint untouched for that day, and the WHOLE day (including
        the hours that had already decoded successfully) is safely
        retried from scratch on resume -- extra re-download, never lost
        data."""
        with tempfile.TemporaryDirectory() as tmp:
            keys = tuple(f"node_fills_by_block/hourly/20260601/{h}.lz4" for h in range(5))

            def fake_list_hour_keys(*, date, bucket, prefix, region, client=None):
                return keys if date == "20260601" else ()

            def fake_fetch_hour_crash_at_3(key, *, bucket, region, symbols=None, client=None):
                h = int(key.rsplit("/", 1)[1].split(".", 1)[0])
                if h == 3:
                    raise HistoricalDataError("simulated crash mid-day, at hour 3 of 5")
                return (_fake_liquidation_obs("BTC", key, h, "B"), _fake_liquidation_obs("BTC", key, h, "A"))

            hyperliquid_s3.list_hour_keys = fake_list_hour_keys
            hyperliquid_s3.fetch_hour = fake_fetch_hour_crash_at_3

            csv_path = Path(tmp) / "liquidation__BTC__hyperliquid_s3.csv"
            cp_path = Path(tmp) / ".liquidation_checkpoint.json"

            with self.assertRaises(HistoricalDataError):
                collect_liquidations((Symbol("BTC"),), date(2026, 6, 1), date(2026, 6, 1), tmp, clock=_CLOCK)

            # Nothing for this day may exist yet: neither a CSV nor a
            # checkpoint entry. Hours 0-2 were successfully decoded before
            # the crash at hour 3 -- they must NOT be silently discarded
            # by a checkpoint that outran what was actually persisted.
            self.assertFalse(csv_path.exists(), "rows were written before the day's fetch finished")
            self.assertIsNone(
                hyperliquid_s3.read_checkpoint(cp_path),
                "checkpoint advanced into the interrupted day despite nothing being persisted",
            )

            # Resume, with the crash cleared: the ENTIRE day must be
            # retried (including hours 0-2, which decoded fine before the
            # crash) and every hour must end up on disk -- none silently
            # lost.
            def fake_fetch_hour_recovered(key, *, bucket, region, symbols=None, client=None):
                h = int(key.rsplit("/", 1)[1].split(".", 1)[0])
                return (_fake_liquidation_obs("BTC", key, h, "B"), _fake_liquidation_obs("BTC", key, h, "A"))

            hyperliquid_s3.fetch_hour = fake_fetch_hour_recovered
            collect_liquidations((Symbol("BTC"),), date(2026, 6, 1), date(2026, 6, 1), tmp, clock=_CLOCK)

            # _fake_liquidation_obs's tid == the hour number here (see the
            # fetch fakes above), so the set of tids present is exactly the
            # set of hours whose data survived.
            series = load(csv_path, LiquidationObservation)
            hours_present = sorted({o.tid for o in series})
            self.assertEqual(hours_present, [0, 1, 2, 3, 4], "at least one hour was permanently lost")
            self.assertEqual(len(series), 10)  # 5 hours x 2 rows/liquidation
            self.assertEqual(hyperliquid_s3.read_checkpoint(cp_path), keys[-1])

    def test_custom_checkpoint_path_is_honored(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = "node_fills_by_block/hourly/20260601/0.lz4"
            self._patch_source(
                hours_by_date={"20260601": (key,)},
                obs_by_key={key: (_fake_liquidation_obs("BTC", key, 1, "B"), _fake_liquidation_obs("BTC", key, 1, "A"))},
            )
            cp = Path(tmp) / "custom_checkpoint.json"
            collect_liquidations(
                (Symbol("BTC"),), date(2026, 6, 1), date(2026, 6, 1), tmp,
                checkpoint_path=cp, clock=_CLOCK,
            )
            self.assertTrue(cp.is_file())
            self.assertFalse((Path(tmp) / ".liquidation_checkpoint.json").exists())

    def test_wrong_symbols_type_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(HistoricalDataError):
                collect_liquidations(Symbol("BTC"), date(2026, 6, 1), date(2026, 6, 1), tmp)  # not a tuple

    def test_empty_symbols_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(HistoricalDataError):
                collect_liquidations((), date(2026, 6, 1), date(2026, 6, 1), tmp)

    def test_end_before_start_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(HistoricalDataError):
                collect_liquidations((Symbol("BTC"),), date(2026, 6, 2), date(2026, 6, 1), tmp)

    def test_reuses_one_s3_client_across_the_whole_call(self):
        """L3 (independent QA audit finding, Low severity): a fresh boto3
        client per hour fragments connection reuse against a remote
        Requester-Pays region across a multi-day backfill. One client is
        constructed per collect_liquidations() call and threaded through
        every list_hour_keys/fetch_hour call, matching the pattern both
        source functions already expose `client=` for."""
        with tempfile.TemporaryDirectory() as tmp:
            client_calls = []
            real_client = hyperliquid_s3._client

            def spy_client(region):
                client_calls.append(region)
                return real_client(region)

            hyperliquid_s3._client = spy_client

            key1 = "node_fills_by_block/hourly/20260601/0.lz4"
            key2 = "node_fills_by_block/hourly/20260601/1.lz4"
            key3 = "node_fills_by_block/hourly/20260602/0.lz4"

            def fake_list_hour_keys(*, date, bucket, prefix, region, client=None):
                self.assertIsNotNone(client, "list_hour_keys was not given the shared client")
                return {"20260601": (key1, key2), "20260602": (key3,)}.get(date, ())

            def fake_fetch_hour(key, *, bucket, region, symbols=None, client=None):
                self.assertIsNotNone(client, "fetch_hour was not given the shared client")
                h = int(key.rsplit("/", 1)[1].split(".", 1)[0])
                return (_fake_liquidation_obs("BTC", key, h, "B"), _fake_liquidation_obs("BTC", key, h, "A"))

            hyperliquid_s3.list_hour_keys = fake_list_hour_keys
            hyperliquid_s3.fetch_hour = fake_fetch_hour

            collect_liquidations((Symbol("BTC"),), date(2026, 6, 1), date(2026, 6, 2), tmp, clock=_CLOCK)

            self.assertEqual(len(client_calls), 1, f"expected exactly one client construction, got {client_calls}")


if __name__ == "__main__":
    unittest.main()
