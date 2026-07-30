"""Verification tests for research.deep_history_backfill.collect_backfill
(Backlog 2.1's resumable per-symbol deep-history driver).

No real network calls: collect_funding_rate/collect_metrics are
monkeypatched at the module level the driver imported them into. The
module-level start/end constants are patched to a small range so tests
run in milliseconds rather than iterating the real ~80-month window.
"""

import unittest
from datetime import date
from unittest.mock import patch

from exchange_adapter import Symbol

from alpha_engine.historical.errors import HistoricalDataError
from alpha_engine.historical.pipeline import CollectionResult
from research.deep_history_backfill import collect_backfill as driver


def _fake_funding_result(symbol, rows_added=1):
    return CollectionResult(
        metric="funding_rate", symbol_value=symbol.value, source="binance", path="x",
        periods_requested=1, periods_fetched=1, periods_skipped=0, periods_unavailable=0,
        rows_added=rows_added, quality_report=None, collected_at_utc="2026-07-30T00:00:00+00:00",
    )


def _fake_metrics_result(symbol, rows_added=1):
    oi = CollectionResult(
        metric="open_interest", symbol_value=symbol.value, source="binance", path="x",
        periods_requested=7, periods_fetched=7, periods_skipped=0, periods_unavailable=0,
        rows_added=rows_added, quality_report=None, collected_at_utc="2026-07-30T00:00:00+00:00",
    )
    mark = CollectionResult(
        metric="mark_price", symbol_value=symbol.value, source="binance", path="x",
        periods_requested=7, periods_fetched=7, periods_skipped=0, periods_unavailable=0,
        rows_added=rows_added, quality_report=None, collected_at_utc="2026-07-30T00:00:00+00:00",
    )
    return oi, mark


class TestMonthMath(unittest.TestCase):
    def test_month_bounds_handles_december(self):
        s, e = driver._month_bounds(2020, 12)
        self.assertEqual((s, e), (date(2020, 12, 1), date(2020, 12, 31)))

    def test_month_bounds_handles_february(self):
        s, e = driver._month_bounds(2020, 2)
        self.assertEqual((s, e), (date(2020, 2, 1), date(2020, 2, 29)))  # 2020 is a leap year

    def test_months_is_inclusive_of_both_endpoints(self):
        months = list(driver._months(2020, 11, 2021, 2))
        self.assertEqual(months, [(2020, 11), (2020, 12), (2021, 1), (2021, 2)])


class TestFundingDispatch(unittest.TestCase):
    """Per-symbol deep-history start dates are asymmetric by design
    (docs/ROADMAP.md Section 1.2) -- verify each symbol starts from its
    own declared month, not a shared one."""

    @patch.object(driver, "_END_MONTH", 3)
    @patch.object(driver, "_END_YEAR", 2020)
    @patch.object(driver, "_FUNDING_DEEP_START", {"BTC": (2020, 1), "SOL": (2020, 9)})
    @patch.object(driver, "collect_funding_rate")
    def test_each_symbol_starts_from_its_own_declared_month(self, mock_collect):
        mock_collect.side_effect = lambda symbol, s, e, root, source: _fake_funding_result(symbol)
        driver.run(target="funding")

        btc_calls = [c for c in mock_collect.call_args_list if c.args[0].value == "BTC"]
        sol_calls = [c for c in mock_collect.call_args_list if c.args[0].value == "SOL"]

        # BTC: 2020-01, 02, 03 (3 months). SOL: only 2020-09 is in range,
        # but the shared _END is 2020-03 so SOL's start (09) is already
        # past the end -- zero calls, not an error.
        self.assertEqual([c.args[1] for c in btc_calls], [date(2020, 1, 1), date(2020, 2, 1), date(2020, 3, 1)])
        self.assertEqual(sol_calls, [])

    @patch.object(driver, "_FUNDING_DEEP_START", {"BTC": (2020, 1)})
    @patch.object(driver, "_END_YEAR", 2020)
    @patch.object(driver, "_END_MONTH", 1)
    @patch.object(driver, "collect_funding_rate")
    def test_funding_uses_binance_source_explicitly(self, mock_collect):
        mock_collect.side_effect = lambda symbol, s, e, root, source: _fake_funding_result(symbol)
        driver.run(target="funding")
        self.assertEqual(mock_collect.call_args.kwargs, {"source": "binance"})


