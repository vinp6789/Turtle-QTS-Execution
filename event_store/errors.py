"""Exceptions raised by the Event Store."""


class EventStoreError(Exception):
    """Base exception for all Event Store failures."""


class MalformedEventError(EventStoreError):
    """Raised when an event passed to append() fails structural
    validation: wrong types, non-JSON-serializable payload, oversized
    payload, or a payload field name that suggests secret material."""


class CorruptEventStoreError(EventStoreError):
    """Raised when the log file contains data that cannot be explained by
    a crash during append (mid-file corruption, bad magic, unsupported
    format version, or a non-monotonic/duplicate event_id). Never raised
    for an ordinary torn tail-write, which is recovered automatically
    instead."""


class EventStoreLockError(EventStoreError):
    """Raised when the log file is already locked for writing by another
    process (or another EventStore instance in this one)."""


class EventStoreClosedError(EventStoreError):
    """Raised when append() or replay() is called after close()."""
