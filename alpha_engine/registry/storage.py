"""Storage abstraction for the Experiment Registry.

ExperimentRegistry (registry.py) depends only on RegistryStorage's two
methods -- append() and read_all() -- and has no knowledge of how or
where entries are physically kept. This is the entire seam a future
backend (SQLite, Postgres, or anything else) plugs into, with zero
change to registry business logic or any higher Alpha Engine layer. Per
alpha_engine/DECISIONS.md (D1), Milestone 0.2 ships exactly one
implementation: FileRegistryStorage, a plain, fsync'd, append-only
JSON-Lines log. Treat that choice as an implementation detail, not a
closed architectural decision -- this file is precisely what makes it
swappable.

Hardening (audit finding B3): a real-money deployment cannot assume a
single writer, a clean shutdown, or a bit-perfect disk. This module now
provides, proportionate to a line-delimited JSON log (not a rewrite into
the frozen Module 3 EventStore's binary/magic/version framing, which
would be a redesign this finding does not call for):

  - Single-writer exclusive locking: append() takes an exclusive,
    non-blocking, cross-platform file lock for the duration of the write.
    The locking primitive is INTENTIONALLY a from-scratch, minimal
    implementation local to this module rather than an import of the
    frozen event_store._locking equivalent -- alpha_engine has a
    standing, tested architectural boundary (test_alpha_engine_scaffold.
    py's TestNoFrozenModuleCoupling) forbidding any import of a frozen,
    mutation-capable Execution Engine package, event_store included, and
    that boundary is not something this finding calls for crossing.
    Duplicating ~15 lines of stdlib fcntl/msvcrt calls is a smaller,
    safer footprint than the coupling would be. Two FileRegistryStorage
    instances (same or different process) can no longer interleave
    writes and corrupt a line.
  - Per-entry checksum: each written line carries a "_checksum" field
    (SHA-256 over the canonical JSON of the entry's own fields). On read,
    a line WITH a checksum is verified; a mismatch on any line that is
    not the trailing line raises MalformedRegistryLogError (corruption a
    clean crash cannot explain). A line with no "_checksum" (written
    before this fix) is accepted unverified -- backward compatible with
    every log already on disk.
  - Torn-tail tolerance: a genuinely truncated final line (interrupted
    mid-flush by a crash, so it fails to parse as JSON at all) is
    silently discarded rather than failing the entire replay -- but ONLY
    when it is the last line in the file. The same parse failure on any
    earlier line still raises: a crash during append cannot corrupt
    already-fsync'd earlier lines, so that can only be genuine
    corruption.
"""

import hashlib
import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, List, Mapping, Union

from .errors import MalformedRegistryLogError, RegistryLockError

try:
    import fcntl  # POSIX only
except ImportError:  # pragma: no cover - exercised only off-POSIX
    fcntl = None  # type: ignore[assignment]

try:
    import msvcrt  # Windows only
except ImportError:  # pragma: no cover - exercised only on Windows
    msvcrt = None  # type: ignore[assignment]

# A single sentinel byte, locked purely as a mutual-exclusion token (not
# real data) -- see event_store._locking for the identical, independently
# maintained rationale for this exact technique. Kept local (not
# imported) per alpha_engine's standing no-frozen-coupling boundary; see
# this module's docstring.
_WIN_LOCK_OFFSET = 1 << 62
_WIN_LOCK_NBYTES = 1

_CHECKSUM_KEY = "_checksum"


