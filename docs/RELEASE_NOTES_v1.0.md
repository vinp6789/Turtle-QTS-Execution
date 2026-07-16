# RELEASE NOTES — Turtle Execution Engine v1.0

First stable release. This document describes the completed engine using
**only** facts verifiable in the repository. Where a value is not defined
in the repository, that is stated explicitly rather than invented. No dates
are asserted (none are verifiable in the source).

---

## Executive summary

The Turtle Execution Engine v1.0 is the first stable release of a
crash-safe, event-sourced execution core for a crypto trading strategy. It
comprises nine frozen modules wired into a strict acyclic dependency graph
and backed by **319 passing tests** (Windows, current; 305 on the original
Linux baseline). It is built on the Python standard
library alone, records all state transitions durably through an append-only
event store with an idempotency ledger, and confines all signing to a
secrets boundary that never exposes raw key material. This release provides
the safety and bookkeeping substrate for live execution; it does **not**
itself connect to a live exchange (only an in-memory mock adapter exists)
and contains no top-level orchestration loop. It is verified on Linux
(305 passing at v1.0) and, following the Module 3.1 correction and Module
1.1 evolution described under "Post-release correction" and "Post-release
addition" below, verified on Windows as well (319 passing, current).

---

## Modules completed

Nine packages, all frozen. Numbering is taken from explicit `Module N`
cross-references in the source (Modules 1–8); Module 9 is assigned by
elimination (see `DEPENDENCY_GRAPH.md`).

| # | Package | Responsibility (from `__init__` docstring) |
|---|---------|--------------------------------------------|
| 1 | `config` | Load, validate, provide immutable typed config; holds no secrets, no business logic |
| 2 | `secrets_boundary` | Resolve secret references to signing capability without exposing raw key material |
| 3 | `event_store` | Durable, append-only, crash-safe event sourcing + idempotency ledger; records/replays only |
| 4 | `execution_state_machine` | Single source of truth for execution lifecycle state; deterministic, event-driven |
| 5 | `exchange_adapter` | Abstract exchange contract (+ mock); no exchange-specific logic, no real network, no decisions |
| 6 | `order_manager` | Order lifecycle after a trade decision: id generation, sequencing, replayable order state |
| 7 | `position_manager` | Live-position lifecycle: fill accumulation, avg price, PnL, T1/T2/stop status, close, archival |
| 8 | `portfolio_manager` | Portfolio-level ledger only: cash, margin, PnL, exposure, heat, open-position set |
| 9 | `risk_manager` | Pure approval/veto over a fully-specified proposed trade; never sizes or submits |

