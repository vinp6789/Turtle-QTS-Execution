import dataclasses
import tempfile
import unittest
from pathlib import Path

from config import ConfigFileError, ConfigValidationError, load_config

EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "config" / "example.toml"

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

[risk.profiles.GROWTH]
risk_pct_per_trade = 0.020
max_positions = 4
sizing_mode = "conviction_weighted"
heat_cap = 0.10
ruin_threshold = 0.50

[risk.profiles.BALANCED]
risk_pct_per_trade = 0.010
max_positions = 3
sizing_mode = "fixed"
heat_cap = 0.05
ruin_threshold = 0.60

[risk.profiles.CAPITAL_PRESERVATION]
risk_pct_per_trade = 0.005
max_positions = 2
sizing_mode = "fixed"
heat_cap = 0.02
ruin_threshold = 0.75

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

[telegram]
enabled = true
chat_id = "123456789"

[logging]
level = "INFO"
directory = "/var/log/turtle_execution_engine"
"""


def _write(content: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False)
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


class LoadValidConfig(unittest.TestCase):
    def test_loads_shipped_example_config(self):
        config = load_config(EXAMPLE_PATH, env={})
        self.assertEqual(config.environment, "paper")
        self.assertEqual(config.exchange.name, "hyperliquid")
        self.assertEqual(config.universe.symbols, ("BTC", "ETH", "SOL"))
        self.assertEqual(config.risk.active_profile, "BALANCED")
        self.assertAlmostEqual(config.risk.active_profile_params.risk_pct_per_trade, 0.010)
        self.assertEqual(config.secrets.signing_key_ref, "hyperliquid_signing_key_v1")

    def test_loads_valid_config_from_string(self):
        path = _write(VALID_TOML)
        try:
            config = load_config(path, env={})
            self.assertEqual(config.risk.profiles["GROWTH"].max_positions, 4)
        finally:
            path.unlink()

    def test_config_is_immutable(self):
        config = load_config(EXAMPLE_PATH, env={})
        with self.assertRaises(dataclasses.FrozenInstanceError):
            config.environment = "live"
        with self.assertRaises(dataclasses.FrozenInstanceError):
            config.risk.active_profile = "GROWTH"


class FileLevelFailures(unittest.TestCase):
    def test_missing_file_raises_config_file_error(self):
        with self.assertRaises(ConfigFileError):
            load_config("/nonexistent/path/does_not_exist.toml", env={})

    def test_malformed_toml_raises_config_file_error(self):
        path = _write("this is not [ valid toml")
        try:
            with self.assertRaises(ConfigFileError):
                load_config(path, env={})
        finally:
            path.unlink()


class EnvironmentOverrides(unittest.TestCase):
    def test_mode_override(self):
        path = _write(VALID_TOML)
        try:
            config = load_config(path, env={"TURTLE_EXEC_MODE": "live"})
            self.assertEqual(config.environment, "live")
        finally:
            path.unlink()

    def test_secret_ref_overrides(self):
        path = _write(VALID_TOML)
        try:
            config = load_config(
                path,
                env={
                    "TURTLE_EXEC_SIGNING_KEY_REF": "hyperliquid_signing_key_v2",
                    "TURTLE_EXEC_TELEGRAM_BOT_TOKEN_REF": "telegram_bot_token_v2",
                },
            )
            self.assertEqual(config.secrets.signing_key_ref, "hyperliquid_signing_key_v2")
            self.assertEqual(config.secrets.telegram_bot_token_ref, "telegram_bot_token_v2")
        finally:
            path.unlink()

    def test_env_cannot_override_risk_parameters(self):
        # Deliberately not supported -- risk parameters must only ever come
        # from the reviewed config file.
        path = _write(VALID_TOML)
        try:
            config = load_config(path, env={"TURTLE_EXEC_RISK_PROFILE": "GROWTH"})
            self.assertEqual(config.risk.active_profile, "BALANCED")
        finally:
            path.unlink()


class ValidationFailures(unittest.TestCase):
    def _load_and_expect_issue(self, content: str, expected_substring: str):
        path = _write(content)
        try:
            with self.assertRaises(ConfigValidationError) as ctx:
                load_config(path, env={})
            joined = "\n".join(ctx.exception.issues)
            self.assertIn(expected_substring, joined)
        finally:
            path.unlink()

    def test_rejects_unsupported_exchange(self):
        bad = VALID_TOML.replace('name = "hyperliquid"', 'name = "lighter"')
        self._load_and_expect_issue(bad, "exchange.name")

    def test_rejects_invalid_environment_mode(self):
        bad = VALID_TOML.replace('mode = "paper"', 'mode = "production"')
        self._load_and_expect_issue(bad, "environment.mode")

    def test_rejects_empty_universe(self):
        bad = VALID_TOML.replace('symbols = ["BTC", "ETH", "SOL"]', "symbols = []")
        self._load_and_expect_issue(bad, "universe.symbols")

    def test_rejects_duplicate_symbols(self):
        bad = VALID_TOML.replace('symbols = ["BTC", "ETH", "SOL"]', 'symbols = ["BTC", "BTC"]')
        self._load_and_expect_issue(bad, "duplicate symbols")

    def test_rejects_lowercase_symbols(self):
        bad = VALID_TOML.replace('symbols = ["BTC", "ETH", "SOL"]', 'symbols = ["btc"]')
        self._load_and_expect_issue(bad, "must be uppercase")

    def test_rejects_unknown_active_profile(self):
        bad = VALID_TOML.replace('profile = "BALANCED"', 'profile = "AGGRESSIVE"')
        self._load_and_expect_issue(bad, "risk.profile")

    def test_rejects_zero_headroom_heat_cap(self):
        # GROWTH: 4 positions * 2% = 8% required headroom; set heat_cap to
        # exactly the old, documented-defective 0.08 with zero headroom.
        bad = VALID_TOML.replace("heat_cap = 0.10", "heat_cap = 0.08")
        self._load_and_expect_issue(bad, "zero-headroom")

    def test_rejects_out_of_range_ruin_threshold(self):
        bad = VALID_TOML.replace("ruin_threshold = 0.60", "ruin_threshold = 1.5")
        self._load_and_expect_issue(bad, "ruin_threshold")

    def test_rejects_raw_hex_key_as_signing_ref(self):
        bad = VALID_TOML.replace(
            'signing_key_ref = "hyperliquid_signing_key_v1"',
            'signing_key_ref = "0x' + "a" * 64 + '"',
        )
        self._load_and_expect_issue(bad, "raw key material")

    def test_rejects_implausibly_long_secret_ref(self):
        bad = VALID_TOML.replace(
            'signing_key_ref = "hyperliquid_signing_key_v1"',
            'signing_key_ref = "' + "x" * 150 + '"',
        )
        self._load_and_expect_issue(bad, "raw key material")

    def test_rejects_auto_flatten_enabled_with_zero_confirmation(self):
        bad = VALID_TOML.replace(
            "auto_flatten_enabled = false", "auto_flatten_enabled = true"
        ).replace("auto_flatten_confirmation_seconds = 60", "auto_flatten_confirmation_seconds = 0")
        self._load_and_expect_issue(bad, "must be greater than 0")

    def test_rejects_telegram_enabled_without_chat_id(self):
        bad = VALID_TOML.replace('chat_id = "123456789"', 'chat_id = ""')
        self._load_and_expect_issue(bad, "telegram.chat_id")

    def test_rejects_missing_section(self):
        bad = "\n".join(line for line in VALID_TOML.splitlines() if not line.startswith("[logging]"))
        # Also drop the two lines that belong to [logging]
        bad = bad.replace('level = "INFO"\n', "").replace(
            'directory = "/var/log/turtle_execution_engine"\n', ""
        )
        self._load_and_expect_issue(bad, "logging: section is required")

    def test_reports_multiple_issues_at_once(self):
        bad = VALID_TOML.replace('mode = "paper"', 'mode = "prod"').replace(
            'name = "hyperliquid"', 'name = "binance"'
        )
        path = _write(bad)
        try:
            with self.assertRaises(ConfigValidationError) as ctx:
                load_config(path, env={})
            self.assertGreaterEqual(len(ctx.exception.issues), 2)
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()
