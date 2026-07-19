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

## Run as an application (deploy / monitor from your phone)

The frozen engine is now wrapped by an additive **application layer**
(`app/`) that turns it into a deployable service — identical on a Windows
laptop, Docker, a VPS, or Railway. The engine itself remains standard-library
only and unaware of HTTP/Telegram/Docker.

```bash
pip install -r requirements-app.txt
# Windows:  powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1
# Unix:     bash scripts/run_local.sh
```

Then, in a browser or on your phone:
- **Dashboard** (mobile): http://localhost:8000/
- **API docs** (OpenAPI/Swagger): http://localhost:8000/docs
- **Health**: http://localhost:8000/health · **Metrics**: `/metrics`

Boots in **paper mode** (no network, no real orders) by default. Full guide:
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) ·
[`docs/OPERATIONS.md`](docs/OPERATIONS.md) ·
[`docs/PRODUCTION_CHECKLIST.md`](docs/PRODUCTION_CHECKLIST.md).

Architecture: `Engine → app.runtime (worker) → app.api (FastAPI REST +
dashboard + metrics) + app.telegram (bot)`. The API is only an interface
layer; nothing under `app/` is imported by any frozen module.

## Historical scope notes (superseded by later modules and the app layer)

The three caveats below described the v1.0 (Modules 1–9) snapshot. Module 10
(Hyperliquid adapter) added live connectivity, and the `composition_root` /
`orchestration` / `trading_system` / `app` layers added the wiring and
entrypoint. Retained for provenance:

- ~~No live exchange connectivity~~ → Module 10 `hyperliquid_adapter`.
- ~~No top-level orchestration / entrypoint~~ → `composition_root`,
  `orchestration`, `trading_system.scheduling`, and `app.main`.
- **One signing backend** — still only `EnvironmentHmacBackend` (plus the
  venue wallet signer for EIP-712).

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for source-attested future work.

## Status

- Regression baseline: **319 tests** (config 35, event_store 38) plus 5
  runtime subtests. Verified **319 passing on Windows** (CPython 3.13)
  after the Module 1.1 evolution; the Linux baseline, last directly
  verified at **305 passing** (CPython 3.12.3) as of Module 3.1, is
  expected at 318 by the same platform-neutral delta but was not
  independently re-run on Linux this session.
- All nine modules frozen; Module 3 re-frozen as **Module 3.1** after a
  critical Windows defect correction (v1.0.1), and Module 1 re-frozen as
  **Module 1.1** after an additive evolution (v1.1.0, optional
  `wallet_key_ref`). See [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md)
  and [`docs/CHANGELOG.md`](docs/CHANGELOG.md).

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

Expected: `319 passed, 5 subtests passed` (Windows, current; Linux was last
directly verified at `305 passed, 5 subtests passed` as of Module 3.1 and is
expected at 318, not independently re-run this session).

## Repository layout

```
config/  secrets_boundary/  event_store/  execution_state_machine/
exchange_adapter/  order_manager/  position_manager/  portfolio_manager/
risk_manager/          # the nine frozen modules (one package each)
tests/                 # one test_*.py per module, two for config (319 tests total)
docs/                  # documentation set (start at docs/MASTER_INDEX.md)
config/example.toml    # sample configuration
```

Full tree: [`docs/REPOSITORY_STRUCTURE.md`](docs/REPOSITORY_STRUCTURE.md).

## Platform support

- **Linux:** last directly verified at 305 passing (CPython 3.12.3) as of
  Module 3.1; expected at 318 after Module 1.1's platform-neutral
  additions, not independently re-run this session.
- **Windows:** verified (319 passing, CPython 3.13) after the Module 1.1
  evolution. Module 3 locks via an import-guarded `fcntl` (POSIX) /
  `msvcrt` (Windows) shim and opens its log with `O_BINARY`; both the
  `msvcrt` lock path and the binary-open fix remain runtime-exercised on a
  real Windows host, including a dedicated binary-framing regression test.

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