class TestMetricsDispatch(unittest.TestCase):
    @patch.object(driver, "_METRICS_DEEP_START", {"BTC": (2021, 1), "ETH": (2022, 1)})
    @patch.object(driver, "_END_YEAR", 2021)
    @patch.object(driver, "_END_MONTH", 1)
    @patch.object(driver, "collect_metrics")
    def test_each_symbol_starts_from_its_own_declared_month(self, mock_collect):
        mock_collect.side_effect = lambda symbol, s, e, root: _fake_metrics_result(symbol)
        driver.run(target="metrics")

        btc_calls = [c for c in mock_collect.call_args_list if c.args[0].value == "BTC"]
        eth_calls = [c for c in mock_collect.call_args_list if c.args[0].value == "ETH"]

        self.assertEqual([c.args[1] for c in btc_calls], [date(2021, 1, 1)])
        self.assertEqual(eth_calls, [])  # ETH's 2022-01 start is after the shared 2021-01 end


class TestRetryAndReporting(unittest.TestCase):
    @patch.object(driver, "_FUNDING_DEEP_START", {"BTC": (2020, 1)})
    @patch.object(driver, "_END_YEAR", 2020)
    @patch.object(driver, "_END_MONTH", 1)
    @patch("time.sleep")
    @patch.object(driver, "collect_funding_rate")
    def test_transient_failure_is_retried_then_succeeds(self, mock_collect, mock_sleep):
        calls = {"n": 0}

        def flaky(symbol, s, e, root, source):
            calls["n"] += 1
            if calls["n"] < 3:
                raise HistoricalDataError("transient")
            return _fake_funding_result(symbol)

        mock_collect.side_effect = flaky
        driver.run(target="funding")
        self.assertEqual(calls["n"], 3)
        self.assertTrue(mock_sleep.called)

    @patch.object(driver, "_FUNDING_DEEP_START", {"BTC": (2020, 1)})
    @patch.object(driver, "_END_YEAR", 2020)
    @patch.object(driver, "_END_MONTH", 1)
    @patch.object(driver, "_MAX_ATTEMPTS", 2)
    @patch("time.sleep")
    @patch.object(driver, "collect_funding_rate")
    def test_exhausted_retries_recorded_as_failed_not_raised(self, mock_collect, mock_sleep):
        mock_collect.side_effect = HistoricalDataError("permanent")
        with patch("builtins.print") as mock_print:
            driver.run(target="funding")  # must not raise
        printed = "\n".join(str(c.args[0]) for c in mock_print.call_args_list)
        self.assertIn("BACKFILL_INCOMPLETE", printed)
        self.assertIn("funding/BTC 2020-01", printed)
        self.assertEqual(mock_collect.call_count, 2)  # _MAX_ATTEMPTS, not unbounded

    @patch.object(driver, "_FUNDING_DEEP_START", {"BTC": (2020, 1)})
    @patch.object(driver, "_METRICS_DEEP_START", {})
    @patch.object(driver, "_END_YEAR", 2020)
    @patch.object(driver, "_END_MONTH", 1)
    @patch.object(driver, "collect_funding_rate")
    def test_clean_run_prints_backfill_complete(self, mock_collect):
        mock_collect.side_effect = lambda symbol, s, e, root, source: _fake_funding_result(symbol)
        with patch("builtins.print") as mock_print:
            driver.run(target="all")
        printed = "\n".join(str(c.args[0]) for c in mock_print.call_args_list)
        self.assertIn("BACKFILL_COMPLETE target=all", printed)
        self.assertNotIn("BACKFILL_INCOMPLETE", printed)

    def test_invalid_target_raises(self):
        with self.assertRaises(ValueError):
            driver.run(target="bogus")


class TestTargetSelection(unittest.TestCase):
    """target="funding"/"metrics" must not call the other collector at all."""

    @patch.object(driver, "_FUNDING_DEEP_START", {"BTC": (2020, 1)})
    @patch.object(driver, "_METRICS_DEEP_START", {"BTC": (2020, 1)})
    @patch.object(driver, "_END_YEAR", 2020)
    @patch.object(driver, "_END_MONTH", 1)
    @patch.object(driver, "collect_metrics")
    @patch.object(driver, "collect_funding_rate")
    def test_funding_target_never_calls_collect_metrics(self, mock_funding, mock_metrics):
        mock_funding.side_effect = lambda symbol, s, e, root, source: _fake_funding_result(symbol)
        driver.run(target="funding")
        mock_funding.assert_called()
        mock_metrics.assert_not_called()

    @patch.object(driver, "_FUNDING_DEEP_START", {"BTC": (2020, 1)})
    @patch.object(driver, "_METRICS_DEEP_START", {"BTC": (2020, 1)})
    @patch.object(driver, "_END_YEAR", 2020)
    @patch.object(driver, "_END_MONTH", 1)
    @patch.object(driver, "collect_metrics")
    @patch.object(driver, "collect_funding_rate")
    def test_metrics_target_never_calls_collect_funding_rate(self, mock_funding, mock_metrics):
        mock_metrics.side_effect = lambda symbol, s, e, root: _fake_metrics_result(symbol)
        driver.run(target="metrics")
        mock_metrics.assert_called()
        mock_funding.assert_not_called()


if __name__ == "__main__":
    unittest.main()
