# DEPENDENCY_GRAPH.md

Complete module dependency graph for the Turtle Execution Engine, derived
**only** from actual `import` statements in the repository. No assumptions;
every edge below corresponds to a real cross-package import.

## Module numbering (source of truth)

Numbering is taken from explicit `Module N` cross-references written in the
source code, not from memory:

| # | Package | Source attestation of the number |
|---|---------|----------------------------------|
| 1 | `config` | `risk_manager/models.py`, `risk_manager/manager.py` ("RiskProfileParams from Module 1", "Module 1 validates only its own config-file") |
| 2 | `secrets_boundary` | `event_store/store.py` ("Module 2's secret-reference guard"), `execution_state_machine/transitions.py` ("Module 2's SigningBoundary.revoke()") |
| 3 | `event_store` | `exchange_adapter/idempotency.py` ("Module 3 (EventStore)"), many others |
| 4 | `execution_state_machine` | `exchange_adapter/idempotency.py` ("Module 4 (ExecutionStateMachine)"), `order_manager/states.py` |
| 5 | `exchange_adapter` | `order_manager/manager.py` ("Module 5's typed ExchangeAdapter interface"), `risk_manager/models.py` ("Fill from Module 5") |
| 6 | `order_manager` | `order_manager/snapshot.py` ("which Module 6 consumes") |
| 7 | `position_manager` | `risk_manager/models.py` ("PositionSnapshot from Module 7") |
| 8 | `portfolio_manager` | `risk_manager/models.py` ("PortfolioSnapshot from Module 8") |
| 9 | `risk_manager` | **Inferred** — see inconsistency note below |

> **Flagged inference:** No literal string `Module 9` appears in the
> repository. `risk_manager` is assigned #9 by elimination (it is the only
> package without an explicit number) and because it is the top-level
> consumer (depends on Modules 1, 4, 5, 7, 8 and nothing depends on it).
> This is consistent with the strict acyclic ordering below but is **not**
> directly attested in source.

## Dependency direction

The engine forms a strict layered DAG. Every module depends only on
**lower-numbered** modules; there are **no cycles**. Numbers 1–3 are
foundational (zero internal dependencies).

## Import graph (actual cross-package edges)

```
config (1)                    -> (no internal dependencies)
secrets_boundary (2)          -> (no internal dependencies)
event_store (3)               -> (no internal dependencies)
execution_state_machine (4)   -> event_store (3)
exchange_adapter (5)          -> secrets_boundary (2)
order_manager (6)             -> event_store (3), execution_state_machine (4), exchange_adapter (5)
position_manager (7)          -> event_store (3), exchange_adapter (5)
portfolio_manager (8)         -> event_store (3)
risk_manager (9)              -> config (1), execution_state_machine (4), exchange_adapter (5),
                                 position_manager (7), portfolio_manager (8)
```

### Reverse view (who depends on each module)

```
config (1)                    <- risk_manager (9)
secrets_boundary (2)          <- exchange_adapter (5)
event_store (3)               <- execution_state_machine (4), order_manager (6),
                                 position_manager (7), portfolio_manager (8)
execution_state_machine (4)   <- order_manager (6), risk_manager (9)
exchange_adapter (5)          <- order_manager (6), position_manager (7), risk_manager (9)
order_manager (6)             <- (none)
position_manager (7)          <- risk_manager (9)
portfolio_manager (8)         <- risk_manager (9)
risk_manager (9)              <- (none)
```

### ASCII layer diagram

```
Layer 0 (foundational):   config(1)   secrets_boundary(2)   event_store(3)
                             |              |                    |
Layer 1:                     |        exchange_adapter(5)  execution_state_machine(4)
                             |         /        |    \          |
Layer 2:              order_manager(6) position_manager(7) portfolio_manager(8)
                             \______________ | ______________ /
Layer 3 (top consumer):                risk_manager(9)  <- config(1), esm(4), adapter(5), pos(7), port(8)
```

## Package responsibilities (verbatim/paraphrased from each `__init__.py`)

- **config (1)** — Load, validate, and provide immutable, typed access to
  deployment configuration. Owns no business logic and never holds secret
  material (only named references resolved later).
- **secrets_boundary (2)** — Resolve secret references to usable signing
  capability without ever exposing raw secret material. Other modules
  depend only on `SigningBoundary.sign(...)`.
- **event_store (3)** — Durable, append-only, crash-safe event sourcing
  with an idempotency ledger for exchange actions. No business logic; it
  only records and replays.
- **execution_state_machine (4)** — Single source of truth for execution
  lifecycle state; explicit, finite, event-driven, deterministic. Only
  validates and durably records transitions requested by other modules.
- **exchange_adapter (5)** — Abstract exchange contract only (plus a mock).
  No exchange-specific business logic, no real network calls, no trading
  decisions.
- **order_manager (6)** — Order lifecycle after a trade decision:
  deterministic id generation, outbound sequencing, and durable, replayable
  order-state tracking. Talks to the exchange only through Module 5.
- **position_manager (7)** — Complete lifecycle of live positions after an
  order begins filling: fill accumulation, average price, realized/
  unrealized PnL, T1/T2/stop/breakeven status, close, archival. Pure
  bookkeeping over caller-supplied levels.
- **portfolio_manager (8)** — Portfolio-level state only: cash, margin,
  PnL, exposure, heat, and the set of open positions. A single-lock ledger,
  not a lifecycle state machine.
- **risk_manager (9)** — Pure approval/veto module: given a fully-specified
  proposed trade and already-computed inputs from other frozen modules,
  determines whether the trade is permitted. Never sizes or submits.

## Verification method

- Edges extracted by AST-walking every `*.py` in each package and keeping
  only `import`/`from` targets whose top-level name is another package in
  this repository.
- Result: acyclic, strictly lower-numbered dependencies only.
- External (non-local) imports across the whole codebase are Python
  **standard library only** (`abc`, `ast`, `dataclasses`, `datetime`,
  `decimal`, `enum`, `hashlib`, `hmac`, `json`, `os`, `pathlib`, `re`,
  `struct`, `threading`, `time`, `tomllib`, `types`, `typing`, `uuid`,
  and `copy`/`pickle`/`tempfile`/`unittest` in tests). No third-party
  runtime dependency.
- **Platform-specific import (portable):** `event_store/_locking.py`
  import-guards `fcntl` (POSIX) and `msvcrt` (Windows); `store.py` locks
  only through that shim. The module imports on both platforms. `_locking`
  is an intra-package private module, so it adds **no cross-package edge**;
  `event_store` remains dependency-free at the package level.
