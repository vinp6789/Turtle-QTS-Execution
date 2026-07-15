# PROJECT_STATUS.md

Current status of the Turtle Execution Engine, from repository facts only.
No dates are asserted (none are verifiable in the source).

## Overall status

**Modules 1–9 complete and frozen. First stable release (v1.0) candidate.**
Module 3 has since received one critical Windows defect correction, re-frozen
as **Module 3.1** (v1.0.1) — see below and `CHANGELOG.md`.

- Nine packages present, each with an `__init__.py` and a minimal `__all__`.
- Regression: **306 tests passing on Windows** (CPython 3.13) after the
  Module 3.1 correction — the prior 305 plus one additive Windows regression
  test — plus the 5 runtime subtests. The original 305 baseline was verified
  on Linux/CPython 3.12.3 and is unchanged by the fix (POSIX flags are
  byte-identical).
- Repository reconciled to the approved frozen implementation (the Module 3
  cross-platform locking layer, `event_store/_locking.py` + the shim-based
  `store.py`, was reintegrated after being absent from an earlier uploaded
  snapshot). A per-file checksum comparison confirms identity with the
  approved implementation.

## Module status

| # | Package | Status |
|---|---------|--------|
| 1 | `config` | Frozen |
| 2 | `secrets_boundary` | Frozen |
| 3 | `event_store` | Frozen as **Module 3.1** (cross-platform lock reconciled; Windows `O_BINARY` correction applied) |
| 4 | `execution_state_machine` | Frozen |
| 5 | `exchange_adapter` | Frozen (abstract contract + mock only) |
| 6 | `order_manager` | Frozen |
| 7 | `position_manager` | Frozen |
| 8 | `portfolio_manager` | Frozen |
| 9 | `risk_manager` | Frozen |

## What works today

- Durable, crash-safe, append-only event sourcing with idempotency ledger.
- Deterministic execution/order/position state machines with replay
  integrity.
- Risk approval/veto, portfolio accounting, position bookkeeping.
- Secrets boundary with HMAC-SHA256 signing and one-way revocation.
- Full test suite green on Linux.

## What is not present (repository facts)

- **No live exchange connectivity** — only `MockExchangeAdapter` (no
  network) exists.
- **No top-level orchestration / entrypoint** — no module wires 1–9 into a
  running loop.
- **Single signing backend** — only `EnvironmentHmacBackend`.
- **No packaging/metadata/VCS files** — no `README`, `LICENSE`,
  `requirements.txt`, `pyproject.toml`, `setup.*`, `.gitignore`,
  `CHANGELOG` at root, or version file; no git metadata.

## Platform status

- **Linux:** verified (305 passing on CPython 3.12.3; unchanged by the
  Module 3.1 fix, whose POSIX flags are byte-identical).
- **Windows:** verified after the Module 3.1 correction — full suite green
  (306 passing on CPython 3.13), including a dedicated binary-framing
  regression test. The `msvcrt` lock shim and the `O_BINARY` binary-open fix
  are both exercised. Prior to the fix, the missing `O_BINARY` caused
  text-mode newline translation that corrupted the binary log; that defect
  is now resolved.
- **Python:** 3.11+ (inferred from `tomllib`); verified on 3.12.3 (Linux)
  and 3.13 (Windows).

## Readiness for Git tag v1.0.1

- **Linux:** ready. Complete, frozen-consistent, 305 green.
- **Windows:** ready. 306 green after the Module 3.1 correction; the
  previously pending cross-platform validation of the `event_store` binary
  path is now satisfied.
- **Recommended tag:** `v1.0.1` (records the Module 3.1 critical Windows
  defect correction on top of the existing `v1.0`). Tagging is a separate
  authorized step and is not itself asserted as applied by this document.
