"""Loader for the Turtle Execution Engine configuration.

Reads a TOML configuration file, applies a narrow, explicit set of
environment-variable overrides, validates the result exhaustively
(collecting every issue found rather than stopping at the first), and
returns an immutable EngineConfig. This is the single point of entry for
constructing an EngineConfig -- no other module builds one directly.
"""

import os
import re
import tomllib
from pathlib import Path
from typing import Mapping, Optional, Union

from .errors import ConfigFileError, ConfigValidationError
from .schema import (
    EngineConfig,
    ExchangeConfig,
    LoggingConfig,
    OperationalConfig,
    RiskConfig,
    RiskProfileParams,
    SecretsConfig,
    SUPPORTED_ENVIRONMENTS,
    SUPPORTED_EXCHANGES,
    SUPPORTED_LOG_LEVELS,
    SUPPORTED_NETWORKS,
    SUPPORTED_RISK_PROFILE_NAMES,
    SUPPORTED_SIZING_MODES,
    TelegramConfig,
    UniverseConfig,
)

# Deliberately narrow: only the deployment target and secret *reference
# names* may be overridden from the environment. Anything that affects
# trading behavior (risk parameters, universe, thresholds) must live in the
# reviewed config file and can never be silently swapped via env var.
_ENV_MODE_OVERRIDE = "TURTLE_EXEC_MODE"
_ENV_SIGNING_KEY_REF_OVERRIDE = "TURTLE_EXEC_SIGNING_KEY_REF"
_ENV_TELEGRAM_TOKEN_REF_OVERRIDE = "TURTLE_EXEC_TELEGRAM_BOT_TOKEN_REF"
_ENV_WALLET_KEY_REF_OVERRIDE = "TURTLE_EXEC_WALLET_KEY_REF"

_RAW_HEX_KEY_PATTERN = re.compile(r"^0x[0-9a-fA-F]{64}$")
_MAX_PLAUSIBLE_REF_LENGTH = 100


def load_config(path: Union[str, Path], env: Optional[Mapping[str, str]] = None) -> EngineConfig:
    """Load, override, validate, and return an immutable EngineConfig.

    Raises ConfigFileError if the file is missing, unreadable, or not valid
    TOML. Raises ConfigValidationError (carrying every issue found) if the
    parsed configuration fails schema or invariant validation.
    """
    env = os.environ if env is None else env
    raw = _read_toml(Path(path))
    raw = _apply_env_overrides(raw, env)

    issues: list = []
    _validate(raw, issues)
    if issues:
        raise ConfigValidationError(issues)

    return _build(raw)


def _read_toml(path: Path) -> dict:
    if not path.is_file():
        raise ConfigFileError(f"Configuration file not found: {path}")
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigFileError(f"Configuration file is not valid TOML: {path} ({exc})") from exc
    except OSError as exc:
        raise ConfigFileError(f"Configuration file could not be read: {path} ({exc})") from exc


def _apply_env_overrides(raw: dict, env: Mapping[str, str]) -> dict:
    raw = dict(raw)
    if _ENV_MODE_OVERRIDE in env:
        raw["environment"] = {**raw.get("environment", {}), "mode": env[_ENV_MODE_OVERRIDE]}
    if _ENV_SIGNING_KEY_REF_OVERRIDE in env:
        raw["secrets"] = {**raw.get("secrets", {}), "signing_key_ref": env[_ENV_SIGNING_KEY_REF_OVERRIDE]}
    if _ENV_TELEGRAM_TOKEN_REF_OVERRIDE in env:
        raw["secrets"] = {**raw.get("secrets", {}), "telegram_bot_token_ref": env[_ENV_TELEGRAM_TOKEN_REF_OVERRIDE]}
    if _ENV_WALLET_KEY_REF_OVERRIDE in env:
        raw["secrets"] = {**raw.get("secrets", {}), "wallet_key_ref": env[_ENV_WALLET_KEY_REF_OVERRIDE]}
    return raw


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def _validate(raw: dict, issues: list) -> None:
    _validate_environment(raw, issues)
    _validate_exchange(raw, issues)
    _validate_universe(raw, issues)
    _validate_risk(raw, issues)
    _validate_operational(raw, issues)
    _validate_secrets(raw, issues)
    _validate_telegram(raw, issues)
    _validate_logging(raw, issues)


