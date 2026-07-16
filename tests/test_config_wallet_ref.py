"""Tests for the optional secrets.wallet_key_ref field (ADR-20/ADR-21).

New test file only -- tests/test_config.py (the frozen Module 1 test file)
is not modified. This file is self-contained and duplicates only the
minimal TOML fixture needed, so it does not depend on test_config.py.
"""

import tempfile
import unittest
from pathlib import Path

from config import ConfigValidationError, load_config

VALID_TOML = """
[environment]
mode = "paper"

[exchange]
name = "hyperliquid"
network = "testnet"

[universe]
symbols = ["BTC", "ETH", "SOL"]

[risk]
profile = "BALANCED"
max_daily_loss_pct = 0.05
max_drawdown_from_peak_pct = 0.20
auto_flatten_enabled = false
auto_flatten_confirmation_seconds = 60

[risk.profiles.BALANCED]
risk_pct_per_trade = 0.010
max_positions = 3
sizing_mode = "fixed"
heat_cap = 0.05
ruin_threshold = 0.60

[operational]
max_retries = 5
retry_base_delay_seconds = 0.5
retry_max_delay_seconds = 30.0
clock_drift_tolerance_ms = 250
data_staleness_price_ms = 5000
data_staleness_orderbook_ms = 3000
data_staleness_position_ms = 10000

[secrets]
signing_key_ref = "hyperliquid_signing_key_v1"
telegram_bot_token_ref = "telegram_bot_token_v1"
{wallet_key_line}

[telegram]
enabled = false
chat_id = ""

[logging]
level = "INFO"
directory = "/var/log/turtle_execution_engine"
"""


def _write(content: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False)
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


class WalletKeyRefAbsent(unittest.TestCase):
    def test_absent_wallet_key_ref_defaults_to_none(self):
        path = _write(VALID_TOML.format(wallet_key_line=""))
        try:
            config = load_config(path, env={})
            self.assertIsNone(config.secrets.wallet_key_ref)
        finally:
            path.unlink()

    def test_existing_two_refs_unaffected_by_absence(self):
        path = _write(VALID_TOML.format(wallet_key_line=""))
        try:
            config = load_config(path, env={})
            self.assertEqual(config.secrets.signing_key_ref, "hyperliquid_signing_key_v1")
            self.assertEqual(config.secrets.telegram_bot_token_ref, "telegram_bot_token_v1")
        finally:
            path.unlink()


class WalletKeyRefPresent(unittest.TestCase):
    def test_valid_wallet_key_ref_is_loaded(self):
        path = _write(VALID_TOML.format(wallet_key_line='wallet_key_ref = "hyperliquid_wallet_key_v1"'))
        try:
            config = load_config(path, env={})
            self.assertEqual(config.secrets.wallet_key_ref, "hyperliquid_wallet_key_v1")
        finally:
            path.unlink()

    def test_empty_wallet_key_ref_is_rejected(self):
        path = _write(VALID_TOML.format(wallet_key_line='wallet_key_ref = ""'))
        try:
            with self.assertRaises(ConfigValidationError) as ctx:
                load_config(path, env={})
            self.assertTrue(any("wallet_key_ref" in issue for issue in ctx.exception.issues))
        finally:
            path.unlink()

    def test_whitespace_only_wallet_key_ref_is_rejected(self):
        path = _write(VALID_TOML.format(wallet_key_line='wallet_key_ref = "   "'))
        try:
            with self.assertRaises(ConfigValidationError) as ctx:
                load_config(path, env={})
            self.assertTrue(any("wallet_key_ref" in issue for issue in ctx.exception.issues))
        finally:
            path.unlink()

    def test_raw_hex_key_is_rejected(self):
        raw_hex = "0x" + "a" * 64
        path = _write(VALID_TOML.format(wallet_key_line=f'wallet_key_ref = "{raw_hex}"'))
        try:
            with self.assertRaises(ConfigValidationError) as ctx:
                load_config(path, env={})
            issues = ctx.exception.issues
            self.assertTrue(any("wallet_key_ref" in issue and "raw key material" in issue for issue in issues))
        finally:
            path.unlink()

    def test_implausibly_long_value_is_rejected(self):
        path = _write(VALID_TOML.format(wallet_key_line=f'wallet_key_ref = "{"a" * 200}"'))
        try:
            with self.assertRaises(ConfigValidationError) as ctx:
                load_config(path, env={})
            self.assertTrue(any("wallet_key_ref" in issue for issue in ctx.exception.issues))
        finally:
            path.unlink()

    def test_non_string_wallet_key_ref_is_rejected(self):
        path = _write(VALID_TOML.format(wallet_key_line="wallet_key_ref = 12345"))
        try:
            with self.assertRaises(ConfigValidationError) as ctx:
                load_config(path, env={})
            self.assertTrue(any("wallet_key_ref" in issue for issue in ctx.exception.issues))
        finally:
            path.unlink()


class WalletKeyRefEnvOverride(unittest.TestCase):
    def test_env_override_sets_wallet_key_ref_when_absent_from_toml(self):
        path = _write(VALID_TOML.format(wallet_key_line=""))
        try:
            config = load_config(path, env={"TURTLE_EXEC_WALLET_KEY_REF": "hyperliquid_wallet_key_v1"})
            self.assertEqual(config.secrets.wallet_key_ref, "hyperliquid_wallet_key_v1")
        finally:
            path.unlink()

    def test_env_override_replaces_toml_value(self):
        path = _write(VALID_TOML.format(wallet_key_line='wallet_key_ref = "hyperliquid_wallet_key_v1"'))
        try:
            config = load_config(path, env={"TURTLE_EXEC_WALLET_KEY_REF": "hyperliquid_wallet_key_v2"})
            self.assertEqual(config.secrets.wallet_key_ref, "hyperliquid_wallet_key_v2")
        finally:
            path.unlink()

    def test_env_override_value_is_still_validated(self):
        path = _write(VALID_TOML.format(wallet_key_line=""))
        try:
            with self.assertRaises(ConfigValidationError) as ctx:
                load_config(path, env={"TURTLE_EXEC_WALLET_KEY_REF": "0x" + "a" * 64})
            self.assertTrue(any("wallet_key_ref" in issue for issue in ctx.exception.issues))
        finally:
            path.unlink()

    def test_absent_env_var_leaves_toml_value_untouched(self):
        path = _write(VALID_TOML.format(wallet_key_line='wallet_key_ref = "hyperliquid_wallet_key_v1"'))
        try:
            config = load_config(path, env={})
            self.assertEqual(config.secrets.wallet_key_ref, "hyperliquid_wallet_key_v1")
        finally:
            path.unlink()


class WalletKeyRefImmutability(unittest.TestCase):
    def test_secrets_config_remains_frozen_with_new_field(self):
        import dataclasses

        path = _write(VALID_TOML.format(wallet_key_line='wallet_key_ref = "hyperliquid_wallet_key_v1"'))
        try:
            config = load_config(path, env={})
            with self.assertRaises(dataclasses.FrozenInstanceError):
                config.secrets.wallet_key_ref = "other_ref_v1"
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()
