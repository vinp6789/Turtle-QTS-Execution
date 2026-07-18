"""Durable engine-id <-> venue-token mapping (Module 10, mechanism M1).

Records, in the shared canonical EventStore, which venue client token
(Hyperliquid cloid) each engine client_order_id was transmitted with, so
venue-returned data can be attributed back to engine orders after a
restart without parsing engine-id structure and without any parallel
persistence mechanism.

Invariant obligations implemented here (see the approved catalogue):
  INV-2  Tokens are minted by hashing the id's opaque bytes -- the id's
         internal structure is never inspected, parsed or reconstructed.
  INV-5  record() appends the mapping fsync-durably (EventStore.append
         returns only after fsync) BEFORE returning; callers must
         transmit only a token returned by record(), which makes
         persist-before-transmit structural. record() without a durable
         store raises rather than degrading silently.
  INV-6  Minting is deterministic (same id -> same token), and record()
         returns the token from the DURABLY STORED event (first-writer-
         wins), never a freshly minted candidate. Because BOTH the token
         and the idempotency key derive from the same fixed minting
         function, the stored and freshly-minted tokens are always equal
         under the current scheme; record() returns the stored one on
         principle (the durable log is authoritative).
  INV-7  Tokens are the first 128 bits of SHA-256 over the id bytes;
         collision within a deployment's order-id population is
         negligible (not impossible), and record() DETECTS any collision
         via the stored-event client_order_id check -- a collision fails
         loudly, it is never silently merged.
  INV-8  Token format is "0x" + 32 lowercase hex chars (16 bytes), the
         venue's documented cloid shape.
  INV-9  Idempotency keys are source-tag-first (a literal prefix distinct
         from every frozen writer's tag) and length-prefix the account,
         with a fixed-length terminal token -- making the key injective
         over (account, id) and unable to collide with any other module's
         keys. record() additionally verifies that any deduplicated event
         it receives back is genuinely its own.
  INV-10 Every mapping event carries this module's source tag plus the
         account address; rebuild() replays exactly those events.
  INV-12 Payload field names contain none of event_store's forbidden
         substrings; payloads carry no secret material (a cloid is a
         public order tag, not key material).
  INV-13 The in-memory map is a pure function of this module's own
         events in log order; no other module's payload schema is read.

Event-type note: mapping events reuse EventType.ORDER_SUBMITTED rather
than extending Module 3's closed enum, following the repository's
documented best-fit pattern ("the coarse category is cosmetic, the
payload's own action/details fields are authoritative for replay" --
portfolio_manager/manager.py). Every frozen consumer filters on
payload["source"] before anything else, so these events are invisible to
Modules 4/6/7/8. They are adapter-private (INV-11): no other module may
consume them.
"""

import hashlib
from typing import Dict, Optional

from event_store import EventStore, EventType

from exchange_adapter import ExchangeAdapterError

_SOURCE_TAG = "hyperliquid_adapter"
_ACTION = "venue_order_mapped"


def mint_venue_token(client_order_id: str) -> str:
    """Deterministically derive the venue client token (cloid) for an
    engine client_order_id, treating the id as opaque bytes (INV-2).
    "0x" + first 32 hex chars of SHA-256 = a 16-byte cloid (INV-8)."""
    digest = hashlib.sha256(client_order_id.encode("utf-8")).hexdigest()
    return "0x" + digest[:32]


def _idempotency_key(account: str, client_order_id: str) -> str:
    # Source-tag-first: the "hyperliquid_adapter:" literal prefix differs
    # from every frozen writer's tag, so this key cannot collide with any
    # other module's keys regardless of their internal structure. The
    # account is length-prefixed and the token is a fixed-length terminal
    # component, making the key injective over (account, id). (Same
    # collision-avoidance goal as machine.py's _namespaced_key, though that
    # scheme length-prefixes both of its components.) The id is represented
    # by its BOUNDED venue token rather than embedded raw: Module 5 permits
    # arbitrary-length ids, which would blow event_store's 200-char key
    # cap. The token is a deterministic function of the id, so the key is
    # stable per (account, id); a token collision (INV-7) would surface as
    # a mismatched-client_order_id check in record() (INV-9), never a
    # silent merge. Fixed length ~100 chars.
    return f"{_SOURCE_TAG}:{len(account)}:{account}:{mint_venue_token(client_order_id)}"


