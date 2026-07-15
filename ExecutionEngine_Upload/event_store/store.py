"""Append-only, crash-safe Event Store and Idempotency Ledger.

Single responsibility: durably record events in strict append-only order,
detect corruption and torn writes, and provide a replay API that always
rebuilds identical state from the same file. No business logic: this
module does not interpret event_type semantics, does not trigger side
effects, and does not validate payload shape beyond "well-formed JSON
within size limits, containing no field names that look like secret
material."

Two ways to read events back:
  - EventStore.replay(): fast, from the in-memory state of a store that
    holds the write lock and has already validated the whole file.
  - read_events(path): a standalone, lock-free, read-only function that
    can be called from a separate process (e.g. a future Audit Trail
    reader) while the owning EventStore process is still appending. It
    never mutates the file, even if it finds a torn tail.
"""

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from ._locking import acquire_exclusive_nonblocking, release_lock
from .codec import (
    RecordDecodeBadMagic,
    RecordDecodeChecksumMismatch,
    RecordDecodeIncomplete,
    RecordDecodeUnsupportedVersion,
    decode_record,
    encode_record,
)
from .errors import (
    CorruptEventStoreError,
    EventStoreClosedError,
    EventStoreLockError,
    MalformedEventError,
)
from .types import Event, EventType, RecoveryReport

MAX_PAYLOAD_BYTES = 256 * 1024
MAX_IDEMPOTENCY_KEY_LENGTH = 200

