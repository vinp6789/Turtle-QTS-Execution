# CHANGELOG.md

Changes to the Turtle Execution Engine. This changelog begins at v1.0; the
repository contains no prior changelog or VCS history, so pre-v1.0
development is not itemized here. No calendar dates are asserted (none are
verifiable in the source). Entries record only facts observable in the
repository and in this session's verified work.

> No formal version number is asserted for the entries below beyond what
> is already established (v1.0/v1.0.1/v1.1.0) — per this file's own
> no-invented-version discipline, they are labeled descriptively. See
> `git log` for the actual commit sequence and `PROJECT_STATUS.md` for
> current state.

## Module 10 — Hyperliquid Adapter (frozen)

### Added
- `hyperliquid_adapter/`: concrete `ExchangeAdapter` implementation for
  Hyperliquid — read-only methods, four authenticated mutations
  (place/cancel/cancel_all/amend), EIP-712 venue signing, durable
  engine-id↔cloid order attribution. Full detail, known limitations, and
  validation evidence: `../MODULE_10_FREEZE.md`.
- 206 module tests; full-suite regression at freeze: 534 passing (no
  regression in the frozen core).

## Application layer

### Added
- `app/`, `composition_root/`, `trading_system/`, `orchestration/`: the
  deployable service wrapping the frozen engine (REST API, mobile
  dashboard, Telegram bot, Prometheus metrics, worker loop) — see
  `DEPLOYMENT.md`, `OPERATIONS.md`, `PRODUCTION_CHECKLIST.md`.
- Capital-safety fixes (accounting wiring, quantization, crash-window
  healing, short-side PnL, staleness validation, emergency-stop
  propagation, fail-closed control endpoints, read-path isolation,
  Telegram lifecycle) — see `../AUDIT_HISTORY.md` (superseded snapshot)
  and `../FINAL_PRODUCTION_AUDIT.md` (independently re-verified from
  source, GO verdict on engineering/capital safety).
- Full-suite regression at this point: 820 passing.

## Alpha Engine — platform build (R1–R8)

### Added
- `alpha_engine/`: an additive research subsystem — Experiment Registry,
  two data sources (funding rate, open interest), feature transforms,
  rule-based candidates, a five-stage validation gate, immutable evidence
  packages, governance (reviewer-separation), a ten-state lifecycle,
  degradation/freeze policy, conflict-refusing portfolio selection, and
  an execution bridge (`ApprovedFundingAlphaStrategy`) consuming the
  Execution Engine only through its public `Strategy`/`TradeIntent` seam.
- Zero frozen Execution Engine modules modified — enforced by an
  automated test (`tests/test_alpha_engine_scaffold.py`).
- Full detail: `ALPHA_ENGINE.md`; decision record: `../alpha_engine/DECISIONS.md` (D1–D8).

## Alpha Engine — adversarial audit remediation

### Fixed
- Ten findings (A1, A2, B1–B6, C3, C4) from an independent adversarial
  audit: bridge liveness re-checking, cadence enforcement, dataset
  fingerprinting, evidence-fingerprint scope, registry storage hardening
  (lock/checksum/torn-tail tolerance), structured logging, canonical
  timestamp handling, registry deep-copy at read/write boundaries,
  catalog-based candidate dispatch, and watchlist enforcement. All fixes
  additive and (mostly) opt-in via new optional arguments defaulting to
  prior behavior. Full detail: `ALPHA_ENGINE.md` §8; decision record:
  `../alpha_engine/DECISIONS.md` D9.

## Alpha Engine — historical data pipeline

### Added
- `alpha_engine/historical/`: a reproducible, incrementally-rerunnable
  pipeline collecting Open Interest, mark price, and Funding Rate history
  for BTC/ETH/SOL from Binance (primary) and Hyperliquid (secondary,
  venue-consistent) public sources — checksummed, integrity-validated,
  point-in-time-correct. Full detail: `HISTORICAL_DATA.md`.

