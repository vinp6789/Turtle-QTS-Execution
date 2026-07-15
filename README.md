# Turtle Execution Engine

Crash-safe, event-sourced execution core for a crypto trading strategy.
**v1.0 — Modules 1–9 frozen.** This README orients the repository; the
authoritative detail lives in [`docs/`](docs/MASTER_INDEX.md). Everything
below reflects actual repository contents.

## What this is

Nine frozen modules that provide the safety and bookkeeping substrate for
live execution: durable event sourcing with an idempotency ledger, a
secrets/signing boundary that never exposes raw key material, deterministic
lifecycle state machines, and a risk approval/veto layer. It is built on the
**Python standard library only** (no third-party runtime dependency).

## What this is not (yet)

- **No live exchange connectivity** — only an in-memory `MockExchangeAdapter`
  exists; `ExchangeAdapter` is an abstract contract.
- **No top-level orchestration / entrypoint** — the repository contains the
  modules but no module that wires them into a running loop.
- **One signing backend** — only `EnvironmentHmacBackend`.

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for source-attested future work.

## Status

- Regression baseline: **305 tests passing** (plus 5 runtime subtests),
  verified on CPython 3.12.3.
- All nine modules frozen; repository reconciled to the approved
  implementation. See [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md).

## Modules

| # | Package | Responsibility (short) |
|---|---------|------------------------|
| 1 | `config` | Load/validate immutable typed config; no secrets, no business logic |
| 2 | `secrets_boundary` | Resolve secret references to signing capability; never expose raw keys |
| 3 | `event_store` | Append-only, crash-safe event sourcing + idempotency ledger |
| 4 | `execution_state_machine` | Deterministic execution-lifecycle state |
| 5 | `exchange_adapter` | Abstract exchange contract (+ mock) |
| 6 | `order_manager` | Order lifecycle: id generation, sequencing, replayable state |
| 7 | `position_manager` | Position lifecycle: fills, avg price, PnL, T1/T2/stop, close |
| 8 | `portfolio_manager` | Portfolio ledger: cash, margin, PnL, exposure, heat |
| 9 | `risk_manager` | Pure approval/veto over a proposed trade |

Numbering follows explicit `Module N` source references (1–8); Module 9 is
by elimination. Full API/dependency detail:
[`docs/MODULE_INVENTORY.md`](docs/MODULE_INVENTORY.md),
[`docs/DEPENDENCY_GRAPH.md`](docs/DEPENDENCY_GRAPH.md).

## Requirements

- **Python 3.11+** (inferred from `config/loader.py` using stdlib `tomllib`;
  verified on 3.12.3). No formal pin exists in the repository.
- **Tests:** `pytest` (the runner); tests themselves are `unittest`-based.
  No `requirements.txt`/`pyproject.toml` is present in the repository.

## Running the tests

```bash
python -m pytest
```

Expected: `305 passed, 5 subtests passed`.

## Repository layout

```
config/  secrets_boundary/  event_store/  execution_state_machine/
exchange_adapter/  order_manager/  position_manager/  portfolio_manager/
risk_manager/          # the nine frozen modules (one package each)
tests/                 # one test_*.py per module (305 tests total)
docs/                  # documentation set (start at docs/MASTER_INDEX.md)
config/example.toml    # sample configuration
```

Full tree: [`docs/REPOSITORY_STRUCTURE.md`](docs/REPOSITORY_STRUCTURE.md).

## Platform support

- **Linux:** verified (305 passing).
- **Windows:** portable by design — Module 3 locks via an import-guarded
  `fcntl` (POSIX) / `msvcrt` (Windows) shim. The `msvcrt` path is
  code-reviewed but **not runtime-verified** in this environment; validate on
  a real Windows host before it guards live capital.

## Documentation

Start at [`docs/MASTER_INDEX.md`](docs/MASTER_INDEX.md). Key entries:
release notes, project status, changelog, roadmap, architecture decisions,
security assumptions, module inventory, dependency graph, development
workflow, and onboarding.

## Contributing / freeze discipline

Modules 1–9 are frozen. Changes are additive-only and approval-gated; frozen
public APIs, on-disk formats, state-machine tables, and existing tests are
not modified except to correct an authorized critical defect. See
[`docs/DEVELOPMENT_WORKFLOW.md`](docs/DEVELOPMENT_WORKFLOW.md) and
[`docs/CLAUDE_ONBOARDING.md`](docs/CLAUDE_ONBOARDING.md).

## License

No license file is present in the repository. Licensing is therefore
unspecified here and not asserted.

---

*First stable release (Modules 1–9, frozen). All figures and interfaces are
taken directly from the repository.*
