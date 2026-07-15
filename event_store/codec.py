"""Binary record framing for the Event Store's append-only log file.

Each record on disk, in order:

    MAGIC            4 bytes    b"TQEV"
    FORMAT_VERSION   1 byte     on-disk framing version (currently 1)
    EVENT_ID         8 bytes    big-endian unsigned, monotonic
    PAYLOAD_LENGTH   4 bytes    big-endian unsigned
    PAYLOAD          N bytes    UTF-8 JSON (N = PAYLOAD_LENGTH)
    CHECKSUM         32 bytes   SHA-256 over everything above

This module has no business logic and no opinion on payload contents; it
only frames and verifies bytes. store.py owns all recovery-classification
decisions (torn tail vs. genuine corruption); this module only reports,
via distinct exception types, exactly what went wrong so store.py can make
that call precisely rather than guessing.
"""

import hashlib
import struct
from dataclasses import dataclass

MAGIC = b"TQEV"
FORMAT_VERSION = 1
CHECKSUM_SIZE = 32
_HEADER_TAIL_STRUCT = struct.Struct(">BQI")  # format_version, event_id, payload_length
HEADER_SIZE = len(MAGIC) + _HEADER_TAIL_STRUCT.size
RECORD_OVERHEAD = HEADER_SIZE + CHECKSUM_SIZE


def encode_record(event_id: int, payload_bytes: bytes) -> bytes:
    header = MAGIC + _HEADER_TAIL_STRUCT.pack(FORMAT_VERSION, event_id, len(payload_bytes))
    checksum = hashlib.sha256(header + payload_bytes).digest()
    return header + payload_bytes + checksum


@dataclass(frozen=True)
class DecodedRecord:
    event_id: int
    payload_bytes: bytes
    consumed_bytes: int


class RecordDecodeError(Exception):
    """Base class for all record-decode failures."""


class RecordDecodeIncomplete(RecordDecodeError):
    """Fewer bytes are present than the framing requires to complete this
    record. Because a single record is written by one os.write() call
    starting with MAGIC, a torn write can only ever produce a byte-exact
    PREFIX of an intended record -- so an incomplete record can only occur
    at the true end of the file, and is always safe to treat as a torn
    tail-write from a crash during append."""


class RecordDecodeBadMagic(RecordDecodeError):
    """The magic bytes at this offset are present but wrong.

    This can NOT be produced by a torn write: MAGIC is the first four
    bytes written, so a short write either includes all of MAGIC correctly
    or includes none of it (and would raise RecordDecodeIncomplete
    instead). Wrong-but-present magic bytes mean the file has been
    corrupted or tampered with after the fact, or the reader is not
    positioned at a true record boundary. Always treated as a hard
    failure, regardless of position in the file.
    """


class RecordDecodeUnsupportedVersion(RecordDecodeError):
    """The record's framing version is not one this reader understands.
    Not corruption -- most likely the file was written by a newer,
    incompatible version of this module. Always a hard failure."""


class RecordDecodeChecksumMismatch(RecordDecodeError):
    """A full-length record was read but its checksum does not match.

    Carries `end_offset`, the absolute byte offset where this record
    claims to end, so the caller can determine whether this is a torn
    tail-write (claimed end == true end of file, e.g. corruption of the
    last few checksum bytes during an interrupted flush) or genuine
    mid-file corruption (claimed end < true end of file, meaning valid
    trailing bytes exist beyond a record that shouldn't be there)."""

    def __init__(self, message: str, end_offset: int):
        super().__init__(message)
        self.end_offset = end_offset


def decode_record(buf: bytes, offset: int) -> DecodedRecord:
    """Decode one record starting at buf[offset:]."""
    available = len(buf) - offset

    if available < len(MAGIC):
        raise RecordDecodeIncomplete("not enough bytes to read magic")

    magic = buf[offset: offset + len(MAGIC)]
    if magic != MAGIC:
        raise RecordDecodeBadMagic(f"bad magic bytes at offset {offset}")

    if available < HEADER_SIZE:
        raise RecordDecodeIncomplete("not enough bytes for record header")

    tail_off = offset + len(MAGIC)
    format_version, event_id, payload_length = _HEADER_TAIL_STRUCT.unpack_from(buf, tail_off)
    if format_version != FORMAT_VERSION:
        raise RecordDecodeUnsupportedVersion(
            f"unsupported record format version {format_version} at offset {offset}"
        )

    payload_start = offset + HEADER_SIZE
    payload_end = payload_start + payload_length
    checksum_end = payload_end + CHECKSUM_SIZE
    if len(buf) < checksum_end:
        raise RecordDecodeIncomplete("not enough bytes for declared payload and checksum")

    payload_bytes = buf[payload_start:payload_end]
    checksum = buf[payload_end:checksum_end]
    header = buf[offset:payload_start]
    expected_checksum = hashlib.sha256(header + payload_bytes).digest()
    if checksum != expected_checksum:
        raise RecordDecodeChecksumMismatch(f"checksum mismatch at offset {offset}", end_offset=checksum_end)

    return DecodedRecord(event_id=event_id, payload_bytes=payload_bytes, consumed_bytes=checksum_end - offset)
