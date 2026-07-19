"""Deployment-specific settings the composition root needs but
config.EngineConfig does not carry.

Two values are required to wire a live venue adapter that have no home in
Module 1's frozen schema:

  - account_address: the venue wallet address. It is PUBLIC data (what the
    private key controls, never the key itself -- see
    hyperliquid_adapter.adapter's own constructor docstring), not a secret,
    so it does not belong in config.SecretsConfig and is not resolved
    through SigningBoundary/EnvironmentHmacBackend.
  - engine_version: the version string bound into every SigningBoundary
    signature's domain separation (secrets_boundary.domain.build_preimage).
    No repository-wide version constant exists (confirmed: no __version__
    anywhere in config/ or secrets_boundary/); it is caller-supplied by
    every existing SigningBoundary construction site, including the test
    suite (tests/test_secrets_boundary.py).

Resolving both here -- rather than adding fields to config/schema.py --
keeps Module 1 unchanged, per the additive-only integration rule in
docs/ROADMAP.md.
"""

import os
from dataclasses import dataclass
from typing import Mapping, Optional

_ACCOUNT_ADDRESS_ENV_VAR = "TURTLE_DEPLOYMENT_ACCOUNT_ADDRESS"
_ENGINE_VERSION_ENV_VAR = "TURTLE_ENGINE_VERSION"
_DEFAULT_ENGINE_VERSION = "1.0.0"


@dataclass(frozen=True)
class DeploymentSettings:
    """account_address is required only when config.environment == 'live'
    (build_engine enforces this); None is valid for 'paper', where no venue
    account exists because MockExchangeAdapter never transmits anywhere."""

    engine_version: str
    account_address: Optional[str] = None


def load_deployment_settings(env: Optional[Mapping[str, str]] = None) -> DeploymentSettings:
    """Reads deployment settings from the process environment (or an
    injected mapping, for tests). Neither value is secret material, so
    neither goes through SigningBoundary or EnvironmentHmacBackend --
    this is a plain env-var read, mirroring config.loader's own env
    parameter shape."""
    environ = os.environ if env is None else env
    return DeploymentSettings(
        engine_version=environ.get(_ENGINE_VERSION_ENV_VAR, _DEFAULT_ENGINE_VERSION),
        account_address=environ.get(_ACCOUNT_ADDRESS_ENV_VAR) or None,
    )
