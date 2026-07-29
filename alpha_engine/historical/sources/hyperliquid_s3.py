"""Hyperliquid's own official S3 archive of block-batched fills -- the
historical LIQUIDATION source (RD-10 Step 2).

Everything below was live-measured by the RD-10 Step 1 probe, not assumed:

  - Bucket `hl-mainnet-node-data`, region `ap-northeast-1`, **Requester
    Pays** (the caller's AWS account is billed for requests and transfer).
  - Layout: `node_fills_by_block/hourly/YYYYMMDD/H.lz4` -- exactly one
    object per hour, hour unpadded ("3.lz4", not "03.lz4").
  - Earliest object measured: 2025-07-27 (partial day, from hour 10);
    first complete day 2025-07-28.
  - LZ4-frame compressed, ~4.8x ratio; ~10-56 MB compressed per hour.
  - Payload: newline-delimited JSON, one BLOCK per line:
      {"local_time", "block_time", "block_number",
       "events": [[<user_address>, <fill_object>], ...]}
  - A fill carries an OPTIONAL `liquidation` sub-object:
      {"liquidatedUser", "markPx", "method"}
    Measured: 328 of 107,066 fills in one sampled hour (0.31%), and 100%
    of occurrences were non-null -- the key is absent when inapplicable,
    never null-filled.
  - ONE liquidation surfaces as TWO paired fills sharing a single `tid`
    (liquidator side and liquidated side). Both are emitted here; which
    side is meaningful is a research question, not this module's.

SCOPE (RD-10 Step 2): discovery, incremental download, and decode into
LiquidationObservation. Nothing else -- no backfill driver, no research
logic, no generic S3 layer, no transport abstraction. This module is the
Hyperliquid-S3 sibling of `sources/binance.py` and `sources/hyperliquid.py`
and follows their shape: concrete, self-contained, independently
reviewable.

PLATFORM INDEPENDENCE (Constitution §5): boto3's own default credential
chain is used, so the SAME code authenticates from environment variables
(Railway, Docker, Kubernetes) or a shared credentials file (laptop, VPS)
with no branch and no change. Bucket, prefix, region and checkpoint path
are parameters with documented defaults -- never hardcoded at a call
site, never read from a platform-specific location. No `os.name`/
`sys.platform` check exists anywhere in this module.

boto3 is imported lazily inside the functions that need it so that
importing this module (and therefore the whole historical package) never
requires the optional AWS dependency.
"""

import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from exchange_adapter import Symbol

from ..errors import HistoricalDataError
from ..models import LiquidationObservation

_logger = logging.getLogger(__name__)

SOURCE_NAME = "hyperliquid_s3"
DEFAULT_BUCKET = "hl-mainnet-node-data"
DEFAULT_PREFIX = "node_fills_by_block/hourly/"
DEFAULT_REGION = "ap-northeast-1"
EARLIEST_MEASURED_DATE = "20250727"


def _client(region: str):
    """boto3 S3 client using boto3's own default credential chain --
    env vars, shared credentials file, or instance role, whichever the
    deployment provides. No credential is read, stored, or logged here."""
    try:
        import boto3  # noqa: PLC0415 -- optional dependency, imported lazily by design
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise HistoricalDataError(
            "boto3 is required for the hyperliquid_s3 source but is not installed"
        ) from exc
    return boto3.client("s3", region_name=region)


def list_hour_keys(
    *,
    date: str,
    bucket: str = DEFAULT_BUCKET,
    prefix: str = DEFAULT_PREFIX,
    region: str = DEFAULT_REGION,
    client: Any = None,
) -> Tuple[str, ...]:
    """Every hourly object key for one YYYYMMDD date, sorted by hour.

    Sorted NUMERICALLY by hour, not lexicographically: the measured names
    are unpadded, so a string sort would order 10 before 2."""
    if not isinstance(date, str) or len(date) != 8 or not date.isdigit():
        raise HistoricalDataError(f"date must be YYYYMMDD, got {date!r}")
    s3 = client or _client(region)
    resp = s3.list_objects_v2(
        Bucket=bucket, Prefix=f"{prefix}{date}/", RequestPayer="requester"
    )
    keys = [c["Key"] for c in resp.get("Contents", ())]

    def _hour(key: str) -> int:
        stem = key.rsplit("/", 1)[-1].split(".", 1)[0]
        return int(stem) if stem.isdigit() else -1

    return tuple(sorted(keys, key=_hour))


