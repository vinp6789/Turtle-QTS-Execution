"""Application settings, loaded from environment variables.

Deployment-agnostic: the SAME AppSettings.from_env() works on a Windows
laptop and on Railway. Railway injects PORT; everything else has a safe
default so the app boots with zero configuration in paper mode. No secret
material is stored here -- signing/wallet keys stay in TURTLE_SECRET_*
(read only by secrets_boundary), and the Telegram token is read straight
from the environment at send time, never persisted on this object beyond
the process.

Every field is overridable by an environment variable so the exact same
image can be reconfigured per deployment without code changes.
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Mapping, Optional

import os

_TRUE = {"1", "true", "yes", "on"}


def _bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in _TRUE


def _int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"environment variable {key}={raw!r} is not a valid integer") from exc


def _decimal(env: Mapping[str, str], key: str, default: str) -> Decimal:
    raw = env.get(key)
    if raw is None or raw.strip() == "":
        raw = default
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"environment variable {key}={raw!r} is not a valid decimal") from exc


@dataclass(frozen=True)
class AppSettings:
    # -- HTTP server --
    host: str
    port: int
    # -- engine wiring --
    engine_config_path: str
    event_store_path: str
    # -- background worker --
    worker_enabled: bool
    cycle_interval_seconds: int
    # -- cycle parameters not carried by EngineConfig --
    maintenance_margin_rate: Decimal
    target_leverage: Decimal
    # -- risk limits (risk_manager.RiskManagerLimits) --
    risk_max_leverage: Decimal
    risk_min_liquidation_buffer_pct: Decimal
    risk_max_funding_rate_abs: Decimal
    risk_max_correlated_positions: int
    risk_max_stale_data_seconds: int
    # -- observability --
    log_level: str
    log_format: str  # "json" | "text"
    metrics_enabled: bool
    # -- interface toggles --
    dashboard_enabled: bool
    # -- security: optional bearer key protecting mutating/control endpoints --
    api_key: Optional[str]
    # -- telegram --
    telegram_enabled: bool
    telegram_bot_token: Optional[str]
    telegram_chat_id: Optional[str]

    @staticmethod
    def from_env(env: Optional[Mapping[str, str]] = None) -> "AppSettings":
        e = os.environ if env is None else env
        # Railway sets PORT; APP_PORT is the explicit override; else 8000.
        port_raw = e.get("PORT") or e.get("APP_PORT") or "8000"
        try:
            port = int(port_raw)
        except ValueError as exc:
            raise ValueError(f"PORT/APP_PORT={port_raw!r} is not a valid integer") from exc

        return AppSettings(
            host=e.get("APP_HOST", "0.0.0.0"),
            port=port,
            engine_config_path=e.get("ENGINE_CONFIG_PATH", "deploy/engine.paper.toml"),
            event_store_path=e.get("ENGINE_STORE_PATH", "data/events.log"),
            worker_enabled=_bool(e, "WORKER_ENABLED", True),
            cycle_interval_seconds=_int(e, "CYCLE_INTERVAL_SECONDS", 60),
            maintenance_margin_rate=_decimal(e, "CYCLE_MAINTENANCE_MARGIN_RATE", "0.005"),
            target_leverage=_decimal(e, "CYCLE_TARGET_LEVERAGE", "1"),
            risk_max_leverage=_decimal(e, "RISK_MAX_LEVERAGE", "10"),
            risk_min_liquidation_buffer_pct=_decimal(e, "RISK_MIN_LIQ_BUFFER_PCT", "0.1"),
            risk_max_funding_rate_abs=_decimal(e, "RISK_MAX_FUNDING_RATE_ABS", "0.05"),
            risk_max_correlated_positions=_int(e, "RISK_MAX_CORRELATED_POSITIONS", 3),
            risk_max_stale_data_seconds=_int(e, "RISK_MAX_STALE_DATA_SECONDS", 30),
            log_level=e.get("LOG_LEVEL", "INFO").upper(),
            log_format=e.get("LOG_FORMAT", "json").lower(),
            metrics_enabled=_bool(e, "METRICS_ENABLED", True),
            dashboard_enabled=_bool(e, "DASHBOARD_ENABLED", True),
            api_key=(e.get("API_KEY") or None),
            telegram_enabled=_bool(e, "TELEGRAM_ENABLED", False),
            telegram_bot_token=(e.get("TELEGRAM_BOT_TOKEN") or None),
            telegram_chat_id=(e.get("TELEGRAM_CHAT_ID") or None),
        )
