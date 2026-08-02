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

        def fake_collect(symbols, start, end, storage_root, force=False, checkpoint_path=None):
            self._calls.append((symbols, start, end, storage_root, force, checkpoint_path))
            return tuple(_result(s.value) for s in symbols)

        cli.collect_liquidations = fake_collect

    def tearDown(self):
        cli.collect_liquidations = self._real_collect

    def test_defaults_to_watchlist_symbols(self):
        exit_code = cli.main(["--start", "2026-06-01", "--end", "2026-06-30"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(self._calls), 1)
        symbols, start, end, storage_root, force, checkpoint_path = self._calls[0]
        self.assertEqual([s.value for s in symbols], ["BTC", "ETH", "SOL"])
        self.assertEqual(start, date(2026, 6, 1))
        self.assertEqual(end, date(2026, 6, 30))
        self.assertEqual(storage_root, "data/alpha_engine_historical")
        self.assertFalse(force)
        self.assertIsNone(checkpoint_path)

    def test_custom_symbols_and_storage_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            cli.main([
                "--symbols", "BTC", "ETH",
                "--start", "2026-06-01", "--end", "2026-06-01",
                "--storage-root", tmp,
            ])
            symbols, _, _, storage_root, _, _ = self._calls[0]
            self.assertEqual([s.value for s in symbols], ["BTC", "ETH"])
            self.assertEqual(storage_root, tmp)

    def test_missing_required_args_exits_nonzero(self):
        with self.assertRaises(SystemExit) as ctx:
            cli.main(["--start", "2026-06-01"])  # --end missing
        self.assertNotEqual(ctx.exception.code, 0)

    def test_force_flag_reaches_collect_liquidations(self):
        cli.main(["--start", "2026-06-01", "--end", "2026-06-01", "--force"])
        *_, force, _ = self._calls[0]
        self.assertTrue(force)

    def test_checkpoint_path_flag_reaches_collect_liquidations(self):
        with tempfile.TemporaryDirectory() as tmp:
            cp = str(Path(tmp) / "custom_checkpoint.json")
            cli.main(["--start", "2026-06-01", "--end", "2026-06-01", "--checkpoint-path", cp])
            *_, checkpoint_path = self._calls[0]
            self.assertEqual(checkpoint_path, cp)


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

        def flaky(symbols, start, end, storage_root, force=False, checkpoint_path=None):
            attempts.append(1)
            if len(attempts) < 3:
                raise HistoricalDataError("simulated transient failure")
            return tuple(_result(s.value) for s in symbols)

        cli.collect_liquidations = flaky
        exit_code = cli.run(symbols=(Symbol("BTC"),), start=date(2026, 6, 1), end=date(2026, 6, 1))
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(attempts), 3)

    def test_exhausting_retries_returns_nonzero(self):
        def always_fails(symbols, start, end, storage_root, force=False, checkpoint_path=None):
            raise HistoricalDataError("permanent failure")

        cli.collect_liquidations = always_fails
        exit_code = cli.run(symbols=(Symbol("BTC"),), start=date(2026, 6, 1), end=date(2026, 6, 1))
        self.assertEqual(exit_code, 1)

    def test_force_and_checkpoint_path_are_threaded_through_run(self):
        calls = []

        def spy(symbols, start, end, storage_root, force=False, checkpoint_path=None):
            calls.append((force, checkpoint_path))
            return tuple(_result(s.value) for s in symbols)

        cli.collect_liquidations = spy
        cli.run(
            symbols=(Symbol("BTC"),), start=date(2026, 6, 1), end=date(2026, 6, 1),
            force=True, checkpoint_path="/tmp/custom_cp.json",
        )
        self.assertEqual(calls, [(True, "/tmp/custom_cp.json")])

    def test_missing_dates_raises(self):
        with self.assertRaises(HistoricalDataError):
            cli.run(symbols=(Symbol("BTC"),), start=None, end=date(2026, 6, 1))


