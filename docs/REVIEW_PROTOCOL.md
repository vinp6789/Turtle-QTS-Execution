# REVIEW_PROTOCOL.md

The project-wide review workflow, spanning both subsystems and naming
responsibilities across every tool/human involved in this repository's
development. This is the newer, broader layer that sits above
`docs/DEVELOPMENT_WORKFLOW.md` (the Execution-Engine-specific engineering
discipline it was built from) and `docs/RESEARCH_PLAYBOOK.md` (the
research-specific decision process) — read those for the domain-specific
detail; this document is the cross-cutting workflow and the "who does
what" that neither of them names.

```
Implementation
  ↓
Independent Review
  ↓
Security Audit
  ↓
Approval
  ↓
Merge
```

No stage is skipped, regardless of how small the change looks. Ambiguity
defaults to "do not merge; ask" — the same default `docs/
DEVELOPMENT_WORKFLOW.md` already establishes for the Execution Engine.

---

## 1. Implementation

Whoever implements (an AI session or a human contributor) works from the
repository as the sole source of truth — never from prior chat memory,
never from an assumption about what "probably" exists. For Execution
Engine work: read `docs/CLAUDE_ONBOARDING.md` first. For Alpha Engine
work: read `PROJECT_CONSTITUTION.md` and `PROJECT_STATUS.md` first. The
smallest additive change that accomplishes the stated goal is preferred
over a larger one, in both subsystems.

## 2. Independent Review

A reviewer distinct from the implementer checks: is the change additive
(no frozen file modified without explicit authorization), does it
preserve every existing public API and test, is the dependency direction
still correct (Alpha Engine depends on Execution Engine's public seam
only, never the reverse — mechanically checked by `tests/
test_alpha_engine_scaffold.py::TestNoFrozenModuleCoupling`), and does the
full regression suite still pass with an explained delta.

For research work specifically, independent review additionally means:
was the acceptance/rejection criteria genuinely locked *before* the
result was seen (`docs/RESEARCH_PLAYBOOK.md` §2's decision point)?

## 3. Security Audit

Required for any change touching signing, order submission, idempotency,
crash recovery, the single-writer lock, secrets/config handling, or —
on the Alpha Engine side — anything that could allow a mismatched or
stale specification to reach live trading (see the A1/A2/B-series audit
findings in `alpha_engine/DECISIONS.md` D9 for the precedent: a full
independent adversarial audit was run against the completed Alpha Engine
platform, findings were prioritized by risk, and the ten highest-priority
findings were remediated — that audit is the template for how a security
audit here should be conducted: verify every hypothesis against actual
source, never accept "tests pass" as proof of correctness, assess against
a real-money frame).

## 4. Approval

Explicit, human-given approval to proceed — never inferred, never
self-granted by an implementing session, and never generalized from a
past approval to a new, unrelated change (a prior "yes" authorizes what
was actually asked, not everything downstream of it). Reversible,
local, additive actions (editing a new file, running tests) don't need
this gate; changes to frozen code, destructive operations, or anything
with real-world side effects (a commit, a push, a live trade) do.

## 5. Merge

Only after approval. Commit messages state what changed, why it is
additive, the regression result, and any security/capital-protection
implications — per `docs/DEVELOPMENT_WORKFLOW.md` §5's existing
convention, which this protocol does not replace, only extends to cover
Alpha Engine and research work as well.

---

## Responsibilities by actor

- **Claude** (implementation and/or review, depending on the session's
  role): follows the process above; is explicit about which role it is
  currently playing (a session appointed "implementation engineer" is not
  simultaneously its own independent reviewer — see the historical
  precedent in `alpha_engine/DECISIONS.md` D9, where an explicit role
  switch — "you are NOT the implementation engineer, you are an
  independent adversarial reviewer" — was required before a real audit
  could be trusted). Never treats its own prior turn's claims as
  independently verified.
- **ChatGPT** (or any other general-purpose AI reviewer): usable as an
  independent second opinion specifically because it did not write the
  implementation — the same reasoning that motivates a distinct-identity
  reviewer in governance (`docs/RESEARCH_PLAYBOOK.md` §5). Should be
  given the repository state directly, not a summary from the
  implementing session, to avoid inheriting that session's blind spots.
- **Fable**: the adversarial-audit role — assumes real money/real
  consequences are at stake, does not defer to "tests pass" as proof of
  correctness, and actively tries to find what would break under
  real-world conditions (the same posture the Alpha Engine's own
  post-implementation audit used, `alpha_engine/DECISIONS.md` D9).
  Engaged specifically for security-audit-stage work (§3) or whenever a
  second, deliberately skeptical read is warranted before a
  capital-relevant change is approved.
- **The repository itself**: the automated, non-negotiable layer of
  review — the full test suite, the frozen-module-coupling test, the
  scaffold export-consistency tests. A change that breaks any of these is
  not reviewed further until fixed; the repository's own checks are not
  optional and are not overridden by a reviewer's opinion.
- **Human owner**: holds final approval authority (§4) for every
  merge-worthy change, sets research priorities (`ROADMAP.md`), and is
  the only party who can authorize modifying a frozen Execution Engine
  component or approve a model for live capital.

## Relationship to existing workflow documents

- `docs/DEVELOPMENT_WORKFLOW.md` — the Execution-Engine-specific
  engineering discipline (feature process, freeze process, regression
  policy, git workflow) this protocol builds on. Still authoritative for
  its scope; not superseded.
- `docs/RESEARCH_PLAYBOOK.md` — the research-specific decision process
  (idea → registration → validation → evidence → governance → promotion
  → retirement → post-mortem). This protocol's Independent Review /
  Security Audit stages apply *around* that process (reviewing the
  engineering that implements each stage), not *instead of* it.
- `docs/CLAUDE_ONBOARDING.md` — the standing onboarding prompt for any AI
  session; read this (or `PROJECT_CONSTITUTION.md` for Alpha Engine work)
  before starting Implementation (§1).
