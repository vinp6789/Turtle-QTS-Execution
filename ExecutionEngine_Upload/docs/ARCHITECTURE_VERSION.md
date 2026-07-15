# ARCHITECTURE_VERSION.md

All values below are grounded in repository contents. Where the repository
does not define a value, this is stated explicitly rather than guessed. No
dates are asserted (the repository contains no verifiable dates).

## Architecture Version

**1.0** (no version identifier is otherwise defined anywhere in the
repository; per instruction, 1.0 is used).

## Frozen Modules

Modules 1–9, all FROZEN:

| # | Package |
|---|---------|
| 1 | `config` |
| 2 | `secrets_boundary` |
| 3 | `event_store` |
| 4 | `execution_state_machine` |
| 5 | `exchange_adapter` |
| 6 | `order_manager` |
| 7 | `position_manager` |
| 8 | `portfolio_manager` |
| 9 | `risk_manager` |

## Regression baseline

- **305 tests collected and passing** (`pytest --collect-only` reports 305;
  full run reports `305 passed, 5 subtests passed`).
- The 5 subtests originate from one `self.subTest` loop in
  `tests/test_secrets_boundary.py`.
- Per-package counts: config 22, secrets_boundary 41, event_store 37,
  execution_state_machine 42, exchange_adapter 41, order_manager 23,
  position_manager 22, portfolio_manager 21, risk_manager 56.
- Verified in this environment under **CPython 3.12.3**, pytest 9.1.1.

## Python version

- **Minimum: Python 3.11+** — established from `config/loader.py`, which
  imports the standard-library `tomllib` (added in 3.11).
- Repository bytecode caches are present for **CPython 3.13**
  (`*.cpython-313.pyc`, the uploader's environment) and **CPython 3.12**
  (`*.cpython-312.pyc`, produced by verification runs in this environment).
- No `python_requires`, `pyproject.toml`, or `setup.py` exists in the
  repository to pin this formally — the 3.11 floor is inferred from
  `tomllib` usage only.

## Platform assumptions

- **Module 3 (`event_store`) is cross-platform (reconciled).**
  `event_store/_locking.py` import-guards `fcntl` (POSIX) and `msvcrt`
  (Windows); `store.py` locks only through that shim, so the module — and
  test collection — works on both platforms.
- **Linux is the verified platform.** The full suite (305) passes on
  Linux/CPython in this environment. The POSIX branch issues the identical
  `fcntl.flock` calls as before; the Windows `msvcrt` branch is
  code-reviewed but not runtime-executed here and should be validated on a
  real Windows host before it guards live capital.
- **Dependency footprint:** Python standard library only; no third-party
  runtime dependency. `pytest` is the runner; tests are `unittest`-based.

> **INCONSISTENCY — RESOLVED.** The uploaded ZIP was a pre-fix snapshot
> missing the approved Module 3 locking layer. The repository has been
> reconciled to the approved frozen implementation (`_locking.py`
> reconstructed, `store.py` restored). Delta vs the ZIP is exactly those
> two files; 305 tests still pass on Linux.

## Last verified module

- **Not declared in the repository.** The uploaded source contains no
  "last verified module" marker, changelog, or version file. All nine
  modules' tests pass on Linux (305 total), so no single module is
  distinguished as most-recently-verified by any repository field.
- Stated as unknown rather than guessed. (Prior-session activity is
  deliberately not used here, per the "do not rely on previous chat
  memory" instruction.)

## Current development milestone

- **Not defined in the repository.** The project statement is that Modules
  1–9 are "completed and frozen"; the repository itself carries no
  milestone marker, roadmap file, or changelog. Documentation packaging
  (this `docs/` set) is the activity in progress and is documentation-only.

## Next planned module

- **Not defined in the repository.** No roadmap, TODO, or "Module 10"
  reference exists anywhere in the source. Stated as unknown rather than
  guessed.
