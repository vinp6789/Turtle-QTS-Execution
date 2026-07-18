"""Hyperliquid /exchange mutation-transport foundation (Module 10, WP-6).

Dependency-free (stdlib only): nonce generation and the POST-body envelope
for authenticated /exchange requests. It does NOT construct order actions
(that, with its msgpack action-hash serialization, is WP-8) and it does
NOT transmit -- the actual POST goes through the existing transport.post_json
seam. This module only assembles the envelope and issues monotonic nonces.
"""

import threading
import time
from typing import Callable, Optional

# Hyperliquid's documented /exchange endpoint path.
EXCHANGE_PATH = "/exchange"


class NonceSource:
    """Thread-safe, strictly-increasing millisecond nonce source.

    Hyperliquid requires each signed action to carry a nonce that is recent
    and larger than the account's last-used nonce. Milliseconds-since-epoch
    satisfies "recent"; forcing strict monotonicity (never returning a value
    <= the previous one, even if the clock is read twice within the same
    millisecond or steps backward) satisfies "larger than last".
    """

    def __init__(self, clock_ms: Optional[Callable[[], int]] = None):
        self._clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self._lock = threading.Lock()
        self._last = 0

    def next(self) -> int:
        with self._lock:
            now = self._clock_ms()
            nonce = now if now > self._last else self._last + 1
            self._last = nonce
            return nonce


def build_exchange_request(action: dict, nonce: int, signature: dict, vault_address: Optional[str] = None) -> dict:
    """Assemble the /exchange POST body from an already-built action dict,
    a nonce, and an already-produced signature. Pure: no signing, no
    network, no action construction. The result is JSON-serializable by
    transport.post_json.

    signature is Hyperliquid's shape {"r","s","v"}; vault_address is None
    for a normal (non-vault) account.
    """
    if not isinstance(action, dict):
        raise ValueError("action must be a dict")
    if not isinstance(nonce, int) or isinstance(nonce, bool) or nonce <= 0:
        raise ValueError("nonce must be a positive int")
    if not (isinstance(signature, dict) and {"r", "s", "v"} <= set(signature)):
        raise ValueError("signature must be a dict with r, s, v")
    return {
        "action": action,
        "nonce": nonce,
        "signature": signature,
        "vaultAddress": vault_address,
    }
