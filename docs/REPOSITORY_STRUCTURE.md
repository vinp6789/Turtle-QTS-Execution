# REPOSITORY_STRUCTURE.md

> **INCONSISTENCY — RESOLVED.** The uploaded ZIP was a pre-fix snapshot
> missing Module 3's approved cross-platform locking layer. It has since
> been reconciled: `event_store/_locking.py` was reconstructed from the
> approved frozen implementation and `event_store/store.py` restored to its
> approved (shim-based) version. The repository now matches the approved
> Modules 1–9 implementation and collects on Windows.

> **SCOPE NOTE.** The detailed tree below is the original Modules 1–9
> packaging snapshot and remains accurate *for that scope*. Since then the
> repository has grown substantially: Module 10 (`hyperliquid_adapter/`),
> the app layer (`app/`, `composition_root/`, `trading_system/`,
> `orchestration/`), and the entire Alpha Engine subsystem
> (`alpha_engine/`, `research/`, `data/`). See "Current top-level layout"
> below for the additions; the Modules 1–9 detail underneath is unchanged
> and still correct.

Repository tree for the Turtle Execution Engine, listing only files that
actually exist. Nine frozen packages (Modules 1–9), one test suite, one
sample config, generated caches, and this documentation set.

## Current top-level layout (addendum — everything added since the snapshot below)

```
├── hyperliquid_adapter/            # Module 10 (frozen) — see MODULE_10_FREEZE.md
├── app/                            # Application layer (API, dashboard, Telegram, worker)
├── composition_root/               # Wires Modules 1-10 + app into a running Engine
├── trading_system/                 # Strategy/TradeIntent seam, scheduling, execution
├── orchestration/                  # Cycle orchestration
├── alpha_engine/                   # Alpha Engine subsystem (registry, data_sources,
│                                   #   features, candidates, validation, governance,
│                                   #   lifecycle, portfolio, execution_bridge,
│                                   #   historical, watchlist.py, research.py)
│   └── DECISIONS.md                # Alpha Engine decision log (D1 onward)
├── research/                       # Research campaign harnesses (not platform code)
│   └── campaign_01_open_interest/  # Campaign 01's sample-construction + execution scripts
├── data/                           # Runtime state, historical backfills (git-ignored)
├── deploy/                         # Deployment configs (e.g. engine.paper.toml)
├── scripts/                        # Operational scripts (backup, validate_env, smoke_test)
├── README.md, PROJECT_HANDOVER.md, AUDIT_HISTORY.md,
│   FINAL_PRODUCTION_AUDIT.md, MODULE_10_FREEZE.md   # root-level docs — see MASTER_INDEX.md
└── docs/                           # full documentation set — see MASTER_INDEX.md
```

`tests/` now holds one `test_*.py` per Execution Engine module/package
plus a large Alpha Engine test set (`test_alpha_engine_*.py`,
`test_research_campaign_01_*.py`) — **1,567 tests total** (820 Execution
Engine + 747 Alpha Engine), see `MASTER_INDEX.md`.

## Modules 1-9 packaging snapshot (original tree, still accurate for its scope)

## Tree

