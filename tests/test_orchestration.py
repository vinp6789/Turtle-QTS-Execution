"""Verification tests for the orchestration layer (Milestone 3).

Two levels, deliberately:

  - Real-engine tests build a genuine paper-mode Engine via
    composition_root.build_engine() (MockExchangeAdapter + real
    OrderManager/PositionManager/PortfolioManager/RiskManager/
    ExecutionStateMachine/EventStore) and drive orchestration against it
    end-to-end. No network; MockExchangeAdapter is in-memory.
  - Isolated unit tests use lightweight duck-typed stand-ins (SimpleNamespace)
    for Engine's components to verify orchestration's OWN coordination
    logic (iteration, translation, delegation) without needing to
    reverse-engineer frozen-module state-machine fixtures unrelated to
    this milestone's own correctness.

Neither level touches a trading loop, a scheduler, or any decision logic --
consistent with orchestration's own scope boundary.
"""

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from config import (
    EngineConfig,
    ExchangeConfig,
    LoggingConfig,
    OperationalConfig,
    RiskConfig,
    RiskProfileParams,
    SecretsConfig,
    TelegramConfig,
    UniverseConfig,
)
from exchange_adapter import (
    Fill,
    MockExchangeAdapter,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Symbol,
    TimeInForce,
)
from risk_manager import RiskManagerLimits

from composition_root import DeploymentSettings, build_engine
from orchestration import (
    FillObserved,
    Orchestrator,
    OrderStatusObserved,
    UnknownVenueEventError,
    dispatch,
    reconcile,
    shutdown,
    startup,
    synchronize,
)

_SIGNING_KEY_REF = "hyperliquid_signing_key_v1"


def _engine_config():
    return EngineConfig(
        environment="paper",
        exchange=ExchangeConfig(name="hyperliquid", network="testnet"),
        universe=UniverseConfig(symbols=("BTC",)),
        risk=RiskConfig(
            active_profile="BALANCED",
            profiles={
                "BALANCED": RiskProfileParams(
                    risk_pct_per_trade=0.01, max_positions=3, sizing_mode="fixed",
                    heat_cap=0.05, ruin_threshold=0.6,
                )
            },
            max_daily_loss_pct=0.05, max_drawdown_from_peak_pct=0.2,
            auto_flatten_enabled=False, auto_flatten_confirmation_seconds=60,
        ),
        operational=OperationalConfig(
            max_retries=5, retry_base_delay_seconds=0.5, retry_max_delay_seconds=30.0,
            clock_drift_tolerance_ms=250, data_staleness_price_ms=5000,
            data_staleness_orderbook_ms=3000, data_staleness_position_ms=10000,
        ),
        secrets=SecretsConfig(
            signing_key_ref=_SIGNING_KEY_REF, telegram_bot_token_ref="telegram_bot_token_v1",
        ),
        telegram=TelegramConfig(enabled=False, chat_id="123"),
        logging=LoggingConfig(level="INFO", directory="/tmp/log"),
    )


def _risk_limits():
    return RiskManagerLimits(
        max_leverage=Decimal("5"), min_liquidation_buffer_pct=Decimal("0.1"),
        max_funding_rate_abs=Decimal("0.01"), max_correlated_positions=3,
        max_stale_data_seconds=30,
    )


def _env():
    return {f"TURTLE_SECRET_{_SIGNING_KEY_REF.upper()}": "signing-secret-material"}


class _RealPaperEngineCase(unittest.TestCase):
    """Builds one genuine paper-mode Engine per test via composition_root,
    then connects it (Engine.start()) so adapter-facing calls work."""

    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.engine = build_engine(
            config=_engine_config(),
            deployment=DeploymentSettings(engine_version="1.0.0"),
            risk_limits=_risk_limits(),
            event_store_path=Path(tmpdir.name) / "events.log",
            env=_env(),
        )
        self.addCleanup(self.engine.event_store.close)


class TestLifecycle(_RealPaperEngineCase):
    def test_startup_connects_syncs_and_reconciles(self):
        report = startup(self.engine)
        self.assertTrue(self.engine.is_started)
        self.assertEqual(report.resynced_orders, ())  # nothing placed yet -> nothing in doubt
        self.assertTrue(report.reconciliation.matches)  # both sides empty

    def test_shutdown_disconnects_and_closes_the_event_store(self):
        startup(self.engine)
        shutdown(self.engine)
        self.assertFalse(self.engine.is_started)
        self.assertTrue(self.engine.event_store._closed)

    def test_orchestrator_delegates_startup_and_shutdown_to_the_same_engine(self):
        orchestrator = Orchestrator(self.engine)
        report = orchestrator.startup()
        self.assertTrue(self.engine.is_started)
        self.assertTrue(report.reconciliation.matches)
        orchestrator.shutdown()
        self.assertFalse(self.engine.is_started)

    def test_orchestrator_rejects_a_non_engine(self):
        with self.assertRaises(TypeError):
            Orchestrator(SimpleNamespace(order_manager=None))