def _validate_environment(raw: dict, issues: list) -> None:
    section = raw.get("environment")
    if not isinstance(section, dict):
        issues.append("environment: section is required")
        return
    mode = section.get("mode")
    if mode not in SUPPORTED_ENVIRONMENTS:
        issues.append(f"environment.mode: must be one of {sorted(SUPPORTED_ENVIRONMENTS)}, got {mode!r}")


def _validate_exchange(raw: dict, issues: list) -> None:
    section = raw.get("exchange")
    if not isinstance(section, dict):
        issues.append("exchange: section is required")
        return
    name = section.get("name")
    if name not in SUPPORTED_EXCHANGES:
        issues.append(
            f"exchange.name: must be one of {sorted(SUPPORTED_EXCHANGES)}, got {name!r} "
            "(an exchange without an implemented, production Exchange Adapter "
            "must never be selectable in config)"
        )
    network = section.get("network")
    if network not in SUPPORTED_NETWORKS:
        issues.append(f"exchange.network: must be one of {sorted(SUPPORTED_NETWORKS)}, got {network!r}")


def _validate_universe(raw: dict, issues: list) -> None:
    section = raw.get("universe")
    if not isinstance(section, dict):
        issues.append("universe: section is required")
        return
    symbols = section.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        issues.append("universe.symbols: must be a non-empty list of symbol strings")
        return
    if not all(isinstance(s, str) and s.strip() for s in symbols):
        issues.append("universe.symbols: every entry must be a non-empty string")
        return
    if len(set(symbols)) != len(symbols):
        issues.append("universe.symbols: duplicate symbols are not allowed")
    if any(s != s.upper() for s in symbols):
        issues.append("universe.symbols: symbols must be uppercase")


def _validate_risk(raw: dict, issues: list) -> None:
    section = raw.get("risk")
    if not isinstance(section, dict):
        issues.append("risk: section is required")
        return

    active = section.get("profile")
    if active not in SUPPORTED_RISK_PROFILE_NAMES:
        issues.append(f"risk.profile: must be one of {sorted(SUPPORTED_RISK_PROFILE_NAMES)}, got {active!r}")

    profiles = section.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        issues.append("risk.profiles: must define at least one risk profile table")
        profiles = {}

    for name, params in profiles.items():
        prefix = f"risk.profiles.{name}"
        if not isinstance(params, dict):
            issues.append(f"{prefix}: must be a table")
            continue
        _validate_risk_profile_params(prefix, params, issues)

    if active in SUPPORTED_RISK_PROFILE_NAMES and active not in profiles:
        issues.append(f"risk.profile: '{active}' selected but risk.profiles.{active} is not defined")

    max_daily_loss = section.get("max_daily_loss_pct")
    if not _is_fraction(max_daily_loss):
        issues.append(f"risk.max_daily_loss_pct: must be a number in (0, 1], got {max_daily_loss!r}")

    max_dd = section.get("max_drawdown_from_peak_pct")
    if not _is_fraction(max_dd):
        issues.append(f"risk.max_drawdown_from_peak_pct: must be a number in (0, 1], got {max_dd!r}")

    auto_flatten = section.get("auto_flatten_enabled")
    if not isinstance(auto_flatten, bool):
        issues.append(f"risk.auto_flatten_enabled: must be a boolean, got {auto_flatten!r}")

    confirm_seconds = section.get("auto_flatten_confirmation_seconds")
    if not _is_nonnegative_number(confirm_seconds):
        issues.append(
            f"risk.auto_flatten_confirmation_seconds: must be a non-negative number, got {confirm_seconds!r}"
        )
    elif auto_flatten is True and confirm_seconds == 0:
        issues.append(
            "risk.auto_flatten_confirmation_seconds: must be greater than 0 when "
            "auto_flatten_enabled is true -- auto-flatten must never fire on an "
            "instantaneous, unconfirmed breach (see Kill Switch: Hard Kill requires "
            "a sustained, confirmed trigger, never a single transient signal)"
        )