def _entry_checksum(entry_without_checksum: Mapping[str, Any]) -> str:
    canonical = json.dumps(entry_without_checksum, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _acquire_exclusive_nonblocking(fd: int) -> None:
    """Raises OSError immediately if another holder already owns the lock."""
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return
    if msvcrt is not None:
        saved = os.lseek(fd, 0, os.SEEK_CUR)
        try:
            os.lseek(fd, _WIN_LOCK_OFFSET, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, _WIN_LOCK_NBYTES)
        finally:
            os.lseek(fd, saved, os.SEEK_SET)
        return
    raise OSError("no supported file-locking mechanism on this platform")


def _release_lock(fd: int) -> None:
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return
    if msvcrt is not None:
        saved = os.lseek(fd, 0, os.SEEK_CUR)
        try:
            os.lseek(fd, _WIN_LOCK_OFFSET, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, _WIN_LOCK_NBYTES)
        finally:
            os.lseek(fd, saved, os.SEEK_SET)
        return
    raise OSError("no supported file-locking mechanism on this platform")


class RegistryStorage(ABC):
    """The entire seam a storage backend must satisfy. Both methods deal
    only in plain, JSON-serializable mappings -- no knowledge of
    ExperimentRecord, sealing, or lineage belongs here; that is
    ExperimentRegistry's job (registry.py)."""

    @abstractmethod
    def append(self, entry: Mapping[str, Any]) -> None:
        """Durably appends one entry. Must preserve insertion order for
        read_all() -- the registry replays entries in the order
        returned."""
        raise NotImplementedError

    @abstractmethod
    def read_all(self) -> List[Mapping[str, Any]]:
        """Returns every entry ever appended, in append order. Empty list
        for a store with nothing written yet."""
        raise NotImplementedError


def _write_full(fd: int, data: bytes) -> None:
    """Write every byte of `data`, looping over short writes -- os.write()
    is permitted by POSIX to write fewer bytes than requested without
    raising; treating a partial count as success could silently truncate
    a record on disk. Same guarantee as event_store.store's own helper,
    kept local rather than imported since it is a private implementation
    detail of that module, not part of its public seam."""
    view = memoryview(data)
    total = 0
    while total < len(view):
        written = os.write(fd, view[total:])
        if written <= 0:
            raise OSError("os.write() made no progress")
        total += written


class FileRegistryStorage(RegistryStorage):
    """Append-only, fsync'd JSON-Lines file: one JSON object per line,
    each line carrying a per-entry checksum (B3). Plain JSON-Lines framing
    (not the frozen Module 3 EventStore's binary magic/version/checksum
    record format -- that would be a redesign this finding does not call
    for): a JSON-Lines entry is self-delimited by its own newline, and
    json.loads() tolerates the trailing '\\r' Windows text mode would add;
    writes here use binary mode only because the exclusive lock (below)
    needs a raw fd, not because framing requires it.

    Locking: append() acquires a cross-platform exclusive, non-blocking
    sentinel-byte lock (a local, from-scratch equivalent of event_store's
    -- see module docstring for why it is not imported), held only for
    the duration of one append -- unlike EventStore, this class does not
    hold a persistent open file handle across its lifetime, so there is
    no session-long lock to acquire at construction. This still closes
    the concrete gap the audit found: two writers (two processes, or two
    FileRegistryStorage instances in one process) can no longer
    interleave partial writes into the same line.
    """

    def __init__(self, path: Union[str, Path]):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: Mapping[str, Any]) -> None:
        entry_dict = dict(entry)
        checksummed = dict(entry_dict)
        checksummed[_CHECKSUM_KEY] = _entry_checksum(entry_dict)
        payload = (json.dumps(checksummed, sort_keys=True) + "\n").encode("utf-8")

        fd = os.open(
            str(self._path),
            os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0),
            0o600,
        )
        try:
            try:
                _acquire_exclusive_nonblocking(fd)
            except OSError as exc:
                raise RegistryLockError(
                    f"{self._path}: already locked by another writer: {exc}"
                ) from exc
            try:
                _write_full(fd, payload)
                os.fsync(fd)
            finally:
                _release_lock(fd)
        finally:
            os.close(fd)

    def read_all(self) -> List[Mapping[str, Any]]:
        if not self._path.is_file():
            return []
        with open(self._path, "r", encoding="utf-8") as f:
            raw_lines = f.readlines()

        # Strip trailing blank lines first so "the last line" (torn-tail
        # candidate, below) means the last line with actual content.
        stripped = [line.strip() for line in raw_lines]
        last_content_index = None
        for index in range(len(stripped) - 1, -1, -1):
            if stripped[index]:
                last_content_index = index
                break

        entries: List[Mapping[str, Any]] = []
        for line_number, line in enumerate(stripped, start=1):
            if not line:
                continue
            is_last_content_line = (line_number - 1) == last_content_index
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                if is_last_content_line:
                    # Torn tail (B3): an interrupted final flush leaves an
                    # incomplete line only at the true end of the file --
                    # a clean crash-during-append cannot corrupt earlier,
                    # already-fsync'd lines. Recoverable: discard silently.
                    break
                raise MalformedRegistryLogError(
                    f"{self._path}: line {line_number} is not valid JSON: {exc}"
                ) from exc

            if isinstance(parsed, dict) and _CHECKSUM_KEY in parsed:
                claimed = parsed[_CHECKSUM_KEY]
                without_checksum = {k: v for k, v in parsed.items() if k != _CHECKSUM_KEY}
                actual = _entry_checksum(without_checksum)
                if claimed != actual:
                    if is_last_content_line:
                        # A checksum-verified-corrupt tail is just as
                        # recoverable a torn write as an unparseable one.
                        break
                    raise MalformedRegistryLogError(
                        f"{self._path}: line {line_number} failed checksum verification "
                        f"(expected {actual!r}, found {claimed!r}) -- corruption a clean "
                        "crash during append cannot explain"
                    )
                parsed = without_checksum
            # A line with no "_checksum" key is a pre-B3 entry -- accepted
            # unverified, preserving backward compatibility with logs
            # written before this fix.
            entries.append(parsed)
        return entries

    def __repr__(self) -> str:
        return f"FileRegistryStorage(path={str(self._path)!r})"

    __str__ = __repr__