Full per-module public APIs (each package's `__all__`) are in
`MODULE_INVENTORY.md`.

---

## Architecture summary

- **Single-file-free, package-per-module layout.** Nine packages, each with
  an `__init__.py` declaring a minimal `__all__`. No top-level entrypoint or
  live-orchestration module exists in the repository.
- **Strict acyclic, lower-numbered-only dependency graph** (from actual
  imports):
  - `config` (1), `secrets_boundary` (2), `event_store` (3) — foundational,
    zero internal dependencies.
  - `execution_state_machine` (4) → `event_store`.
  - `exchange_adapter` (5) → `secrets_boundary`.
  - `order_manager` (6) → `event_store`, `execution_state_machine`,
    `exchange_adapter`.
  - `position_manager` (7) → `event_store`, `exchange_adapter`.
  - `portfolio_manager` (8) → `event_store`.
  - `risk_manager` (9) → `config`, `execution_state_machine`,
    `exchange_adapter`, `position_manager`, `portfolio_manager`.
- **Event-sourced core.** State transitions are durably recorded through the
  Event Store, which provides an append-only log with crash-safe recovery,
  torn-tail truncation, checksummed record framing, and an idempotency
  ledger. Its closed `EventType` enum has 13 members: `ORDER_SUBMITTED`,
  `ORDER_ACKNOWLEDGED`, `ORDER_FILLED`, `ORDER_CANCELLED`,
  `POSITION_OPENED`, `POSITION_UPDATED`, `POSITION_CLOSED`, `STOP_UPDATED`,
  `TAKE_PROFIT_UPDATED`, `KILL_SWITCH_TRIGGERED`, `HEALTH_ALERT`,
  `SYSTEM_STARTED`, `SYSTEM_STOPPED`.
- **Secrets never cross module boundaries.** Only
  `SigningBoundary.sign(...)` is exposed; the Event Store additionally
  rejects payload field names that look like secret material.
- **Deterministic state machines.** Execution, order, and position lifecycles
  are explicit finite transition tables with replay-integrity checks.
- **Dependency footprint: Python standard library only.** No third-party
  runtime dependency. `pytest` is used as the test runner; tests are written
  against `unittest`.

---

## Major security features

- **Secrets boundary (Module 2).** The only exposed signing operation is
  `SigningBoundary.sign(ref, purpose, message)`; raw key material never
  crosses a module boundary. `EnvironmentHmacBackend` signs with
  HMAC-SHA256. `SigningPurpose` provides purpose separation and
  `build_preimage` + `ENGINE_ID` provide domain separation of signed
  messages. `MAX_SIGNING_PAYLOAD_BYTES` bounds message size
  (`PayloadTooLargeError`).
- **One-way revocation.** `revoke()`/`revoke_all()` move a reference to
  revoked; per source, no reference can be un-revoked or have its material
  replaced on a live instance (`SecretRevokedError`,
  `UnknownSecretReferenceError`).
- **No secrets in the event log (Module 3).** `append()` rejects payloads
  whose field names look like secret material (`_FORBIDDEN_KEY_SUBSTRINGS`
  scan → `MalformedEventError`).
- **Least-privilege file mode.** The event log is opened `0o600`
  (owner read/write only).
- **Config holds references, not secrets (Module 1).** Configuration carries
  only named secret references, resolved later by the secrets boundary.
- **Tamper/corruption detection.** Each event record is SHA-256 checksummed;
  bad magic, unsupported version, mid-file corruption, and non-monotonic
  ids are hard errors, distinct from a recoverable torn tail.

## Capital-protection features

- **Idempotency ledger (Module 3).** An `idempotency_key` deduplicates
  actions so a caller can safely retry after a crash without issuing a
  duplicate exchange action.
- **Single-writer, crash-safe log.** An exclusive file lock enforces exactly
  one writer; append is `fsync`-durable with automatic torn-tail recovery,
  and a failed write rolls back rather than stranding a partial record.
- **Risk approval/veto (Module 9).** `RiskManager` returns a `Decision`
  (`APPROVED`, `REJECTED`, `BLOCKED`, `FAIL_SAFE`) with a `ReasonCode`.
  Reason codes include kill-switch tiers (`KILL_SWITCH_SOFT`/`HARD`/
  `EMERGENCY`), `ENGINE_STOPPED`, `RISK_PER_TRADE_EXCEEDED`,
  `PORTFOLIO_HEAT_EXCEEDED`, `MAX_POSITIONS_EXCEEDED`, `INSUFFICIENT_MARGIN`,
  `LEVERAGE_EXCEEDED`, `LIQUIDATION_TOO_CLOSE`, `FUNDING_RATE_TOO_HIGH`,
  `CORRELATION_LIMIT_EXCEEDED`, `EXCHANGE_CAPABILITY_UNSUPPORTED`,
  `NON_POSITIVE_EQUITY`, `MISSING_REQUIRED_DATA`, and `STALE_DATA`.
- **Fail-closed on bad/missing data.** `FAIL_SAFE` / `MISSING_REQUIRED_DATA`
  / `STALE_DATA` let the risk layer veto rather than proceed on uncertain
  inputs; `RiskManagerLimits` bounds `max_leverage`,
  `min_liquidation_buffer_pct`, `max_funding_rate_abs`,
  `max_correlated_positions`, and `max_stale_data_seconds`.
  `CORRELATION_THRESHOLD` is `0.5`.
- **Accounting invariants (Module 8).** The portfolio ledger raises
  `InsufficientFundsError`, `InsufficientMarginError`, and
  `AccountingInvariantError` to prevent invalid capital states, and tracks
  heat/exposure.
- **Reconciliation + safe retries (Module 5).** The adapter contract defines
  `reconcile()` → `ReconciliationReport`, an `OperationSafety`
  classification with a `RetryPolicy` (retry only safe operations), an
  `IdempotencyCache`, and `StaleSnapshotError` / `SequenceGapError` /
  `ReconciliationMismatchError`.
- **Deterministic lifecycles.** Execution, order, and position state machines
  enforce legal transitions and replay-integrity, preventing illegal state
  jumps. A `KILL_SWITCH_TRIGGERED` event type exists in the event schema.
- **Decimal money math.** Risk calculations use `Decimal` (not float),
  avoiding binary rounding error in capital-sensitive arithmetic.

---

## Regression baseline

- **306 tests** (plus 5 runtime subtests from one `self.subTest`
  loop in `tests/test_secrets_boundary.py`). Verified **306 passing on
  Windows** (CPython 3.13) after the v1.0.1 / Module 3.1 correction; the
  original v1.0 baseline was **305 passing on Linux** (CPython 3.12.3,
  pytest 9.1.1), unchanged by the fix.
- Per package: `config` 22, `secrets_boundary` 41, `event_store` 38,
  `execution_state_machine` 42, `exchange_adapter` 41, `order_manager` 23,
  `position_manager` 22, `portfolio_manager` 21, `risk_manager` 56.
- One test file per package; no test file is shared across modules.

---

## Known assumptions

- **Windows locking — now runtime-verified (v1.0.1 / Module 3.1).** Module 3
  locks via `event_store/_locking.py`, which import-guards `fcntl` (POSIX)
  and `msvcrt` (Windows). Both the `msvcrt` lock path and the `O_BINARY`
  binary-open fix have since been run on a real Windows host (full suite
  green, 306 on CPython 3.13). This statement is retained for history; the
  assumption it recorded no longer holds open.
- **Windows sentinel-lock offset.** The Windows path locks a single sentinel
  byte at offset `2**62`, relying on the event log never approaching that
  size so a mandatory lock never overlaps bytes that the lock-free
  `read_events()` reader touches.
- **Minimum Python is inferred, not pinned.** `config/loader.py` uses the
  stdlib `tomllib` (added in 3.11); no `python_requires`/`pyproject.toml`
  pins this formally.
- **Module 9 numbering** is inferred by elimination — no literal `Module 9`
  string exists in the source.

---

## Known limitations

- **No live exchange connectivity.** Only `MockExchangeAdapter` (an
  in-memory, no-network test double) exists. `ExchangeAdapter` is an abstract
  contract; concrete adapters (the source names Hyperliquid, Lighter,
  Variational, or any future exchange) are not implemented in this release.
- **No live orchestration / no entrypoint.** The repository contains the
  nine modules but no top-level engine, main loop, or wiring that runs them
  together against a live venue.
- **Single signing backend.** `EnvironmentHmacBackend` is the only concrete
  `SigningBackend`; hardware/KMS backends are described in source as a future
  extension point.
- **No packaging/metadata files.** The repository root has no `README`,
  `LICENSE`, `requirements.txt`, `pyproject.toml`, `setup.*`, `.gitignore`,
  `CHANGELOG`, or version file, and no VCS metadata.
- **No dates or milestone markers** are recorded in the repository.

---

## Supported platforms

- **Linux — verified.** Full suite (305) passes on Linux/CPython 3.12.3.
- **Windows — verified (v1.0.1 / Module 3.1).** The full suite passes on a
  real Windows host (306 on CPython 3.13), exercising both the `fcntl`/
  `msvcrt` lock shim and the `O_BINARY` binary-open fix, plus a dedicated
  binary-framing regression test. The previously recommended Windows
  validation run is complete; the `msvcrt` locking path and binary log
  writes are runtime-verified.
- **Python:** 3.11+ (inferred from `tomllib` usage); verified on CPython
  3.12.3 (Linux) and CPython 3.13 (Windows).

---

## Repository tag

- **Recommended tag:** `execution-engine-v1.0` (Modules 1–9 Frozen).
- **Status: not yet applied.** The repository contains no VCS metadata, so
  no tag exists in-tree. This is the recommended tag string to apply when
  the release is cut; it is not asserted as already present.
- **Release contents match the approved frozen implementation.** A per-file
  checksum comparison confirms the reconciled repository is identical to the
  approved Modules 1–9 implementation (the reconciliation reintegrated the
  approved Module 3 locking layer that was absent from the earlier uploaded
  snapshot).

---

## Post-release correction — v1.0.1 (Module 3.1, event_store)

One critical defect was found and corrected after v1.0, under the frozen
workflow's critical-defect exception (propose → approve → implement →
full-regression → audit → re-freeze). It is additive and confined to
`event_store`.

