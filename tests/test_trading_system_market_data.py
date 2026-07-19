"""Verification tests for trading_system.market_data (Milestone 5).

Builds a genuine paper-mode Engine via composition_root (MockExchangeAdapter,
in-memory, no network) and verifies MarketDataView is a pure, stateless
delegation to engine.adapter -- no caching (two calls after changing the
underlying value must both reach the adapter fresh), and no path to
mutate anything (order_manager/risk_manager are never touched).
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
from exchange_adapter import FundingRate, MarkPrice, Symbol
from risk_manager import RiskManagerLimits

from composition_root import DeploymentSettings, build_engine
from trading_system.market_data import MarketDataView

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


class TestMarketDataView(_RealPaperEngineCase):
    def test_rejects_a_non_engine(self):
        with self.assertRaises(TypeError):
            MarketDataView(engine="not an engine")

    def test_get_mark_price_delegates_to_the_adapter(self):
        self.engine.adapter.set_mark_price(MarkPrice(symbol=Symbol("BTC"), price=Decimal("50000"), timestamp_utc="t"))
        view = MarketDataView(self.engine)
        result = view.get_mark_price(Symbol("BTC"))
        self.assertEqual(result.price, Decimal("50000"))

    def test_get_mark_price_reflects_a_changed_value_with_no_caching(self):
        view = MarketDataView(self.engine)
        self.engine.adapter.set_mark_price(MarkPrice(symbol=Symbol("BTC"), price=Decimal("100"), timestamp_utc="t"))
        first = view.get_mark_price(Symbol("BTC"))
        self.engine.adapter.set_mark_price(MarkPrice(symbol=Symbol("BTC"), price=Decimal("200"), timestamp_utc="t2"))
        second = view.get_mark_price(Symbol("BTC"))
        self.assertEqual(first.price, Decimal("100"))
        self.assertEqual(second.price, Decimal("200"))  # no memoized value from the first call

    def test_get_funding_rate_delegates_to_the_adapter(self):
        self.engine.adapter.set_funding_rate(
            FundingRate(symbol=Symbol("BTC"), rate=Decimal("0.0001"), next_funding_time_utc="t", timestamp_utc="t")
        )
        view = MarketDataView(self.engine)
        result = view.get_funding_rate(Symbol("BTC"))
        self.assertEqual(result.rate, Decimal("0.0001"))

    def test_get_mark_price_propagates_the_adapters_own_error_when_unset(self):
        view = MarketDataView(self.engine)
        with self.assertRaises(Exception):
            view.get_mark_price(Symbol("ETH"))  # never set -- MockExchangeAdapter itself raises

    def test_exposes_no_mutation_path(self):
        # Structural guard: this facade must never grow a method capable
        # of placing/amending/cancelling an order or evaluating risk.
        view = MarketDataView(self.engine)
        forbidden = {"place_order", "amend_order", "cancel_order", "cancel_all", "evaluate", "order_manager", "risk_manager"}
        exposed = set(dir(view))
        self.assertEqual(exposed & forbidden, set())


if __name__ == "__main__":
    unittest.main()
