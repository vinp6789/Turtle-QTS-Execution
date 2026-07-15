"""Signing backends for the Secrets & Signing Boundary.

`SigningBackend` is the extension point that lets a future hardware or KMS
backend be substituted for `EnvironmentHmacBackend` without any change to
`SigningBoundary` or to Exchange Adapters -- both depend only on this
abstract interface, never on how a concrete backend stores or accesses
material.

`EnvironmentHmacBackend` is the only concrete backend implemented in this
module: it loads secret material from environment variables (stdlib only,
no file, no network, no KMS call) and signs with HMAC-SHA256. Exchanges
that authenticate REST requests via an HMAC-signed API secret can use this
directly; a wallet/ECDSA-signing exchange (e.g. Hyperliquid's EIP-712
signing) needs a backend capable of secp256k1 signing, which is outside
this module's stdlib-only scope and belongs to a future backend
implementation (or to the Exchange Adapter module, with explicit
authorization to add a cryptography dependency at that time).
"""

import abc
import hashlib
import hmac
import os
import re
from typing import Dict, FrozenSet, List, Mapping, Optional

_ENV_VAR_PREFIX = "TURTLE_SECRET_"


def _env_var_name(ref: str) -> str:
    return f"{_ENV_VAR_PREFIX}{ref.upper()}"


def _zero(buf: bytearray) -> None:
    """Best-effort zeroization of a mutable buffer.

    This overwrites the bytearray's own backing memory, which is real and
    effective for the bytearray itself. It cannot reach the original
    `str` object CPython read from `os.environ` (Python strings are
    immutable and the interpreter may have interned or copied that data
    before this module ever saw it) -- that is an inherent limitation of
    using environment variables as a secret store in Python, not a defect
    in this function. Operators should still avoid leaving raw secrets in
    the parent process's environment beyond what is required.
    """
    for i in range(len(buf)):
        buf[i] = 0


class SigningBackend(abc.ABC):
    """Abstract signing backend. A concrete backend owns how secret
    material is located and how signing is performed; it never hands raw
    material back to the caller."""

    @abc.abstractmethod
    def validate_and_load(self, refs: FrozenSet[str]) -> List[str]:
        """Attempt to resolve every reference in `refs` to usable material.

        Returns a list of human-readable issue strings (empty if all
        references resolved successfully). Must not raise for ordinary
        resolution failures -- the caller (SigningBoundary) decides how to
        surface issues. Must never include secret material in any issue
        string.
        """

    @abc.abstractmethod
    def sign(self, ref: str, message: bytes) -> bytes:
        """Sign `message` using the material for `ref`. Only called by
        SigningBoundary after it has confirmed `ref` is known and not
        revoked."""

    @abc.abstractmethod
    def discard(self, ref: str) -> None:
        """Irreversibly destroy any material held for `ref`, if any.
        Subsequent sign() calls for this ref must fail. Idempotent."""


class EnvironmentHmacBackend(SigningBackend):
    """Loads secret material from environment variables named
    `TURTLE_SECRET_<REF_UPPERCASED>` and signs with HMAC-SHA256.

    Stdlib only (hmac, hashlib, os). Immutable after successful
    validate_and_load, aside from discard()'s one-way zeroization.
    """

    def __init__(self, env: Optional[Mapping[str, str]] = None):
        self._env = os.environ if env is None else env
        self._materials: Dict[str, bytearray] = {}
        object.__setattr__(self, "_loaded", False)

    def validate_and_load(self, refs: FrozenSet[str]) -> List[str]:
        if self._loaded:
            raise RuntimeError("EnvironmentHmacBackend.validate_and_load() called more than once")

        issues: List[str] = []
        materials: Dict[str, bytearray] = {}

        for ref in sorted(refs):
            var_name = _env_var_name(ref)
            raw = self._env.get(var_name)
            if raw is None:
                issues.append(f"missing secret: environment variable '{var_name}' is not set (reference '{ref}')")
                continue
            if raw == "":
                issues.append(f"empty secret: environment variable '{var_name}' is set but empty (reference '{ref}')")
                continue
            materials[ref] = bytearray(raw.encode("utf-8"))

        issues.extend(_find_duplicate_values(materials))

        if issues:
            for buf in materials.values():
                _zero(buf)
            return issues

        self._materials = materials
        object.__setattr__(self, "_loaded", True)
        return []

    def sign(self, ref: str, message: bytes) -> bytes:
        material = self._materials.get(ref)
        if material is None:
            # SigningBoundary is expected to have already rejected unknown
            # or revoked references; this guards the backend against being
            # used directly, out of band, without that check.
            raise KeyError(f"no material loaded for reference '{ref}'")
        return hmac.new(bytes(material), message, hashlib.sha256).digest()

    def discard(self, ref: str) -> None:
        buf = self._materials.pop(ref, None)
        if buf is not None:
            _zero(buf)

    def __repr__(self) -> str:
        return f"EnvironmentHmacBackend(refs={sorted(self._materials.keys())!r})"

    __str__ = __repr__

    def __getstate__(self):
        raise TypeError("EnvironmentHmacBackend cannot be pickled or serialized -- it holds secret material")

    def __deepcopy__(self, memo):
        raise TypeError("EnvironmentHmacBackend cannot be deep-copied -- it holds secret material")


def _find_duplicate_values(materials: Dict[str, bytearray]) -> List[str]:
    """Constant-time pairwise comparison of loaded secret material, to
    catch two different reference names accidentally pointing at the same
    physical secret (an operational-hygiene misconfiguration)."""
    issues: List[str] = []
    refs = list(materials.keys())
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            a, b = refs[i], refs[j]
            if hmac.compare_digest(bytes(materials[a]), bytes(materials[b])):
                issues.append(
                    f"secret references '{a}' and '{b}' resolve to identical secret material -- "
                    "each reference must map to distinct material"
                )
    return issues
