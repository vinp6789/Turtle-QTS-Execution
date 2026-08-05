"""Verification tests for alpha_engine.historical.live_recorder.

No real network calls: a fake transport returns a canned
metaAndAssetCtxs payload shaped exactly like the live one
(live-verified 2026-08-05: string-encoded decimals; BTC index 0,
ETH 1, SOL 5 -- deliberately NOT contiguous, so a fixed-index
implementation would fail these tests).

The guarantees under test are the ones that make an unattended,
long-running recorder trustworthy: idempotency across restarts,
merge/dedup semantics, hour-slot timestamping, storage layout, and
fail-safe behaviour on a bad response.
"""

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from exchange_adapter import Symbol

from alpha_engine.historical import live_recorder as lr
from alpha_engine.historical import storage
from alpha_engine.historical.models import (
    FundingRateObservation,
    MarkPriceObservation,
    OpenInterestObservation,
)

_SYMS = (Symbol("BTC"), Symbol("ETH"), Symbol("SOL"))


def _payload(oi="35416.7642", funding="-0.0000068349", mark="64221.0", *, drop=None, bad=None):
    """metaAndAssetCtxs shape. Universe deliberately puts SOL at index 5
    with filler assets between -- matching the live venue."""
    universe = [{"name": n} for n in ("BTC", "ETH", "ATOM", "MATIC", "DYDX", "SOL")]
    ctx = {"openInterest": oi, "funding": funding, "markPx": mark,
           "oraclePx": "64000.0", "midPx": "64220.0"}
    ctxs = []
    for name in ("BTC", "ETH", "ATOM", "MATIC", "DYDX", "SOL"):
        entry = dict(ctx)
        if drop and name in drop:
            entry.pop(drop[name], None)
        if bad and name in bad:
            entry[bad[name][0]] = bad[name][1]
        ctxs.append(entry)
    return [{"universe": universe}, ctxs]


def _transport(body):
    def _t(url, payload, timeout_seconds):
        return body
    return _t


_CLOCK = lambda: "2026-08-05T14:37:22.123456+00:00"


class TestHourSlot(unittest.TestCase):
    def test_truncates_to_top_of_hour(self):
        self.assertTrue(lr.hour_slot("2026-08-05T14:37:22.123456+00:00").startswith("2026-08-05T14:00:00"))

    def test_already_on_the_hour_is_unchanged(self):
        a = lr.hour_slot("2026-08-05T14:00:00+00:00")
        b = lr.hour_slot("2026-08-05T14:59:59.999999+00:00")
        self.assertEqual(a, b)

    def test_does_not_roll_into_the_next_hour(self):
        self.assertIn("T14:00:00", lr.hour_slot("2026-08-05T14:59:59.999999+00:00"))


