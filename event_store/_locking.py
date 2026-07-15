"""Cross-platform single-writer exclusive file locking for the Event Store.

Additive portability shim. It exposes exactly the two lock operations the
Event Store already relied on, with byte-identical semantics on POSIX and
an equivalent implementation on Windows:

  * exclusive     -- at most one holder at a time, across processes;
  * non-blocking  -- acquisition fails immediately (raises OSError) if
                     another holder exists, never waits;
  * releasable    -- released explicitly on close and on init failure.

POSIX keeps its original behavior verbatim: fcntl.flock with
LOCK_EX | LOCK_NB to acquire and LOCK_UN to release (a whole-file
*advisory* lock). Windows uses msvcrt.locking with LK_NBLCK / LK_UNLCK
over a single sentinel byte at a fixed offset far beyond any real data.

Both paths raise OSError on contention, which store.py already maps to
EventStoreLockError, so callers observe identical behavior on both
platforms. See store.py's module docstring and the audit notes for the
one behavioral difference this cannot erase (advisory vs mandatory), and
why the sentinel offset is chosen to keep read_events() concurrency-safe.
"""

import os

try:
    import fcntl  # POSIX only
except ImportError:  # pragma: no cover - exercised only off-POSIX
    fcntl = None  # type: ignore[assignment]

try:
    import msvcrt  # Windows only
except ImportError:  # pragma: no cover - exercised only on Windows
    msvcrt = None  # type: ignore[assignment]

# msvcrt.locking() locks a byte RANGE starting at the current file
# position -- not the file as an object the way flock does. We therefore
# lock a single sentinel byte used purely as a mutual-exclusion token.
#
# The offset MUST sit beyond every byte that read_events() reads. On
# Windows msvcrt locks are *mandatory*: a lock overlapping real data
# would block the standalone, lock-free read_events() reader in another
# process, breaking a documented guarantee. 2**62 is astronomically
# beyond any event log yet well within a 64-bit file offset, and locking
# beyond EOF is permitted on Windows -- so the token never overlaps a
# record, an append, or a recovery truncate, and never blocks a reader.
_WIN_LOCK_OFFSET = 1 << 62
_WIN_LOCK_NBYTES = 1


def acquire_exclusive_nonblocking(fd: int) -> None:
    """Acquire an exclusive, non-blocking lock on open descriptor `fd`.

    Raises OSError immediately if another holder already owns the lock.
    """
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return
    if msvcrt is not None:
        _win_lock(fd, msvcrt.LK_NBLCK)
        return
    raise OSError("no supported file-locking mechanism on this platform")


def release_lock(fd: int) -> None:
    """Release a lock previously taken with acquire_exclusive_nonblocking."""
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return
    if msvcrt is not None:
        _win_lock(fd, msvcrt.LK_UNLCK)
        return
    raise OSError("no supported file-locking mechanism on this platform")


def _win_lock(fd: int, mode: int) -> None:  # pragma: no cover - Windows only
    """Lock/unlock the sentinel byte, restoring the file position so this
    shim has no observable side effect on the caller's cursor."""
    saved = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        os.lseek(fd, _WIN_LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(fd, mode, _WIN_LOCK_NBYTES)
    finally:
        os.lseek(fd, saved, os.SEEK_SET)
