"""The Secrets & Signing Boundary's public interface.

`SigningBoundary` is the ONLY object Exchange Adapters (and any other
module) may use to produce a signature. It never exposes raw secret
material through any public method, its __repr__/__str__, or through
pickling/copying. Exchange Adapters call `sign(ref, message)` and receive
bytes back -- nothing else about the underlying key is ever visible to
them.
"""

import re
import threading
from typing import FrozenSet, Iterable, List, Optional

from .backend import EnvironmentHmacBackend, SigningBackend
from .domain import MAX_SIGNING_PAYLOAD_BYTES, SigningPurpose, build_preimage
from .errors import (
    PayloadTooLargeError,
    SecretRevokedError,
    SecretsConfigurationError,
    SecretsStartupError,
    UnknownSecretReferenceError,
)

# Reference format: lowercase name, underscores, ending in an explicit
# version suffix (e.g. "hyperliquid_signing_key_v1") so key rotation is
# expressible as a new reference rather than an in-place value change.
_REF_PATTERN = re.compile(r"^[a-z][a-z0-9_]*_v[1-9][0-9]*$")


class SigningBoundary:
    """Resolves secret references and produces signatures on demand.

    Immutable after construction, with exactly one deliberate exception:
    revoke()/revoke_all() may move a reference from active to revoked.
    This is a one-way security control (needed so an Emergency Kill can
    instantly cut off signing capability), never a general mutation path --
    no reference can ever be un-revoked or have its material replaced on a
    live instance. Everything else about the instance (which references
    exist, which backend is in use) is fixed for its lifetime.
    """

    def __init__(
        self,
        refs: Iterable[str],
        engine_version: str,
        exchange_name: str,
        backend: Optional[SigningBackend] = None,
        env: Optional[dict] = None,
    ):
        ref_list = list(refs)
        structural_issues = _validate_ref_structure(ref_list)
        structural_issues.extend(_validate_domain(engine_version, exchange_name))
        if structural_issues:
            raise SecretsConfigurationError(structural_issues)

        expected_refs: FrozenSet[str] = frozenset(ref_list)
        resolved_backend = backend if backend is not None else EnvironmentHmacBackend(env=env)

        load_issues = resolved_backend.validate_and_load(expected_refs)
        if load_issues:
            raise SecretsStartupError(load_issues)

        object.__setattr__(self, "_engine_version", engine_version)
        object.__setattr__(self, "_exchange_name", exchange_name)
        object.__setattr__(self, "_expected_refs", expected_refs)
        object.__setattr__(self, "_backend", resolved_backend)
        object.__setattr__(self, "_revoked", set())
        object.__setattr__(self, "_lock", threading.Lock())
        object.__setattr__(self, "_initialized", True)

    def __setattr__(self, name, value):
        if getattr(self, "_initialized", False):
            raise AttributeError(
                f"SigningBoundary is immutable; cannot set attribute '{name}' after initialization"
            )
        object.__setattr__(self, name, value)

    def has_reference(self, ref: str) -> bool:
        return ref in self._expected_refs

    def is_revoked(self, ref: str) -> bool:
        return ref in self._revoked

    def sign(self, ref: str, purpose: SigningPurpose, message: bytes) -> bytes:
        """Produce a signature bound to (engine, engine version, exchange,
        purpose, message) using the material for `ref`.

        `message` itself is NEVER signed directly -- what is signed is the
        canonical domain-separated preimage built by build_preimage(), so a
        signature obtained for one purpose/exchange/version can never be
        replayed as valid in another context.

        Raises UnknownSecretReferenceError if `ref` was never registered,
        SecretRevokedError if it has been revoked, TypeError if `purpose` is
        not a SigningPurpose member, and PayloadTooLargeError if `message`
        exceeds MAX_SIGNING_PAYLOAD_BYTES. Never returns or logs the
        underlying key material.
        """
        if not isinstance(purpose, SigningPurpose):
            # A free-form string purpose would let an adapter invent an
            # unaudited signing context; only the closed enum is accepted.
            raise TypeError(f"purpose must be a SigningPurpose member, got {type(purpose).__name__}")
        if not isinstance(message, (bytes, bytearray)):
            raise TypeError(f"message must be bytes, got {type(message).__name__}")
        if len(message) > MAX_SIGNING_PAYLOAD_BYTES:
            raise PayloadTooLargeError(
                f"signing payload is {len(message)} bytes, exceeding the "
                f"{MAX_SIGNING_PAYLOAD_BYTES}-byte limit (reference '{ref}', purpose {purpose.value})"
            )
        if ref not in self._expected_refs:
            raise UnknownSecretReferenceError(f"unknown secret reference: '{ref}'")
        if ref in self._revoked:
            raise SecretRevokedError(f"secret reference '{ref}' has been revoked and can no longer sign")

        preimage = build_preimage(self._engine_version, self._exchange_name, purpose, bytes(message))
        return self._backend.sign(ref, preimage)

    def revoke(self, ref: str) -> None:
        """Permanently disable signing for `ref` on this instance and
        instruct the backend to destroy its material immediately. Intended
        to be called by the Kill Switch's Emergency tier. Idempotent."""
        if ref not in self._expected_refs:
            raise UnknownSecretReferenceError(f"unknown secret reference: '{ref}'")
        with self._lock:
            self._revoked.add(ref)
            self._backend.discard(ref)

    def revoke_all(self) -> None:
        """Permanently disable signing for every registered reference.
        Intended for an Emergency Kill that must cut off all signing
        capability regardless of which reference an attacker or fault
        might target next."""
        with self._lock:
            for ref in self._expected_refs:
                self._revoked.add(ref)
                self._backend.discard(ref)

    def __repr__(self) -> str:
        # engine_version and exchange_name are public deployment context,
        # not secrets; including them makes the bound signing domain
        # auditable from logs without exposing any key material.
        return (
            f"SigningBoundary(engine_version={self._engine_version!r}, "
            f"exchange={self._exchange_name!r}, refs={sorted(self._expected_refs)}, "
            f"revoked={sorted(self._revoked)}, backend={type(self._backend).__name__})"
        )

    __str__ = __repr__

    def __getstate__(self):
        raise TypeError("SigningBoundary cannot be pickled or serialized -- it holds secret material")

    def __deepcopy__(self, memo):
        raise TypeError("SigningBoundary cannot be deep-copied -- it holds secret material")


def _validate_domain(engine_version: str, exchange_name: str) -> List[str]:
    """An empty or non-string domain component would silently weaken domain
    separation, so both are validated at construction time."""
    issues: List[str] = []
    if not isinstance(engine_version, str) or not engine_version.strip():
        issues.append(f"engine_version must be a non-empty string, got {engine_version!r}")
    if not isinstance(exchange_name, str) or not exchange_name.strip():
        issues.append(f"exchange_name must be a non-empty string, got {exchange_name!r}")
    return issues


def _validate_ref_structure(refs: List[str]) -> List[str]:
    issues: List[str] = []
    seen = set()
    for ref in refs:
        if not isinstance(ref, str) or not _REF_PATTERN.match(ref):
            issues.append(
                f"secret reference {ref!r} has invalid format "
                "(expected lowercase 'name_v<N>', e.g. 'hyperliquid_signing_key_v1')"
            )
            continue
        if ref in seen:
            issues.append(f"duplicate secret reference: '{ref}'")
        seen.add(ref)
    return issues
