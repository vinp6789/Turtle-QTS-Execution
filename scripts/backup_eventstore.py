"""Timestamped, read-only backup of the durable event store.

The EventStore is an append-only log; copying the file byte-for-byte while
the engine runs is safe (a torn tail, if any, is simply carried into the
copy and would be truncated on next open -- exactly as the live file would
be). This never mutates the source.

Usage:
    python scripts/backup_eventstore.py [--store PATH] [--out DIR]

Defaults: store = $ENGINE_STORE_PATH or data/events.log ; out = data/backups
"""

import argparse
import datetime as _dt
import os
import shutil
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup the Turtle event store.")
    parser.add_argument("--store", default=os.environ.get("ENGINE_STORE_PATH", "data/events.log"))
    parser.add_argument("--out", default="data/backups")
    args = parser.parse_args()

    src = Path(args.store)
    if not src.is_file():
        print(f"NOTHING TO BACK UP: {src} does not exist yet.", file=sys.stderr)
        return 0  # not an error -- a fresh deploy has no store yet

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = out_dir / f"{src.stem}-{stamp}{src.suffix}"
    shutil.copy2(src, dest)
    print(f"OK: backed up {src} -> {dest} ({dest.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
