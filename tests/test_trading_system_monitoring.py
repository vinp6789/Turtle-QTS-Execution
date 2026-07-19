"""Verification tests for trading_system.monitoring (Milestone 9).

Builds a genuine paper-mode Engine via composition_root (MockExchangeAdapter,
in-memory, no network) and verifies capture_snapshot() reads real state,
degrades gracefully (no crash, None fields) before the engine is started,
and never mutates anything.
"""

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

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
from exchange_adapter import OrderSide, OrderType, Symbol, TimeInForce
from execution_state_machine import State
from risk_manager import Decision, ReasonCode, RiskDecision, RiskManagerLimits, TradeRequest

from composition_root import DeploymentSettings, build_engine
from trading_system.execution import execute_place
from trading_system.monitoring import EngineSnapshot, MonitoringError, capture_snapshot

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
                    risk_pct_per_trade=0.02, max_positions=3, sizing_mode="fixed",
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
        max_leverage=Decimal("10"), min_liquidation_buffer_pct=Decimal("0.1"),
        max_funding_rate_abs=Decimal("1"), max_correlated_positions=10,
        max_stale_data_seconds=3600,
    )


def _env():
    return {f"TURTLE_SECRET_{_SIGNING_KEY_REF.upper()}": "signing-secret-material"}


def _trade_request(**overrides):
    fields = dict(
        symbol=Symbol("BTC"), side=OrderSide.BUY, order_type=OrderType.LIMIT,
        time_in_force=TimeInForce.GTC, reduce_only=False, quantity=Decimal("1"),
        entry_price=Decimal("100"), stop_price=Decimal("90"), proposed_risk_amount=Decimal("100"),
        proposed_notional=Decimal("100"), proposed_margin_required=Decimal("100"),
        leverage=Decimal("1"), estimated_liquidation_price=Decimal("50"),
    )
    fields.update(overrides)
    return TradeRequest(**fields)


def _approved_decision():
    return RiskDecision(
        decision=Decision.APPROVED, reason_codes=(ReasonCode.OK,), violated_limits=(),
        calculated_exposure=None, calculated_heat=None, leverage=None, liquidation_buffer=None,
        funding_estimate=None, timestamp_utc="2026-01-01T00:00:00+00:00", audit_metadata={},
    )


class _RealPaperEngineCase(unittest.TestCase):
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


class TestCaptureSnapshotBeforeStart(_RealPaperEngineCase):
    def test_degrades_gracefully_without_crashing(self):
        snapshot = capture_snapshot(self.engine)
        self.assertIsInstance(snapshot, EngineSnapshot)
        self.assertFalse(snapshot.is_started)
        self.assertIsNone(snapshot.open_order_count)
        self.assertIsNone(snapshot.reconciliation)
        self.assertEqual(snapshot.position_count, 0)
        self.assertEqual(snapshot.current_state, State.INITIALIZING)
        self.assertFalse(snapshot.is_kill_switch_active)


class TestCaptureSnapshotAfterStart(_RealPaperEngineCase):
    def test_reflects_live_connected_state(self):
        self.engine.start()
        snapshot = capture_snapshot(self.engine)
        self.assertTrue(snapshot.is_started)
        self.assertEqual(snapshot.open_order_count, 0)
        self.assertIsNotNone(snapshot.reconciliation)
        self.assertTrue(snapshot.reconciliation.matches)

    def test_open_order_count_reflects_a_real_placed_order(self):
        self.engine.start()
        execute_place(_trade_request(), _approved_decision(), self.engine.order_manager)
        snapshot = capture_snapshot(self.engine)
        self.assertEqual(snapshot.open_order_count, 1)


class TestHistoricalFieldsPassThrough(_RealPaperEngineCase):
    def test_defaults_to_none_when_not_supplied(self):
        snapshot = capture_snapshot(self.engine)
        self.assertIsNone(snapshot.last_cycle_completed_at_utc)
        self.assertIsNone(snapshot.last_cycle_construction)
        self.assertIsNone(snapshot.last_cycle_executions)
        self.assertIsNone(snapshot.last_cycle_resynced_order_count)
        self.assertIsNone(snapshot.last_error)

    def test_passes_through_supplied_values_unchanged(self):
        snapshot = capture_snapshot(
            self.engine,
            last_cycle_completed_at_utc="2026-01-01T00:00:00+00:00",
            last_cycle_resynced_order_count=3,
            last_error="boom",
        )
        self.assertEqual(snapshot.last_cycle_completed_at_utc, "2026-01-01T00:00:00+00:00")
        self.assertEqual(snapshot.last_cycle_resynced_order_count, 3)
        self.assertEqual(snapshot.last_error, "boom")


class TestInputValidation(_RealPaperEngineCase):
    def test_rejects_wrong_type_engine(self):
        with self.assertRaises(MonitoringError):
            capture_snapshot("not an engine")


class TestClockInjection(_RealPaperEngineCase):
    def test_uses_the_injected_clock_deterministically(self):
        snapshot = capture_snapshot(self.engine, clock=lambda: "2030-05-05T00:00:00+00:00")
        self.assertEqual(snapshot.captured_at_utc, "2030-05-05T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
