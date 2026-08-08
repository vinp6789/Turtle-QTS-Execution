"""The ENGINE_TEST lifecycle probe: entry -> reduce-only exit -> silence.

These tests assert the STATE MACHINE and its safety properties. They do
not test alpha, because the probe has none by construction.

No network: StrategyContext is built with stubs, exactly as the existing
trading_system strategy tests do.
"""

import unittest
from decimal import Decimal

from exchange_adapter import MarkPrice, OrderSide, OrderType, Symbol, TimeInForce
from execution_state_machine import State as EsmState
from position_manager import PositionLifecycleState, PositionSnapshot
from portfolio_manager import PortfolioSnapshot

from alpha_engine.platform import STRATEGY_REGISTRY, PluginKind, get_plugin
from alpha_engine.platform.lifecycle_probe import LifecycleProbeStrategy
from trading_system.market_data import MarketDataView
from trading_system.strategy import StrategyContext

BTC = Symbol("BTC")
MARK = Decimal("64000")


class _Market(MarketDataView):
    """A real MarketDataView subclass (StrategyContext type-checks it),
    with the one method the probe uses overridden. Deliberately skips
    super().__init__ so no Engine, adapter or network is required."""

    def __init__(self):
        pass

    def get_mark_price(self, symbol):
        return MarkPrice(symbol=symbol, price=MARK,
                         timestamp_utc="2026-08-08T00:00:00+00:00")


def _portfolio(open_position_ids=()):
    """Field-for-field the fixture used by tests/test_trading_system_strategy.py."""
    return PortfolioSnapshot(
        available_cash=Decimal("999"), reserved_margin=Decimal("0"), used_margin=Decimal("0"),
        unrealized_pnl=Decimal("0"), realized_pnl_cumulative=Decimal("0"),
        funding_cumulative=Decimal("0"), fees_cumulative=Decimal("0"),
        deposits_cumulative=Decimal("999"), withdrawals_cumulative=Decimal("0"),
        exposure=Decimal("0"), heat=Decimal("0"), open_position_ids=tuple(open_position_ids),
        updated_at_utc="2026-08-08T00:00:00+00:00",
    )


def _position(side=OrderSide.BUY, remaining=Decimal("0.00026"), symbol=BTC):
    return PositionSnapshot(
        position_id="pos-1", lifecycle_state=PositionLifecycleState.OPEN, symbol=symbol,
        side=side, intended_quantity=remaining, filled_quantity=remaining,
        remaining_quantity=remaining, avg_entry_price=MARK,
        stop_price=MARK * Decimal("0.7"), stop_d=MARK * Decimal("0.3"),
        t1_price=MARK * Decimal("1.1"), t2_price=MARK * Decimal("1.2"),
        conviction=None, realized_pnl=Decimal("0"), realized_r=Decimal("0"),
        fees_paid=Decimal("0"), funding_paid=Decimal("0"),
        created_at_utc="2026-08-08T00:00:00+00:00",
        updated_at_utc="2026-08-08T00:00:00+00:00",
    )


def _ctx(open_positions=()):
    return StrategyContext(
        universe=(BTC,), portfolio_snapshot=_portfolio(),
        open_positions=tuple(open_positions), kill_switch_state=EsmState.READY,
        market_data=_Market(), evaluated_at_utc="2026-08-08T00:00:00+00:00",
    )


class TestLifecycleStateMachine(unittest.TestCase):

    def test_1_entry_when_flat(self):
        probe = LifecycleProbeStrategy(BTC)
        intents = probe.generate_intents(_ctx())
        self.assertEqual(len(intents), 1)
        i = intents[0]
        self.assertIs(i.side, OrderSide.BUY)
        self.assertFalse(i.reduce_only)
        self.assertIs(i.order_type, OrderType.LIMIT)
        self.assertIs(i.time_in_force, TimeInForce.GTC)

    def test_2_no_close_before_an_actual_fill(self):
        """Submission must never be mistaken for a position. The probe is
        driven by open_positions (rebuilt from FILL events), so an
        unfilled entry produces another entry, never an exit."""
        probe = LifecycleProbeStrategy(BTC)
        probe.generate_intents(_ctx())              # entry submitted...
        again = probe.generate_intents(_ctx())      # ...still no fill
        self.assertEqual(len(again), 1)
        self.assertFalse(again[0].reduce_only, "emitted an exit with no open position")

    def test_3_close_when_position_exists(self):
        probe = LifecycleProbeStrategy(BTC)
        probe.generate_intents(_ctx())
        intents = probe.generate_intents(_ctx([_position()]))
        self.assertEqual(len(intents), 1)
        self.assertIs(intents[0].side, OrderSide.SELL, "exit must oppose a long")

    def test_4_exit_is_reduce_only(self):
        probe = LifecycleProbeStrategy(BTC)
        intents = probe.generate_intents(_ctx([_position()]))
        self.assertTrue(intents[0].reduce_only,
                        "exit MUST be reduce_only or it could increase the position")

    def test_4b_exit_opposes_a_short_too(self):
        probe = LifecycleProbeStrategy(BTC)
        intents = probe.generate_intents(_ctx([_position(side=OrderSide.SELL)]))
        self.assertIs(intents[0].side, OrderSide.BUY)
        self.assertTrue(intents[0].reduce_only)

    def test_5_silence_after_close(self):
        probe = LifecycleProbeStrategy(BTC)
        probe.generate_intents(_ctx())                 # entry
        probe.generate_intents(_ctx([_position()]))    # exit
        self.assertEqual(probe.generate_intents(_ctx()), (),
                         "probe must latch shut after the lifecycle completes")
        self.assertTrue(probe.completed)
        self.assertEqual(probe.generate_intents(_ctx()), ())

    def test_5b_latch_holds_even_if_a_position_reappears(self):
        probe = LifecycleProbeStrategy(BTC)
        probe.generate_intents(_ctx())
        probe.generate_intents(_ctx([_position()]))
        probe.generate_intents(_ctx())                 # closed -> latch
        self.assertEqual(probe.generate_intents(_ctx([_position()])), ())

    def test_probe_ignores_positions_in_other_symbols(self):
        """An ETH position must not cause a BTC probe to emit an exit."""
        probe = LifecycleProbeStrategy(BTC)
        intents = probe.generate_intents(_ctx([_position(symbol=Symbol("ETH"))]))
        self.assertEqual(len(intents), 1)
        self.assertFalse(intents[0].reduce_only)
        self.assertEqual(intents[0].symbol, BTC)