class TestSynchronizeRealEngine(_RealPaperEngineCase):
    def test_no_in_doubt_orders_on_a_freshly_built_engine(self):
        startup(self.engine)
        self.assertEqual(synchronize(self.engine), ())


class TestReconcileRealEngine(_RealPaperEngineCase):
    def test_matches_when_both_sides_have_no_positions(self):
        startup(self.engine)
        report = reconcile(self.engine)
        self.assertTrue(report.matches)
        self.assertEqual(report.discrepancies, ())

    def test_detects_a_venue_side_position_with_no_local_counterpart(self):
        startup(self.engine)
        self.engine.adapter.set_position(
            Position(
                symbol=Symbol("BTC"), quantity=Decimal("1"), entry_price=Decimal("100"),
                mark_price=Decimal("100"), unrealized_pnl=Decimal("0"), liquidation_price=None,
            )
        )
        report = reconcile(self.engine)
        self.assertFalse(report.matches)
        self.assertEqual(len(report.discrepancies), 1)
        self.assertIn("BTC", report.discrepancies[0])


class TestDispatchRealEngine(_RealPaperEngineCase):
    def test_dispatch_fill_observed_updates_the_real_order(self):
        startup(self.engine)
        placed = self.engine.order_manager.place_order(
            symbol=Symbol("BTC"), side=OrderSide.BUY, order_type=OrderType.LIMIT,
            quantity=Decimal("1"), limit_price=Decimal("100"),
        )
        fill = Fill(
            fill_id="fill-1", client_order_id=placed.client_order_id,
            exchange_order_id=placed.exchange_order_id, symbol=Symbol("BTC"),
            side=OrderSide.BUY, price=Decimal("100"), quantity=Decimal("1"),
            fee=Decimal("0.01"), timestamp_utc="2026-01-01T00:00:00+00:00",
        )
        updated = dispatch(self.engine, FillObserved(placed.client_order_id, fill))
        self.assertEqual(updated.filled_quantity, Decimal("1"))

    def test_dispatch_order_status_observed_updates_the_real_order(self):
        startup(self.engine)
        placed = self.engine.order_manager.place_order(
            symbol=Symbol("BTC"), side=OrderSide.BUY, order_type=OrderType.LIMIT,
            quantity=Decimal("1"), limit_price=Decimal("100"),
        )
        # A re-affirming ACKNOWLEDGED status update (e.g. a second poll of
        # adapter.get_orders() before anything has changed) -- a realistic
        # duplicate/idempotent status observation. CANCELLED is deliberately
        # not used here: OrderManager's own state machine only accepts a
        # CANCEL_CONFIRMED trigger after a CANCEL_REQUESTED has already been
        # driven (i.e. via cancel_order()), so asserting a direct ACKNOWLEDGED
        # -> CANCELLED report_order_update would be asserting on an
        # OrderManager rule this test has no business overriding.
        venue_order = Order(
            client_order_id=placed.client_order_id, exchange_order_id=placed.exchange_order_id,
            symbol=Symbol("BTC"), side=OrderSide.BUY, order_type=OrderType.LIMIT,
            quantity=Decimal("1"), filled_quantity=Decimal("0"), limit_price=Decimal("100"),
            status=OrderStatus.ACKNOWLEDGED, time_in_force=TimeInForce.GTC, reduce_only=False,
            created_at_utc="2026-01-01T00:00:00+00:00", updated_at_utc="2026-01-01T00:00:00+00:00",
        )
        updated = dispatch(self.engine, OrderStatusObserved(placed.client_order_id, venue_order))
        self.assertEqual(updated.lifecycle_state.value, "ACKNOWLEDGED")
        self.assertEqual(updated.client_order_id, placed.client_order_id)

    def test_dispatch_unknown_event_type_raises(self):
        with self.assertRaises(UnknownVenueEventError):
            dispatch(self.engine, "not a real event")


