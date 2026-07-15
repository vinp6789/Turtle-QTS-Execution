"""Configuration System for the Turtle Execution Engine.

Single responsibility: load, validate, and provide immutable, typed access to
deployment configuration. Owns no business logic (risk decisions, order
routing, kill-switch triggers, etc. belong to other modules) and never holds
secret material -- only named references resolved later by the
Secrets/Signing Boundary module.

Public API:
    load_config(path, env=None) -> EngineConfig

`EngineConfig` and its nested dataclasses are frozen: once loaded, a
configuration cannot be mutated for the lifetime of the process. Any change
requires reloading (and re-validating) a new configuration file.
"""

from .errors import ConfigError, ConfigFileError, ConfigValidationError
from .loader import load_config
from .schema import (
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

__all__ = [
    "load_config",
    "EngineConfig",
    "ExchangeConfig",
    "UniverseConfig",
    "RiskConfig",
    "RiskProfileParams",
    "OperationalConfig",
    "SecretsConfig",
    "TelegramConfig",
    "LoggingConfig",
    "ConfigError",
    "ConfigFileError",
    "ConfigValidationError",
]