def _validate_risk_profile_params(prefix: str, params: dict, issues: list) -> None:
    risk_pct = params.get("risk_pct_per_trade")
    if not _is_fraction(risk_pct):
        issues.append(f"{prefix}.risk_pct_per_trade: must be a number in (0, 1], got {risk_pct!r}")

    max_positions = params.get("max_positions")
    valid_max_positions = isinstance(max_positions, int) and not isinstance(max_positions, bool) and max_positions >= 1
    if not valid_max_positions:
        issues.append(f"{prefix}.max_positions: must be a positive integer, got {max_positions!r}")

    sizing_mode = params.get("sizing_mode")
    if sizing_mode not in SUPPORTED_SIZING_MODES:
        issues.append(f"{prefix}.sizing_mode: must be one of {sorted(SUPPORTED_SIZING_MODES)}, got {sizing_mode!r}")

    heat_cap = params.get("heat_cap")
    if not _is_fraction(heat_cap):
        issues.append(f"{prefix}.heat_cap: must be a number in (0, 1], got {heat_cap!r}")
    elif _is_fraction(risk_pct) and valid_max_positions:
        required_headroom = max_positions * risk_pct
        if heat_cap <= required_headroom:
            issues.append(
                f"{prefix}.heat_cap ({heat_cap}) leaves no real headroom over "
                f"max_positions * risk_pct_per_trade ({required_headroom}) -- this is the exact "
                "zero-headroom misconfiguration "
                "documented as the GROWTH profile's root-cause defect in the frozen Research "
                "Engine (AI_CONTEXT.md C6 summary). heat_cap must leave real headroom above "
                "a fully-open book."
            )

    ruin_threshold = params.get("ruin_threshold")
    if not isinstance(ruin_threshold, (int, float)) or isinstance(ruin_threshold, bool) or not (0 < ruin_threshold < 1):
        issues.append(f"{prefix}.ruin_threshold: must be a number in (0, 1), got {ruin_threshold!r}")


def _validate_operational(raw: dict, issues: list) -> None:
    section = raw.get("operational")
    if not isinstance(section, dict):
        issues.append("operational: section is required")
        return

    max_retries = section.get("max_retries")
    if not isinstance(max_retries, int) or isinstance(max_retries, bool) or max_retries < 0:
        issues.append(f"operational.max_retries: must be a non-negative integer, got {max_retries!r}")

    base_delay = section.get("retry_base_delay_seconds")
    max_delay = section.get("retry_max_delay_seconds")
    if not _is_positive_number(base_delay):
        issues.append(f"operational.retry_base_delay_seconds: must be a positive number, got {base_delay!r}")
    if not _is_positive_number(max_delay):
        issues.append(f"operational.retry_max_delay_seconds: must be a positive number, got {max_delay!r}")
    if _is_positive_number(base_delay) and _is_positive_number(max_delay) and base_delay > max_delay:
        issues.append("operational.retry_base_delay_seconds must not exceed operational.retry_max_delay_seconds")

    for field_name in (
        "clock_drift_tolerance_ms",
        "data_staleness_price_ms",
        "data_staleness_orderbook_ms",
        "data_staleness_position_ms",
    ):
        value = section.get(field_name)
        if not _is_positive_number(value):
            issues.append(f"operational.{field_name}: must be a positive number, got {value!r}")


def _validate_secrets(raw: dict, issues: list) -> None:
    section = raw.get("secrets")
    if not isinstance(section, dict):
        issues.append("secrets: section is required")
        return
    for field_name in ("signing_key_ref", "telegram_bot_token_ref"):
        value = section.get(field_name)
        if not isinstance(value, str) or not value.strip():
            issues.append(f"secrets.{field_name}: must be a non-empty string reference")
            continue
        if _looks_like_raw_secret(value):
            issues.append(
                f"secrets.{field_name}: value looks like raw key material, not a reference "
                "name. The Configuration System must only ever hold references resolved "
                "later by the Secrets/Signing Boundary -- never the secret itself."
            )

    # Optional: a venue wallet-signing key reference, kept as a separate
    # secret domain from signing_key_ref (see ADR-20/ADR-21). Absent means no
    # wallet-signing venue is configured; if present it is validated
    # identically to the required refs above.
    wallet_key_ref = section.get("wallet_key_ref")
    if wallet_key_ref is not None:
        if not isinstance(wallet_key_ref, str) or not wallet_key_ref.strip():
            issues.append("secrets.wallet_key_ref: must be a non-empty string reference if provided")
        elif _looks_like_raw_secret(wallet_key_ref):
            issues.append(
                "secrets.wallet_key_ref: value looks like raw key material, not a reference "
                "name. The Configuration System must only ever hold references resolved "
                "later by the Secrets/Signing Boundary -- never the secret itself."
            )


