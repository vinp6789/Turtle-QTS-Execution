"""Hyperliquid venue signing (Module 10, WP-6/7).

Produces the EIP-712 "phantom agent" secp256k1 signature Hyperliquid's
/exchange endpoint requires for authenticated (capital-moving) actions.

WHY THIS IS SEPARATE FROM SigningBoundary (ADR-20/ADR-24, established):
SigningBoundary.sign() unconditionally wraps every message in Turtle's
domain-separated preimage (secrets_boundary/boundary.py), so a signature
it produces is over Turtle's preimage -- which no exchange will accept.
SigningBoundary therefore stays the *authorization gate* (Emergency Kill
via revocation), and venue-format signatures are produced HERE, by a
separate signer keyed on wallet_key_ref (Module 1.1). This mirrors, but
does not route through, the frozen boundary.

SECURITY DISCIPLINE (mirrors secrets_boundary, never weaker):
  - The raw wallet private key never leaves this object: no public
    accessor, no __repr__/__str__ exposure, no pickling, no deep-copy.
  - revoke() is one-way (Emergency Kill): after it, signing raises and the
    key reference is dropped. It cannot be un-revoked on a live instance.
  - Only the wallet ADDRESS (public) is exposed, for audit/logging.
  - As with EnvironmentHmacBackend, the raw key is read from an env var
    (TURTLE_SECRET_<REF>); Python cannot zeroize the immutable str the
    interpreter already holds -- an inherent env-var-store limitation
    documented there and unchanged here.

DEPENDENCY: eth-account (approved, WP-6/7). Imported lazily so the rest of
Module 10 and Modules 1-9 import with the dependency absent; only
constructing a signer requires it.
"""

import threading
from typing import Mapping, Optional

from exchange_adapter import ExchangeAdapterError, ExchangeAuthenticationError

try:  # lazy/guarded: package import must not require eth-account
    from eth_account import Account as _Account
    from eth_account.messages import encode_typed_data as _encode_typed_data
    _IMPORT_ERROR: Optional[ImportError] = None
except ImportError as _exc:  # pragma: no cover - exercised only without the dep
    _Account = None
    _encode_typed_data = None
    _IMPORT_ERROR = _exc

# Hyperliquid L1-action phantom-agent EIP-712 context (fixed by the venue).
_DOMAIN = {
    "name": "Exchange",
    "version": "1",
    "chainId": 1337,
    "verifyingContract": "0x" + "00" * 20,
}
_TYPES = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "Agent": [
        {"name": "source", "type": "string"},
        {"name": "connectionId", "type": "bytes32"},
    ],
}
# mainnet actions carry source "a"; testnet "b". This binds a signature to
# a network -- a testnet signature can never be replayed on mainnet.
_SOURCE_MAINNET = "a"
_SOURCE_TESTNET = "b"

_ENV_VAR_PREFIX = "TURTLE_SECRET_"  # matches secrets_boundary.backend convention


def _env_var_name(ref: str) -> str:
    return f"{_ENV_VAR_PREFIX}{ref.upper()}"