class TestFetchSnapshot(unittest.TestCase):
    def test_locates_symbols_by_name_not_index(self):
        """SOL is at index 5. A fixed-index implementation would read
        ATOM's context and silently record wrong data."""
        _, by_metric, skipped = lr.fetch_snapshot(
            _SYMS, transport=_transport(_payload()), clock=_CLOCK)
        self.assertEqual(skipped, ())
        for metric in ("open_interest", "funding_rate", "mark_price"):
            got = sorted(o.symbol.value for o in by_metric[metric])
            self.assertEqual(got, ["BTC", "ETH", "SOL"])

    def test_produces_all_three_metrics_from_one_call(self):
        calls = []

        def counting(url, payload, timeout_seconds):
            calls.append(payload)
            return _payload()

        _, by_metric, _ = lr.fetch_snapshot(_SYMS, transport=counting, clock=_CLOCK)
        self.assertEqual(len(calls), 1)  # ONE http call, not one per symbol
        self.assertEqual(calls[0], {"type": "metaAndAssetCtxs"})
        self.assertEqual(sum(len(v) for v in by_metric.values()), 9)  # 3 metrics x 3 symbols

    def test_values_parse_as_decimals(self):
        _, by_metric, _ = lr.fetch_snapshot(_SYMS, transport=_transport(_payload()), clock=_CLOCK)
        oi = [o for o in by_metric["open_interest"] if o.symbol.value == "BTC"][0]
        self.assertEqual(oi.value, Decimal("35416.7642"))

    def test_negative_funding_is_preserved(self):
        _, by_metric, _ = lr.fetch_snapshot(_SYMS, transport=_transport(_payload()), clock=_CLOCK)
        f = [o for o in by_metric["funding_rate"] if o.symbol.value == "BTC"][0]
        self.assertEqual(f.value, Decimal("-0.0000068349"))

    def test_observed_at_is_the_hour_slot_and_ingested_is_the_instant(self):
        observed, by_metric, _ = lr.fetch_snapshot(
            _SYMS, transport=_transport(_payload()), clock=_CLOCK)
        self.assertIn("T14:00:00", observed)
        obs = by_metric["open_interest"][0]
        self.assertEqual(obs.observed_at_utc, observed)
        self.assertEqual(obs.ingested_at_utc, "2026-08-05T14:37:22.123456+00:00")

    def test_source_tag_is_distinct_from_the_api_backfilled_series(self):
        _, by_metric, _ = lr.fetch_snapshot(_SYMS, transport=_transport(_payload()), clock=_CLOCK)
        self.assertEqual(by_metric["open_interest"][0].source, "hyperliquid_live")

    def test_unknown_symbol_is_skipped_not_fatal(self):
        _, by_metric, skipped = lr.fetch_snapshot(
            (Symbol("BTC"), Symbol("DOGE")), transport=_transport(_payload()), clock=_CLOCK)
        self.assertEqual(len(skipped), 1)
        self.assertIn("DOGE", skipped[0])
        self.assertEqual(len(by_metric["open_interest"]), 1)  # BTC still recorded

    def test_missing_field_skips_only_that_metric(self):
        body = _payload(drop={"ETH": "markPx"})
        _, by_metric, skipped = lr.fetch_snapshot(_SYMS, transport=_transport(body), clock=_CLOCK)
        self.assertEqual(len(by_metric["mark_price"]), 2)     # ETH mark dropped
        self.assertEqual(len(by_metric["open_interest"]), 3)  # ETH OI still present
        self.assertTrue(any("ETH/mark_price" in s for s in skipped))

    def test_non_decimal_value_is_skipped_never_fabricated(self):
        body = _payload(bad={"SOL": ("openInterest", "not-a-number")})
        _, by_metric, skipped = lr.fetch_snapshot(_SYMS, transport=_transport(body), clock=_CLOCK)
        self.assertEqual(len(by_metric["open_interest"]), 2)
        self.assertTrue(any("SOL/open_interest" in s for s in skipped))

    def test_malformed_envelope_degrades_to_all_skipped_never_fabricates(self):
        """A malformed envelope fails every symbol. The fail-safe contract
        means that surfaces as skips with zero observations, not an
        exception -- and critically, zero fabricated rows."""
        _, by_metric, skipped = lr.fetch_snapshot(
            _SYMS, transport=_transport({"nope": 1}), clock=_CLOCK)
        self.assertEqual(len(skipped), 3)  # one per symbol
        self.assertEqual(sum(len(v) for v in by_metric.values()), 0)


