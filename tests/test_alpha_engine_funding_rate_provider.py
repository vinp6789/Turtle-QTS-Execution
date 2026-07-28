"""Verification tests for the Funding Rate Provider (Alpha Engine
Milestone 1.1).

Uses the same real-engine fixture pattern already established in
tests/test_trading_system_strategy.py: a paper-mode composition_root.
Engine backed by MockExchangeAdapter, wrapped in the real
trading_system.market_data.MarketDataView. MockExchangeAdapter's own
test-only helpers (set_funding_rate, fail_next) drive every scenario --
no new test double is introduced for the adapter itself.
"""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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
from exchange_adapter import ExchangeAdapterError, ExchangeConnectionError, FundingRate, Symbol
from risk_manager import RiskManagerLimits

from composition_root import DeploymentSettings, build_engine
from trading_system.market_data import MarketDataView

from alpha_engine.data_sources import DataSourceError, FundingRateProvider, FundingRateReading

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


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class _RealPaperEngineCase(unittest.TestCase):
    """Mirrors tests/test_trading_system_strategy.py's fixture exactly --
    a real paper-mode Engine, connected, wrapped in a real
    MarketDataView. self.adapter is the underlying MockExchangeAdapter,
    used only for its documented test-only helpers (set_funding_rate,
    fail_next)."""

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
        self.adapter = self.engine.adapter
        self.market_data = MarketDataView(self.engine)
        self.symbol = Symbol("BTC")


class TestConstructorValidation(unittest.TestCase):
    def test_rejects_non_market_data_view(self):
        with self.assertRaises(DataSourceError):
            FundingRateProvider(market_data="not-a-market-data-view")

    def test_rejects_non_positive_max_staleness(self):
        class _FakeMarketData(MarketDataView):
            def __init__(self):
                pass  # bypass real constructor -- only used to satisfy isinstance()

        with self.assertRaises(DataSourceError):
            FundingRateProvider(market_data=_FakeMarketData(), max_staleness_seconds=0)
        with self.assertRaises(DataSourceError):
            FundingRateProvider(market_data=_FakeMarketData(), max_staleness_seconds=-5)


class TestFundingRateReadingValidation(unittest.TestCase):
    def test_available_reading_requires_value_and_observed_at(self):
        with self.assertRaises(DataSourceError):
            FundingRateReading(
                symbol=Symbol("BTC"), fetched_at_utc="2026-01-01T00:00:00+00:00",
                available=True, value=None, observed_at_utc=None,
            )

    def test_unavailable_reading_must_not_carry_a_value(self):
        with self.assertRaises(DataSourceError):
            FundingRateReading(
                symbol=Symbol("BTC"), fetched_at_utc="2026-01-01T00:00:00+00:00",
                available=False, value=Decimal("0.0001"), reason="whatever",
            )

    def test_unavailable_reading_requires_a_reason(self):
        with self.assertRaises(DataSourceError):
            FundingRateReading(
                symbol=Symbol("BTC"), fetched_at_utc="2026-01-01T00:00:00+00:00",
                available=False, reason=None,
            )


class TestFetchSuccess(_RealPaperEngineCase):
    def test_fetch_returns_available_reading_for_fresh_data(self):
        now = datetime.now(timezone.utc)
        self.adapter.set_funding_rate(FundingRate(
            symbol=self.symbol, rate=Decimal("0.0001"),
            next_funding_time_utc=_iso(now + timedelta(hours=1)),
            timestamp_utc=_iso(now),
        ))
        provider = FundingRateProvider(self.market_data, clock=lambda: _iso(now))

        reading = provider.fetch(self.symbol)

        self.assertTrue(reading.available)
        self.assertEqual(reading.value, Decimal("0.0001"))
        self.assertEqual(reading.symbol, self.symbol)
        self.assertIsNone(reading.reason)
        self.assertIsNotNone(reading.observed_at_utc)

    def test_fetch_never_raises_type_error_for_valid_input(self):
        now = datetime.now(timezone.utc)
        self.adapter.set_funding_rate(FundingRate(
            symbol=self.symbol, rate=Decimal("0.0002"),
            next_funding_time_utc=_iso(now + timedelta(hours=1)), timestamp_utc=_iso(now),
        ))
        provider = FundingRateProvider(self.market_data)
        try:
            provider.fetch(self.symbol)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"fetch() raised unexpectedly for valid, fresh data: {exc!r}")


class TestFetchAdapterFailure(_RealPaperEngineCase):
    def test_no_funding_rate_seeded_degrades_to_unavailable(self):
        # No set_funding_rate() call -- adapter raises ExchangeAdapterError internally.
        provider = FundingRateProvider(self.market_data)
        reading = provider.fetch(self.symbol)
        self.assertFalse(reading.available)
        self.assertIsNone(reading.value)
        self.assertIn("ExchangeAdapterError", reading.reason)

    def test_injected_connection_error_degrades_to_unavailable(self):
        self.adapter.fail_next("get_funding_rate", ExchangeConnectionError("simulated outage"))
        provider = FundingRateProvider(self.market_data)
        reading = provider.fetch(self.symbol)
        self.assertFalse(reading.available)
        self.assertIsNone(reading.value)
        self.assertIn("ExchangeConnectionError", reading.reason)

    def test_fetch_never_raises_for_adapter_failure(self):
        self.adapter.fail_next("get_funding_rate", ExchangeConnectionError("simulated outage"))
        provider = FundingRateProvider(self.market_data)
        try:
            reading = provider.fetch(self.symbol)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"fetch() must never raise for a data-source failure, raised {exc!r}")
        self.assertFalse(reading.available)