class TestSizingIntent(unittest.TestCase):
    """The notional is kept small through the EXISTING sizing identity,
    not by weakening a risk control."""

    def test_entry_stop_is_wide_and_below_mark(self):
        i = LifecycleProbeStrategy(BTC).generate_intents(_ctx())[0]
        self.assertLess(i.stop_price, MARK)
        self.assertEqual(i.stop_price, MARK * Decimal("0.70"))

    def test_exit_stop_is_narrower_than_entry_stop(self):
        """Guarantees the sized exit >= the position, so reduce_only
        clamps to a FULL close rather than leaving a residue."""
        p = LifecycleProbeStrategy(BTC)
        entry = p.generate_intents(_ctx())[0]
        exit_ = p.generate_intents(_ctx([_position()]))[0]
        self.assertLess(abs(MARK - exit_.stop_price), abs(MARK - entry.stop_price))

    def test_exit_stop_fraction_wider_than_entry_is_rejected(self):
        with self.assertRaises(ValueError):
            LifecycleProbeStrategy(BTC, stop_fraction=Decimal("0.1"),
                                   exit_stop_fraction=Decimal("0.2"))

    def test_rejects_degenerate_parameters(self):
        for kw in ({"stop_fraction": Decimal("0")}, {"stop_fraction": Decimal("1")},
                   {"limit_slip": Decimal("-1")}):
            with self.assertRaises(ValueError):
                LifecycleProbeStrategy(BTC, **kw)


class TestRegistryClassification(unittest.TestCase):

    def test_6_registered_as_engine_test(self):
        entry = get_plugin("lifecycle_probe")
        self.assertIs(entry.kind, PluginKind.ENGINE_TEST,
                      "the probe must never be classified as ALPHA")

    def test_6b_warning_states_the_real_safety_model(self):
        w = get_plugin("lifecycle_probe").warning
        self.assertIn("INFRASTRUCTURE VALIDATION ONLY", w)
        self.assertIn("NO STOP IS PLACED AT THE VENUE", w)

    def test_6c_factory_builds_through_the_normal_plugin_path(self):
        s = get_plugin("lifecycle_probe").build({"symbol": "BTC"})
        self.assertIsInstance(s, LifecycleProbeStrategy)
        self.assertEqual(s.name, "lifecycle_probe")

    def test_no_alpha_kind_plugin_exists_yet(self):
        """Guards against the probe -- or anything else -- being quietly
        promoted to ALPHA without governance."""
        self.assertEqual(
            [n for n, e in STRATEGY_REGISTRY.items() if e.kind is PluginKind.ALPHA], [])

    def test_7_probe_absent_from_research_and_evidence_surfaces(self):
        """It must never appear in the Alpha Library, Research Ledger,
        campaign reports or the scorecard."""
        from pathlib import Path
        for doc in ("docs/ALPHA_LIBRARY.md", "docs/RESEARCH_LEDGER.md",
                    "docs/ALPHA_SCORECARD.md", "docs/RESEARCH_DECISIONS.md"):
            p = Path(doc)
            if p.is_file():
                self.assertNotIn("lifecycle_probe", p.read_text(encoding="utf-8"),
                                 f"{doc} must not reference an ENGINE_TEST plugin")

    def test_7b_disabled_by_default_in_shipped_config(self):
        from alpha_engine.platform import load_strategies
        strategies, entries = load_strategies("config/strategies.toml")
        self.assertNotIn("lifecycle_probe", [e.name for e in entries],
                         "the probe must ship DISABLED; it places real orders when enabled")


if __name__ == "__main__":
    unittest.main()
