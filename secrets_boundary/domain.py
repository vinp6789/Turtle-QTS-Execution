"""Cryptographic domain separation for the Secrets & Signing Boundary.

Every signature this engine produces is bound to four independent context
values, so a signature obtained in one context can never be replayed as a
valid signature in another:

    1. A fixed engine identifier  ("TurtleExecutionEngine")
    2. The engine version         (e.g. "1.0.0")
    3. The exchange name          (e.g. "hyperliquid")
    4. The signing purpose        (ORDER, CANCEL, AMEND, AUTH, FLATTEN, QUERY, NOTIFY)

Without this, a signature over an order payload could be presented as a
cancel, or a signature produced against a testnet adapter could be reused
against mainnet. Domain separation makes each of those a distinct
cryptographic context by construction.

Encoding is unambiguous: each field is length-prefixed with a 4-byte
big-endian length before its bytes. Length-prefixing (rather than a
separator character) means no combination of field values can ever produce
the same preimage as a different combination -- a canonical-encoding
property that separator-based schemes do not have.
"""

import struct
from enum import Enum
from typing import Final

ENGINE_ID: Final[bytes] = b"TurtleExecutionEngine"

# Maximum message accepted for signing. A legitimate order, cancel, or auth
# payload is a few hundred bytes at most; anything approaching this bound is
# a bug or an abuse attempt, not a real trading action.
MAX_SIGNING_PAYLOAD_BYTES: Final[int] = 64 * 1024


class SigningPurpose(Enum):
    """The set of contexts in which this engine is permitted to sign.

    A closed enum, not a free-form string: an adapter cannot invent a new
    signing context at runtime, and every context that exists is auditable
    from this one declaration.
    """

    ORDER = "ORDER"
    CANCEL = "CANCEL"
    AMEND = "AMEND"
    AUTH = "AUTH"
    FLATTEN = "FLATTEN"
    QUERY = "QUERY"
    NOTIFY = "NOTIFY"


def _field(value: bytes) -> bytes:
    return struct.pack(">I", len(value)) + value


def build_preimage(
    engine_version: str,
    exchange_name: str,
    purpose: SigningPurpose,
    message: bytes,
) -> bytes:
    """Construct the canonical, domain-separated preimage that is actually
    signed. The caller's `message` is never signed directly -- only this
    preimage is."""
    return (
        _field(ENGINE_ID)
        + _field(engine_version.encode("utf-8"))
        + _field(exchange_name.encode("utf-8"))
        + _field(purpose.value.encode("utf-8"))
        + _field(message)
    )