- **Defect (critical: correctness / capital-protection / crash-recovery).**
  On Windows, `EventStore` opened its append-only log without `os.O_BINARY`,
  so the C runtime used text mode and `os.write` translated every `0x0A`
  byte to `0x0D 0x0A`. Binary record framing (magic, big-endian
  `event_id`/length, SHA-256 checksum) routinely contains `0x0A`, so the
  `fsync`-durable log was silently corrupted on disk and detected only as
  `CorruptEventStoreError` on the next open. This defeated durable replay —
  the module's core guarantee — on Windows, and is exactly the risk the
  original "Windows path not runtime-verified" caveat anticipated.
- **Fix.** Add `getattr(os, "O_BINARY", 0)` to the `os.open` flags in
  `event_store/store.py`. Windows-only by construction; on POSIX the term is
  `0`, so the flag set is byte-identical and Linux behavior is unchanged. No
  public-API change, no on-disk-format change, no dependency-graph change.
- **Verification.** Full regression now **306 passing on Windows**
  (CPython 3.13) — the prior 305 plus one additive Windows regression test
  (`tests/test_event_store.py::BinaryModeIntegrity`), proven to fail without
  the fix and pass with it. The Linux 305 baseline is unaffected.
- **Status.** Module 3 re-frozen as **Module 3.1**. Recommended tag:
  `v1.0.1`.
