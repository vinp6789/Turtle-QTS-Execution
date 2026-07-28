"""Canonical UTC timestamp handling (audit finding B5).

The audit demonstrated that ordering ISO-8601 timestamps as raw STRINGS
is chronologically wrong the moment two producers use different offsets
("2026-01-01T05:00:00+05:00" is midnight UTC but string-sorts after
"2026-01-01T00:00:01+00:00"), different suffix conventions (Z vs
+00:00), or different fractional-second precision. Every chronological
comparison, duplicate key, and content fingerprint in the Alpha Engine
now goes through this module instead:

  - parse_utc(): tolerant parse (naive treated as UTC, Z accepted),
    returning an aware datetime for CORRECT temporal comparison.
  - canonical_utc(): the single canonical rendering (UTC, +00:00 offset,
    fixed microsecond precision) used wherever a timestamp participates
    in a hash or an equality key, so equal instants are equal strings.

Stored values are left as supplied (rewriting them inside frozen value
types would ripple through every layer); comparisons and fingerprints
are what must be canonical, and now are.
"""

from datetime import datetime, timezone


def parse_utc(value: str) -> datetime:
    """Parses an ISO-8601 string to an aware UTC datetime. Accepts a
    trailing 'Z', treats a naive timestamp as UTC. Raises ValueError for
    anything unparseable -- timestamps are configuration-grade data;
    garbage must fail loudly, never sort arbitrarily."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"timestamp must be a non-empty string, got {value!r}")
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def canonical_utc(value: str) -> str:
    """The canonical string form of a timestamp: UTC, +00:00, fixed
    microsecond precision. Equal instants map to equal strings
    regardless of the producer's formatting."""
    return parse_utc(value).isoformat(timespec="microseconds")