class TestRetryPolicyConfiguration(unittest.TestCase):
    """The retry policy is configurable rather than hard-coded, and its
    defaults tolerate a multi-minute outage. The original hard-coded
    policy (6 attempts, 2+4+8+16+32 = 62s) was shorter than the real
    outages that repeatedly killed the Backlog 1.5 backfill."""

    def test_default_backoff_matches_the_original_progression(self):
        # The change must EXTEND the old behaviour, not alter its shape:
        # the first five backoffs are exactly what they always were.
        policy = cli.RetryPolicy()
        self.assertEqual(
            [policy.backoff_for(a) for a in range(1, 6)], [2.0, 4.0, 8.0, 16.0, 32.0],
        )

    def test_backoff_is_capped(self):
        policy = cli.RetryPolicy(backoff_base_seconds=2.0, max_backoff_seconds=120.0)
        self.assertEqual(policy.backoff_for(7), 120.0)   # 2*2**6 = 128 -> capped
        self.assertEqual(policy.backoff_for(20), 120.0)  # never grows past the cap

    def test_default_budget_tolerates_at_least_ten_minutes(self):
        """The stated purpose of the change: survive ~10-15 min outages."""
        policy = cli.RetryPolicy()
        total = 0.0
        for attempt in range(1, policy.max_attempts):
            nxt = policy.backoff_for(attempt)
            if total + nxt > policy.max_total_seconds:
                break
            total += nxt
        self.assertGreaterEqual(total, 600.0)  # >= 10 minutes
        self.assertLessEqual(total, 900.0)     # and within the stated budget

    def test_invalid_configuration_is_rejected(self):
        for kwargs in (
            {"max_attempts": 0},
            {"max_attempts": -1},
            {"backoff_base_seconds": -1.0},
            {"max_backoff_seconds": -1.0},
            {"max_total_seconds": -1.0},
        ):
            with self.subTest(**kwargs):
                with self.assertRaises(HistoricalDataError):
                    cli.RetryPolicy(**kwargs)

    def test_cli_flags_parse_into_the_policy(self):
        seen = {}
        real_run = cli.run

        def spy_run(**kwargs):
            seen.update(kwargs)
            return 0

        cli.run = spy_run
        try:
            cli.main([
                "--start", "2026-06-01", "--end", "2026-06-01",
                "--retry-max-attempts", "20",
                "--retry-backoff-base-seconds", "1.5",
                "--retry-max-backoff-seconds", "60",
                "--retry-max-total-seconds", "1800",
            ])
        finally:
            cli.run = real_run
        policy = seen["policy"]
        self.assertEqual(policy.max_attempts, 20)
        self.assertEqual(policy.backoff_base_seconds, 1.5)
        self.assertEqual(policy.max_backoff_seconds, 60.0)
        self.assertEqual(policy.max_total_seconds, 1800.0)

    def test_cli_defaults_produce_the_default_policy(self):
        seen = {}
        real_run = cli.run

        def spy_run(**kwargs):
            seen.update(kwargs)
            return 0

        cli.run = spy_run
        try:
            cli.main(["--start", "2026-06-01", "--end", "2026-06-01"])
        finally:
            cli.run = real_run
        self.assertEqual(seen["policy"], cli.RetryPolicy())


