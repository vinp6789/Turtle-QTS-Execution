# Alpha Engine — Architecture, Operations, and Production Checklist

> **This is the technical architecture reference.** For current
> project-wide state, start at `PROJECT_DASHBOARD.md` or
> `PROJECT_CONSTITUTION.md`. For the research process this platform
> supports, see `RESEARCH_PLAYBOOK.md`; for what research has actually
> found, see `RESEARCH_LEDGER.md` and `ALPHA_LIBRARY.md`; for the
> watchlist, see `WATCHLIST.md`.

**Status:** implementation complete through R8; adversarial audit
remediation complete (§8); historical data pipeline complete
(`HISTORICAL_DATA.md`); Research Campaign 01 (Open Interest) complete and
closed (`RESEARCH_LEDGER.md`). **747** Alpha-Engine-scoped tests
(**1,567** total repository suite, 820 Execution Engine baseline, verified
current — see `PROJECT_STATUS.md`). Entirely additive: zero frozen
Execution Engine modules modified; the only Execution Engine surfaces
consumed are the public `exchange_adapter` value types,
`trading_system.market_data.MarketDataView`, and the
`trading_system.strategy` Strategy/TradeIntent seam (the latter only from
`alpha_engine.execution_bridge`).

## 1. What it is

A deterministic, evidence-gated research platform that discovers,
validates, compares, promotes, and retires trading hypotheses — and
emits `TradeIntent`s for governance-approved ones through the Execution
Engine's existing strategy seam. "Self-improving" means the *research
loop* iterates (new hypotheses → validation → governance → live →
degradation → retirement); production code never modifies itself.

## 2. Layer map

| Package | Role |
|---|---|
| `alpha_engine.registry` | Durable experiment store: specs (sealed), evidence, governance decisions, ten-state lifecycle. Append-only JSONL behind a two-method `RegistryStorage` seam. |
| `alpha_engine.data_sources` | Fail-safe providers: funding rate (via `MarketDataView`), open interest (independent HTTP, live-verified response shape). |
| `alpha_engine.features` | Pure, versioned transforms (`funding_rate_raw` v1, `open_interest_raw` v1). |
| `alpha_engine.candidates` | `CandidateSpecification` (pre-registered, immutable, fingerprinted), two rule candidates, `CANDIDATE_CATALOG`. |
| `alpha_engine.validation` | Five stages (single-pass, causality audit, walk-forward, bootstrap, regime stratification) + immutable `EvidencePackage` + registry attachment with integrity cross-check. |
| `alpha_engine.governance` | `GovernanceDecision` (reviewer separation, evidence-fingerprint match) — the only path into APPROVED/REJECTED/DEFERRED. |
| `alpha_engine.lifecycle` | Degradation policy: pre-registered-bar assessment → freeze. |
| `alpha_engine.portfolio` | Conflict-refusing approved-signal selection (no sizing — the Execution Engine sizes). |
| `alpha_engine.execution_bridge` | `ApprovedFundingAlphaStrategy` (a real `Strategy`) + `load_approved_specifications`. |
| `alpha_engine.watchlist` / `alpha_engine.research` | Configurable universe; `run_research_cycle` + `compare_experiments`. |

## 3. Experiment lifecycle

```
PROPOSED → VALIDATING → EVIDENCE_SEALED → IN_REVIEW ─(governance)─→ APPROVED → SHAKEDOWN → FULL_PRODUCTION
   │            │                                        ├→ REJECTED (terminal)      │            │
   └→ WITHDRAWN └→ WITHDRAWN                             └→ DEFERRED (terminal)      ├────→ FROZEN ┘
                                                                                     └──────→ RETIRING → RETIRED
```
Guards: EVIDENCE_SEALED requires attached evidence; the three governance
states require a recorded decision; every transition is durable and
replay-verified.

## 4. Operating workflow

1. **Research:** build a `CandidateSpecification` (via a catalog
   factory), gather `ValidationSample`s (with outcome timestamps and
   regime labels for a clean audit), call `run_research_cycle(...)` —
   lands the experiment in EVIDENCE_SEALED with a five-stage
   `EvidencePackage` attached. Pass `watchlist=<Watchlist>` to refuse a
   specification whose universe reaches outside the configured watchlist
   (audit finding C4; optional, defaults to unconstrained).
2. **Review:** `compare_experiments(...)` for the ranked view;
   `registry.transition(id, IN_REVIEW)`; a human records a
   `GovernanceDecision` via `record_governance_decision(...)`.
