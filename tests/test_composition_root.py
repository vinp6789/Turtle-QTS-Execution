"""Construction-only tests for composition_root (Milestone 2).

These tests build an Engine and inspect the wired graph -- they never
call Engine.start()/stop(), never invoke a real network transport, and
never drive order_manager/position_manager/portfolio_manager/risk_manager
through any decision logic. That scope boundary is deliberate: this
package is a composition root, not a trading loop.

Fixture note: EngineConfig instances here are constructed directly via
its frozen dataclasses (config.EngineConfig et al.), not via
config.load_config() and a TOML file on disk -- config.load_config()'s
own loader already enforces environment/exchange/network against its
SUPPORTED_* sets, and this test module's job is to verify
composition_root's OWN defensive validation, which must also hold for a
directly-constructed EngineConfig (e.g. an in-process test double)
bypassing that loader entirely.
"""

import os
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
from event_store import EventStore, EventStoreLockError
from exchange_adapter import MockExchangeAdapter
from hyperliquid_adapter import HyperliquidAdapter
from hyperliquid_adapter.transport import MAINNET_BASE_URL, TESTNET_BASE_URL
from risk_manager import RiskManagerLimits

from composition_root import (
    CompositionRootTypeError,
    DeploymentSettings,
    MissingDeploymentSettingError,
    UnsupportedEnvironmentError,
    UnsupportedExchangeError,
    build_engine,
)

# A well-known, publicly-documented test-only private key (Hardhat/Anvil's
# default account #0) -- never used to hold real funds, safe to embed in a
# test fixture. Only exercised by eth-account's offline key parsing during
# HyperliquidWalletSigner construction; no network call is made.
_TEST_WALLET_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"

_SIGNING_KEY_REF = "hyperliquid_signing_key_v1"
_WALLET_KEY_REF = "hyperliquid_wallet_key_v1"
_ACCOUNT_ADDRESS = "0x127643A7eaa55Cd7157224737cB0146AD1Cc1269"


def _engine_config(*, environment="paper", network="testnet", wallet_key_ref=None):
    return EngineConfig(
        environment=environment,
        exchange=ExchangeConfig(name="hyperliquid", network=network),
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
            signing_key_ref=_SIGNING_KEY_REF,
            telegram_bot_token_ref="telegram_bot_token_v1",
            wallet_key_ref=wallet_key_ref,
        ),
        telegram=TelegramConfig(enabled=False, chat_id="123"),
        logging=LoggingConfig(level="INFO", directory="/tmp/log"),
    )


def _risk_limits():
    return RiskManagerLimits(
        max_leverage=Decimal("5"),
        min_liquidation_buffer_pct=Decimal("0.1"),
        max_funding_rate_abs=Decimal("0.01"),
        max_correlated_positions=3,
        max_stale_data_seconds=30,
    )


def _env(**overrides):
    base = {
        f"TURTLE_SECRET_{_SIGNING_KEY_REF.upper()}": "signing-secret-material",
        f"TURTLE_SECRET_{_WALLET_KEY_REF.upper()}": _TEST_WALLET_PRIVATE_KEY,
    }
    base.update(overrides)
    return base


