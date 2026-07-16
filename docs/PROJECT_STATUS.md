# PROJECT_STATUS.md

Current status of the Turtle Execution Engine, from repository facts only.
No dates are asserted (none are verifiable in the source).

## Overall status

**Modules 1–9 complete and frozen. First stable release (v1.0) candidate.**
Module 3 has since received one critical Windows defect correction, re-frozen
as **Module 3.1** (v1.0.1), and Module 1 has since received one additive
evolution, re-frozen as **Module 1.1** (v1.1.0) — see below and
`CHANGELOG.md`.

- Nine packages present, each with an `__init__.py` and a minimal `__all__`.
- Regression: **319 tests passing on Windows** (CPython 3.13) after the
  Module 1.1 evolution — 306 after Module 3.1, plus 13 additive
  `config`-only tests — plus the 5 runtime subtests. The Linux baseline is
  expected to rise from 305 to 318 by the same platform-neutral delta but
  was not independently re-run on Linux this session.
- Repository reconciled to the approved frozen implementation (the Module 3
  cross-platform locking layer, `event_store/_locking.py` + the shim-based
  `store.py`, was reintegrated after being absent from an earlier uploaded
  snapshot). A per-file checksum comparison confirms identity with the
  approved implementation.

## Module status

| # | Package | Status |
|---|---------|--------|
| 1 | `config` | Frozen as **Module 1.1** (optional `wallet_key_ref` added) |
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

- **Linux:** verified 305 on CPython 3.12.3 as of Module 3.1 (POSIX flags
  byte-identical to that fix); the Module 1.1 addition is platform-neutral
  pure Python, expected to raise this to 318, but was not independently
  re-run on Linux this session.
- **Windows:** verified — full suite green (319 passing on CPython 3.13)
  after the Module 1.1 evolution, including the Module 3.1 binary-framing
  regression test. The `msvcrt` lock shim and the `O_BINARY` binary-open fix
  are both exercised.
- **Python:** 3.11+ (inferred from `tomllib`); verified on 3.12.3 (Linux, as
  of Module 3.1) and 3.13 (Windows, current).

## Readiness for Git tag v1.1.0

- **Linux:** ready by inference (frozen-consistent; expected 318 green, not
  independently re-run this session).
- **Windows:** ready. 319 green after the Module 1.1 evolution.
- **Recommended tag:** `v1.1.0` — a MINOR version bump under standard
  semantic-versioning convention (no formal SemVer policy is asserted in
  the repository), because this change adds new, optional, backward-compatible
  capability (`wallet_key_ref`) rather than fixing a defect; `v1.0.1` was
  reserved for the Module 3.1 defect correction. Tagging is a separate
  authorized step and is not itself asserted as applied by this document.
