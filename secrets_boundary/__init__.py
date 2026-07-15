"""Secrets & Signing Boundary for the Turtle Execution Engine.

Single responsibility: resolve secret references to usable signing
capability, without ever exposing raw secret material to any caller.
Exchange Adapters (and every other module) depend only on
`SigningBoundary.sign(ref, purpose, message)` -- never on raw key material,
never on how a backend stores or accesses it.

Every signature is cryptographically bound to the engine identity, engine
version, exchange name, and signing purpose (see `domain.py`), so a
signature produced in one context can never be replayed in another.

Public API:
    SigningBoundary(refs, engine_version, exchange_name, backend=None, env=None)
    SigningPurpose (closed enum of permitted signing contexts)
    SigningBackend (abstract base for future open-source backends:
                    HashiCorp Vault, SoftHSM/PKCS#11, hardware wallets)
    EnvironmentHmacBackend (stdlib-only, environment-variable-backed backend)
"""

from .backend import EnvironmentHmacBackend, SigningBackend
from .boundary import SigningBoundary
from .domain import ENGINE_ID, MAX_SIGNING_PAYLOAD_BYTES, SigningPurpose, build_preimage
from .errors import (
    PayloadTooLargeError,
    SecretRevokedError,
    SecretsConfigurationError,
    SecretsError,
    SecretsStartupError,
    UnknownSecretReferenceError,
)

__all__ = [
    "SigningBoundary",
    "SigningPurpose",
    "SigningBackend",
    "EnvironmentHmacBackend",
    "build_preimage",
    "ENGINE_ID",
    "MAX_SIGNING_PAYLOAD_BYTES",
    "SecretsError",
    "SecretsConfigurationError",
    "SecretsStartupError",
    "UnknownSecretReferenceError",
    "SecretRevokedError",
    "PayloadTooLargeError",
]
