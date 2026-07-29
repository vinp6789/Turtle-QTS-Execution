"""Verification tests for alpha_engine.historical.backfill_liquidations
(the CLI entry point for collect_liquidations() -- Backlog 1.3).

collect_liquidations() itself is already covered by
tests/test_alpha_engine_historical_pipeline.py -- these tests exercise
only this module's own logic: argument parsing and run()'s wiring/retry,
via a monkeypatched collect_liquidations (no real network/AWS calls).
"""

import tempfile
import unittest
from datetime import date
from pathlib import Path

from exchange_adapter import Symbol

import alpha_engine.historical.backfill_liquidations as cli
from alpha_engine.historical.errors import HistoricalDataError
from alpha_engine.historical.pipeline import CollectionResult


def _result(symbol_value, rows_added=1):
    return CollectionResult(
        metric="liquidation", symbol_value=symbol_value, source="hyperliquid_s3", path="x.csv",
        periods_requested=1, periods_fetched=1, periods_skipped=0, periods_unavailable=0,
        rows_added=rows_added, quality_report=None, collected_at_utc="2026-07-29T00:00:00+00:00",
    )


class TestParseDate(unittest.TestCase):
    def test_parses_iso_date(self):
        self.assertEqual(cli._parse_date("2026-06-01"), date(2026, 6, 1))

    def test_rejects_malformed_date(self):
        with self.assertRaises(ValueError):
            cli._parse_date("06/01/2026")


class TestMainArgParsing(unittest.TestCase):
    def setUp(self):
        self._real_collect = cli.collect_liquidations
        self._calls = []

        def fake_collect(symbols, start, end, storage_root):
            self._calls.append((symbols, start, end, storage_root))
            return tuple(_result(s.value) for s in symbols)

        cli.collect_liquidations = fake_collect

    def tearDown(self):
        cli.collect_liquidations = self._real_collect

    def test_defaults_to_watchlist_symbols(self):
        exit_code = cli.main(["--start", "2026-06-01", "--end", "2026-06-30"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(self._calls), 1)
        symbols, start, end, storage_root = self._calls[0]
        self.assertEqual([s.value for s in symbols], ["BTC", "ETH", "SOL"])
        self.assertEqual(start, date(2026, 6, 1))
        self.assertEqual(end, date(2026, 6, 30))
        self.assertEqual(storage_root, "data/alpha_engine_historical")

    def test_custom_symbols_and_storage_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            cli.main([
                "--symbols", "BTC", "ETH",
                "--start", "2026-06-01", "--end", "2026-06-01",
                "--storage-root", tmp,
            ])
            symbols, _, _, storage_root = self._calls[0]
            self.assertEqual([s.value for s in symbols], ["BTC", "ETH"])
            self.assertEqual(storage_root, tmp)

    def test_missing_required_args_exits_nonzero(self):
        with self.assertRaises(SystemExit) as ctx:
            cli.main(["--start", "2026-06-01"])  # --end missing
        self.assertNotEqual(ctx.exception.code, 0)


class TestRunRetry(unittest.TestCase):
    def setUp(self):
        self._real_collect = cli.collect_liquidations
        self._real_sleep = cli.time.sleep
        cli.time.sleep = lambda _seconds: None  # no real delay in tests

    def tearDown(self):
        cli.collect_liquidations = self._real_collect
        cli.time.sleep = self._real_sleep

    def test_retries_on_transient_failure_then_succeeds(self):
        attempts = []

        def flaky(symbols, start, end, storage_root):
            attempts.append(1)
            if len(attempts) < 3:
                raise HistoricalDataError("simulated transient failure")
            return tuple(_result(s.value) for s in symbols)

        cli.collect_liquidations = flaky
        exit_code = cli.run(symbols=(Symbol("BTC"),), start=date(2026, 6, 1), end=date(2026, 6, 1))
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(attempts), 3)

    def test_exhausting_retries_returns_nonzero(self):
        def always_fails(symbols, start, end, storage_root):
            raise HistoricalDataError("permanent failure")

        cli.collect_liquidations = always_fails
        exit_code = cli.run(symbols=(Symbol("BTC"),), start=date(2026, 6, 1), end=date(2026, 6, 1))
        self.assertEqual(exit_code, 1)

    def test_missing_dates_raises(self):
        with self.assertRaises(HistoricalDataError):
            cli.run(symbols=(Symbol("BTC"),), start=None, end=date(2026, 6, 1))


if __name__ == "__main__":
    unittest.main()
