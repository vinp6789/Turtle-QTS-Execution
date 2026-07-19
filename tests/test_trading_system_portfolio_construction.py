"""Verification tests for trading_system.portfolio_construction (Milestone 6).

Builds a genuine paper-mode Engine via composition_root (MockExchangeAdapter,
in-memory, no network) so risk_manager, capabilities, and market data are
all real, not faked -- only the ordering-verification test subclasses
RiskManager to record call order without changing its behavior.
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
from exchange_adapter import FundingRate, MarkPrice, OrderSide, OrderType, Symbol, TimeInForce
from execution_state_machine import State
from portfolio_manager import PortfolioSnapshot
from risk_manager import CorrelationInfo, RiskManagerLimits

from composition_root import DeploymentSettings, build_engine
from trading_system.market_data import MarketDataView
from trading_system.portfolio_construction import (
    PortfolioConstructionError,
    construct_trade_requests,
)
from trading_system.strategy import StrategyContext, TradeIntent

_SIGNING_KEY_REF = "hyperliquid_signing_key_v1"
_NOW = "2026-01-01T00:00:00+00:00"


def _engine_config():
    return EngineConfig(
        environment="paper",
        exchange=ExchangeConfig(name="hyperliquid", network="testnet"),
        universe=UniverseConfig(symbols=("BTC", "ETH")),
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
    fields = dict(
        risk_pct_per_trade=0.02, max_positions=3, sizing_mode="fixed", heat_cap=0.05, ruin_threshold=0.6,
    )
    fields.update(overrides)
    return RiskProfileParams(**fields)


def _portfolio_snapshot(**overrides):
    fields = dict(
        available_cash=Decimal("100000"), reserved_margin=Decimal("0"), used_margin=Decimal("0"),
        unrealized_pnl=Decimal("0"), realized_pnl_cumulative=Decimal("0"), funding_cumulative=Decimal("0"),
        fees_cumulative=Decimal("0"), deposits_cumulative=Decimal("100000"), withdrawals_cumulative=Decimal("0"),
        exposure=Decimal("0"), heat=Decimal("0"), open_position_ids=(), updated_at_utc=_NOW,
    )
    fields.update(overrides)
    return PortfolioSnapshot(**fields)


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
        self.engine.start()
        self.engine.adapter.set_mark_price(MarkPrice(symbol=Symbol("BTC"), price=Decimal("100"), timestamp_utc=_NOW))
        self.engine.adapter.set_mark_price(MarkPrice(symbol=Symbol("ETH"), price=Decimal("50"), timestamp_utc=_NOW))
        self.engine.adapter.set_funding_rate(
            FundingRate(symbol=Symbol("BTC"), rate=Decimal("0.0001"), next_funding_time_utc=_NOW, timestamp_utc=_NOW)
        )
        self.engine.adapter.set_funding_rate(
            FundingRate(symbol=Symbol("ETH"), rate=Decimal("0.0001"), next_funding_time_utc=_NOW, timestamp_utc=_NOW)
        )
        self.market_data = MarketDataView(self.engine)

    def _context(self, universe=(Symbol("BTC"), Symbol("ETH")), portfolio_snapshot=None, open_positions=()):
        return StrategyContext(
            universe=universe, portfolio_snapshot=portfolio_snapshot or _portfolio_snapshot(),
            open_positions=open_positions, kill_switch_state=State.READY,
            market_data=self.market_data, evaluated_at_utc=_NOW,
        )

    def _construct(self, intents, context=None, **overrides):
        kwargs = dict(
            risk_manager=self.engine.risk_manager, risk_profile=_risk_profile(),
            capabilities=self.engine.adapter.capabilities,
            correlation_info=CorrelationInfo(entries=(), as_of_utc=_NOW),
            maintenance_margin_rate=Decimal("0.005"), target_leverage=Decimal("1"),
        )
        kwargs.update(overrides)
        return construct_trade_requests(intents, context or self._context(), **kwargs)


class TestApprovalAndRejection(_RealPaperEngineCase):
    def test_a_well_formed_intent_is_approved(self):
        result = self._construct((_intent(),))
        self.assertEqual(len(result.approved), 1)
        self.assertEqual(result.rejected, ())
        self.assertEqual(result.skipped, ())
        self.assertEqual(result.approved[0].symbol, Symbol("BTC"))

    def test_insufficient_margin_is_rejected_with_a_real_risk_decision(self):
        # equity (deposits_cumulative-derived) stays large so sizing computes
        # a realistic risk_amount/quantity; available_cash is independently
        # tiny -- simulating most equity being locked up elsewhere, so the
        # resulting margin requirement genuinely exceeds free cash.
        poor_snapshot = _portfolio_snapshot(available_cash=Decimal("10"))
        result = self._construct((_intent(),), context=self._context(portfolio_snapshot=poor_snapshot))
        self.assertEqual(result.approved, ())
        self.assertEqual(len(result.rejected), 1)
        rejected = result.rejected[0]
        self.assertEqual(rejected.intent.symbol, Symbol("BTC"))
        from risk_manager import ReasonCode

        self.assertIn(ReasonCode.INSUFFICIENT_MARGIN, rejected.decision.reason_codes)


class TestUniverseFiltering(_RealPaperEngineCase):
    def test_intent_outside_universe_is_skipped_not_evaluated(self):
        result = self._construct(
            (_intent(symbol=Symbol("SOL"), limit_price=Decimal("10")),),
            context=self._context(universe=(Symbol("BTC"), Symbol("ETH"))),
        )
        self.assertEqual(result.approved, ())
        self.assertEqual(result.rejected, ())
        self.assertEqual(len(result.skipped), 1)
        self.assertIn("universe", result.skipped[0].reason)


class TestDeduplication(_RealPaperEngineCase):
    def test_higher_conviction_intent_wins_for_the_same_symbol(self):
        low = _intent(conviction=Decimal("0.2"))
        high = _intent(conviction=Decimal("0.9"))
        result = self._construct((low, high))
        self.assertEqual(len(result.approved) + len(result.rejected), 1)  # only one reached RiskManager
        self.assertEqual(len(result.skipped), 1)
        self.assertIs(result.skipped[0].intent, low)
        self.assertIn("duplicate", result.skipped[0].reason)

    def test_missing_conviction_is_lowest_priority_in_deduplication(self):
        no_conviction = _intent()  # conviction=None
        scored = _intent(conviction=Decimal("0.1"))
        result = self._construct((no_conviction, scored))
        self.assertEqual(len(result.skipped), 1)
        self.assertIs(result.skipped[0].intent, no_conviction)


class TestSizingFailureIsolation(_RealPaperEngineCase):
    def test_one_bad_intent_does_not_abort_the_batch(self):
        conviction_profile = _risk_profile(sizing_mode="conviction_weighted")
        bad = _intent(symbol=Symbol("BTC"), conviction=None)   # will fail sizing (conviction_weighted needs it)
        good = _intent(symbol=Symbol("ETH"), conviction=Decimal("0.5"), limit_price=Decimal("50"), stop_price=Decimal("45"))
        result = self._construct((bad, good), risk_profile=conviction_profile)
        self.assertEqual(len(result.approved), 1)
        self.assertEqual(result.approved[0].symbol, Symbol("ETH"))
        self.assertEqual(len(result.skipped), 1)
        self.assertIs(result.skipped[0].intent, bad)
        self.assertIn("sizing failed", result.skipped[0].reason)


class TestPrioritizationOrder(_RealPaperEngineCase):
    def test_survivors_are_evaluated_in_descending_conviction_order(self):
        call_order = []
        engine = self.engine

        class _RecordingRiskManager(engine.risk_manager.__class__):
            def evaluate(self, **kwargs):
                call_order.append(kwargs["trade_request"].symbol)
                return super().evaluate(**kwargs)

        recording_risk_manager = _RecordingRiskManager(engine.risk_manager.limits)
        low = _intent(symbol=Symbol("BTC"), conviction=Decimal("0.1"))
        high = _intent(symbol=Symbol("ETH"), conviction=Decimal("0.9"), limit_price=Decimal("50"), stop_price=Decimal("45"))
        self._construct((low, high), risk_manager=recording_risk_manager)
        self.assertEqual(call_order, [Symbol("ETH"), Symbol("BTC")])  # higher conviction evaluated first


class TestInputValidation(_RealPaperEngineCase):
    def test_rejects_wrong_type_context(self):
        with self.assertRaises(PortfolioConstructionError):
            construct_trade_requests(
                (_intent(),), "not a context", risk_manager=self.engine.risk_manager,
                risk_profile=_risk_profile(), capabilities=self.engine.adapter.capabilities,
                correlation_info=CorrelationInfo(entries=(), as_of_utc=_NOW),
                maintenance_margin_rate=Decimal("0.005"),
            )

    def test_rejects_wrong_type_risk_manager(self):
        with self.assertRaises(PortfolioConstructionError):
            self._construct((_intent(),), risk_manager="not a risk manager")

    def test_rejects_wrong_type_intents(self):
        with self.assertRaises(PortfolioConstructionError):
            self._construct(("not an intent",))

    def test_rejects_wrong_type_correlation_info(self):
        with self.assertRaises(PortfolioConstructionError):
            self._construct((_intent(),), correlation_info="not correlation info")


if __name__ == "__main__":
    unittest.main()
