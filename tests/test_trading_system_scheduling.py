"""Verification tests for trading_system.scheduling (Milestone 8).

Builds a genuine paper-mode Engine via composition_root (MockExchangeAdapter,
in-memory, no network) and drives run_cycle() end-to-end with minimal stub
Strategy test doubles (no trading logic) -- verifying the full pipeline
actually places real orders through the real OrderManager, and that
startup only happens once across repeated cycles.
"""

import tempfile
import unittest
from datetime import datetime, timezone
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
from exchange_adapter import FundingRate, MarkPrice, OrderSide, OrderType, Symbol, TimeInForce
from risk_manager import CorrelationInfo, RiskManagerLimits

from composition_root import DeploymentSettings, build_engine
from trading_system.scheduling import CycleResult, SchedulingError, run_cycle
from trading_system.strategy import Strategy, TradeIntent

_SIGNING_KEY_REF = "hyperliquid_signing_key_v1"
# A real wall-clock timestamp, not an arbitrary fixed date: PortfolioManager/
# OrderManager stamp their OWN events with the real clock (e.g. deposit()),
# and RiskManager's staleness check treats a NEGATIVE age (evaluated_at_utc
# earlier than a snapshot's own timestamp) as suspicious -- so the injected
# cycle clock must not predate real events this fixture creates.
_NOW = datetime.now(timezone.utc).isoformat()


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


def _risk_profile(**overrides):
    fields = dict(risk_pct_per_trade=0.02, max_positions=3, sizing_mode="fixed", heat_cap=0.05, ruin_threshold=0.6)
    fields.update(overrides)
    return RiskProfileParams(**fields)


class _NoOpStrategy(Strategy):
    """A stub returning no intents -- proves the pipeline runs cleanly
    with nothing to do. Not a trading strategy."""

    @property
    def name(self):
        return "no-op"

    def generate_intents(self, context):
        return ()


class _FixedIntentStrategy(Strategy):
    """A stub returning one fixed TradeIntent every cycle, for
    integration testing only -- not a real trading strategy (no market
    analysis, no signal)."""

    def __init__(self, intent, label="fixed"):
        self._intent = intent
        self._label = label

    @property
    def name(self):
        return self._label

    def generate_intents(self, context):
        return (self._intent,)


def _intent(**overrides):
    fields = dict(
        symbol=Symbol("BTC"), side=OrderSide.BUY, order_type=OrderType.LIMIT,
        time_in_force=TimeInForce.GTC, reduce_only=False, stop_price=Decimal("90"),
        limit_price=Decimal("100"),
    )
    fields.update(overrides)
    return TradeIntent(**fields)


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
        self.engine.adapter.set_mark_price(MarkPrice(symbol=Symbol("BTC"), price=Decimal("100"), timestamp_utc=_NOW))
        self.engine.adapter.set_funding_rate(
            FundingRate(symbol=Symbol("BTC"), rate=Decimal("0.0001"), next_funding_time_utc=_NOW, timestamp_utc=_NOW)
        )

    def _run(self, strategies, **overrides):
        # No clock override by default: run_cycle's own real-time default
        # clock is used, so evaluated_at_utc always postdates whatever
        # real wall-clock timestamps other frozen modules (PortfolioManager
        # deposit/reserve_margin, etc.) stamp during the test -- avoiding a
        # spurious negative "age" that RiskManager's own staleness check
        # would otherwise (correctly) flag.
        kwargs = dict(
            universe=(Symbol("BTC"),), risk_profile=_risk_profile(),
            correlation_info=CorrelationInfo(entries=(), as_of_utc=_NOW),
            maintenance_margin_rate=Decimal("0.005"), target_leverage=Decimal("1"),
        )
        kwargs.update(overrides)
        return run_cycle(self.engine, strategies, **kwargs)


class TestCycleStartup(_RealPaperEngineCase):
    def test_first_cycle_starts_the_engine(self):
        self.assertFalse(self.engine.is_started)
        result = self._run((_NoOpStrategy(),))
        self.assertTrue(result.started)
        self.assertIsNotNone(result.health)
        self.assertTrue(self.engine.is_started)

    def test_second_cycle_does_not_restart(self):
        self._run((_NoOpStrategy(),))
        result = self._run((_NoOpStrategy(),))
        self.assertFalse(result.started)
        self.assertIsNone(result.health)