3. **Promote:** `transition(id, SHAKEDOWN)`;
   `load_approved_specifications(registry)` →
   `ApprovedFundingAlphaStrategy(specs, registry=registry, watchlist=watchlist)`
   → wire into `AppState.create(strategies=...)` (see checklist §9).
   Passing `registry` enables live approval re-checking every cycle
   (audit finding A1); each spec's own `cadence_seconds` is now enforced
   against `context.evaluated_at_utc` automatically (audit finding A2).
4. **Monitor/retire:** periodically re-validate recent live samples,
   `assess_degradation(...)`; if degraded, `freeze_degraded(...)`
   (emission stops next reload); retire via
   `transition(RETIRING)` → `transition(RETIRED)`.

## 5. Known limitations (honest, load-bearing)

- **No proven edge exists.** Both candidate families are pipeline
  proofs. A validation PASS means "cleared its pre-registered bar on the
  supplied samples," never "has real alpha."
- **No historical sample store.** Validation consumes caller-supplied
  `(feature, outcome)` samples; the platform does not yet record live
  readings into a research dataset.
- **OI family is not live-tradeable** (bridge purity constraint —
  `DECISIONS.md` D6).
- **Deferred validation techniques** with named preconditions:
  attribution (needs a multi-feature candidate), calibration +
  purge/embargo (need a probabilistic/fitted candidate type), Monte
  Carlo + risk-of-ruin (need equity-curve machinery).
- **Identity is strings** — governance separation is enforced on names,
  not authenticated identities.
- **No scheduler** — research cycles and degradation checks are invoked,
  not self-running. The Execution Engine's worker only runs the bridge
  strategy once wired.
- **Registry storage locking is per-append, not session-held.**
  `FileRegistryStorage` now takes a cross-platform exclusive lock and a
  per-entry checksum for every `append()` call, and tolerates a torn
  trailing write on read (audit finding B3) — but unlike the frozen
  `EventStore`, it does not hold the lock for the storage object's whole
  lifetime (it has no persistent open handle). Acceptable for the current
  single-operator posture; revisit if a genuinely concurrent-writer
  deployment model emerges.
- **Approved-spec reload is opt-in, not automatic.** `ApprovedFundingAlphaStrategy`
  accepts an optional `registry` argument (audit finding A1): when
  supplied, every `generate_intents()` call re-verifies each held
  specification is still APPROVED/SHAKEDOWN/FULL_PRODUCTION before
  evaluating it, so a freeze/retirement takes effect on the very next
  cycle with no process restart. Omitting `registry` (or omitting it from
  `load_approved_specifications` + reconstruction) preserves the older,
  restart-to-reload behavior — a deployment must consciously wire the
  registry through to get live liveness checking.

## 6. Recommended future enhancements (in rough priority order)

1. Live sample recorder (persist provider readings + realized outcomes →
   feeds validation with real history, unlocks degradation on live data
   at cadence).
2. A fitted/probabilistic candidate type (unlocks calibration,
   purge/embargo, and a genuine Candidate behavior contract).
3. A second feature per family + a combining candidate (unlocks
   attribution).
4. Portfolio equity-curve machinery (unlocks Monte Carlo,
   risk-of-ruin, and shakedown ramp criteria).
5. Context extension or snapshot-injection design for OI live emission.
6. Authenticated identity for governance; scheduler/cadence driver;
   SQLite `RegistryStorage` backend if concurrency needs grow.

## 8. Audit remediation (2026-07-22)

An independent adversarial audit (post-R8) found 2 critical, 6 high, and
several medium/low findings. Per explicit instruction, only the
following were remediated in this pass; all others were intentionally
deferred (see below) rather than addressed opportunistically:

**Closed:**

- **A1 (critical) — stale live approval.** `ApprovedFundingAlphaStrategy`
  captured its specifications once, forever; a later freeze/retirement
  had no effect short of a process restart. Fixed with an optional
  `registry` constructor argument: when supplied, liveness is re-checked
  from the registry every `generate_intents()` cycle.
- **A2 (critical) — cadence never enforced.** `CandidateSpecification.
  cadence_seconds` was declared but ignored; every spec evaluated on
  every cycle. Fixed with internal per-spec due-tracking compared via
  `context.evaluated_at_utc` and `alpha_engine._time.parse_utc` (never
  the wall clock).