class TestFetchStaleness(_RealPaperEngineCase):
    def test_reading_older_than_max_staleness_is_unavailable(self):
        now = datetime.now(timezone.utc)
        observed_at = now - timedelta(seconds=400)
        self.adapter.set_funding_rate(FundingRate(
            symbol=self.symbol, rate=Decimal("0.0001"),
            next_funding_time_utc=_iso(now + timedelta(hours=1)), timestamp_utc=_iso(observed_at),
        ))
        provider = FundingRateProvider(self.market_data, max_staleness_seconds=300.0, clock=lambda: _iso(now))

        reading = provider.fetch(self.symbol)

        self.assertFalse(reading.available)
        self.assertIsNone(reading.value)
        self.assertIn("stale", reading.reason)

    def test_reading_within_max_staleness_is_available(self):
        now = datetime.now(timezone.utc)
        observed_at = now - timedelta(seconds=200)
        self.adapter.set_funding_rate(FundingRate(
            symbol=self.symbol, rate=Decimal("0.0001"),
            next_funding_time_utc=_iso(now + timedelta(hours=1)), timestamp_utc=_iso(observed_at),
        ))
        provider = FundingRateProvider(self.market_data, max_staleness_seconds=300.0, clock=lambda: _iso(now))

        reading = provider.fetch(self.symbol)

        self.assertTrue(reading.available)
        self.assertEqual(reading.value, Decimal("0.0001"))

    def test_reading_exactly_at_staleness_boundary_is_available(self):
        now = datetime.now(timezone.utc)
        observed_at = now - timedelta(seconds=300)
        self.adapter.set_funding_rate(FundingRate(
            symbol=self.symbol, rate=Decimal("0.0001"),
            next_funding_time_utc=_iso(now + timedelta(hours=1)), timestamp_utc=_iso(observed_at),
        ))
        provider = FundingRateProvider(self.market_data, max_staleness_seconds=300.0, clock=lambda: _iso(now))

        reading = provider.fetch(self.symbol)

        self.assertTrue(reading.available)  # age == max_staleness_seconds, not > it

    def test_future_dated_reading_is_unavailable(self):
        now = datetime.now(timezone.utc)
        observed_at = now + timedelta(seconds=60)  # clock-skew scenario
        self.adapter.set_funding_rate(FundingRate(
            symbol=self.symbol, rate=Decimal("0.0001"),
            next_funding_time_utc=_iso(now + timedelta(hours=2)), timestamp_utc=_iso(observed_at),
        ))
        provider = FundingRateProvider(self.market_data, clock=lambda: _iso(now))

        reading = provider.fetch(self.symbol)

        self.assertFalse(reading.available)
        self.assertIsNone(reading.value)
        self.assertIn("future", reading.reason)


class TestFetchInputValidation(_RealPaperEngineCase):
    def test_fetch_rejects_non_symbol_argument(self):
        provider = FundingRateProvider(self.market_data)
        with self.assertRaises(DataSourceError):
            provider.fetch("BTC")  # str, not Symbol


class TestProviderIsStateless(_RealPaperEngineCase):
    """No caching: two consecutive fetch() calls each hit the adapter
    fresh -- a changed underlying value is observed immediately, and a
    failure on one call does not poison subsequent calls."""

    def test_second_fetch_reflects_a_changed_underlying_rate(self):
        now = datetime.now(timezone.utc)
        provider = FundingRateProvider(self.market_data, clock=lambda: _iso(now))

        self.adapter.set_funding_rate(FundingRate(
            symbol=self.symbol, rate=Decimal("0.0001"),
            next_funding_time_utc=_iso(now + timedelta(hours=1)), timestamp_utc=_iso(now),
        ))
        first = provider.fetch(self.symbol)
        self.assertEqual(first.value, Decimal("0.0001"))

        self.adapter.set_funding_rate(FundingRate(
            symbol=self.symbol, rate=Decimal("0.0009"),
            next_funding_time_utc=_iso(now + timedelta(hours=1)), timestamp_utc=_iso(now),
        ))
        second = provider.fetch(self.symbol)
        self.assertEqual(second.value, Decimal("0.0009"))

    def test_a_failed_fetch_does_not_affect_the_next_successful_fetch(self):
        now = datetime.now(timezone.utc)
        provider = FundingRateProvider(self.market_data, clock=lambda: _iso(now))

        self.adapter.fail_next("get_funding_rate", ExchangeAdapterError("transient"))
        failed = provider.fetch(self.symbol)
        self.assertFalse(failed.available)

        self.adapter.set_funding_rate(FundingRate(
            symbol=self.symbol, rate=Decimal("0.0003"),
            next_funding_time_utc=_iso(now + timedelta(hours=1)), timestamp_utc=_iso(now),
        ))
        recovered = provider.fetch(self.symbol)
        self.assertTrue(recovered.available)
        self.assertEqual(recovered.value, Decimal("0.0003"))


if __name__ == "__main__":
    unittest.main()