class TestSynchronizeCoordinationLogic(unittest.TestCase):
    """Isolated: verifies synchronize() iterates in_doubt_client_order_ids
    and calls resync_order for each -- using a duck-typed stand-in so this
    test targets orchestration's OWN glue, not OrderManager's internal
    in-doubt/crash-recovery state machine (already covered by
    tests/test_hyperliquid_crash_recovery.py and order_manager's own suite)."""

    def test_calls_resync_order_for_every_in_doubt_id(self):
        resynced = []

        class _FakeOrderManager:
            in_doubt_client_order_ids = ("a", "b", "c")

            def resync_order(self, client_order_id):
                resynced.append(client_order_id)
                return f"snapshot-{client_order_id}"

        fake_engine = SimpleNamespace(order_manager=_FakeOrderManager())
        result = synchronize(fake_engine)
        self.assertEqual(resynced, ["a", "b", "c"])
        self.assertEqual(result, ("snapshot-a", "snapshot-b", "snapshot-c"))

    def test_returns_empty_when_nothing_is_in_doubt(self):
        class _FakeOrderManager:
            in_doubt_client_order_ids = ()

            def resync_order(self, client_order_id):
                raise AssertionError("must not be called when nothing is in doubt")

        fake_engine = SimpleNamespace(order_manager=_FakeOrderManager())
        self.assertEqual(synchronize(fake_engine), ())


class TestReconcileCoordinationLogic(unittest.TestCase):
    """Isolated: verifies reconcile()'s translation from PositionSnapshot's
    shape into the adapter's Position shape -- sign flip for SELL, delegation
    to PositionManager.unrealized_pnl (never recomputed here), and skipping
    a locally-flat position -- using duck-typed stand-ins."""

    def _snapshot(self, side, remaining_quantity, avg_entry_price=Decimal("100")):
        return SimpleNamespace(
            symbol=Symbol("BTC"), side=side, remaining_quantity=remaining_quantity,
            avg_entry_price=avg_entry_price,
        )

    def test_buy_side_yields_positive_signed_quantity(self):
        snapshot = self._snapshot(OrderSide.BUY, Decimal("2"))
        position_manager = SimpleNamespace(
            get_position=lambda pid: snapshot,
            unrealized_pnl=lambda pid, mark: Decimal("42"),
        )
        portfolio_manager = SimpleNamespace(
            get_snapshot=lambda: SimpleNamespace(open_position_ids=("pos-1",))
        )
        captured = {}
        adapter = SimpleNamespace(
            get_mark_price=lambda symbol: SimpleNamespace(price=Decimal("105")),
            reconcile=lambda positions: captured.setdefault("positions", positions),
        )
        fake_engine = SimpleNamespace(
            position_manager=position_manager, portfolio_manager=portfolio_manager, adapter=adapter,
        )
        reconcile(fake_engine)
        (position,) = captured["positions"]
        self.assertEqual(position.quantity, Decimal("2"))
        self.assertEqual(position.mark_price, Decimal("105"))
        self.assertEqual(position.unrealized_pnl, Decimal("42"))
        self.assertIsNone(position.liquidation_price)

    def test_sell_side_yields_negative_signed_quantity(self):
        snapshot = self._snapshot(OrderSide.SELL, Decimal("3"))
        position_manager = SimpleNamespace(
            get_position=lambda pid: snapshot, unrealized_pnl=lambda pid, mark: Decimal("0"),
        )
        portfolio_manager = SimpleNamespace(
            get_snapshot=lambda: SimpleNamespace(open_position_ids=("pos-1",))
        )
        captured = {}
        adapter = SimpleNamespace(
            get_mark_price=lambda symbol: SimpleNamespace(price=Decimal("105")),
            reconcile=lambda positions: captured.setdefault("positions", positions),
        )
        fake_engine = SimpleNamespace(
            position_manager=position_manager, portfolio_manager=portfolio_manager, adapter=adapter,
        )
        reconcile(fake_engine)
        (position,) = captured["positions"]
        self.assertEqual(position.quantity, Decimal("-3"))

    def test_locally_flat_position_is_skipped(self):
        snapshot = self._snapshot(OrderSide.BUY, Decimal("0"))
        position_manager = SimpleNamespace(
            get_position=lambda pid: snapshot,
            unrealized_pnl=lambda pid, mark: (_ for _ in ()).throw(AssertionError("must not be called")),
        )
        portfolio_manager = SimpleNamespace(
            get_snapshot=lambda: SimpleNamespace(open_position_ids=("pos-1",))
        )
        captured = {}
        adapter = SimpleNamespace(
            get_mark_price=lambda symbol: (_ for _ in ()).throw(AssertionError("must not be called")),
            reconcile=lambda positions: captured.setdefault("positions", positions),
        )
        fake_engine = SimpleNamespace(
            position_manager=position_manager, portfolio_manager=portfolio_manager, adapter=adapter,
        )
        reconcile(fake_engine)
        self.assertEqual(captured["positions"], ())


if __name__ == "__main__":
    unittest.main()