class TestRetryBounds(unittest.TestCase):
    """Retrying must always terminate: a deterministic failure raises the
    same HistoricalDataError a network blip does and is indistinguishable
    here, so both the attempt count and the wall-clock budget must bound
    the loop."""

    def setUp(self):
        self._real_collect = cli.collect_liquidations

    def tearDown(self):
        cli.collect_liquidations = self._real_collect

    def _fake_clock(self, step):
        """Monotonic clock that advances `step` seconds per reading."""
        state = {"t": 0.0}

        def monotonic():
            now = state["t"]
            state["t"] += step
            return now

        return monotonic

    def test_transient_failure_recovers_without_exhausting_budget(self):
        attempts = []
        slept = []

        def flaky(symbols, start, end, storage_root, force=False, checkpoint_path=None):
            attempts.append(1)
            if len(attempts) < 8:  # would have been fatal under the old 6-attempt policy
                raise HistoricalDataError("connection reset by peer")
            return tuple(_result(s.value) for s in symbols)

        cli.collect_liquidations = flaky
        results = cli._collect_with_retry(
            (Symbol("BTC"),), date(2026, 6, 1), date(2026, 6, 1), "root", False, None,
            sleep=slept.append,
        )
        self.assertEqual(len(attempts), 8)
        self.assertEqual(len(results), 1)
        # Backoffs grew then capped, matching the configured policy.
        self.assertEqual(slept, [2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 120.0])

    def test_deterministic_failure_stops_at_max_attempts_not_forever(self):
        attempts = []

        def always_fails(symbols, start, end, storage_root, force=False, checkpoint_path=None):
            attempts.append(1)
            raise HistoricalDataError("MarkPriceObservation.value must be strictly positive, got 0")

        cli.collect_liquidations = always_fails
        policy = cli.RetryPolicy(max_attempts=5, max_total_seconds=10_000.0)
        with self.assertRaises(HistoricalDataError):
            cli._collect_with_retry(
                (Symbol("BTC"),), date(2026, 6, 1), date(2026, 6, 1), "root", False, None,
                policy=policy, sleep=lambda _s: None,
            )
        self.assertEqual(len(attempts), 5)  # bounded by attempts, did not loop forever

    def test_time_budget_stops_retrying_before_max_attempts(self):
        attempts = []

        def always_fails(symbols, start, end, storage_root, force=False, checkpoint_path=None):
            attempts.append(1)
            raise HistoricalDataError("Could not connect to the endpoint URL")

        cli.collect_liquidations = always_fails
        # A huge attempt allowance, but only 10s of budget: the clock
        # advances 5s per reading, so the budget -- not the attempt
        # count -- must be what stops the loop.
        policy = cli.RetryPolicy(max_attempts=1000, max_total_seconds=10.0)
        with self.assertRaises(HistoricalDataError):
            cli._collect_with_retry(
                (Symbol("BTC"),), date(2026, 6, 1), date(2026, 6, 1), "root", False, None,
                policy=policy, sleep=lambda _s: None,
            )
        self.assertLess(len(attempts), 1000)
        self.assertGreaterEqual(len(attempts), 1)

    def test_keyboard_interrupt_is_never_retried(self):
        attempts = []

        def interrupted(symbols, start, end, storage_root, force=False, checkpoint_path=None):
            attempts.append(1)
            raise KeyboardInterrupt()

        cli.collect_liquidations = interrupted
        with self.assertRaises(KeyboardInterrupt):
            cli._collect_with_retry(
                (Symbol("BTC"),), date(2026, 6, 1), date(2026, 6, 1), "root", False, None,
                sleep=lambda _s: None,
            )
        self.assertEqual(len(attempts), 1)  # immediate, no backoff wait

    def test_unexpected_exception_is_never_retried(self):
        attempts = []

        def boom(symbols, start, end, storage_root, force=False, checkpoint_path=None):
            attempts.append(1)
            raise ValueError("a genuine bug, not a network blip")

        cli.collect_liquidations = boom
        with self.assertRaises(ValueError):
            cli._collect_with_retry(
                (Symbol("BTC"),), date(2026, 6, 1), date(2026, 6, 1), "root", False, None,
                sleep=lambda _s: None,
            )
        self.assertEqual(len(attempts), 1)


class TestRetryBudgetMeasuresWaitingNotRuntime(unittest.TestCase):
    """Regression for a real defect: the budget originally measured total
    wall-clock elapsed since the call began, which INCLUDED however long
    the backfill had been successfully collecting. A backfill runs for
    hours before its first blip, so `elapsed` already exceeded the budget
    and the very first failure gave up with ZERO retries -- strictly
    worse than the 6 retries the hard-coded policy had managed. Observed
    in production: 'BACKFILL_FAILED after up to 12 attempts' with not one
    'transient failure' line logged.
    """

    def setUp(self):
        self._real_collect = cli.collect_liquidations

    def tearDown(self):
        cli.collect_liquidations = self._real_collect

    def test_long_successful_run_does_not_consume_the_retry_budget(self):
        attempts = []

        def fails_after_long_work(symbols, start, end, storage_root, force=False, checkpoint_path=None):
            attempts.append(1)
            raise HistoricalDataError("Read timeout on endpoint URL")

        cli.collect_liquidations = fails_after_long_work
        policy = cli.RetryPolicy(max_attempts=12, max_total_seconds=900.0)
        # No checkpoint exists -> no progress detectable -> the ONLY thing
        # that may stop the loop is the attempt/budget bound itself.
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(HistoricalDataError):
                cli._collect_with_retry(
                    (Symbol("BTC"),), date(2026, 6, 1), date(2026, 6, 1), tmp, False, None,
                    policy=policy, sleep=lambda _s: None,
                )
        # Must use the full attempt allowance, not stop at 1.
        self.assertEqual(len(attempts), 12)

    def test_budget_counts_cumulative_backoff_only(self):
        attempts = []
        slept = []

        def always_fails(symbols, start, end, storage_root, force=False, checkpoint_path=None):
            attempts.append(1)
            raise HistoricalDataError("Could not connect to the endpoint URL")

        cli.collect_liquidations = always_fails
        # 60s of budget: 2+4+8+16 = 30 fits, +32 would reach 62 > 60, so
        # it must stop after 4 sleeps regardless of the high attempt cap.
        policy = cli.RetryPolicy(max_attempts=100, max_total_seconds=60.0)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(HistoricalDataError):
                cli._collect_with_retry(
                    (Symbol("BTC"),), date(2026, 6, 1), date(2026, 6, 1), tmp, False, None,
                    policy=policy, sleep=slept.append,
                )
        self.assertEqual(slept, [2.0, 4.0, 8.0, 16.0])
        self.assertEqual(len(attempts), 5)