# Field-name heuristic, not a value-shape heuristic: scanning values for
# "looks like a key" would false-positive on legitimate 0x-prefixed
# transaction/order hashes. Scanning field NAMES for secret-suggestive
# names catches the realistic accidental-leak case (a field literally
# called "private_key" or "api_key") without rejecting normal exchange
# data. Best-effort, same spirit as Module 2's secret-reference guard.
_FORBIDDEN_KEY_SUBSTRINGS = (
    "secret", "private_key", "priv_key", "password", "passphrase",
    "api_key", "signing_key", "mnemonic", "seed_phrase",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _scan_forbidden_keys(value: Any, path: str = "") -> Optional[str]:
    if isinstance(value, dict):
        for k, v in value.items():
            lowered = str(k).lower()
            if any(bad in lowered for bad in _FORBIDDEN_KEY_SUBSTRINGS):
                return f"{path}.{k}" if path else str(k)
            found = _scan_forbidden_keys(v, f"{path}.{k}" if path else str(k))
            if found:
                return found
    elif isinstance(value, list):
        for i, item in enumerate(value):
            found = _scan_forbidden_keys(item, f"{path}[{i}]")
            if found:
                return found
    return None


def _envelope_to_event(event_id: int, envelope: Dict[str, Any]) -> Event:
    return Event(
        event_id=event_id,
        event_type=EventType(envelope["event_type"]),
        timestamp_utc=envelope["timestamp_utc"],
        schema_version=envelope["schema_version"],
        idempotency_key=envelope.get("idempotency_key"),
        payload=envelope["payload"],
    )


def _scan_file(path: Path) -> Tuple[List[Event], RecoveryReport, int]:
    """Pure, read-only scan of the log file at `path`. Never mutates the
    file. Returns (events, recovery_report, last_valid_offset).

    Raises CorruptEventStoreError for anything a crash-during-append
    cannot explain: bad magic, an unsupported format version, a
    checksum-mismatched record that is not at the true end of the file,
    or a non-monotonic/duplicate event_id.
    """
    if not path.exists():
        return [], RecoveryReport(valid_event_count=0, tail_truncated=False, discarded_byte_count=0), 0

    data = path.read_bytes()
    events: List[Event] = []
    offset = 0
    last_event_id: Optional[int] = None
    tail_truncated = False

    while offset < len(data):
        try:
            record = decode_record(data, offset)
        except RecordDecodeIncomplete:
            # Can only happen at the true end of the file (see codec.py) --
            # always a safe-to-recover torn tail-write.
            tail_truncated = True
            break
        except RecordDecodeBadMagic as exc:
            raise CorruptEventStoreError(f"corrupt event record at byte offset {offset}: {exc}") from exc
        except RecordDecodeUnsupportedVersion as exc:
            raise CorruptEventStoreError(f"unsupported record format at byte offset {offset}: {exc}") from exc
        except RecordDecodeChecksumMismatch as exc:
            if exc.end_offset == len(data):
                # This record's claimed span reaches exactly to the true
                # end of file -- consistent with a torn write corrupting
                # only the tail (e.g. an interrupted final flush).
                tail_truncated = True
                break
            # Valid-looking bytes exist AFTER this corrupt record's claimed
            # end. A crash can only ever truncate the tail, never leave
            # further content past a corrupted record -- this is genuine
            # mid-file corruption.
            raise CorruptEventStoreError(f"corrupt event record at byte offset {offset}: {exc}") from exc

        envelope = json.loads(record.payload_bytes.decode("utf-8"))
        event = _envelope_to_event(record.event_id, envelope)

        if last_event_id is not None and event.event_id <= last_event_id:
            raise CorruptEventStoreError(
                f"non-monotonic or duplicate event_id {event.event_id} "
                f"following {last_event_id} at byte offset {offset}"
            )
        last_event_id = event.event_id

        events.append(event)
        offset += record.consumed_bytes

    report = RecoveryReport(
        valid_event_count=len(events),
        tail_truncated=tail_truncated,
        discarded_byte_count=len(data) - offset,
    )
    return events, report, offset


def read_events(path: Union[str, Path]) -> Tuple[Tuple[Event, ...], RecoveryReport]:
    """Read-only replay API. Does not open the file for writing, does not
    take a lock, and never modifies the file -- safe to call concurrently
    with a live EventStore in another process. Raises
    CorruptEventStoreError under the same conditions as EventStore itself."""
    events, report, _ = _scan_file(Path(path))
    return tuple(events), report


def _write_full(fd: int, data: bytes) -> None:
    """Write every byte of `data` to `fd`, looping over short writes.

    os.write() is permitted by POSIX to write fewer bytes than requested
    without raising. Treating that partial count as success would let a
    record be silently truncated on disk while the caller believes it
    fully succeeded -- exactly the "third state" (neither a complete
    record nor a safely-detectable torn tail) this store must never
    produce.
    """
    view = memoryview(data)
    total = 0
    while total < len(view):
        written = os.write(fd, view[total:])
        if written <= 0:
            raise OSError("os.write() made no progress")
        total += written


class EventStore:
    """Single-writer, crash-safe, append-only event log.

    Exactly one EventStore may hold the write lock on a given path at a
    time (enforced via an exclusive, non-blocking flock). On construction
    it validates the entire existing file and, if it finds a torn tail
    left over from a crash during a previous append, truncates exactly
    that tail before accepting any new writes.
    """

    def __init__(self, path: Union[str, Path]):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._closed = False

        self._fd = os.open(str(self._path), os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            acquire_exclusive_nonblocking(self._fd)
        except OSError as exc:
            os.close(self._fd)
            raise EventStoreLockError(
                f"could not acquire exclusive lock on {self._path} -- "
                "another process may already have it open for writing"
            ) from exc

        try:
            events, report, last_valid_offset = _scan_file(self._path)

            if report.tail_truncated and report.discarded_byte_count > 0:
                # Safe here specifically because this instance holds the
                # exclusive write lock -- read_events() never does this.
                os.ftruncate(self._fd, last_valid_offset)
                os.fsync(self._fd)
        except BaseException:
            # Any failure past this point must not leak the exclusive
            # lock or the file descriptor -- otherwise no future process
            # (including a corrected retry) could ever open this store.
            release_lock(self._fd)
            os.close(self._fd)
            raise

        os.lseek(self._fd, 0, os.SEEK_END)

        self._events: List[Event] = events
        self._by_id: Dict[int, Event] = {e.event_id: e for e in events}
        self._idempotency_index: Dict[str, int] = {
            e.idempotency_key: e.event_id for e in events if e.idempotency_key is not None
        }
        self._next_event_id = (events[-1].event_id + 1) if events else 1
        self.recovery_report = report

    # -- validation ----------------------------------------------------

    def _validate_new_event(self, event_type, payload, idempotency_key, schema_version) -> None:
        issues = []
        if not isinstance(event_type, EventType):
            issues.append(f"event_type must be an EventType member, got {type(event_type).__name__}")
        if not isinstance(payload, dict):
            issues.append(f"payload must be a dict, got {type(payload).__name__}")
        if not isinstance(schema_version, int) or isinstance(schema_version, bool) or schema_version < 1:
            issues.append(f"schema_version must be a positive integer, got {schema_version!r}")
        if idempotency_key is not None:
            if not isinstance(idempotency_key, str) or not idempotency_key.strip():
                issues.append("idempotency_key must be a non-empty string when provided")
            elif len(idempotency_key) > MAX_IDEMPOTENCY_KEY_LENGTH:
                issues.append(f"idempotency_key exceeds {MAX_IDEMPOTENCY_KEY_LENGTH} characters")
        if issues:
            raise MalformedEventError("; ".join(issues))

        forbidden = _scan_forbidden_keys(payload)
        if forbidden:
            raise MalformedEventError(
                f"payload field '{forbidden}' has a name suggesting secret material -- "
                "events must never carry secrets; store a reference instead"
            )
        try:
            canonical = _canonical_json(payload)
        except (TypeError, ValueError) as exc:
            raise MalformedEventError(f"payload is not JSON-serializable: {exc}") from exc
        if len(canonical) > MAX_PAYLOAD_BYTES:
            raise MalformedEventError(
                f"payload is {len(canonical)} bytes, exceeding the {MAX_PAYLOAD_BYTES}-byte limit"
            )

    # -- public API ------------------------------------------------------

    def append(
        self,
        event_type: EventType,
        payload: Dict[str, Any],
        idempotency_key: Optional[str] = None,
        schema_version: int = 1,
    ) -> Event:
        """Durably append a new event and return it. If `idempotency_key`
        matches a previously appended event, no new event is written --
        the original event is returned unchanged (idempotent no-op), which
        is what makes it safe for a caller to retry the same exchange
        action after a crash without risking a duplicate."""
        if self._closed:
            raise EventStoreClosedError("cannot append to a closed EventStore")
        self._validate_new_event(event_type, payload, idempotency_key, schema_version)

        with self._lock:
            if idempotency_key is not None and idempotency_key in self._idempotency_index:
                return self._by_id[self._idempotency_index[idempotency_key]]

            event_id = self._next_event_id
            envelope = {
                "event_type": event_type.value,
                "timestamp_utc": _utc_now_iso(),
                "schema_version": schema_version,
                "idempotency_key": idempotency_key,
                "payload": payload,
            }
            payload_bytes = _canonical_json(envelope)
            record_bytes = encode_record(event_id, payload_bytes)

            pre_write_offset = os.lseek(self._fd, 0, os.SEEK_CUR)
            try:
                _write_full(self._fd, record_bytes)
                os.fsync(self._fd)
            except BaseException:
                # Never leave a partial record on disk, even on a failure
                # that isn't a process crash (e.g. ENOSPC mid-write): a
                # short write followed by a later, unrelated append would
                # otherwise leave this truncated record stranded in the
                # MIDDLE of the file, which on next open is indistinguishable
                # from genuine corruption. Roll back to exactly where this
                # append started and let the caller retry.
                os.ftruncate(self._fd, pre_write_offset)
                os.fsync(self._fd)
                raise

            event = _envelope_to_event(event_id, envelope)
            self._events.append(event)
            self._by_id[event_id] = event
            if idempotency_key is not None:
                self._idempotency_index[idempotency_key] = event_id
            self._next_event_id += 1
            return event

    def replay(self, from_event_id: int = 1) -> Iterator[Event]:
        """Yield already-validated events in ascending event_id order,
        from a stable snapshot taken at call time. Read-only: never
        mutates store state."""
        if self._closed:
            raise EventStoreClosedError("cannot replay a closed EventStore")
        for event in list(self._events):
            if event.event_id >= from_event_id:
                yield event

    def has_idempotency_key(self, key: str) -> bool:
        return key in self._idempotency_index

    def get_by_idempotency_key(self, key: str) -> Optional[Event]:
        event_id = self._idempotency_index.get(key)
        return self._by_id.get(event_id) if event_id is not None else None

    @property
    def event_count(self) -> int:
        return len(self._events)

    @property
    def next_event_id(self) -> int:
        return self._next_event_id

    def close(self) -> None:
        if self._closed:
            return
        try:
            release_lock(self._fd)
        finally:
            os.close(self._fd)
            self._closed = True

    def __enter__(self) -> "EventStore":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"EventStore(path={str(self._path)!r}, event_count={len(self._events)}, closed={self._closed})"

    __str__ = __repr__