```
ExecutionEngine_Upload/
├── config/                         # Module 1 (frozen as Module 1.1)
│   ├── __init__.py
│   ├── errors.py
│   ├── loader.py                   # uses stdlib tomllib (Python 3.11+)
│   ├── schema.py
│   └── example.toml                # sample configuration (not generated)
│
├── secrets_boundary/               # Module 2 (frozen)
│   ├── __init__.py
│   ├── backend.py
│   ├── boundary.py
│   ├── domain.py
│   └── errors.py
│
├── event_store/                    # Module 3 (frozen as Module 3.1)
│   ├── __init__.py
│   ├── _locking.py                 # cross-platform lock shim (fcntl POSIX / msvcrt Windows)
│   ├── codec.py
│   ├── errors.py
│   ├── store.py                    # locks via ._locking shim; opens log with O_BINARY (portable)
│   └── types.py
│
├── execution_state_machine/        # Module 4 (frozen)
│   ├── __init__.py
│   ├── errors.py
│   ├── machine.py
│   ├── states.py
│   └── transitions.py
│
├── exchange_adapter/               # Module 5 (frozen)
│   ├── __init__.py
│   ├── adapter.py
│   ├── audit.py
│   ├── errors.py
│   ├── idempotency.py
│   ├── mock_adapter.py
│   ├── models.py
│   └── retry.py
│
├── order_manager/                  # Module 6 (frozen)
│   ├── __init__.py
│   ├── errors.py
│   ├── ids.py
│   ├── manager.py
│   ├── snapshot.py
│   └── states.py
│
├── position_manager/               # Module 7 (frozen)
│   ├── __init__.py
│   ├── errors.py
│   ├── ids.py
│   ├── manager.py
│   ├── pnl.py
│   ├── snapshot.py
│   └── states.py
│
├── portfolio_manager/              # Module 8 (frozen)
│   ├── __init__.py
│   ├── errors.py
│   ├── manager.py
│   └── snapshot.py
│
├── risk_manager/                   # Module 9 (frozen)
│   ├── __init__.py
│   ├── errors.py
│   ├── manager.py
│   └── models.py
│
├── tests/                          # unittest-based; 319 tests total
│   ├── test_config.py                     # 22
│   ├── test_config_wallet_ref.py          # 13 (Module 1.1)
│   ├── test_secrets_boundary.py           # 41 (+5 runtime subtests)
│   ├── test_event_store.py                # 38
│   ├── test_execution_state_machine.py    # 42
│   ├── test_exchange_adapter.py           # 41
│   ├── test_order_manager.py              # 23
│   ├── test_position_manager.py           # 22
│   ├── test_portfolio_manager.py          # 21
│   └── test_risk_manager.py               # 56
│
└── docs/                           # documentation (this set)
    ├── DEPENDENCY_GRAPH.md
    ├── MODULE_INVENTORY.md
    ├── ARCHITECTURE_VERSION.md
    ├── CLAUDE_ONBOARDING.md
    ├── REPOSITORY_STRUCTURE.md
    └── DEVELOPMENT_WORKFLOW.md
```

## Packages (frozen modules)

Nine packages, each with an `__init__.py` declaring a minimal `__all__`.
Numbering 1–9 as in `MODULE_INVENTORY.md` / `DEPENDENCY_GRAPH.md`.

## Tests

`tests/` contains ten `test_*.py` files (config has two: `test_config.py`
and `test_config_wallet_ref.py`), all `unittest`-based. **319 tests**
collected; per-file counts shown above. Verified 319 passing on Windows
(CPython 3.13) after the Module 1.1 evolution; the Linux baseline is
expected at 318 by the same platform-neutral delta but was not
independently re-run this session.

## Documentation

`docs/` (created as part of this packaging task) holds the six markdown
documents listed in the tree.

## Generated files (not source; safe to delete/regenerate)

- `**/__pycache__/` — compiled bytecode. Caches for CPython 3.13 (from the
  uploader's environment) and CPython 3.12 (from verification runs here)
  are present.
- `.pytest_cache/` — pytest run cache (`CACHEDIR.TAG`, `README.md`,
  `.gitignore`, `v/cache/nodeids`). Produced by running the suite.

> These generated artifacts should be excluded from version control (e.g.
> via `.gitignore`). No `.gitignore` currently exists at the repository
> root — flagged, not created (documentation-only task).

## Files that are notably absent

For accuracy: the repository root contains **no** `README`, `LICENSE`,
`requirements.txt`, `pyproject.toml`, `setup.py`/`setup.cfg`, `.gitignore`,
`CHANGELOG`, or version file. Their absence is stated here rather than
assumed.
