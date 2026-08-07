"""Tests for execution_sim.transport -- the simulated execution venue.

Four jobs:

  1. DETERMINISM -- a hard requirement. Two runs over identical market
     data must produce identical fills, byte for byte. Tested by running
     the same sequence twice and comparing the whole fill ledger.

  2. THE PASSTHROUGH BOUNDARY. Market-scoped reads must reach the venue
     unmodified; account-scoped reads must never. Getting this backwards
     is the defect that would make reconciliation diverge on cycle one,
     so it is asserted directly rather than assumed.

  3. ARITHMETIC. Fees and realised PnL are checked against values derived
     by hand in the test, not against values the code produced.

  4. EXECUTION PARITY. The simulated path must present the SAME response
     contract the real venue does, so the adapter above it cannot tell
     the difference. Asserted against the shapes hyperliquid_adapter
     actually parses.
"""

import unittest
from decimal import Decimal

from hyperliquid_adapter.transport import HttpResponse

from execution_sim.transport import (
    MAKER_FEE_RATE,
    TAKER_FEE_RATE,
    SimulatedTransport,
)

BASE = "https://api.hyperliquid-testnet.xyz"


class RecordingVenue:
    """A stand-in for the real venue. Records what reached it."""

    def __init__(self, mids=None):
        self.seen = []
        self._mids = mids or {"BTC": "100000", "ETH": "4000"}

    def __call__(self, url, payload, timeout_seconds):
        self.seen.append(payload.get("type"))
        t = payload.get("type")
        if t == "meta":
            return HttpResponse(200, {"universe": [{"name": "BTC"}, {"name": "ETH"}]})
        if t == "allMids":
            return HttpResponse(200, dict(self._mids))
        if t == "candleSnapshot":
            return HttpResponse(200, [{"t": 1, "c": "100000"}])
        return HttpResponse(200, {})


def _order(asset=0, buy=True, px="100000", sz="0.01", reduce_only=False, cloid="0x1"):
    return {"action": {"type": "order", "orders": [
        {"a": asset, "b": buy, "p": px, "s": sz, "r": reduce_only, "c": cloid}]}}


def _new(venue=None, equity="10000"):
    return SimulatedTransport(base_url=BASE, passthrough=venue or RecordingVenue(),
                              starting_equity=Decimal(equity))


class TestDeterminism(unittest.TestCase):
    """A hard requirement, not a nice-to-have."""

    def _run(self):
        t = _new()
        for px, buy in (("100000", True), ("101000", False), ("99000", True)):
            t(BASE + "/exchange", _order(px=px, buy=buy), 10)
        return t._fills, t.snapshot()

    def test_two_identical_runs_produce_identical_fills(self):
        fills_a, snap_a = self._run()
        fills_b, snap_b = self._run()
        self.assertEqual(fills_a, fills_b)
        self.assertEqual(snap_a, snap_b)

    def test_order_ids_come_from_a_counter_not_a_clock(self):
        t = _new()
        oids = []
        for _ in range(3):
            body = t(BASE + "/exchange", _order(), 10).body
            oids.append(body["response"]["data"]["statuses"][0]["filled"]["oid"])
        self.assertEqual(oids, [1000, 1001, 1002])

    def test_no_rng_or_wall_clock_in_the_module(self):
        from pathlib import Path
        src = Path("execution_sim/transport.py").read_text(encoding="utf-8")
        for banned in ("import random", "time.time", "datetime.now", "uuid"):
            self.assertNotIn(banned, src, f"{banned} would break determinism")


class TestPassthroughBoundary(unittest.TestCase):
    """Market reads reach the venue; account reads never do."""

    def test_market_reads_pass_through_unmodified(self):
        venue = RecordingVenue()
        t = _new(venue)
        for req in ("candleSnapshot", "meta", "metaAndAssetCtxs", "allMids"):
            t(BASE + "/info", {"type": req}, 10)
        for req in ("candleSnapshot", "meta", "metaAndAssetCtxs", "allMids"):
            self.assertIn(req, venue.seen)

    def test_account_reads_never_reach_the_venue(self):
        venue = RecordingVenue()
        t = _new(venue)
        for req in ("userFills", "clearinghouseState", "frontendOpenOrders", "orderStatus"):
            t(BASE + "/info", {"type": req, "oid": 1}, 10)
        for req in ("userFills", "clearinghouseState", "frontendOpenOrders", "orderStatus"):
            self.assertNotIn(req, venue.seen,
                             f"{req} describes OUR account and must be simulated")

    def test_unrecognised_types_pass_through_rather_than_guess(self):
        venue = RecordingVenue()
        t = _new(venue)
        t(BASE + "/info", {"type": "somethingBrandNew"}, 10)
        self.assertIn("somethingBrandNew", venue.seen)

    def test_exchange_never_reaches_the_venue(self):
        venue = RecordingVenue()
        t = _new(venue)
        t(BASE + "/exchange", _order(), 10)
        self.assertNotIn("order", venue.seen)