class TestRetryResetsOnForwardProgress(unittest.TestCase):
    """A failure arriving AFTER the checkpoint advanced is a fresh
    outage, not a stuck loop. Without resetting, a multi-day backfill
    accumulates unrelated outages toward a cap that never resets and
    eventually dies mid-run -- the exact manual-resume churn this work
    exists to stop."""

    def setUp(self):
        self._real_collect = cli.collect_liquidations

    def tearDown(self):
        cli.collect_liquidations = self._real_collect

    def _write_cp(self, path, key):
        path.write_text(f'{{"last_processed_key": "{key}"}}', encoding="utf-8")

    def test_progress_between_failures_resets_the_attempt_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            cp = Path(tmp) / "cp.json"
            self._write_cp(cp, "node_fills_by_block/hourly/20250101/0.lz4")
            state = {"n": 0}

            def fails_but_progresses(symbols, start, end, storage_root, force=False, checkpoint_path=None):
                state["n"] += 1
                # Each attempt advances the checkpoint (real work done),
                # then hits a fresh outage -- until it finally succeeds.
                self._write_cp(cp, f"node_fills_by_block/hourly/2025010{state['n']}/0.lz4")
                if state["n"] < 8:
                    raise HistoricalDataError("Read timeout on endpoint URL")
                return tuple(_result(s.value) for s in symbols)

            cli.collect_liquidations = fails_but_progresses
            # Only 3 attempts allowed: without the progress reset this
            # would die at attempt 3. With it, each advance resets.
            policy = cli.RetryPolicy(max_attempts=3, max_total_seconds=900.0)
            results = cli._collect_with_retry(
                (Symbol("BTC"),), date(2026, 6, 1), date(2026, 6, 1), tmp, False, str(cp),
                policy=policy, sleep=lambda _s: None,
            )
            self.assertEqual(len(results), 1)
            self.assertEqual(state["n"], 8)  # survived well past max_attempts

    def test_no_progress_still_terminates_at_max_attempts(self):
        """The termination guarantee: a deterministic failure advances
        nothing, so nothing resets and the bound still applies."""
        with tempfile.TemporaryDirectory() as tmp:
            cp = Path(tmp) / "cp.json"
            self._write_cp(cp, "node_fills_by_block/hourly/20250101/0.lz4")
            attempts = []

            def always_fails(symbols, start, end, storage_root, force=False, checkpoint_path=None):
                attempts.append(1)  # checkpoint deliberately never moves
                raise HistoricalDataError("MarkPriceObservation.value must be strictly positive, got 0")

            cli.collect_liquidations = always_fails
            policy = cli.RetryPolicy(max_attempts=4, max_total_seconds=900.0)
            with self.assertRaises(HistoricalDataError):
                cli._collect_with_retry(
                    (Symbol("BTC"),), date(2026, 6, 1), date(2026, 6, 1), tmp, False, str(cp),
                    policy=policy, sleep=lambda _s: None,
                )
            self.assertEqual(len(attempts), 4)

    def test_unreadable_checkpoint_is_treated_as_no_progress(self):
        """Best-effort read: a missing/corrupt checkpoint must not crash
        the retry loop, and must not be mistaken for progress."""
        with tempfile.TemporaryDirectory() as tmp:
            cp = Path(tmp) / "cp.json"
            cp.write_text("{ this is not json", encoding="utf-8")
            attempts = []

            def always_fails(symbols, start, end, storage_root, force=False, checkpoint_path=None):
                attempts.append(1)
                raise HistoricalDataError("Read timeout on endpoint URL")

            cli.collect_liquidations = always_fails
            policy = cli.RetryPolicy(max_attempts=3, max_total_seconds=900.0)
            with self.assertRaises(HistoricalDataError):
                cli._collect_with_retry(
                    (Symbol("BTC"),), date(2026, 6, 1), date(2026, 6, 1), tmp, False, str(cp),
                    policy=policy, sleep=lambda _s: None,
                )
            self.assertEqual(len(attempts), 3)  # bounded, no crash


if __name__ == "__main__":
    unittest.main()