def _validate_telegram(raw: dict, issues: list) -> None:
    section = raw.get("telegram")
    if not isinstance(section, dict):
        issues.append("telegram: section is required")
        return
    enabled = section.get("enabled")
    if not isinstance(enabled, bool):
        issues.append(f"telegram.enabled: must be a boolean, got {enabled!r}")
    chat_id = section.get("chat_id")
    if enabled is True and (not isinstance(chat_id, str) or not chat_id.strip()):
        issues.append("telegram.chat_id: must be a non-empty string when telegram.enabled is true")


def _validate_logging(raw: dict, issues: list) -> None:
    section = raw.get("logging")
    if not isinstance(section, dict):
        issues.append("logging: section is required")
        return
    level = section.get("level")
    if level not in SUPPORTED_LOG_LEVELS:
        issues.append(f"logging.level: must be one of {sorted(SUPPORTED_LOG_LEVELS)}, got {level!r}")
    directory = section.get("directory")
    if not isinstance(directory, str) or not directory.strip():
        issues.append("logging.directory: must be a non-empty string path")


def _is_fraction(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value <= 1


def _is_positive_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _is_nonnegative_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def _looks_like_raw_secret(value: str) -> bool:
    """Heuristic guard, not a guarantee: catches the common accident of a raw
    hex private key or an implausibly long token being pasted directly into
    the config file instead of a short reference name."""
    if _RAW_HEX_KEY_PATTERN.match(value):
        return True
    if len(value) > _MAX_PLAUSIBLE_REF_LENGTH:
        return True
    return False


# --------------------------------------------------------------------------
# Construction (only reached once _validate has produced zero issues)
# --------------------------------------------------------------------------

def _build(raw: dict) -> EngineConfig:
    env_section = raw["environment"]
    exch_section = raw["exchange"]
    universe_section = raw["universe"]
    risk_section = raw["risk"]
    operational_section = raw["operational"]
    secrets_section = raw["secrets"]
    telegram_section = raw["telegram"]
    logging_section = raw["logging"]

    profiles = {
        name: RiskProfileParams(
            risk_pct_per_trade=float(params["risk_pct_per_trade"]),
            max_positions=int(params["max_positions"]),
            sizing_mode=params["sizing_mode"],
            heat_cap=float(params["heat_cap"]),
            ruin_threshold=float(params["ruin_threshold"]),
        )
        for name, params in risk_section["profiles"].items()
    }

    return EngineConfig(
        environment=env_section["mode"],
        exchange=ExchangeConfig(name=exch_section["name"], network=exch_section["network"]),
        universe=UniverseConfig(symbols=tuple(universe_section["symbols"])),
        risk=RiskConfig(
            active_profile=risk_section["profile"],
            profiles=profiles,
            max_daily_loss_pct=float(risk_section["max_daily_loss_pct"]),
            max_drawdown_from_peak_pct=float(risk_section["max_drawdown_from_peak_pct"]),
            auto_flatten_enabled=bool(risk_section["auto_flatten_enabled"]),
            auto_flatten_confirmation_seconds=float(risk_section["auto_flatten_confirmation_seconds"]),
        ),
        operational=OperationalConfig(
            max_retries=int(operational_section["max_retries"]),
            retry_base_delay_seconds=float(operational_section["retry_base_delay_seconds"]),
            retry_max_delay_seconds=float(operational_section["retry_max_delay_seconds"]),
            clock_drift_tolerance_ms=float(operational_section["clock_drift_tolerance_ms"]),
            data_staleness_price_ms=float(operational_section["data_staleness_price_ms"]),
            data_staleness_orderbook_ms=float(operational_section["data_staleness_orderbook_ms"]),
            data_staleness_position_ms=float(operational_section["data_staleness_position_ms"]),
        ),
        secrets=SecretsConfig(
            signing_key_ref=secrets_section["signing_key_ref"],
            telegram_bot_token_ref=secrets_section["telegram_bot_token_ref"],
            wallet_key_ref=secrets_section.get("wallet_key_ref"),
        ),
        telegram=TelegramConfig(
            enabled=bool(telegram_section["enabled"]),
            chat_id=telegram_section.get("chat_id") or "",
        ),
        logging=LoggingConfig(level=logging_section["level"], directory=logging_section["directory"]),
    )
