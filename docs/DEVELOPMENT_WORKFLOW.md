# DEVELOPMENT_WORKFLOW.md

The workflow the Turtle Execution Engine follows from here forward. It
encodes the practices already used to build and freeze Modules 1–9:
additive-only change, security/capital-protection first, full regression
after every milestone, and explicit human approval before freezing.

## Guiding constraints

- The **repository is the only source of truth**; prior-chat memory never
  overrides it.
- **Security and capital protection take precedence** over speed and
  convenience.
- **Additive-only:** prefer the smallest change that preserves existing
  behavior. Frozen modules are not redesigned or optimized.
- **Nothing frozen changes** except to correct an authorized critical
  defect (see Freeze process).

## 1. Feature development process

1. **Read first.** Read the repository and `docs/` completely before
   proposing anything. Never recreate an interface from memory.
2. **Verify the ground truth.** Confirm the dependency graph, the public
   interfaces (`__all__`), the actual imports, and any duplicated
   contracts. State assumptions explicitly.
3. **Plan.** Write an implementation plan: what changes, why it is
   additive, which module owns it, and how backward compatibility is kept.
   Wait for approval.
4. **Implement.** Make the smallest additive change. New behavior goes in a
   new module/function/private helper; frozen logic is not rewritten.
5. **Self-check.** Confirm no public API changed, no cycle/upward
   dependency introduced, no test modified.

## 2. Security audit process

Run for any change touching signing, order submission, idempotency, crash
recovery, the single-writer lock, or config/secret handling:

1. Confirm no secret material can enter events, logs, config values, or
   payloads (the signing boundary must remain the only path to key use).
2. Confirm fail-safe behavior: uncertain/bad state blocks new actions
   rather than proceeding.
3. Enumerate the security implications and the capital-protection
   implications in writing.
4. Enumerate every assumption introduced (especially platform-specific
   ones, e.g. Windows locking).
5. Present findings; a security-relevant change is not frozen without an
   explicit sign-off on these implications.

## 3. Freeze process

A module (or change) is frozen only after:

1. The implementation plan was approved.
2. The full regression suite passes with the expected count.
3. Security and capital-protection implications were reported and accepted.
4. Assumptions were documented.
5. **Explicit human approval** to freeze is given.

**Critical-defect exception:** a frozen module may be modified only to fix
a genuine correctness, security, or capital-protection defect, following
propose → approve → implement → full-regression → audit → re-freeze, and
only with explicit authorization. Never self-initiated.

## 4. Regression process

- Baseline: **319 tests passing on Windows** (CPython 3.13, current), plus
  5 subtests. Linux was last directly verified at 305 (CPython 3.12.3, as
  of Module 3.1) and is expected at 318 after Module 1.1's 13
  platform-neutral tests, but this was not independently re-run on Linux
  this session. The one Windows-only test (Module 3.1) is the sole platform
  delta beyond that expected +13.
- Run the **complete** suite after every milestone: `python -m pytest`.
- Report the pass/fail count and diff against baseline; explain any change.
- **Never edit a test to make it pass.** Tests are part of the frozen
  contract; changing one requires the same authorization as changing
  frozen source. A new module adds its own test file; it does not touch
  existing ones.
- When a new module is frozen, update the baseline count in
  `ARCHITECTURE_VERSION.md` (documentation update, not a code change).

## 5. Git workflow

> The repository currently has no VCS metadata or `.gitignore` present in
> the uploaded tree; the following is the recommended convention, flagged
> as not-yet-present rather than assumed.

- One logical change per branch; branch name references the module/feature.
- Exclude generated artifacts (`__pycache__/`, `.pytest_cache/`) via
  `.gitignore`.
- Commit messages state: what changed, why it is additive, regression
  result, and (if applicable) security/capital-protection implications.
- Tag a frozen baseline once Modules 1–9 (and later modules) are approved
  — e.g. `execution-engine-v1.0` (see the readiness note in this session's
  summary and `ARCHITECTURE_VERSION.md`).

## 6. Review workflow

- Every change is reviewed against: additive-only, no public-API change,
  no dependency cycle, full regression green, tests untouched, security +
  capital-protection implications stated.
- The reviewer explicitly approves before freeze. Ambiguity defaults to
  "do not freeze; ask."

## 7. Documentation update workflow

- `docs/` is updated whenever a module is added or a baseline changes.
- Update `MODULE_INVENTORY.md` (new row), `DEPENDENCY_GRAPH.md` (new
  edges), `ARCHITECTURE_VERSION.md` (baseline, frozen list, last-verified),
  and `REPOSITORY_STRUCTURE.md` (tree).
- Documentation must be regenerated from actual repository contents, never
  from memory. Every asserted number (tests, deps, APIs) is re-verified
  against the repo before the docs are updated.

## 8. When to start a new chat

Start a fresh session when: a module is complete and frozen; the context
has grown long enough to risk drift; or you are switching from one module
to an unrelated one. A clean boundary reduces the chance of carrying stale
assumptions forward.

## 9. How to continue safely after a new chat

1. Load `docs/CLAUDE_ONBOARDING.md` as the standing prompt.
2. Re-read the repository — do **not** trust prior-chat memory.
3. Re-verify the baseline by running the full suite before making changes.
4. Re-verify the dependency graph and public interfaces from source.
5. Only then proceed with the plan → approve → implement → regress →
   audit → freeze loop above.
