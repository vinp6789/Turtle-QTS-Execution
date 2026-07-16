"""Immutable configuration schema for the Turtle Execution Engine.

These dataclasses define the SHAPE of a valid configuration only. All
validation (presence, type, range, and cross-field invariants) happens in
loader.py before any of these objects are constructed. By the time an
EngineConfig exists, it is known-valid and is never mutated again for the
lifetime of the process -- every field is frozen.
"""

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

# Exchanges with an implemented, production Exchange Adapter. Selecting a
# name outside this set must fail configuration loading -- an unimplemented
# adapter must never be silently accepted and discovered missing at runtime.
SUPPORTED_EXCHANGES = frozenset({"hyperliquid"})

SUPPORTED_NETWORKS = frozenset({"mainnet", "testnet"})
SUPPORTED_ENVIRONMENTS = frozenset({"paper", "live"})

# Must mirror the Research Engine's frozen RISK_PROFILES key set exactly
# (see AI_CONTEXT.md section 12, Stable Interfaces). This module does not
# import the Research Engine -- it independently declares the same allowed
# names so a typo'd profile name fails loudly at config-load time.
SUPPORTED_RISK_PROFILE_NAMES = frozenset({"GROWTH", "BALANCED", "CAPITAL_PRESERVATION"})
SUPPORTED_SIZING_MODES = frozenset({"fixed", "vol_targeted", "conviction_weighted"})
SUPPORTED_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


@dataclass(frozen=True)
class ExchangeConfig:
    name: str
    network: str


@dataclass(frozen=True)
class UniverseConfig:
    symbols: Tuple[str, ...]


@dataclass(frozen=True)
class RiskProfileParams:
    """Mirrors the Research Engine's frozen RISK_PROFILES entry schema
    (risk_pct_per_trade, max_positions, sizing_mode, heat_cap,
    ruin_threshold) -- see AI_CONTEXT.md section 12."""

    risk_pct_per_trade: float
    max_positions: int
    sizing_mode: str
    heat_cap: float
    ruin_threshold: float


@dataclass(frozen=True)
class RiskConfig:
    active_profile: str
    profiles: Mapping[str, RiskProfileParams]
    max_daily_loss_pct: float
    max_drawdown_from_peak_pct: float
    auto_flatten_enabled: bool
    auto_flatten_confirmation_seconds: float

    @property
    def active_profile_params(self) -> RiskProfileParams:
        return self.profiles[self.active_profile]


@dataclass(frozen=True)
class OperationalConfig:
    max_retries: int
    retry_base_delay_seconds: float
    retry_max_delay_seconds: float
    clock_drift_tolerance_ms: float
    data_staleness_price_ms: float
    data_staleness_orderbook_ms: float
    data_staleness_position_ms: float


@dataclass(frozen=True)
class SecretsConfig:
    """Holds only named references to secrets, never secret material itself.
    Resolved by the Secrets/Signing Boundary module, which is the only
    module permitted to read the actual key/token bytes.

    wallet_key_ref is optional and distinct from signing_key_ref: it names a
    venue wallet-signing key (e.g. for EIP-712/secp256k1 exchange
    authentication) as its own secret domain, separate from Turtle-internal
    authorization signing. None means no wallet-signing venue is configured."""

    signing_key_ref: str
    telegram_bot_token_ref: str
    wallet_key_ref: Optional[str] = None


@dataclass(frozen=True)
class TelegramConfig:
    enabled: bool
    chat_id: str


@dataclass(frozen=True)
class LoggingConfig:
    level: str
    directory: str


@dataclass(frozen=True)
class EngineConfig:
    environment: str
    exchange: ExchangeConfig
    universe: UniverseConfig
    risk: RiskConfig
    operational: OperationalConfig
    secrets: SecretsConfig
    telegram: TelegramConfig
    logging: LoggingConfig