class HyperliquidWalletSigner:
    """Holds a Hyperliquid wallet key (referenced by wallet_key_ref) and
    signs action hashes with the venue's phantom-agent EIP-712 scheme.

    Construction resolves the key from the environment and validates it;
    it never exposes the key thereafter. `is_mainnet` fixes the network
    source, so a signer cannot be tricked into producing a mainnet
    signature on a testnet deployment or vice versa.
    """

    def __init__(self, wallet_key_ref: str, is_mainnet: bool, env: Optional[Mapping[str, str]] = None):
        if _Account is None:
            raise ExchangeAdapterError(
                "eth-account is required for Hyperliquid wallet signing but is not "
                f"installed ({_IMPORT_ERROR}). Install eth-account (>=0.13.5)."
            )
        if not isinstance(wallet_key_ref, str) or not wallet_key_ref.strip():
            raise ValueError("wallet_key_ref must be a non-empty string")
        if not isinstance(is_mainnet, bool):
            raise ValueError("is_mainnet must be a bool")

        import os

        environ = os.environ if env is None else env
        var = _env_var_name(wallet_key_ref)
        raw = environ.get(var)
        if raw is None or not raw.strip():
            # A missing/blank signing identity is an authentication-config
            # failure -- RetryPolicy never auto-retries this class.
            raise ExchangeAuthenticationError(
                f"wallet key for ref '{wallet_key_ref}' not found: environment "
                f"variable '{var}' is unset or empty"
            )
        try:
            account = _Account.from_key(raw.strip())
        except Exception as exc:  # eth-account raises ValueError/BadFunctionCallOutput-family on bad keys
            raise ExchangeAuthenticationError(
                f"wallet key for ref '{wallet_key_ref}' is not a valid secp256k1 key"
            ) from exc

        self._wallet_key_ref = wallet_key_ref
        self._source = _SOURCE_MAINNET if is_mainnet else _SOURCE_TESTNET
        self._account = account  # eth-account LocalAccount; holds the key privately
        self._address = account.address
        self._revoked = False
        # Guards the revoked-flag / account pair so that a concurrent revoke()
        # (Emergency Kill) can never be observed half-applied: sign either sees
        # a valid account or raises ExchangeAuthenticationError -- never a raw
        # AttributeError from a nulled account.
        self._lock = threading.Lock()
        # Drop the local reference to the raw key string (best-effort; the
        # interpreter may retain interned copies -- see module docstring).
        del raw

    @property
    def wallet_address(self) -> str:
        """The public wallet address (safe to log/audit). Never the key."""
        return self._address

    @property
    def is_revoked(self) -> bool:
        return self._revoked

    @property
    def is_mainnet(self) -> bool:
        """True if this signer produces mainnet-source ('a') signatures.
        The network is fixed at construction and bound into every signature,
        so it cannot be changed and a signature cannot be replayed across
        networks. Exposed (read-only) so the adapter can reject a
        base_url/network mismatch."""
        return self._source == _SOURCE_MAINNET

    def sign_connection_id(self, connection_id: bytes) -> dict:
        """Sign a 32-byte Hyperliquid action hash (connectionId) with the
        phantom-agent EIP-712 scheme. Returns Hyperliquid's signature
        shape: {"r": "0x..", "s": "0x..", "v": int}.

        Raises ExchangeAuthenticationError if the signer has been revoked
        (Emergency Kill) -- never auto-retried by RetryPolicy.

        Concurrency: the revoked-check and account capture happen atomically
        under the lock, so a concurrent revoke() is observed as either fully
        before (this raises cleanly) or fully after (a valid account was
        already captured). The actual EIP-712 signing runs OUTSIDE the lock on
        the captured local reference -- so revoke() never blocks on the crypto
        op, and the captured account can never be nulled mid-sign. The only
        outcomes are a signature or ExchangeAuthenticationError."""
        with self._lock:
            if self._revoked:
                raise ExchangeAuthenticationError("wallet signer has been revoked and can no longer sign")
            account = self._account  # captured atomically with the not-revoked check
        if not isinstance(connection_id, (bytes, bytearray)) or len(connection_id) != 32:
            raise ValueError("connection_id must be exactly 32 bytes")

        typed = {
            "domain": _DOMAIN,
            "types": _TYPES,
            "primaryType": "Agent",
            "message": {"source": self._source, "connectionId": bytes(connection_id)},
        }
        signable = _encode_typed_data(full_message=typed)
        signed = account.sign_message(signable)  # local ref -> never None
        return {
            "r": "0x" + format(signed.r, "064x"),
            "s": "0x" + format(signed.s, "064x"),
            "v": signed.v,
        }

    def revoke(self) -> None:
        """Permanently disable signing on this instance (Emergency Kill's
        wallet-key lever) and drop the key reference. One-way, idempotent.
        Atomic with sign_connection_id's check/capture via the lock."""
        with self._lock:
            self._revoked = True
            self._account = None

    def __repr__(self) -> str:
        # Public deployment context only -- address and revoked flag, never
        # key material. Mirrors SigningBoundary.__repr__.
        return f"HyperliquidWalletSigner(address={self._address!r}, revoked={self._revoked})"

    __str__ = __repr__

    def __getstate__(self):
        raise TypeError("HyperliquidWalletSigner cannot be pickled -- it holds wallet key material")

    def __deepcopy__(self, memo):
        raise TypeError("HyperliquidWalletSigner cannot be deep-copied -- it holds wallet key material")
