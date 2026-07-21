# MASTER_INDEX.md

Index of the Turtle Execution Engine repository: documentation set, modules,
and tests. All entries reflect actual repository contents.

## Documentation (`docs/`)

| Document | Purpose |
|----------|---------|
| `RELEASE_NOTES_v1.0.md` | First stable release summary (features, baseline, roadmap, credits) |
| `PROJECT_STATUS.md` | Current status and readiness snapshot |
| `CHANGELOG.md` | Recorded changes, starting at v1.0 |
| `ROADMAP.md` | Future work, grounded in source-attested hooks |
| `ARCHITECTURE_DECISIONS.md` | Design decisions evidenced in the source |
| `ADR_ACCOUNTING_CRASH_WINDOWS.md` | AD-25 full analysis: the accepted venue-ACK ↔ EventStore crash windows (timeline, impossibility argument, recovery) |
| `SECURITY_ASSUMPTIONS.md` | Security posture and assumptions |
| `MODULE_INVENTORY.md` | Per-module table: API, deps, test file, test count |
| `DEPENDENCY_GRAPH.md` | Import graph, layering, responsibilities |
| `ARCHITECTURE_VERSION.md` | Version, frozen modules, baseline, platform |
| `REPOSITORY_STRUCTURE.md` | Repository tree |
| `DEVELOPMENT_WORKFLOW.md` | Feature/security/freeze/regression workflow |
| `CLAUDE_ONBOARDING.md` | Standing onboarding prompt for future sessions |
| `MASTER_INDEX.md` | This index |

## Modules (frozen, 1–9)

Numbering from explicit `Module N` source references (1–8); Module 9 by
elimination.

| # | Package | Test file | # Tests |
|---|---------|-----------|--------|
| 1 | `config` | `tests/test_config.py`, `tests/test_config_wallet_ref.py` | 35 |
| 2 | `secrets_boundary` | `tests/test_secrets_boundary.py` | 41 |
| 3 | `event_store` | `tests/test_event_store.py` | 38 |
| 4 | `execution_state_machine` | `tests/test_execution_state_machine.py` | 42 |
| 5 | `exchange_adapter` | `tests/test_exchange_adapter.py` | 41 |
| 6 | `order_manager` | `tests/test_order_manager.py` | 23 |
| 7 | `position_manager` | `tests/test_position_manager.py` | 22 |
| 8 | `portfolio_manager` | `tests/test_portfolio_manager.py` | 21 |
| 9 | `risk_manager` | `tests/test_risk_manager.py` | 56 |
| | **Total** | | **319** |

Module 3 (`event_store`) is frozen as **Module 3.1** following a critical
Windows defect correction (v1.0.1); its test count rose 37→38 with a
binary-framing regression test. Module 1 (`config`) is frozen as
**Module 1.1** following an additive evolution (v1.1.0, optional
`wallet_key_ref`); its test count rose 22→35 with a new test file,
`tests/test_config_wallet_ref.py` (13 tests). Verified 319 passing on
Windows (CPython 3.13); the Linux baseline is expected at 318 by the same
platform-neutral delta but was not independently re-run this session.

## Recommended reading order

1. `RELEASE_NOTES_v1.0.md` — what this release is.
2. `PROJECT_STATUS.md` — where it stands.
3. `MODULE_INVENTORY.md` + `DEPENDENCY_GRAPH.md` — the modules and their wiring.
4. `ARCHITECTURE_DECISIONS.md` + `SECURITY_ASSUMPTIONS.md` — why it is built this way.
5. `DEVELOPMENT_WORKFLOW.md` + `CLAUDE_ONBOARDING.md` — how to work on it.
6. `ROADMAP.md` + `CHANGELOG.md` — where it is going and what changed.