def list_dates(
    *,
    bucket: str = DEFAULT_BUCKET,
    prefix: str = DEFAULT_PREFIX,
    region: str = DEFAULT_REGION,
    client: Any = None,
) -> Tuple[str, ...]:
    """Every YYYYMMDD date directory present in the archive, ascending."""
    s3 = client or _client(region)
    dates: List[str] = []
    token: Optional[str] = None
    while True:
        kwargs: Dict[str, Any] = {
            "Bucket": bucket, "Prefix": prefix, "Delimiter": "/", "RequestPayer": "requester",
        }
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        for cp in resp.get("CommonPrefixes", ()):
            dates.append(cp["Prefix"].rstrip("/").rsplit("/", 1)[-1])
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return tuple(sorted(dates))


def _decimal(raw: Any, field: str, key: str) -> Decimal:
    try:
        return Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise HistoricalDataError(f"{key}: {field} {raw!r} is not a valid decimal") from exc


def decode_liquidations(
    payload: bytes,
    *,
    key: str,
    symbols: Optional[Tuple[Symbol, ...]] = None,
    ingested_at_utc: Optional[str] = None,
) -> Tuple[LiquidationObservation, ...]:
    """Decodes one decompressed hourly object into LiquidationObservations.

    Only fills carrying a non-null `liquidation` sub-object are emitted;
    every other fill is ignored. A malformed line raises (a parsing error
    is a configuration/data-integrity problem, never a silently dropped
    row), but a fill missing `liquidation` is simply not a liquidation and
    is skipped without comment.

    `symbols`, when given, restricts output to that watchlist; None emits
    every symbol present."""
    if not isinstance(payload, bytes):
        raise HistoricalDataError(f"payload must be bytes, got {type(payload).__name__}")
    wanted = {s.value for s in symbols} if symbols else None
    ingested = ingested_at_utc or datetime.now(timezone.utc).isoformat()

    out: List[LiquidationObservation] = []
    for line_no, line in enumerate(payload.decode("utf-8", "strict").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            block = json.loads(line)
        except ValueError as exc:
            raise HistoricalDataError(f"{key}: line {line_no} is not valid JSON: {exc}") from exc
        for event in block.get("events") or ():
            # Measured shape: [<user_address>, <fill_object>]
            if not (isinstance(event, list) and len(event) == 2 and isinstance(event[1], dict)):
                continue
            fill = event[1]
            liq = fill.get("liquidation")
            if not liq:
                continue
            coin = fill.get("coin")
            if wanted is not None and coin not in wanted:
                continue
            observed_ms = fill.get("time")
            if not isinstance(observed_ms, int):
                raise HistoricalDataError(f"{key}: fill has non-integer time {observed_ms!r}")
            out.append(LiquidationObservation(
                symbol=Symbol(coin),
                observed_at_utc=datetime.fromtimestamp(
                    observed_ms / 1000, tz=timezone.utc
                ).isoformat(),
                price=_decimal(fill.get("px"), "px", key),
                size=_decimal(fill.get("sz"), "sz", key),
                side=str(fill.get("side")),
                direction=str(fill.get("dir")),
                method=str(liq.get("method")),
                liquidated_user=str(liq.get("liquidatedUser")),
                mark_price=_decimal(liq.get("markPx"), "markPx", key),
                tid=int(fill["tid"]),
                source=SOURCE_NAME,
                source_detail=key,
                ingested_at_utc=ingested,
            ))
    return tuple(out)


def fetch_hour(
    key: str,
    *,
    bucket: str = DEFAULT_BUCKET,
    region: str = DEFAULT_REGION,
    symbols: Optional[Tuple[Symbol, ...]] = None,
    client: Any = None,
) -> Tuple[LiquidationObservation, ...]:
    """Downloads and decodes exactly one hourly object (Requester Pays)."""
    try:
        import lz4.frame  # noqa: PLC0415 -- optional dependency, imported lazily by design
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise HistoricalDataError(
            "lz4 is required for the hyperliquid_s3 source but is not installed"
        ) from exc
    s3 = client or _client(region)
    body = s3.get_object(Bucket=bucket, Key=key, RequestPayer="requester")["Body"].read()
    return decode_liquidations(lz4.frame.decompress(body), key=key, symbols=symbols)


# --- checkpoint -------------------------------------------------------
# Deliberately a plain JSON file holding the last fully-processed object
# key. Not a framework, not a state machine: one value, read and written
# by two functions. The key is the checkpoint because keys sort into
# processing order (date, then numeric hour), so "newer than" is decidable
# without any clock or external state -- which is what makes resume
# deterministic and identical on every platform.

def read_checkpoint(path: Union[str, Path]) -> Optional[str]:
    """Last fully-processed object key, or None if none exists yet."""
    p = Path(path)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise HistoricalDataError(f"{p}: checkpoint is not valid JSON: {exc}") from exc
    key = data.get("last_processed_key")
    return key if isinstance(key, str) and key else None


def _fsync_dir(directory: Path) -> None:
    """fsync the DIRECTORY entry so the rename itself is durable.

    POSIX-only in practice: Windows cannot open a directory for fsync, and
    NTFS does not require it for rename durability. Deliberately
    best-effort and never raises -- a failure here cannot corrupt the file,
    which write_checkpoint has already fsync'd before renaming."""
    try:
        fd = os.open(str(directory), getattr(os, "O_RDONLY", 0))
    except (OSError, AttributeError, ValueError):
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def write_checkpoint(path: Union[str, Path], last_processed_key: str) -> None:
    """Persists the checkpoint durably: write -> flush -> fsync(file) ->
    atomic os.replace -> best-effort fsync(parent directory).

    WHY THE fsync IS LOAD-BEARING (measured, not theoretical): an earlier
    version wrote the temp file and renamed it WITHOUT fsync. os.replace is
    atomic at the rename level, but the file's data blocks were still in
    the OS page cache -- so when the pilot backfill process was killed, the
    directory entry survived with the correct SIZE while the contents were
    never flushed, leaving a 68-byte checkpoint of pure NUL bytes and an
    unrecoverable resume point. fsync'ing the data BEFORE the rename is
    what makes the rename publish durable bytes rather than a promise of
    them."""
    if not isinstance(last_processed_key, str) or not last_processed_key.strip():
        raise HistoricalDataError("last_processed_key must be a non-empty string")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    payload = json.dumps({"last_processed_key": last_processed_key}, sort_keys=True)
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, p)
    _fsync_dir(p.parent)


def sort_key(key: str) -> Tuple[str, int]:
    """Processing order for an hourly key: (YYYYMMDD, hour-as-int).

    Hour must sort numerically -- the measured names are unpadded, so a
    plain string comparison would place "10" before "2"."""
    parts = key.rstrip("/").split("/")
    stem = parts[-1].split(".", 1)[0]
    return (parts[-2] if len(parts) >= 2 else "", int(stem) if stem.isdigit() else -1)


def keys_after_checkpoint(
    keys: Tuple[str, ...], checkpoint: Optional[str]
) -> Tuple[str, ...]:
    """The subset of `keys` strictly newer than `checkpoint`, in processing
    order. With no checkpoint every key is returned. Already-processed
    hours are never returned, so they are never re-downloaded."""
    ordered = tuple(sorted(keys, key=sort_key))
    if checkpoint is None:
        return ordered
    limit = sort_key(checkpoint)
    return tuple(k for k in ordered if sort_key(k) > limit)