- **Compatibility note.** The fix heals **new** logs only. A log already
  written in text mode on Windows before this fix remains corrupt and cannot
  be reopened — this is data migration, not code behavior.

---

## Post-release addition — v1.1.0 (Module 1.1, config)

One additive capability was added after v1.0.1, under an explicit
authorization distinct from the critical-defect exception (this is new
capability, not a defect correction) -- see ADR-20 and ADR-21. It is
additive and confined to `config`.

- **Addition.** `SecretsConfig` gains an optional `wallet_key_ref` field
  (default `None`), naming a venue wallet-signing key (e.g. EIP-712/
  secp256k1 exchange authentication) as a secret domain kept separate from
  the existing `signing_key_ref`. ADR-20 determined that Turtle-internal
  authorization signing and exchange-native authentication must remain
  separate security domains; ADR-21 determined the separation should be a
  dedicated config reference (not reuse of `signing_key_ref`, and not a
  reference left outside the validated schema, which would bypass the
  engine's only defense against a raw key pasted into config).
- **Validation and override.** Validated identically to the existing two
  refs when present (non-empty string; rejected if it looks like raw key
  material). An optional `TURTLE_EXEC_WALLET_KEY_REF` environment override
  follows the existing override pattern exactly, and the override value is
  still fully validated.
- **Verification.** Full regression now **319 passing on Windows**
  (CPython 3.13) — the prior 306 plus 13 additive tests in a new file,
  `tests/test_config_wallet_ref.py`; zero failures. `tests/test_config.py`
  (frozen) untouched. Backward compatibility verified empirically: old
  2-argument `SecretsConfig` construction, the unmodified shipped
  `example.toml`, equality, and frozen-instance semantics all confirmed
  intact. Public API (`config.__all__`) identical (13 names) -- one
  optional field on an existing exported type, not a new export.
  Dependency graph unchanged and acyclic.
- **Status.** Module 1 re-frozen as **Module 1.1**. Recommended tag:
  `v1.1.0` (a minor version, since this adds backward-compatible capability
  rather than fixing a defect).
- **Known limitation.** Module 1 does not enforce `wallet_key_ref !=
  signing_key_ref`; the two-key separation is representable, not enforced.
  Enforcement belongs to a future signing module and remains open.

---

## Future roadmap — beginning with Module 10

> **Repository fact vs. convention.** The repository does **not** define a
> roadmap, a "Module 10", or any numbering for future work. "Module 10"
> below denotes only the next integer in the existing sequence (frozen
> modules run 1–9); the repository does not assign that number to any
> specific package. The candidate items are the future-work hooks that are
> **explicitly named in the source**, listed without inventing priority,
> scope, or module assignments.

**Module 10 (next in sequence) — candidate work, source-attested hooks:**

- **Concrete Exchange Adapter(s).** Implement `ExchangeAdapter` for a real
  venue (source explicitly names Hyperliquid, Lighter, Variational, or any
  future exchange), replacing `MockExchangeAdapter` for live use. This is
  the single largest gap between this release and live trading.

**Further source-attested future work (unnumbered in the repository):**

- **Live orchestration / engine entrypoint** that wires Modules 1–9 into a
  running loop (no such module exists today).
- **Audit Trail reader.** `event_store.read_events()` is documented as a
  lock-free, read-only API intended for a future separate-process Audit
  Trail reader.
- **Additional signing backends.** `SigningBackend` is documented as the
  extension point for future hardware or KMS backends beyond the current
  `EnvironmentHmacBackend`.
- **Windows runtime validation** of the Module 3 `msvcrt` locking path —
  **completed in v1.0.1 / Module 3.1** (see Post-release correction, Known
  assumptions, and Supported platforms).

Each future module must follow the freeze process and integration rules in
`DEVELOPMENT_WORKFLOW.md` and `CLAUDE_ONBOARDING.md`: additive-only, no
public-API changes to frozen modules, no dependency cycles, and full
regression green before freeze.

---

## Credits

- **Turtle QTS project** — engine design, module architecture, and freeze
  authority (the human maintainer who owns approval and freeze decisions).
- **AI-assisted development** — portions of this release cycle were carried
  out with AI assistance under human direction, including the Module 3
  cross-platform locking layer (implemented and audited during this
  session), the repository reconciliation to the approved frozen
  implementation, and this documentation set. All changes were made under
  the additive-only, approval-gated workflow in `DEVELOPMENT_WORKFLOW.md`;
  no frozen module's public API was altered.

> Attribution note: this credits section records the process facts
> observable in this session. The repository itself contains no `AUTHORS`,
> `CONTRIBUTORS`, or license file; no individual authorship beyond the above
> is asserted.

---

*This release describes the first stable version of the Turtle Execution
Engine (Modules 1–9, frozen). All figures and interfaces above are taken
directly from the repository; nothing is inferred beyond the explicitly
flagged items.*
