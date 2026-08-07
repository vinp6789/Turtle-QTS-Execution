"""Append-only equity history: the substrate every business metric reads.

WHY THIS EXISTS AT ALL. Realised PnL is reconstructible from the event
store (ORDER_FILLED / POSITION_*), but UNREALISED PnL depends on the mark
at that instant and marks are never persisted. A point-in-time equity
series therefore cannot be derived from replay() and needs its own
record. This is the only thing here that is genuinely new.

WHAT IS REUSED, NOT REBUILT. Every value written is read straight off
PortfolioSnapshot (portfolio_manager/snapshot.py), which AccountingSync
already refreshes before each cycle. NOTHING is recomputed here -- no
accounting logic is duplicated, and this module owns no arithmetic beyond
selecting fields. If a number is wrong, it is wrong in the portfolio
manager, not here.

DESIGNED FOR TASK 2, NOT ONLY TASK 1. The schema carries every input the
business-metrics engine will need, so no migration follows:

  Sharpe / rolling returns  <- equity + observed_at_utc (a return series)
  CAGR                      <- first/last equity + elapsed time
  Max drawdown              <- the equity path
  Cost attribution          <- fees_cumulative and funding_cumulative,
                               kept SEPARATE (they are different costs)
  Exposure / leverage stats <- exposure, heat, used_margin
  Trade-count cross-checks  <- open_position_count

THE FIELD MOST EQUITY LOGS OMIT, AND WHY IT IS HERE. deposits_cumulative
and withdrawals_cumulative are recorded on every row. Without them a
capital inflow is indistinguishable from a gain, and every return-based
metric (Sharpe, CAGR, total return) is silently wrong the first time
capital moves. Task 2 must compute returns on equity NET of flows; the
data to do that is present from row one.

GUARANTEES
  append-only    -- opened "a", never rewritten, never truncated
  restart-safe   -- state recovered by reading the last line on open
  deterministic  -- no clock and no RNG here; the timestamp is the
                    snapshot's own updated_at_utc
  no duplicates  -- a row whose idempotency key matches the last written
                    row is a no-op, so a replayed or retried cycle cannot
                    double-write
  replay-safe    -- one JSON object per line; a torn final line (crash
                    mid-write) is detected and ignored on read
"""

import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

SCHEMA_VERSION = 1


def _d(value) -> str:
    """Decimals are written as strings, for the same reason every other
    Decimal in this repository is: canonical JSON must never round-trip a
    monetary quantity through a binary float."""
    return str(value if value is not None else Decimal("0"))


def row_from_snapshot(snapshot, *, cycle_seq: int, strategy_names=()) -> Dict[str, Any]:
    """One measurement row, read straight off PortfolioSnapshot.

    Pure: no I/O, no clock, no arithmetic beyond field selection. Every
    monetary field is the portfolio manager's own figure.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "cycle_seq": int(cycle_seq),
        "observed_at_utc": snapshot.updated_at_utc,
        # --- equity and its decomposition
        "equity": _d(snapshot.equity),
        "wallet_balance": _d(snapshot.wallet_balance),
        "available_cash": _d(snapshot.available_cash),
        "unrealized_pnl": _d(snapshot.unrealized_pnl),
        "realized_pnl_cumulative": _d(snapshot.realized_pnl_cumulative),
        # --- costs, kept separate: fees and funding are different costs
        #     and Task 2's cost attribution must not merge them
        "fees_cumulative": _d(snapshot.fees_cumulative),
        "funding_cumulative": _d(snapshot.funding_cumulative),
        # --- capital flows: without these, a deposit reads as a gain
        "deposits_cumulative": _d(snapshot.deposits_cumulative),
        "withdrawals_cumulative": _d(snapshot.withdrawals_cumulative),
        # --- risk / exposure
        "exposure": _d(snapshot.exposure),
        "heat": _d(snapshot.heat),
        "used_margin": _d(snapshot.used_margin),
        "reserved_margin": _d(snapshot.reserved_margin),
        # --- positions
        "open_position_count": len(snapshot.open_position_ids),
        "open_position_ids": list(snapshot.open_position_ids),
        # --- provenance: which book produced this row
        "strategies": list(strategy_names),
    }


def idempotency_key(row: Dict[str, Any]) -> str:
    """A row's identity. Two rows for the same cycle at the same instant
    are the same observation, however many times a cycle is retried."""
    return f"{row['cycle_seq']}:{row['observed_at_utc']}"


class EquityLog:
    """Append-only JSONL equity history.

    Mirrors the durability discipline already used by
    alpha_engine/historical/storage.py (flush + fsync before returning),
    rather than inventing a second one.
    """

    def __init__(self, path: Union[str, Path]):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._last_key: Optional[str] = None
        self._last_seq: int = -1
        self._recover()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def last_cycle_seq(self) -> int:
        """Highest cycle_seq durably written; -1 when the log is empty."""
        return self._last_seq

    def _recover(self) -> None:
        """Restart-safety: recover identity from the last intact line.

        A crash mid-write can leave a torn final line. It is skipped, not
        repaired -- a partially written measurement is not a measurement.
        """
        if not self._path.is_file():
            return
        last_good: Optional[Dict[str, Any]] = None
        with self._path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    last_good = json.loads(line)
                except json.JSONDecodeError:
                    continue          # torn line: ignore, never repair
        if last_good is not None:
            self._last_key = idempotency_key(last_good)
            self._last_seq = int(last_good.get("cycle_seq", -1))

    def append(self, row: Dict[str, Any]) -> bool:
        """Durably append one row. Returns False if it was a duplicate.

        Idempotent against the LAST row, which is the only duplicate a
        retried or replayed cycle can produce -- rows are written in
        cycle order, so an older key can never legitimately reappear.
        """
        key = idempotency_key(row)
        if key == self._last_key:
            return False
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        self._last_key = key
        self._last_seq = int(row.get("cycle_seq", self._last_seq))
        return True

    def record(self, snapshot, *, cycle_seq: int, strategy_names=()) -> bool:
        """row_from_snapshot + append, the one call a cycle needs."""
        return self.append(row_from_snapshot(
            snapshot, cycle_seq=cycle_seq, strategy_names=strategy_names))

    def read_all(self) -> List[Dict[str, Any]]:
        """Every intact row, in write order. Torn lines are skipped.

        This is the entire interface Task 2's metrics engine needs.
        """
        rows: List[Dict[str, Any]] = []
        if not self._path.is_file():
            return rows
        with self._path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows
