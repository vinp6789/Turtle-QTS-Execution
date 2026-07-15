"""Event types and immutable data objects for the Event Store.

EventType is a closed enum covering only the event categories future
modules will need. This module does not implement, validate the semantic
correctness of, or react to any of these -- it only stores and replays
them. Business meaning belongs entirely to the modules that append and
later interpret these events.
"""

import types as _types
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional


class EventType(Enum):
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_ACKNOWLEDGED = "ORDER_ACKNOWLEDGED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_UPDATED = "POSITION_UPDATED"
    POSITION_CLOSED = "POSITION_CLOSED"
    STOP_UPDATED = "STOP_UPDATED"
    TAKE_PROFIT_UPDATED = "TAKE_PROFIT_UPDATED"
    KILL_SWITCH_TRIGGERED = "KILL_SWITCH_TRIGGERED"
    HEALTH_ALERT = "HEALTH_ALERT"
    SYSTEM_STARTED = "SYSTEM_STARTED"
    SYSTEM_STOPPED = "SYSTEM_STOPPED"


def _deep_freeze(value: Any) -> Any:
    """Recursively convert dicts to MappingProxyType and lists to tuples.

    The stdlib has no single deep-frozen container, so this composes the
    two immutable/read-only primitives it does have to give a payload
    genuine deep immutability rather than only a frozen top level.
    """
    if isinstance(value, dict):
        return _types.MappingProxyType({k: _deep_freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(v) for v in value)
    return value


@dataclass(frozen=True)
class Event:
    """An immutable, already-durable event. Never constructed directly by
    callers -- produced only by EventStore.append() or by replay."""

    event_id: int
    event_type: EventType
    timestamp_utc: str
    schema_version: int
    idempotency_key: Optional[str]
    payload: Mapping[str, Any]

    def __post_init__(self):
        object.__setattr__(self, "payload", _deep_freeze(dict(self.payload)))


@dataclass(frozen=True)
class RecoveryReport:
    """Summary of what happened when a log file was scanned/opened."""

    valid_event_count: int
    tail_truncated: bool
    discarded_byte_count: int