class _TempStorePath(unittest.TestCase):
    """Gives every test its own EventStore file path and guarantees the
    lock is released even if the test body raises."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self._stores_to_close = []
        self.addCleanup(self._close_stores)

    def _close_stores(self):
        for store in self._stores_to_close:
            try:
                store.close()
            except Exception:
                pass

    def _new_store_path(self, name="events.log"):
        return Path(self._tmpdir.name) / name

    def _track(self, engine):
        self._stores_to_close.append(engine.event_store)
        return engine


class TestSuccessfulWiring(_TempStorePath):
    def test_paper_engine_wires_every_component(self):
        engine = self._track(build_engine(
            config=_engine_config(environment="paper"),
            deployment=DeploymentSettings(engine_version="1.0.0"),
            risk_limits=_risk_limits(),
            event_store_path=self._new_store_path(),
            env=_env(),
        ))
        self.assertIsInstance(engine.event_store, EventStore)
        self.assertIsInstance(engine.adapter, MockExchangeAdapter)
        self.assertIsNone(engine.wallet_signer)
        self.assertIsNotNone(engine.execution_state_machine)
        self.assertIsNotNone(engine.order_manager)
        self.assertIsNotNone(engine.position_manager)
        self.assertIsNotNone(engine.portfolio_manager)
        self.assertIsNotNone(engine.risk_manager)
        self.assertFalse(engine.is_started)

    def test_live_engine_wires_every_component(self):
        engine = self._track(build_engine(
            config=_engine_config(environment="live", network="testnet", wallet_key_ref=_WALLET_KEY_REF),
            deployment=DeploymentSettings(engine_version="1.0.0", account_address=_ACCOUNT_ADDRESS),
            risk_limits=_risk_limits(),
            event_store_path=self._new_store_path(),
            env=_env(),
        ))
        self.assertIsInstance(engine.adapter, HyperliquidAdapter)
        self.assertIsNotNone(engine.wallet_signer)
        self.assertEqual(engine.wallet_signer.wallet_address, engine.adapter.wallet_address)


class TestSingletonEventStore(_TempStorePath):
    def test_paper_managers_share_the_same_event_store_instance(self):
        engine = self._track(build_engine(
            config=_engine_config(environment="paper"),
            deployment=DeploymentSettings(engine_version="1.0.0"),
            risk_limits=_risk_limits(),
            event_store_path=self._new_store_path(),
            env=_env(),
        ))
        store = engine.event_store
        # White-box identity checks: every component that durably persists
        # state must hold a reference to the SAME EventStore object build_
        # engine opened, never a second one of its own.
        self.assertIs(engine.execution_state_machine._store, store)
        self.assertIs(engine.order_manager._store, store)
        self.assertIs(engine.position_manager._store, store)
        self.assertIs(engine.portfolio_manager._store, store)

    def test_live_adapter_and_managers_share_the_same_event_store_instance(self):
        engine = self._track(build_engine(
            config=_engine_config(environment="live", network="testnet", wallet_key_ref=_WALLET_KEY_REF),
            deployment=DeploymentSettings(engine_version="1.0.0", account_address=_ACCOUNT_ADDRESS),
            risk_limits=_risk_limits(),
            event_store_path=self._new_store_path(),
            env=_env(),
        ))
        store = engine.event_store
        self.assertIs(engine.execution_state_machine._store, store)
        self.assertIs(engine.order_manager._store, store)
        self.assertIs(engine.position_manager._store, store)
        self.assertIs(engine.portfolio_manager._store, store)
        # HyperliquidAdapter's own durable order-id mapping (mapping.py,
        # M1) must be backed by the SAME store, not a second one -- this
        # is exactly the wiring invariant adapter.py's module docstring
        # (INV-16) requires callers to honor.
        self.assertIs(engine.adapter._mapping._store, store)

    def test_a_second_event_store_on_the_same_path_fails_loudly(self):
        path = self._new_store_path()
        engine = self._track(build_engine(
            config=_engine_config(environment="paper"),
            deployment=DeploymentSettings(engine_version="1.0.0"),
            risk_limits=_risk_limits(),
            event_store_path=path,
            env=_env(),
        ))
        # Proves exclusivity structurally (an OS-level lock), not just by
        # convention: nothing -- including a second build_engine() call
        # aimed at the same path -- can silently open a competing store
        # while this Engine is alive.
        with self.assertRaises(EventStoreLockError):
            EventStore(path)


class TestNetworkConsistency(_TempStorePath):
    def test_testnet_config_selects_testnet_base_url_and_signer(self):
        engine = self._track(build_engine(
            config=_engine_config(environment="live", network="testnet", wallet_key_ref=_WALLET_KEY_REF),
            deployment=DeploymentSettings(engine_version="1.0.0", account_address=_ACCOUNT_ADDRESS),
            risk_limits=_risk_limits(),
            event_store_path=self._new_store_path(),
            env=_env(),
        ))
        self.assertEqual(engine.adapter._base_url, TESTNET_BASE_URL)
        self.assertFalse(engine.wallet_signer.is_mainnet)

    def test_mainnet_config_selects_mainnet_base_url_and_signer(self):
        engine = self._track(build_engine(
            config=_engine_config(environment="live", network="mainnet", wallet_key_ref=_WALLET_KEY_REF),
            deployment=DeploymentSettings(engine_version="1.0.0", account_address=_ACCOUNT_ADDRESS),
            risk_limits=_risk_limits(),
            event_store_path=self._new_store_path(),
            env=_env(),
        ))
        self.assertEqual(engine.adapter._base_url, MAINNET_BASE_URL)
        self.assertTrue(engine.wallet_signer.is_mainnet)

    def test_live_without_wallet_key_ref_has_no_signer_but_still_wires(self):
        # A live adapter with no wallet_signer is legal (HyperliquidAdapter
        # fails closed on mutations, per its own _require_signer()) -- the
        # composition root must not invent one.
        engine = self._track(build_engine(
            config=_engine_config(environment="live", network="testnet", wallet_key_ref=None),
            deployment=DeploymentSettings(engine_version="1.0.0", account_address=_ACCOUNT_ADDRESS),
            risk_limits=_risk_limits(),
            event_store_path=self._new_store_path(),
            env=_env(),
        ))
        self.assertIsNone(engine.wallet_signer)
        self.assertIsInstance(engine.adapter, HyperliquidAdapter)


class TestPaperVsLiveAdapterSelection(_TempStorePath):
    def test_environment_paper_never_constructs_a_hyperliquid_adapter(self):
        engine = self._track(build_engine(
            config=_engine_config(environment="paper"),
            deployment=DeploymentSettings(engine_version="1.0.0"),
            risk_limits=_risk_limits(),
            event_store_path=self._new_store_path(),
            env=_env(),
        ))
        self.assertNotIsInstance(engine.adapter, HyperliquidAdapter)
        self.assertIsInstance(engine.adapter, MockExchangeAdapter)

    def test_environment_live_never_constructs_a_mock_adapter(self):
        engine = self._track(build_engine(
            config=_engine_config(environment="live", network="testnet", wallet_key_ref=_WALLET_KEY_REF),
            deployment=DeploymentSettings(engine_version="1.0.0", account_address=_ACCOUNT_ADDRESS),
            risk_limits=_risk_limits(),
            event_store_path=self._new_store_path(),
            env=_env(),
        ))
        self.assertNotIsInstance(engine.adapter, MockExchangeAdapter)
        self.assertIsInstance(engine.adapter, HyperliquidAdapter)


class TestMissingConfigurationFailsClearly(_TempStorePath):
    def test_live_without_account_address_raises_missing_deployment_setting(self):
        with self.assertRaises(MissingDeploymentSettingError):
            build_engine(
                config=_engine_config(environment="live", network="testnet", wallet_key_ref=_WALLET_KEY_REF),
                deployment=DeploymentSettings(engine_version="1.0.0", account_address=None),
                risk_limits=_risk_limits(),
                event_store_path=self._new_store_path(),
                env=_env(),
            )

    def test_paper_without_account_address_wires_fine(self):
        # account_address is only required for 'live' -- paper mode has no
        # venue account at all.
        engine = self._track(build_engine(
            config=_engine_config(environment="paper"),
            deployment=DeploymentSettings(engine_version="1.0.0", account_address=None),
            risk_limits=_risk_limits(),
            event_store_path=self._new_store_path(),
            env=_env(),
        ))
        self.assertIsInstance(engine.adapter, MockExchangeAdapter)

    def test_unsupported_environment_raises_clear_error(self):
        with self.assertRaises(UnsupportedEnvironmentError):
            build_engine(
                config=_engine_config(environment="backtest"),
                deployment=DeploymentSettings(engine_version="1.0.0"),
                risk_limits=_risk_limits(),
                event_store_path=self._new_store_path(),
                env=_env(),
            )

    def test_unsupported_exchange_raises_clear_error(self):
        config = _engine_config(environment="paper")
        config = EngineConfig(
            environment=config.environment,
            exchange=ExchangeConfig(name="lighter", network=config.exchange.network),
            universe=config.universe, risk=config.risk, operational=config.operational,
            secrets=config.secrets, telegram=config.telegram, logging=config.logging,
        )
        with self.assertRaises(UnsupportedExchangeError):
            build_engine(
                config=config,
                deployment=DeploymentSettings(engine_version="1.0.0"),
                risk_limits=_risk_limits(),
                event_store_path=self._new_store_path(),
                env=_env(),
            )

    def test_wrong_type_config_raises_clear_type_error(self):
        with self.assertRaises(CompositionRootTypeError):
            build_engine(
                config={"environment": "paper"},
                deployment=DeploymentSettings(engine_version="1.0.0"),
                risk_limits=_risk_limits(),
                event_store_path=self._new_store_path(),
                env=_env(),
            )

    def test_wrong_type_risk_limits_raises_clear_type_error(self):
        with self.assertRaises(CompositionRootTypeError):
            build_engine(
                config=_engine_config(environment="paper"),
                deployment=DeploymentSettings(engine_version="1.0.0"),
                risk_limits={"max_leverage": 5},
                event_store_path=self._new_store_path(),
                env=_env(),
            )

    def test_missing_signing_secret_raises_secrets_startup_error(self):
        # Not this package's own error type -- SigningBoundary's, since the
        # composition root correctly delegates secret resolution to Module
        # 2 rather than re-implementing that check.
        from secrets_boundary import SecretsStartupError

        with self.assertRaises(SecretsStartupError):
            build_engine(
                config=_engine_config(environment="paper"),
                deployment=DeploymentSettings(engine_version="1.0.0"),
                risk_limits=_risk_limits(),
                event_store_path=self._new_store_path(),
                env={},  # no TURTLE_SECRET_* set at all
            )


if __name__ == "__main__":
    unittest.main()
