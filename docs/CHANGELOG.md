# CHANGELOG.md

Changes to the Turtle Execution Engine. This changelog begins at v1.0; the
repository contains no prior changelog or VCS history, so pre-v1.0
development is not itemized here. No calendar dates are asserted (none are
verifiable in the source). Entries record only facts observable in the
repository and in this session's verified work.

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
- Windows `msvcrt` locking path not yet runtime-verified.

### Notes
- No source-code changes were made during documentation work; only files
  under `docs/` were created or updated.
