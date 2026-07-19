"""Verification tests for trading_system.execution (Milestone 7).

Builds a genuine paper-mode Engine via composition_root (MockExchangeAdapter,
in-memory, no network) so OrderManager is real -- execution's own job is
to be a thin, correct pass-through, so these tests verify real orders are
actually placed/amended/cancelled, real errors propagate unmodified, and a
non-APPROVED decision never reaches OrderManager at all.
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
from order_manager import OrderNotFoundError
from risk_manager import Decision, ReasonCode, RiskDecision, RiskManagerLimits, TradeRequest

from composition_root import DeploymentSettings, build_engine
from trading_system.execution import (
    ExecutionError,
    ExecutionOperation,
    execute_amend,
    execute_cancel,
    execute_place,
)

_SIGNING_KEY_REF = "hyperliquid_signing_key_v1"
_NOW = "2026-01-01T00:00:00+00:00"


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


def _decision(decision: Decision, **overrides):
    fields = dict(
        decision=decision, reason_codes=(ReasonCode.OK,), violated_limits=(),
        calculated_exposure=None, calculated_heat=None, leverage=None,
        liquidation_buffer=None, funding_estimate=None, timestamp_utc=_NOW, audit_metadata={},
    )
    fields.update(overrides)
    return RiskDecision(**fields)


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
        self.engine.start()
        self.order_manager = self.engine.order_manager


class TestExecutePlace(_RealPaperEngineCase):
    def test_approved_trade_request_places_a_real_order(self):
        result = execute_place(_trade_request(), _decision(Decision.APPROVED), self.order_manager)
        self.assertEqual(result.operation, ExecutionOperation.PLACE)
        self.assertEqual(result.order_snapshot.symbol, Symbol("BTC"))
        self.assertEqual(result.order_snapshot.quantity, Decimal("1"))
        self.assertIsNotNone(result.order_snapshot.exchange_order_id)
        self.assertEqual(result.trade_request, _trade_request())
        self.assertEqual(result.decision.decision, Decision.APPROVED)

    def test_market_order_type_omits_limit_price(self):
        market_request = _trade_request(order_type=OrderType.MARKET)
        result = execute_place(market_request, _decision(Decision.APPROVED), self.order_manager)
        self.assertIsNone(result.order_snapshot.limit_price)

    def test_limit_order_type_uses_entry_price_as_limit_price(self):
        result = execute_place(_trade_request(), _decision(Decision.APPROVED), self.order_manager)
        self.assertEqual(result.order_snapshot.limit_price, Decimal("100"))

    def test_rejected_decision_refuses_and_places_no_order(self):
        orders_before = self.order_manager.in_doubt_client_order_ids
        with self.assertRaises(ExecutionError):
            execute_place(
                _trade_request(),
                _decision(Decision.REJECTED, reason_codes=(ReasonCode.INSUFFICIENT_MARGIN,)),
                self.order_manager,
            )
        self.assertEqual(self.order_manager.in_doubt_client_order_ids, orders_before)  # nothing new tracked

    def test_blocked_decision_refuses(self):
        with self.assertRaises(ExecutionError):
            execute_place(_trade_request(), _decision(Decision.BLOCKED, reason_codes=(ReasonCode.KILL_SWITCH_HARD,)), self.order_manager)

    def test_fail_safe_decision_refuses(self):
        with self.assertRaises(ExecutionError):
            execute_place(_trade_request(), _decision(Decision.FAIL_SAFE, reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,)), self.order_manager)

    def test_rejects_wrong_type_trade_request(self):
        with self.assertRaises(ExecutionError):
            execute_place("not a trade request", _decision(Decision.APPROVED), self.order_manager)

    def test_rejects_wrong_type_decision(self):
        with self.assertRaises(ExecutionError):
            execute_place(_trade_request(), "not a decision", self.order_manager)

    def test_rejects_wrong_type_order_manager(self):
        with self.assertRaises(ExecutionError):
            execute_place(_trade_request(), _decision(Decision.APPROVED), "not an order manager")


class TestExecuteAmend(_RealPaperEngineCase):
    def test_amends_a_real_order(self):
        placed = execute_place(_trade_request(), _decision(Decision.APPROVED), self.order_manager)
        result = execute_amend(
            placed.order_snapshot.client_order_id, self.order_manager, new_quantity=Decimal("2"),
        )
        self.assertEqual(result.operation, ExecutionOperation.AMEND)
        self.assertEqual(result.order_snapshot.quantity, Decimal("2"))
        self.assertIsNone(result.trade_request)
        self.assertIsNone(result.decision)

    def test_nonexistent_order_propagates_order_not_found(self):
        with self.assertRaises(OrderNotFoundError):
            execute_amend("no-such-order", self.order_manager, new_quantity=Decimal("2"))

    def test_rejects_wrong_type_order_manager(self):
        with self.assertRaises(ExecutionError):
            execute_amend("some-id", "not an order manager", new_quantity=Decimal("2"))

    def test_rejects_empty_client_order_id(self):
        with self.assertRaises(ExecutionError):
            execute_amend("", self.order_manager, new_quantity=Decimal("2"))

    def test_does_not_duplicate_order_managers_own_validation(self):
        # OrderManager.amend_order itself raises ValueError if neither
        # new_quantity nor new_limit_price is given -- this module must
        # not pre-empt that with its own check.
        placed = execute_place(_trade_request(), _decision(Decision.APPROVED), self.order_manager)
        with self.assertRaises(ValueError):
            execute_amend(placed.order_snapshot.client_order_id, self.order_manager)


class TestExecuteCancel(_RealPaperEngineCase):
    def test_cancels_a_real_order(self):
        placed = execute_place(_trade_request(), _decision(Decision.APPROVED), self.order_manager)
        result = execute_cancel(placed.order_snapshot.client_order_id, self.order_manager)
        self.assertEqual(result.operation, ExecutionOperation.CANCEL)
        self.assertEqual(result.order_snapshot.lifecycle_state.value, "CANCELLED")
        self.assertIsNone(result.trade_request)
        self.assertIsNone(result.decision)

    def test_nonexistent_order_propagates_order_not_found(self):
        with self.assertRaises(OrderNotFoundError):
            execute_cancel("no-such-order", self.order_manager)

    def test_rejects_wrong_type_order_manager(self):
        with self.assertRaises(ExecutionError):
            execute_cancel("some-id", "not an order manager")

    def test_rejects_empty_client_order_id(self):
        with self.assertRaises(ExecutionError):
            execute_cancel("", self.order_manager)


if __name__ == "__main__":
    unittest.main()
