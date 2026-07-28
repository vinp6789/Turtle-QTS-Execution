# Alpha Engine — Decision Record

> This is one of **two** decision logs, by design — see
> `../docs/PROJECT_CONSTITUTION.md` §11. This log covers the **Alpha
> Engine** only. For frozen **Execution Engine** decisions, see
> `../docs/ARCHITECTURE_DECISIONS.md`.

Running log of Alpha-Engine-scoped implementation decisions that Roadmap
v1.0 flagged as open. Not an architecture document (see
`ARCHITECTURE_DECISIONS.md`/v0.2 review for that); this is a short,
append-only record of specific calls made during implementation and why.

---

## D1 — Experiment Registry substrate (Milestone 0.1)

**Decision:** File-based, append-only, newline-delimited-JSON log, owned
and stored entirely by `alpha_engine/registry/` — a **new, independent**
store, not the Execution Engine's `EventStore` instance or class.

**Options considered** (per Architecture v0.2 §7.4):

1. **File-based (chosen).** Consistent with this repository's existing,
   proven-at-scale pattern (`event_store/`): append-only, no new runtime
   dependency, no new operational surface (no install, no credentials, no
   backup story beyond what already exists for `data/`).
2. **DB-backed.** Rejected for now: introduces a new dependency and
   operational surface disproportionate to current needs (one registry,
   low write volume, no concurrent-writer requirement yet). Revisitable
   if query complexity grows past what a flat log comfortably serves.
3. **Reuse the Execution Engine's `EventStore` instance/class directly.**
   Rejected: would couple an experimental, still-evolving subsystem's
   lifecycle to a frozen, capital-critical module's locking/replay
   semantics -- the wrong coupling direction. Per the approved
   architecture, the Alpha Engine depends on the Execution Engine only
   through the public `Strategy`/`TradeIntent` seam, never through its
   internal frozen persistence machinery. A shared *pattern* (append-only,
   checksummed) is fine; a shared *instance* is not.

**Reversibility:** Cheap today -- no experiment has been recorded yet.
Revisit only if a genuine substrate limitation is hit during
implementation (per standing instruction: no further architecture churn
absent a real issue).

**Status:** Decided by implementer per user direction to proceed;
override welcome at any time before Milestone 0.2 writes real data.

---

## D2 — Lifecycle state machine lives in the registry (R2)

The ten-state lifecycle (Architecture v0.2 SS3) is stored and enforced by
`ExperimentRegistry` (`registry/lifecycle.py` + durable `state_changed`
entries), because SS1 makes the registry the experiment's outcome
timeline. The `alpha_engine.lifecycle` package hosts POLICIES (when to
request a transition), not the machine. Deliberate deltas from the SS3
diagram are documented in `registry/lifecycle.py` (CANDIDATE merged into
VALIDATING; DEFERRED terminal; FROZEN re-approval unmodeled).

## D3 — Governance-gated states are structurally fenced (R2/R3)

APPROVED/REJECTED/DEFERRED are unreachable through `transition()`
(GovernanceRequiredError); the only path is
`registry.apply_governance_decision()`, called by
`governance.record_governance_decision()` after evidence-fingerprint and
reviewer-separation checks. Replay enforces the same invariant (a state
entry entering a gated state without a preceding decision entry is a
malformed log). Identity is plain strings -- no auth layer exists; the
separation check is the honest subset of SS2.2 buildable today.

## D4 — Evidence attaches once, to a sealed experiment only (R1)

One EvidencePackage per experiment, ever; re-runs are new, parent-linked
experiments. Attachment requires a sealed (immutable) specification, and
the typed path (`validation.attach_evidence_package`) additionally
requires the package's embedded specification to equal the registered
one byte-for-byte (pre-registration integrity).

## D5 — Catalog is explicit source, not discovery (R4)

`CANDIDATE_CATALOG` is a hand-maintained, import-time, read-only mapping.
No filesystem scanning, no entry points, no runtime registration:
determinism and reviewability over convenience.

## D6 — The execution bridge serves the funding family only (R6)

`Strategy.generate_intents` must be pure over its context;
`context.market_data` carries funding rate but NOT open interest, and
the OI provider does its own HTTP (impure in-strategy). OI candidates can
therefore be researched/validated/approved but not traded live until
either a context extension or an injected-snapshot design is consciously
chosen. Stop/T1/T2 levels come from pre-registered spec parameters
("stop_fraction" required; "t1_fraction"/"t2_fraction" optional) --
never fabricated by the bridge.

## D7 — Conflict refusal is the only multi-hypothesis policy (R6)

When approved candidates disagree on a symbol (LONG vs SHORT), every
signal for that symbol is dropped. Netting/weighting/priority are
governance-owned future policies (Architecture v0.2 SS7#2), not silent
defaults.

## D8 — Degradation standard is the pre-registered bar (R7)

A live experiment is degraded exactly when a recent ValidationResult
fails the experiment's OWN acceptance criteria. No invented drift
thresholds. Degradation freezes (stops emission via the approved-set
query); it never force-closes positions, and retirement stays a
deliberate operator/governance act.

## D9 — Audit remediation is additive, opt-in where behavior changes (post-R8)

An independent adversarial audit found 2 critical, 6 high, and several
medium/low findings (docs/ALPHA_ENGINE.md §8 has the full list). Per
explicit instruction, only A1, A2, B1–B6, C3, C4 were remediated; C1, C2,
C5–C12, D1–D9 (audit's own numbering) remain intentionally deferred.

Every fix that changes runtime behavior was made an OPT-IN, backward-
compatible addition rather than a forced behavior change:
- `ApprovedFundingAlphaStrategy(specifications, registry=None,
  watchlist=None)` — both new arguments default to None, preserving the
  exact pre-fix behavior (trust the held specs forever; no watchlist
  gate) for any caller not yet passing them. A1's liveness re-check and
  A2's cadence enforcement are unconditional once `registry` is
  supplied; C4's watchlist gate is unconditional once `watchlist` is
  supplied.
- `run_research_cycle(..., watchlist=None)` — same pattern for C4 at
  research-cycle time.
- B1's `sample_set_fingerprint` field on `ValidationResult`/
  `WalkForwardResult` defaults to `None` for direct construction but is
  always populated by `run_validation`/`run_walk_forward_validation`.

This was a deliberate choice over making any of these mandatory: the
audit asked for the STRUCTURAL capability to exist (liveness checking,
cadence enforcement, watchlist enforcement, integrity checksums), not
for every existing caller/test to be forced to adopt it in this pass —
consistent with "preserve backward compatibility wherever practical"
and "do not redesign subsystems unless required by the finding."

B3's storage hardening (lock + checksum + torn-tail tolerance) is the
one fix that is NOT opt-in — it changes `FileRegistryStorage`
unconditionally, because the finding was about the storage layer's own
integrity, not about a caller-visible behavior choice. It remains
backward compatible in the other direction: a log file written before
this fix (no per-line checksum) is still read correctly, just
unverified.

The locking primitive for B3 is intentionally a small, from-scratch
implementation local to `registry/storage.py` (duplicating ~15 lines of
stdlib `fcntl`/`msvcrt` calls) rather than an import of the frozen
`event_store._locking` equivalent — `alpha_engine` has a standing,
tested boundary (`test_alpha_engine_scaffold.py`'s
`TestNoFrozenModuleCoupling`) forbidding any import of a frozen,
mutation-capable Execution Engine package, and this finding did not
warrant crossing it.