## Alpha Engine — Research Campaign 01 (Open Interest)

### Added
- `research/campaign_01_open_interest/`: point-in-time sample
  construction and campaign execution harness.
- New platform additions required by the campaign's own evidence (not
  built ahead of need): `MarkPriceObservation` + `collect_metrics`
  (historical), rolling percentile-rank/z-score OI features, and the
  `open_interest_extremeness_rule` candidate.

### Result
- Four pre-registered experiments executed on 18 months of real
  BTC/ETH/SOL data. **All four REJECTED on merit** — no reliable 24h
  directional edge in raw Open Interest level. Full record:
  `RESEARCH_LEDGER.md` (CAMP-01), `RESEARCH_CAMPAIGN_01_open_interest.md`.
- Full-suite regression at this point: 1,567 passing.

## Documentation — project-mode transition

### Added
- `PROJECT_CONSTITUTION.md`, `PROJECT_DASHBOARD.md`, `RESEARCH_LEDGER.md`,
  `ALPHA_LIBRARY.md`, `WATCHLIST.md`, `RESEARCH_PLAYBOOK.md`,
  `REVIEW_PROTOCOL.md` — consolidating what had been conversation-only
  context into permanent, repository-resident documentation. Updated
  `PROJECT_STATUS.md`, `ROADMAP.md`, and `MASTER_INDEX.md` to reflect
  current (both-subsystem) state rather than the pre-Alpha-Engine
  snapshot they previously described.

## v1.1.0 — additive evolution (Module 1.1, config)

### Added
- **Optional `wallet_key_ref` on `SecretsConfig`.** Names a venue
  wallet-signing key (e.g. EIP-712/secp256k1 exchange authentication) as a
  secret domain separate from the existing `signing_key_ref`, per ADR-20
  (Turtle-internal authorization vs. exchange-native authentication are
  separate security domains) and ADR-21 (a dedicated ref, not reuse of
  `signing_key_ref`, and not a ref left outside the validated config
  schema). Defaults to `None`; absent means no wallet-signing venue is
  configured.
- Validated identically to the existing two refs (non-empty string,
  rejected if it looks like raw key material via the existing
  `_looks_like_raw_secret` guard), but only when present.
- Optional environment override `TURTLE_EXEC_WALLET_KEY_REF`, following the
  existing `TURTLE_EXEC_SIGNING_KEY_REF` / `TURTLE_EXEC_TELEGRAM_BOT_TOKEN_REF`
  pattern exactly; the override value is still fully validated.
- New test file `tests/test_config_wallet_ref.py` (13 tests): absence
  defaults to `None`, valid refs load, malformed/empty/raw-hex/oversized/
  non-string values are rejected, `SecretsConfig` remains frozen, and the
  env override sets, replaces, is still validated, and is a no-op when unset.

### Verified
- Full regression: **319 tests passing on Windows** (CPython 3.13) — the
  prior 306 plus 13 additive tests; zero failures. `tests/test_config.py`
  (frozen) unmodified and unaffected. Linux baseline is expected to rise by
  the same platform-neutral +13 (to 318) but was not independently re-run
  on Linux this session.
- Backward compatibility verified empirically: pre-existing 2-argument
  `SecretsConfig` construction (positional and keyword) still works; the
  unmodified shipped `example.toml` still loads with `wallet_key_ref is
  None`; equality and frozen-instance semantics unchanged.
- Public API surface (`config.__all__`) identical before and after (13
  names) -- `SecretsConfig` gains an optional field, not a new export.
  Dependency graph unchanged and acyclic; no new import.

### Scope
- Additive evolution of a frozen module under an explicit authorization
  distinct from the critical-defect exception (this is new capability, not
  a defect correction) -- see ADR-20 and ADR-21. Confined to
  `config/schema.py`, `config/loader.py`, and one new test file. No other
  module touched. Module 1 re-frozen as Module 1.1.