class TestCycleStages(_RealPaperEngineCase):
    def test_returns_a_cycle_result_with_every_stage_populated(self):
        result = self._run((_NoOpStrategy(),))
        self.assertIsInstance(result, CycleResult)
        self.assertEqual(result.resynced_orders, ())
        self.assertTrue(result.reconciliation.matches)
        self.assertEqual(result.intents, ())
        self.assertEqual(result.construction.approved, ())
        self.assertEqual(result.executions, ())
        self.assertIsInstance(result.evaluated_at_utc, str)
        self.assertTrue(result.evaluated_at_utc)

    def test_pools_intents_from_multiple_strategies(self):
        strategy_a = _FixedIntentStrategy(_intent(symbol=Symbol("BTC")), label="a")
        strategy_b = _FixedIntentStrategy(_intent(symbol=Symbol("BTC"), conviction=Decimal("0.9")), label="b")
        result = self._run((strategy_a, strategy_b))
        self.assertEqual(len(result.intents), 2)


class TestCycleEndToEndExecution(_RealPaperEngineCase):
    def test_an_approved_intent_places_a_real_order(self):
        # A freshly-built engine has zero equity, and RiskManager
        # unconditionally FAIL_SAFEs on non-positive equity -- seed a
        # deposit so this cycle has something real to approve against.
        self.engine.portfolio_manager.deposit(Decimal("100000"), request_id="seed-deposit")
        strategy = _FixedIntentStrategy(_intent())
        result = self._run((strategy,))
        self.assertEqual(len(result.construction.approved), 1)
        self.assertEqual(len(result.executions), 1)
        execution = result.executions[0]
        self.assertEqual(execution.order_snapshot.symbol, Symbol("BTC"))
        self.assertIsNotNone(execution.order_snapshot.exchange_order_id)
        # Confirm it is a REAL order tracked by OrderManager, not a
        # simulated result.
        tracked = self.engine.order_manager.get_order_status(execution.order_snapshot.client_order_id)
        self.assertEqual(tracked.client_order_id, execution.order_snapshot.client_order_id)

    def test_a_rejected_intent_places_no_order(self):
        # Deposit a large amount (so equity stays realistic and sizing
        # computes a real notional/margin), then reserve nearly all of it
        # against a hypothetical other position -- this reclassifies cash
        # from available to reserved without changing total equity, so
        # available_cash ends up too small to cover this cycle's margin
        # requirement, and RiskManager rejects on INSUFFICIENT_MARGIN.
        self.engine.portfolio_manager.deposit(Decimal("100000"), request_id="seed-deposit")
        self.engine.portfolio_manager.reserve_margin(
            position_id="dummy-lockup", amount=Decimal("99990"), request_id="lock-up-cash",
        )
        strategy = _FixedIntentStrategy(_intent())
        result = self._run((strategy,))
        self.assertEqual(result.construction.approved, ())
        self.assertEqual(len(result.construction.rejected), 1)
        self.assertEqual(result.executions, ())


class TestCycleInputValidation(_RealPaperEngineCase):
    def test_rejects_wrong_type_engine(self):
        with self.assertRaises(SchedulingError):
            run_cycle(
                "not an engine", (_NoOpStrategy(),), universe=(Symbol("BTC"),), risk_profile=_risk_profile(),
                correlation_info=CorrelationInfo(entries=(), as_of_utc=_NOW),
                maintenance_margin_rate=Decimal("0.005"),
            )

    def test_rejects_wrong_type_in_strategies(self):
        with self.assertRaises(SchedulingError):
            self._run(("not a strategy",))


class TestCycleClockInjection(_RealPaperEngineCase):
    def test_uses_the_injected_clock_deterministically(self):
        result = self._run((_NoOpStrategy(),), clock=lambda: "2030-05-05T00:00:00+00:00")
        self.assertEqual(result.evaluated_at_utc, "2030-05-05T00:00:00+00:00")


class TestOnExecutionHook(_RealPaperEngineCase):
    def test_hook_invoked_per_execution_before_cycle_result(self):
        self.engine.portfolio_manager.deposit(Decimal("100000"), request_id="seed-deposit")
        received = []
        strategy = _FixedIntentStrategy(_intent())
        result = self._run((strategy,), on_execution=received.append)
        self.assertEqual(len(result.executions), 1)
        self.assertEqual(received, list(result.executions))  # same objects, in order

    def test_hook_defaults_to_none_with_prior_behavior(self):
        result = self._run((_NoOpStrategy(),))  # no on_execution passed
        self.assertEqual(result.executions, ())


if __name__ == "__main__":
    unittest.main()
