"""Verification tests for trading_system.strategy (Milestone 5).

Covers TradeIntent/StrategyContext structural validation and the Strategy
ABC contract itself, using one minimal stub subclass purely to prove the
interface is implementable and enforced -- not a concrete trading
strategy (no decision logic of any kind).
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
from position_manager import PositionLifecycleState, PositionSnapshot
from portfolio_manager import PortfolioSnapshot
from risk_manager import RiskManagerLimits

from composition_root import DeploymentSettings, build_engine
from trading_system.market_data import MarketDataView
from trading_system.strategy import Strategy, StrategyContext, StrategyError, TradeIntent

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


def _portfolio_snapshot(open_position_ids=()):
    return PortfolioSnapshot(
        available_cash=Decimal("10000"), reserved_margin=Decimal("0"), used_margin=Decimal("0"),
        unrealized_pnl=Decimal("0"), realized_pnl_cumulative=Decimal("0"), funding_cumulative=Decimal("0"),
        fees_cumulative=Decimal("0"), deposits_cumulative=Decimal("10000"), withdrawals_cumulative=Decimal("0"),
        exposure=Decimal("0"), heat=Decimal("0"), open_position_ids=open_position_ids,
        updated_at_utc="2026-01-01T00:00:00+00:00",
    )


def _position_snapshot():
    return PositionSnapshot(
        position_id="pos-1", lifecycle_state=PositionLifecycleState.OPEN, symbol=Symbol("BTC"),
        side=OrderSide.BUY, intended_quantity=Decimal("1"), filled_quantity=Decimal("1"),
        remaining_quantity=Decimal("1"), avg_entry_price=Decimal("100"), stop_price=Decimal("90"),
        stop_d=Decimal("10"), t1_price=Decimal("110"), t2_price=Decimal("120"), conviction=Decimal("0.5"),
        realized_pnl=Decimal("0"), realized_r=Decimal("0"), fees_paid=Decimal("0"), funding_paid=Decimal("0"),
        created_at_utc="2026-01-01T00:00:00+00:00", updated_at_utc="2026-01-01T00:00:00+00:00",
    )


def _trade_intent(**overrides):
    fields = dict(
        symbol=Symbol("BTC"), side=OrderSide.BUY, order_type=OrderType.LIMIT,
        time_in_force=TimeInForce.GTC, reduce_only=False, stop_price=Decimal("90"),
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
        self.engine.start()
        self.market_data = MarketDataView(self.engine)


class TestTradeIntent(unittest.TestCase):
    def test_valid_construction(self):
        intent = _trade_intent(conviction=Decimal("0.7"), limit_price=Decimal("100"))
        self.assertEqual(intent.symbol, Symbol("BTC"))
        self.assertEqual(intent.conviction, Decimal("0.7"))

    def test_minimal_construction_with_only_required_fields(self):
        intent = _trade_intent()
        self.assertIsNone(intent.conviction)
        self.assertIsNone(intent.limit_price)

    def test_rejects_non_symbol(self):
        with self.assertRaises(StrategyError):
            _trade_intent(symbol="BTC")

    def test_rejects_non_positive_stop_price(self):
        with self.assertRaises(StrategyError):
            _trade_intent(stop_price=Decimal("0"))

    def test_rejects_stop_price_as_float(self):
        with self.assertRaises(StrategyError):
            _trade_intent(stop_price=90.0)

    def test_rejects_conviction_out_of_range(self):
        with self.assertRaises(StrategyError):
            _trade_intent(conviction=Decimal("1.5"))

    def test_rejects_non_positive_limit_price(self):
        with self.assertRaises(StrategyError):
            _trade_intent(limit_price=Decimal("-1"))

    def test_rejects_non_positive_t1_price(self):
        with self.assertRaises(StrategyError):
            _trade_intent(t1_price=Decimal("0"))


class TestStrategyContext(_RealPaperEngineCase):
    def test_valid_construction(self):
        context = StrategyContext(
            universe=(Symbol("BTC"),), portfolio_snapshot=_portfolio_snapshot(),
            open_positions=(_position_snapshot(),), kill_switch_state=State.READY,
            market_data=self.market_data, evaluated_at_utc="2026-01-01T00:00:00+00:00",
        )
        self.assertEqual(context.universe, (Symbol("BTC"),))
        self.assertEqual(len(context.open_positions), 1)

    def test_rejects_non_symbol_in_universe(self):
        with self.assertRaises(StrategyError):
            StrategyContext(
                universe=("BTC",), portfolio_snapshot=_portfolio_snapshot(), open_positions=(),
                kill_switch_state=State.READY, market_data=self.market_data,
                evaluated_at_utc="2026-01-01T00:00:00+00:00",
            )

    def test_rejects_wrong_type_portfolio_snapshot(self):
        with self.assertRaises(StrategyError):
            StrategyContext(
                universe=(), portfolio_snapshot={"cash": 1}, open_positions=(),
                kill_switch_state=State.READY, market_data=self.market_data,
                evaluated_at_utc="2026-01-01T00:00:00+00:00",
            )

    def test_rejects_wrong_type_in_open_positions(self):
        with self.assertRaises(StrategyError):
            StrategyContext(
                universe=(), portfolio_snapshot=_portfolio_snapshot(), open_positions=("not a snapshot",),
                kill_switch_state=State.READY, market_data=self.market_data,
                evaluated_at_utc="2026-01-01T00:00:00+00:00",
            )

    def test_rejects_wrong_type_kill_switch_state(self):
        with self.assertRaises(StrategyError):
            StrategyContext(
                universe=(), portfolio_snapshot=_portfolio_snapshot(), open_positions=(),
                kill_switch_state="RUNNING", market_data=self.market_data,
                evaluated_at_utc="2026-01-01T00:00:00+00:00",
            )

    def test_rejects_wrong_type_market_data(self):
        with self.assertRaises(StrategyError):
            StrategyContext(
                universe=(), portfolio_snapshot=_portfolio_snapshot(), open_positions=(),
                kill_switch_state=State.READY, market_data="not a view",
                evaluated_at_utc="2026-01-01T00:00:00+00:00",
            )

    def test_rejects_empty_evaluated_at_utc(self):
        with self.assertRaises(StrategyError):
            StrategyContext(
                universe=(), portfolio_snapshot=_portfolio_snapshot(), open_positions=(),
                kill_switch_state=State.READY, market_data=self.market_data, evaluated_at_utc="",
            )


class TestStrategyInterface(_RealPaperEngineCase):
    def test_cannot_instantiate_the_abstract_base(self):
        with self.assertRaises(TypeError):
            Strategy()

    def test_a_subclass_missing_an_abstract_member_cannot_be_instantiated(self):
        class _Incomplete(Strategy):
            @property
            def name(self):
                return "incomplete"
            # generate_intents deliberately not implemented

        with self.assertRaises(TypeError):
            _Incomplete()

    def test_a_complete_stub_strategy_is_instantiable_and_callable(self):
        # A trivial, always-flat stub used only to prove the interface is
        # implementable and enforced -- not a trading strategy.
        class _NoOpStrategy(Strategy):
            @property
            def name(self):
                return "no-op"

            def generate_intents(self, context):
                return ()

        strategy = _NoOpStrategy()
        self.assertEqual(strategy.name, "no-op")
        context = StrategyContext(
            universe=(Symbol("BTC"),), portfolio_snapshot=_portfolio_snapshot(), open_positions=(),
            kill_switch_state=State.READY, market_data=self.market_data,
            evaluated_at_utc="2026-01-01T00:00:00+00:00",
        )
        self.assertEqual(strategy.generate_intents(context), ())

    def test_a_stub_strategy_can_return_a_trade_intent_built_from_context(self):
        class _EchoStrategy(Strategy):
            @property
            def name(self):
                return "echo"

            def generate_intents(self, context):
                return tuple(
                    _trade_intent(symbol=symbol) for symbol in context.universe
                )

        strategy = _EchoStrategy()
        context = StrategyContext(
            universe=(Symbol("BTC"), Symbol("ETH")), portfolio_snapshot=_portfolio_snapshot(),
            open_positions=(), kill_switch_state=State.READY, market_data=self.market_data,
            evaluated_at_utc="2026-01-01T00:00:00+00:00",
        )
        intents = strategy.generate_intents(context)
        self.assertEqual(len(intents), 2)
        self.assertEqual({i.symbol for i in intents}, {Symbol("BTC"), Symbol("ETH")})


if __name__ == "__main__":
    unittest.main()