## v1.0.1 — critical defect correction (Module 3.1, event_store)

### Fixed
- **Windows event-log corruption (critical; correctness / capital-protection
  / crash-recovery).** On Windows, `EventStore` opened its append-only log
  without `os.O_BINARY`, so the C runtime used text mode and `os.write`
  translated every `0x0A` byte to `0x0D 0x0A`. Binary record framing (magic,
  big-endian `event_id`/length, SHA-256 checksum) routinely contains `0x0A`,
  so the `fsync`-durable log was silently corrupted on disk and surfaced
  only as `CorruptEventStoreError` on the next open — defeating durable
  replay, the module's core guarantee, on Windows. Fix: add
  `getattr(os, "O_BINARY", 0)` to the `os.open` flags in
  `event_store/store.py`. Windows-only by construction; on POSIX the term is
  `0`, so the flag set is byte-identical and Linux behavior is unchanged.

### Added
- Windows regression test `tests/test_event_store.py::BinaryModeIntegrity`
  (one new test): appends records whose framing carries `0x0A` and asserts a
  byte-exact reopen. Verified to fail without the fix and pass with it.

### Verified
- Full regression: **306 tests passing on Windows** (CPython 3.13) — the
  prior 305 plus the one additive regression test; zero failures. Before the
  fix this same host produced nondeterministic `CorruptEventStoreError`
  failures across every crash-recovery/reopen test.
- Linux path unchanged by the fix (POSIX `os.open` flags byte-identical; no
  newline translation on POSIX).
- Public API surface (`event_store.__all__`) identical before and after.
- On-disk record format unchanged; dependency graph still acyclic;
  `event_store` still stdlib-only (uses the already-imported `os`).

### Scope
- One-line additive change to a single frozen module plus one new test file
  method. No other source touched, no refactor, no public-API change, no
  on-disk-format change. Module 3 re-frozen as Module 3.1.

## v1.0 — first stable release (Modules 1–9 frozen)

### Added
- Nine frozen modules constituting the execution engine: `config` (1),
  `secrets_boundary` (2), `event_store` (3), `execution_state_machine` (4),
  `exchange_adapter` (5), `order_manager` (6), `position_manager` (7),
  `portfolio_manager` (8), `risk_manager` (9).
- Full test suite: 305 tests across nine test files (plus 5 runtime
  subtests).
- Documentation set under `docs/` (release notes, status, changelog,
  roadmap, master index, architecture decisions, security assumptions,
  module inventory, dependency graph, architecture version, repository
  structure, development workflow, onboarding).

### Reconciled (this session)
- **Module 3 cross-platform locking layer restored.** An earlier uploaded
  snapshot was missing `event_store/_locking.py` and carried the pre-fix
  `event_store/store.py` (unguarded `import fcntl`). The approved frozen
  implementation was reintegrated: `_locking.py` (import-guarded
  `fcntl`/`msvcrt`) reconstructed, and `store.py` restored to lock via the
  shim. Delta versus the uploaded snapshot is exactly those two files.
  Verified: 305 tests still pass on Linux; public APIs unchanged; no
  cross-package dependency change; POSIX behavior identical (the Windows
  path is not taken on Linux).

### Verified at release
- Regression: 305 passing on CPython 3.12.3.
- Public API surface (`__all__`) identical across all nine packages before
  and after reconciliation.
- Dependency graph acyclic; `event_store` remains dependency-free at the
  package level.

### Not included (see ROADMAP.md)
- No concrete exchange adapter (only `MockExchangeAdapter`).
- No live orchestration/entrypoint.
- No signing backends beyond `EnvironmentHmacBackend`.
- Windows `msvcrt` locking path not yet runtime-verified. *(Resolved in
  v1.0.1 / Module 3.1 — see the v1.0.1 entry above.)*

### Notes
- No source-code changes were made during documentation work; only files
  under `docs/` were created or updated.