class TestRecordOnce(unittest.TestCase):
    def test_writes_one_file_per_metric_and_symbol(self):
        with tempfile.TemporaryDirectory() as tmp:
            lr.record_once(_SYMS, tmp, transport=_transport(_payload()), clock=_CLOCK)
            names = sorted(p.name for p in Path(tmp).glob("*.csv"))
            self.assertEqual(len(names), 9)
            for metric in ("open_interest", "funding_rate", "mark_price"):
                for sym in ("BTC", "ETH", "SOL"):
                    self.assertIn(f"{metric}__{sym}__hyperliquid_live.csv", names)

    def test_does_not_touch_the_api_backfilled_series(self):
        """The live source tag must keep these files separate, so a live
        funding sample can never collide with a fundingHistory row."""
        with tempfile.TemporaryDirectory() as tmp:
            lr.record_once(_SYMS, tmp, transport=_transport(_payload()), clock=_CLOCK)
            names = [p.name for p in Path(tmp).glob("*.csv")]
            self.assertFalse([n for n in names if n.endswith("__hyperliquid.csv")])

    def test_rerun_within_the_same_hour_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = lr.record_once(_SYMS, tmp, transport=_transport(_payload()), clock=_CLOCK)
            second = lr.record_once(_SYMS, tmp, transport=_transport(_payload()), clock=_CLOCK)
            self.assertEqual(sum(first.rows_added.values()), 9)
            self.assertEqual(sum(second.rows_added.values()), 0)  # nothing added twice

    def test_rerun_with_a_different_value_keeps_the_first_seen(self):
        with tempfile.TemporaryDirectory() as tmp:
            lr.record_once(_SYMS, tmp, transport=_transport(_payload(oi="100")), clock=_CLOCK)
            lr.record_once(_SYMS, tmp, transport=_transport(_payload(oi="999")), clock=_CLOCK)
            rows = storage.load(Path(tmp) / "open_interest__BTC__hyperliquid_live.csv",
                                OpenInterestObservation)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].value, Decimal("100"))

    def test_next_hour_appends_a_new_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            lr.record_once(_SYMS, tmp, transport=_transport(_payload()), clock=_CLOCK)
            lr.record_once(_SYMS, tmp, transport=_transport(_payload()),
                           clock=lambda: "2026-08-05T15:04:00+00:00")
            rows = storage.load(Path(tmp) / "open_interest__BTC__hyperliquid_live.csv",
                                OpenInterestObservation)
            self.assertEqual(len(rows), 2)
            self.assertNotEqual(rows[0].observed_at_utc, rows[1].observed_at_utc)

    def test_rows_are_loadable_as_their_declared_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            lr.record_once(_SYMS, tmp, transport=_transport(_payload()), clock=_CLOCK)
            for metric, typ in (("open_interest", OpenInterestObservation),
                                ("funding_rate", FundingRateObservation),
                                ("mark_price", MarkPriceObservation)):
                rows = storage.load(Path(tmp) / f"{metric}__BTC__hyperliquid_live.csv", typ)
                self.assertEqual(len(rows), 1)
                self.assertIsInstance(rows[0], typ)

    def test_transport_failure_is_reported_never_raised(self):
        def boom(url, payload, timeout_seconds):
            raise TimeoutError("The read operation timed out")

        with tempfile.TemporaryDirectory() as tmp:
            result = lr.record_once(_SYMS, tmp, transport=boom, clock=_CLOCK)
            self.assertTrue(result.error)
            self.assertIn("TimeoutError", result.error)
            self.assertEqual(list(Path(tmp).glob("*.csv")), [])


class TestRunLoop(unittest.TestCase):
    def test_max_cycles_bounds_the_loop_and_sleeps_between(self):
        slept = []
        with tempfile.TemporaryDirectory() as tmp:
            rc = lr.run(_SYMS, tmp, interval_seconds=3600, max_cycles=3,
                        sleep=slept.append, transport=_transport(_payload()), clock=_CLOCK)
            self.assertEqual(rc, 0)
            self.assertEqual(slept, [3600, 3600])  # no sleep after the final cycle

    def test_loop_survives_a_failing_cycle(self):
        calls = {"n": 0}

        def flaky(url, payload, timeout_seconds):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectionError("down")
            return _payload()

        with tempfile.TemporaryDirectory() as tmp:
            rc = lr.run(_SYMS, tmp, interval_seconds=1, max_cycles=2,
                        sleep=lambda _s: None, transport=flaky, clock=_CLOCK)
            self.assertEqual(rc, 0)
            self.assertEqual(calls["n"], 2)  # kept going after the failure
            rows = storage.load(Path(tmp) / "open_interest__BTC__hyperliquid_live.csv",
                                OpenInterestObservation)
            self.assertEqual(len(rows), 1)


class TestScopeDiscipline(unittest.TestCase):
    """The approved scope is three metrics. Guard against creep."""

    def test_exactly_three_metrics_recorded(self):
        self.assertEqual([m for _, m, _ in lr._METRICS],
                         ["open_interest", "funding_rate", "mark_price"])

    def test_no_websocket_or_orderbook_code(self):
        """Scope guard on CODE, not prose -- the module docstring names the
        excluded surfaces deliberately, so strip docstrings before checking."""
        import ast
        tree = ast.parse(Path(lr.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                if (node.body and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)
                        and isinstance(node.body[0].value.value, str)):
                    node.body[0].value.value = ""
        code = ast.unparse(tree).lower()
        for forbidden in ("websocket", "l2book", "userfills", "orderbook", "allmids"):
            self.assertNotIn(forbidden, code)

    def test_only_endpoint_type_requested_is_metaandassetctxs(self):
        seen = []

        def spy(url, payload, timeout_seconds):
            seen.append(payload.get("type"))
            return _payload()

        lr.fetch_snapshot(_SYMS, transport=spy, clock=_CLOCK)
        self.assertEqual(seen, ["metaAndAssetCtxs"])


if __name__ == "__main__":
    unittest.main()
