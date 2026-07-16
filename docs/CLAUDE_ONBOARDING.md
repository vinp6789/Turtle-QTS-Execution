# CLAUDE_ONBOARDING.md

Standard onboarding for any future Claude (or other AI) session working on
the **Turtle Execution Engine**. Read this before touching anything. This
document orients you; it does **not** authorize changes.

## 0. First principle

The **repository is the only source of truth.** If anything in a prior
chat, a summary, or your own memory conflicts with the repository, trust
the repository. If information is missing, say so explicitly — do not guess.

## 1. Which documents to read first (in order)

1. `docs/CLAUDE_ONBOARDING.md` — this file.
2. `docs/ARCHITECTURE_VERSION.md` — version, frozen modules, baseline.
3. `docs/MODULE_INVENTORY.md` — the nine modules, APIs, deps, test counts.
4. `docs/DEPENDENCY_GRAPH.md` — real import graph and layering.
5. `docs/REPOSITORY_STRUCTURE.md` — the tree.
6. `docs/DEVELOPMENT_WORKFLOW.md` — how work proceeds from here.

Then read the actual `__init__.py` and module docstrings of any package you
will touch. The docstrings are authoritative on responsibility and scope.

## 2. Which packages are authoritative

All nine packages are authoritative and **FROZEN**:

`config` (1), `secrets_boundary` (2), `event_store` (3),
`execution_state_machine` (4), `exchange_adapter` (5), `order_manager` (6),
`position_manager` (7), `portfolio_manager` (8), `risk_manager` (9).

The public contract of each is exactly its `__all__` in `__init__.py`.
Treat those symbols as stable interfaces.

## 3. Frozen architecture rules

- Modules 1–9 are production-frozen. Do **not** redesign, restructure,
  rename, or "optimize" any of them.
- The dependency graph is a strict acyclic, lower-numbered-only layering
  (see `DEPENDENCY_GRAPH.md`). Do not introduce a cycle or an upward
  dependency (e.g. a foundational module must never import a higher one).
- Do not modify a frozen module's public API (its `__all__`), on-disk
  formats (e.g. the event-store record framing), or documented guarantees.
- Single-responsibility boundaries are intentional. Business logic does not
  belong in `event_store`, `execution_state_machine`, or `exchange_adapter`.

## 4. Additive-only policy

- Prefer the **smallest additive change** that preserves existing behavior.
- New capability arrives as a new module, a new function, or a new private
  helper — never by rewriting frozen logic.
- Backward compatibility is mandatory. Existing callers and existing tests
  must keep working unchanged.
- The only sanctioned exception to "do not modify frozen code" is a
  genuine **correctness, security, or capital-protection defect**,
  corrected via the freeze process in `DEVELOPMENT_WORKFLOW.md`, and only
  after **explicit human authorization** — never self-initiated.

## 5. Regression policy

- The regression baseline is **319 tests passing on Windows** (CPython
  3.13, current), plus 5 subtests. Linux was last directly verified at 305
  (CPython 3.12.3, as of Module 3.1) and is expected at 318 after Module
  1.1's 13 platform-neutral tests, but this was not independently re-run on
  Linux this session. The one Windows-only test (Module 3.1) is the sole
  platform delta beyond that expected +13.
- Run the **complete** suite after any change: `python -m pytest`.
- Report any change in pass count, and explain any regression.
- Do not modify tests to make them pass. Tests are part of the frozen
  contract; changing a test to accommodate new code requires the same
  authorization as changing frozen source.

## 6. Security review policy

- **Security and capital protection take precedence over all else**,
  including helpfulness and convenience.
- Never place secret material in events, logs, config values, or payloads.
  `secrets_boundary` (2) exposes only `SigningBoundary.sign(...)`; raw key
  material must never cross a module boundary. `event_store` actively
  rejects payload field names that look like secrets.
- Any change touching signing, order submission, idempotency, crash
  recovery, or the single-writer lock requires an explicit security +
  capital-protection review (state the implications) before freeze.
- Prefer failing safe: block new actions on bad/uncertain state rather than
  proceeding.

## 7. Module numbering

- Numbers 1–8 are attested by explicit `Module N` comments in the source;
  9 is inferred by elimination (see `DEPENDENCY_GRAPH.md`).
- Numbering reflects the dependency layering: a module may depend only on
  lower-numbered modules.
- A future module continues the sequence (the next would be Module 10) and
  must not renumber existing modules.

## 8. Development workflow (summary; full detail in DEVELOPMENT_WORKFLOW.md)

1. Read the repository completely before proposing anything.
2. Verify the dependency graph, public interfaces, imports, and any
   duplicated contracts.
3. Explain the implementation plan and wait for approval.
4. Implement the smallest additive change.
5. Run the full regression suite; report results, security implications,
   capital-protection implications, and any assumptions introduced.
6. Wait for explicit approval before freezing or continuing.

## 9. How new modules must integrate

- A new module gets the next number and lives in its own package with its
  own `__init__.py` declaring a minimal `__all__`.
- It may depend only on already-frozen, lower-numbered modules through
  their public `__all__` — never on another module's internal control flow.
- It must persist state (if any) through `event_store` (3) and drive
  lifecycle through the relevant state machine, rather than inventing a
  parallel mechanism, matching the existing pattern.
- It ships with its own `tests/test_<package>.py` and must not alter any
  existing test file.
- Integration must not add an upward or circular dependency.

## 10. What must never be modified

- Any frozen module's **public API** (`__all__`).
- The **event-store on-disk record format** and its recovery/replay/
  idempotency guarantees.
- The **signing boundary** contract (no raw-secret exposure).
- The **state-machine transition tables** and their determinism.
- The **dependency layering** (no cycles, no upward edges).
- The **existing tests**.
- Any source file, unless correcting an authorized critical defect.
