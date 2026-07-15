"""Event Store / Idempotency Ledger for the Turtle Execution Engine.

Single responsibility: durable, append-only, crash-safe event sourcing
with an idempotency ledger for exchange actions. No business logic --
this module does not interpret event_type semantics or trigger side
effects; it only records and replays.

Public API:
    EventStore(path)             -- single-writer, locked, self-healing
    read_events(path)            -- standalone, lock-free, read-only replay
    EventType                    -- closed enum of supported event categories
    Event                        -- immutable, deep-frozen event record
    RecoveryReport                -- summary produced on open/read
"""

from .errors import (
    CorruptEventStoreError,
    EventStoreClosedError,
    EventStoreError,
    EventStoreLockError,
    MalformedEventError,
)
from .store import MAX_IDEMPOTENCY_KEY_LENGTH, MAX_PAYLOAD_BYTES, EventStore, read_events
from .types import Event, EventType, RecoveryReport

__all__ = [
    "EventStore",
    "read_events",
    "EventType",
    "Event",
    "RecoveryReport",
    "MAX_PAYLOAD_BYTES",
    "MAX_IDEMPOTENCY_KEY_LENGTH",
    "EventStoreError",
    "MalformedEventError",
    "CorruptEventStoreError",
    "EventStoreLockError",
    "EventStoreClosedError",
]