class TestArithmetic(unittest.TestCase):
    def test_fill_is_at_the_orders_own_limit_price(self):
        t = _new()
        body = t(BASE + "/exchange", _order(px="100000"), 10).body
        self.assertEqual(body["response"]["data"]["statuses"][0]["filled"]["avgPx"], "100000")

    def test_taker_fee_matches_the_measured_rate(self):
        t = _new()
        t(BASE + "/exchange", _order(px="100000", sz="0.01"), 10)
        # 100000 * 0.01 * 0.00045 = 0.45
        self.assertEqual(Decimal(t.snapshot()["fees_paid"]), Decimal("0.45"))

    def test_measured_rates_are_the_documented_ones(self):
        self.assertEqual(TAKER_FEE_RATE, Decimal("0.00045"))
        self.assertEqual(MAKER_FEE_RATE, Decimal("0.00015"))

    def test_realised_pnl_on_a_round_trip(self):
        t = _new()
        t(BASE + "/exchange", _order(buy=True, px="100000", sz="0.01"), 10)
        t(BASE + "/exchange", _order(buy=False, px="101000", sz="0.01"), 10)
        # (101000 - 100000) * 0.01 = 10
        self.assertEqual(Decimal(t.snapshot()["realized_pnl"]), Decimal("10"))
        self.assertEqual(t.snapshot()["open_positions"], {})

    def test_a_losing_round_trip_is_negative(self):
        t = _new()
        t(BASE + "/exchange", _order(buy=True, px="100000", sz="0.01"), 10)
        t(BASE + "/exchange", _order(buy=False, px="99000", sz="0.01"), 10)
        self.assertEqual(Decimal(t.snapshot()["realized_pnl"]), Decimal("-10"))

    def test_short_round_trip_realises_correctly(self):
        t = _new()
        t(BASE + "/exchange", _order(buy=False, px="100000", sz="0.01"), 10)
        t(BASE + "/exchange", _order(buy=True, px="99000", sz="0.01"), 10)
        self.assertEqual(Decimal(t.snapshot()["realized_pnl"]), Decimal("10"))

    def test_adding_to_a_position_uses_a_weighted_average_entry(self):
        t = _new()
        t(BASE + "/exchange", _order(buy=True, px="100000", sz="0.01"), 10)
        t(BASE + "/exchange", _order(buy=True, px="102000", sz="0.01"), 10)
        self.assertEqual(t._entry_px["BTC"], Decimal("101000"))

    def test_equity_is_start_plus_realised_minus_fees_plus_unrealised(self):
        t = _new(equity="10000")
        t(BASE + "/exchange", _order(buy=True, px="100000", sz="0.01"), 10)
        s = t.snapshot()
        expected = (Decimal("10000") + Decimal(s["realized_pnl"])
                    - Decimal(s["fees_paid"]) + Decimal(s["unrealized_pnl"]))
        self.assertEqual(Decimal(s["equity"]), expected)


class TestExecutionParity(unittest.TestCase):
    """The simulated path must present the contract the adapter parses.

    These shapes are taken from hyperliquid_adapter/adapter.py's own
    parsing (_check_ok, _statuses, _parse_place_result), so a drift in
    either direction fails here rather than at runtime.
    """

    def test_place_response_matches_what_the_adapter_parses(self):
        body = _new()(BASE + "/exchange", _order(), 10).body
        self.assertEqual(body["status"], "ok")                      # _check_ok
        statuses = body["response"]["data"]["statuses"]              # _statuses
        self.assertTrue(statuses)
        filled = statuses[0]["filled"]                               # _parse_place_result
        for key in ("totalSz", "avgPx", "oid"):
            self.assertIn(key, filled)

    def test_cancel_response_matches(self):
        body = _new()(BASE + "/exchange",
                      {"action": {"type": "cancel", "cancels": [{"a": 0, "o": 1}]}}, 10).body
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["response"]["data"]["statuses"], ["success"])

    def test_unimplemented_action_returns_a_venue_shaped_error(self):
        body = _new()(BASE + "/exchange", {"action": {"type": "twapOrder"}}, 10).body
        self.assertEqual(body["status"], "err")

    def test_clearinghouse_state_carries_the_fields_the_codec_reads(self):
        t = _new()
        t(BASE + "/exchange", _order(), 10)
        body = t(BASE + "/info", {"type": "clearinghouseState"}, 10).body
        self.assertIn("assetPositions", body)
        self.assertIn("accountValue", body["marginSummary"])
        pos = body["assetPositions"][0]["position"]
        for key in ("coin", "szi", "entryPx", "unrealizedPnl"):
            self.assertIn(key, pos)

    def test_user_fills_carries_the_fields_the_codec_reads(self):
        t = _new()
        t(BASE + "/exchange", _order(), 10)
        fills = t(BASE + "/info", {"type": "userFills"}, 10).body
        self.assertEqual(len(fills), 1)
        for key in ("coin", "px", "sz", "side", "time", "oid", "fee", "tid"):
            self.assertIn(key, fills[0])

    def test_order_status_reports_unknown_for_an_unplaced_order(self):
        body = _new()(BASE + "/info", {"type": "orderStatus", "oid": 99}, 10).body
        self.assertEqual(body["status"], "unknownOid")


class TestPhase1ScopeIsHonest(unittest.TestCase):
    """Phase 1 excludes slippage, partials and resting orders. Assert the
    exclusions hold, so a later phase cannot land silently."""

    def test_no_partial_fills(self):
        t = _new()
        body = t(BASE + "/exchange", _order(sz="5"), 10).body
        self.assertEqual(body["response"]["data"]["statuses"][0]["filled"]["totalSz"], "5")

    def test_nothing_rests(self):
        t = _new()
        t(BASE + "/exchange", _order(), 10)
        self.assertEqual(t(BASE + "/info", {"type": "frontendOpenOrders"}, 10).body, [])

    def test_no_slippage_fill_price_equals_limit_price(self):
        t = _new()
        for px in ("100000", "1", "987654321"):
            body = t(BASE + "/exchange", _order(px=px), 10).body
            self.assertEqual(body["response"]["data"]["statuses"][0]["filled"]["avgPx"], px)


if __name__ == "__main__":
    unittest.main()