- **B1 (high) — no dataset fingerprint.** `ValidationResult` and
  `WalkForwardResult` now carry `sample_set_fingerprint`
  (`validation.models.fingerprint_samples()`), binding evidence to the
  exact samples that produced it.
- **B2 (high) — evidence fingerprint excluded `known_limitations`.**
  `EvidencePackage`'s content fingerprint now covers `known_limitations`;
  two packages differing only in disclosed caveats no longer
  fingerprint identically.
- **B3 (high) — no storage integrity/locking.** `FileRegistryStorage`
  now takes a per-append exclusive lock, writes a per-entry SHA-256
  checksum, and tolerates a torn trailing write on read (an
  unparseable-or-checksum-failing LAST line is discarded, not fatal;
  the same failure anywhere else still raises). Backward compatible:
  a pre-fix line with no checksum is accepted unverified.
- **B4 (high) — zero observability.** Every fail-safe degrade path
  (both providers, both features, both candidates) and every aggregate
  research-integrity failure (causality audit, single-pass validation,
  walk-forward) now logs via the standard `logging` module.
- **B5 (high) — raw-string timestamp ordering.** A new
  `alpha_engine._time` module (`parse_utc`/`canonical_utc`) replaced raw
  string comparison in `walk_forward.py`'s fold sort,
  `governance/decisions.py`'s `approved_experiments()` ranking, and
  `causality_audit.py`'s local timestamp parsing (consolidated onto the
  shared implementation).
- **B6 (high) — shallow copies at registry boundaries.** Every
  specification/evidence/decision read or write in `registry/registry.py`
  now goes through a JSON round-trip deep copy, closing a path where a
  caller mutating a nested value (or a value read back from a snapshot)
  could silently corrupt the registry's durable in-memory state.
- **C3 (medium) — hardcoded candidate dispatch.** The execution bridge
  now resolves `evaluate_fn` via `alpha_engine.candidates.
  get_candidate_type()` instead of importing
  `FundingRateThresholdRuleCandidate` directly.
- **C4 (medium) — watchlist never enforced.** `run_research_cycle`
  and `ApprovedFundingAlphaStrategy` both accept an optional `watchlist`
  argument; when supplied, a specification whose universe reaches
  outside it is refused at construction/cycle-start, not silently
  allowed through.

**Intentionally deferred** (out of scope for this remediation pass; not
attempted): C1, C2, C5–C12, D1–D9. These were explicitly excluded by the
remediation instruction ("treat the audit findings as the highest-priority
remaining work... do not address lower-priority findings yet") and remain
open for a future, separately-scoped pass.

All fixes are additive and backward compatible by default (new
constructor/function arguments are optional and default to the prior,
unconstrained behavior); the architecture, lifecycle, and layer
boundaries from R8 are unchanged. Full regression: 1,448 passed (628
Alpha Engine, 820 Execution Engine), zero failures.

## 9. Production deployment checklist (Alpha Engine)

- [ ] Registry storage path chosen and backed up (`FileRegistryStorage`;
      same disk-durability care as `data/events.log`).
- [ ] Watchlist file created and loaded (`load_watchlist`); candidate
      spec universes ⊆ watchlist.
- [ ] At least one experiment APPROVED by a real governance decision
      (reviewer ≠ researcher) over real (non-synthetic) samples.
- [ ] Approved spec parameters include sane `stop_fraction`
      (+ optional t1/t2) — reviewed as part of the hypothesis.
- [ ] Bridge wiring: construct `ApprovedFundingAlphaStrategy(
      load_approved_specifications(registry), registry=registry,
      watchlist=watchlist)` and pass via `AppState.create(settings,
      strategies=(strategy,))` at the entrypoint. Passing `registry` is
      what enables live approval re-checking (§8, A1) instead of
      restart-to-reload; passing `watchlist` enables the C4 enforcement
      gate. This is the one integration line deliberately NOT pre-wired
      (no approved hypothesis existed at build time). Note:
      `tests/test_alpha_engine_scaffold.py`'s "no production file
      references alpha_engine" test is EXPECTED to be updated in the
      same change.
- [ ] Execution Engine's own pre-flight checklist completed
      (`docs/PRODUCTION_CHECKLIST.md`) — unchanged by the Alpha Engine.
- [ ] Degradation cadence agreed (who re-validates live samples, how
      often) and retirement runbook understood (freeze → emission stops;
      positions exit via the Execution Engine's own machinery).
- [ ] `docs/MASTER_INDEX.md` updated to reference this document at
      commit time (left untouched during development to keep the tree
      purely additive).