class OrderIdMapping:
    """Bidirectional engine-id <-> venue-token map, durable via the shared
    EventStore.

    `store=None` builds a read-only instance with a permanently EMPTY map:
    record() REFUSES to run without a durable store (INV-5), so no mapping
    can ever be added, and resolve()/known_token() therefore always return
    None. A storeless adapter can still serve public market data and
    correctly reports zero engine-owned orders/fills; it can never be used
    on a path that transmits orders.
    """

    def __init__(self, account: str, store: Optional[EventStore]):
        if not isinstance(account, str) or not account.strip():
            raise ValueError("account must be a non-empty string")
        self._account = account
        self._store = store
        self._token_to_cid: Dict[str, str] = {}
        self._cid_to_token: Dict[str, str] = {}
        if store is not None:
            for event in store.replay():
                if self._is_own(event):
                    self._apply(event)

    # -- event identity / application (INV-10, INV-13) --

    def _is_own(self, event) -> bool:
        payload = event.payload
        return (
            payload.get("source") == _SOURCE_TAG
            and payload.get("account") == self._account
            and payload.get("action") == _ACTION
        )

    def _apply(self, event) -> None:
        cid = event.payload.get("client_order_id")
        token = event.payload.get("venue_client_id")
        if cid and token:
            self._token_to_cid[token] = cid
            self._cid_to_token[cid] = token

    # -- write path (INV-5, INV-6, INV-7, INV-9, INV-12) --

    def record(self, client_order_id: str) -> str:
        """Durably record the mapping for `client_order_id` and return the
        venue token that MUST be the one transmitted (INV-6). Appends
        before returning (INV-5); idempotent (re-recording returns the
        original durable token)."""
        if self._store is None:
            raise ExchangeAdapterError(
                "a durable EventStore is required before any order can be "
                "transmitted -- refusing to record a venue-token mapping "
                "in memory only (INV-5: persist-before-transmit)"
            )
        known = self._cid_to_token.get(client_order_id)
        if known is not None:
            return known

        token = mint_venue_token(client_order_id)
        payload = {
            "source": _SOURCE_TAG,
            "account": self._account,
            "action": _ACTION,
            "venue": "hyperliquid",
            "client_order_id": client_order_id,
            "venue_client_id": token,
        }
        event = self._store.append(
            EventType.ORDER_SUBMITTED, payload, idempotency_key=_idempotency_key(self._account, client_order_id)
        )

        # INV-9: first-writer-wins may hand back a pre-existing event under
        # this key. It must be OUR mapping event for THIS id -- anything
        # else is a namespace collision and must fail loudly, never be
        # silently trusted.
        if not self._is_own(event) or event.payload.get("client_order_id") != client_order_id:
            raise ExchangeAdapterError(
                "idempotency-key collision: the event stored under this mapping's "
                "key does not belong to this adapter/account/order -- refusing to "
                "proceed (INV-9)"
            )
        stored_token = event.payload.get("venue_client_id")
        if not stored_token:
            raise ExchangeAdapterError("stored mapping event carries no venue_client_id -- log inconsistency")
        # INV-6: the DURABLE token wins. With deterministic minting these
        # are always equal; if a future minting-scheme change ever made
        # them differ, transmitting the stored one keeps the venue and the
        # log in agreement.
        self._apply(event)
        return stored_token

    # -- read paths --

    def resolve(self, venue_token: str) -> Optional[str]:
        """venue token -> engine client_order_id, or None if this adapter
        instance has no record of it (foreign or never-recorded). Never
        fabricates (INV-4)."""
        return self._token_to_cid.get(venue_token)

    def known_token(self, client_order_id: str) -> Optional[str]:
        """engine id -> durably recorded token, if any. Read-only: never
        mints, never appends."""
        return self._cid_to_token.get(client_order_id)

    def __len__(self) -> int:
        return len(self._token_to_cid)
