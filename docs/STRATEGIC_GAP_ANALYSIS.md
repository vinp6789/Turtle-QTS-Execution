# Strategic Gap Analysis — Long-Term Vision vs. Current Repository

> **STATUS:** point-in-time analysis, dated 2026-07-23, **before** Research
> Campaign 01 was executed. Several findings below are now updated by
> events since — most notably, "no validated alpha exists" is now "one
> campaign closed, zero approved, four rejected" (see
> `docs/RESEARCH_LEDGER.md` and `docs/ALPHA_LIBRARY.md`), and the
> per-capability completion estimates are carried forward, current, in
> `docs/PROJECT_STATUS.md`. This document's item-by-item methodology and
> reasoning remain valid and are not repeated elsewhere — treat it as the
> detailed backing analysis, and `PROJECT_STATUS.md`/`PROJECT_DASHBOARD.md`
> as the current numbers.

**Method:** every claim below was checked directly against the current
repository (grep/read of the actual source, not memory or assumption).
Where the code was inspected live for this analysis, that is noted.
Analysis only — no code changed, no architecture proposed.

---

## Per-item assessment

### 1. Researches new ideas offline
**IMPLEMENTED AND VALIDATED — ~95%.** `run_research_cycle()` (5 validation
stages + evidence sealing) is not just built, it has been run end-to-end
on real 18-month BTC/ETH/SOL data (Research Campaign 01) and produced a
real, sound result. This is the most exercised capability in the system.

### 2. Continuously expands its knowledge through evidence-based research
**PARTIALLY IMPLEMENTED — ~30%.** The mechanism to execute *one*
research act and durably record its evidence is proven. "Continuously"
implies self-driving iteration; there is none. Verified: no scheduler,
no automatic hypothesis generation, no loop — `docs/ALPHA_ENGINE.md`
itself states "research cycles and degradation checks are invoked, not
self-running." Every campaign to date has been manually designed and
manually invoked.

### 3. Promotes only statistically validated alpha models
**IMPLEMENTED AND VALIDATED — ~95%.** `alpha_engine.governance` enforces
reviewer≠researcher and an evidence-fingerprint match as the *only* path
to APPROVED. Verified live: Campaign 01 recorded four real REJECT
decisions this way. Gap: "identity is strings" — no authenticated
reviewer identity (a documented, narrow limitation, not a functional one).

### 4. Retires degraded alpha models
**IMPLEMENTED BUT NOT YET VALIDATED (blocked on a missing input) — ~50%.**
`assess_degradation()`/`freeze_degraded()` and the RETIRING→RETIRED
lifecycle transitions exist and are unit-tested. But degradation
assessment requires a fresh `ValidationResult` over *recent live samples*
— and no live sample recorder exists (see Engineering Gap below), and no
model has ever been live-approved in the first place. The mechanism is
real; it has never fired for a real reason because nothing has reached
the state that would trigger it.

### 5. Maintains an approved Alpha Library
**PARTIALLY IMPLEMENTED — ~40%. No dedicated abstraction exists.**
Verified: there is no "Alpha Library" concept anywhere in the codebase.
What exists instead: `CANDIDATE_CATALOG` (a fixed enumeration of
candidate *mechanism* families — currently 3 rule-based families — not
of validated models), and registry queries
(`list_experiments(state=APPROVED)`, `governance.approved_experiments()`)
that give an implicit, queryable "current approved set" with no curated
metadata or cross-family browsing view. The durable data a library needs
already exists in the registry; the library *as a maintained concept*
does not.

### 6. Evaluates every asset in a configurable watchlist
**PARTIALLY IMPLEMENTED — ~55%.** `Watchlist` exists and — since this
session's audit remediation (finding C4) — is now actually *enforced*
(a `CandidateSpecification.universe` must be a subset of the watchlist,
checked at both `run_research_cycle` and bridge construction; proven in
Campaign 01). But enforcement is a guardrail ("never evaluate outside
the list"), not a driver ("automatically evaluate every member"). A human
still decides which watchlist symbols go into any given
`CandidateSpecification.universe`; nothing iterates the watchlist and
proposes/evaluates a candidate for every member automatically.

### 7. Combines multiple approved alpha models for each asset
**PARTIALLY IMPLEMENTED — ~25%.** Verified in `portfolio/selection.py`:
`select_signals()` only (a) collapses identical-direction duplicates to
one representative and (b) refuses (drops) a symbol entirely if two
approved candidates disagree. There is no actual *combination* —
weighting, consensus-strengthening, or graded scoring of multiple
models' opinions into one stronger verdict. The module's own docstring
confirms this is deliberate and deferred: "Netting, weighting, or
trusting the higher-ranked candidate are all real policies a future
milestone may add under governance control." The conflict-*safety* half
of "combining" exists; the combination-*value* half does not.

### 8. Ranks the watchlist based on combined evidence
**NOT IMPLEMENTED — 0%.** Verified: `alpha_engine.research.
compare_experiments()` ranks *experiments* (hypotheses) by their own
evidence — it has no concept of "asset X currently has combined score Y
across its approved models." No per-asset ranking exists anywhere in the
repository.

### 9. Generates TradeIntents only for the highest-ranked opportunities
**NOT IMPLEMENTED — 0%.** Verified: `ApprovedFundingAlphaStrategy.
generate_intents()` emits an intent for *every* signal that survives
conflict-refusal, cadence, and liveness checks — there is no
ranking-based "top N only" filter anywhere in the bridge or portfolio
layer. Capital discipline downstream of this point comes entirely from
the frozen `RiskManager`'s own generic limits (leverage, heat cap,
correlated positions), which is a different mechanism than
opportunity-ranking.

### 10. Uses the existing Execution Engine for deterministic execution
**IMPLEMENTED AND VALIDATED — ~100% as a mechanism; not yet exercised
live.** `ApprovedFundingAlphaStrategy` is a real, wired
`trading_system.strategy.Strategy`; zero frozen modules are touched;
sizing/execution/risk are entirely delegated downstream. This is the
most mature integration in the codebase (it also inherits the frozen
platform's own separate production audit). Caveat: no model has ever
actually gone live through it — the mechanism is proven by tests, not by
a real trade.

### 11. Preserves replay correctness and auditability
**IMPLEMENTED AND VALIDATED — ~95%.** This has been the dominant
engineering discipline throughout: canonical UTC timestamp handling,
content-derived fingerprints at every layer, injectable clocks/seeds
everywhere, checksummed+locked registry storage, sealed immutable
evidence packages. Proven in Campaign 01 (fixed seed/clock, sealed
fingerprints recorded and reproducible).

### 12. Prioritizes capital preservation over returns
**PARTIALLY IMPLEMENTED, BEHAVIORALLY STRONG BUT STRUCTURALLY IMPLICIT —
~65%.** Real supporting evidence: conflict-refusal defaults to "no
trade" on any disagreement; degradation *freezes* (never force-closes or
compensates); `stop_fraction` is mandatory and never fabricated on any
intent; the frozen `RiskManager` (outside alpha_engine) already enforces
leverage/heat-cap/correlation limits independently; and Campaign 01 is a
direct demonstration of the research culture — a hypothesis was rejected
rather than the bar lowered to manufacture a pass. Gap: there is no
single, *named* capital-preservation policy object in alpha_engine
itself — the behavior is emergent from several separate conservative
defaults, not a unified, governance-owned policy.

### 13. Improves through new research rather than live parameter optimization
**IMPLEMENTED AND VALIDATED — ~100%.** Verified structurally: there is no
online-learning or live-threshold-tuning code path anywhere. Every
parameter is pre-registered and immutable per `CandidateSpecification`;
the only way to change one is a new experiment (new spec, new
fingerprint, new evidence, new governance decision). Campaign 01
explicitly enacted this discipline — a rejected hypothesis was recorded
and closed, not re-tuned.

---

## Groupings

### 1. Finished / stable
- Offline research execution (#1)
- Governance promotion gate (#3)
- Execution Engine integration mechanism (#10)
- Replay correctness / auditability (#11)
- No-live-optimization discipline (#13)

### 2. Partially complete
- Degradation/retirement (#4) — mechanism done, unexercised, blocked on live sample recorder
- Alpha Library (#5) — data exists, curated concept doesn't
- Watchlist evaluation (#6) — enforced as guardrail, not a driver
- Multi-model combination (#7) — conflict-safety only, no real combination
- Capital preservation (#12) — behaviorally present, not a unified policy

### 3. Completely missing
- Continuous/self-driving research loop (#2)
- Watchlist ranking by combined evidence (#8)
- Rank-based (top-N-only) TradeIntent generation (#9)
- (Unnumbered but load-bearing) a **live sample recorder** — nothing
  captures live provider readings + realized outcomes into a durable
  research dataset automatically
- Any live or paper trading track record at all — verified: `alpha_engine`
  is referenced nowhere in `app/` or `composition_root/`; it has never
  been wired into a running deployment

### 4. Infrastructure-classified remaining work
- Live sample recorder (feeds #2 and #4)
- A scheduler/orchestration loop (#2)
- A per-asset evidence-aggregation/ranking layer (#8)
- A model-combination/weighting policy (#7) — explicitly deferred in the
  code's own docstring pending real need
- A curated Alpha Library view (#5) — thin, mostly a query/documentation
  layer over data that already exists

### 5. Research-classified remaining work
- The next pre-registered campaign (Funding Rate — Campaign 01's own
  evidence-based recommendation, priority #2 in the original plan)
- OI velocity/change and longer-horizon OI hypotheses (new, distinct from
  the now-closed OI-level hypothesis)
- Stablecoin flows / on-chain / macro / cross-asset (already prioritized,
  lower in the queue)
- Fundamentally: **finding any approved alpha at all** — this is a
  research gap, not an engineering one; the Alpha Library is currently
  empty

### 6. Operational-classified remaining work
- First paper-trading deployment (currently zero track record)
- Live deployment readiness (partly outside alpha_engine — Execution
  Engine's own secrets/testnet items from the earlier production audit)
- Monitoring routing (B4 added structured logging; nothing routes it to
  a real destination yet)
- An agreed degradation-review operating cadence (a decision, not a build)

---

## Roadmap ordered by VALUE (not by implementation ease)

1. **Continue the pre-registered campaign sequence — Funding Rate next.**
   Highest value, lowest cost: the harness is built and proven; nothing
   downstream (library, ranking, combination, live trading) has anything
   to operate on until at least one model clears governance.
2. **OI velocity/change and longer-horizon OI campaigns.** Same
   reasoning — the most promising immediately-adjacent hypotheses given
   what Campaign 01 actually found.
3. **Live sample recorder.** The single most-leveraged remaining piece
   of infrastructure: it unblocks real degradation testing (#4), live-data
   validation of the rolling-window features, and eventually
   paper-trading with genuine (not backfill-proxy) samples.
4. **First paper-trading deployment**, once (if) a model is actually
   approved. Cannot be scheduled ahead of research success. This is the
   step that finally exercises #4, #10, and #12 for real rather than in
   test.
5. **Formalize the Alpha Library (#5).** Moderate value, low cost —
   mostly documentation/query convenience over data that already exists.
   Worth doing once 2–3 models are approved, not before (nothing to
   organize yet).
6. **Watchlist-driven automatic evaluation + scheduler (#2/#6 upgrade).**
   Wait until ≥2 proven candidate families justify automating a loop
   around them — automating a loop around zero-to-one models is
   premature, and matches this codebase's own consistently-applied
   "wait for a second concrete need" discipline.
7. **Model-combination/weighting policy (#7 upgrade).** Meaningless
   until ≥2 approved models can actually agree or disagree on the same
   asset. Already explicitly named as governance-owned future work in
   the code itself — do not build ahead of need.
8. **Watchlist ranking + rank-based intent generation (#8, #9).** Lowest
   value right now for the identical reason: ranking among approved
   opportunities has no content with a zero-to-one-model library. Simple
   to build later; correctly last because it has nothing to rank today.
9. **Operational hardening / live deployment work beyond paper.** Should
   trail research success, not lead it — consistent with vision item
   #13's own stated discipline of improving through research rather than
   live tuning.

This ordering deliberately does not follow implementation difficulty:
items 8–9 are conceptually simple but last (zero value today), while
items 1–2 are "run the harness already built" — cheap and highest value.

---

## Final summary

- **Overall completion toward the long-term vision: ~50–55%.** The
  platform/plumbing layer (registry, five-stage validation, evidence,
  governance, lifecycle mechanism, execution bridge, historical
  backfill pipeline) is comprehensive, tested, and now proven capable of
  carrying a real campaign start to finish. The asset-level intelligence
  layer (library, combination, ranking) and the automation layer
  (continuous research, scheduling) are the minority-built parts.

- **Biggest remaining engineering gap: the live sample recorder.** It is
  the one missing piece of infrastructure that most other unbuilt
  behaviors (#2 continuous research, #4 real degradation testing,
  live-validated rolling features) are downstream of.

- **Biggest remaining research gap: no validated alpha exists yet.**
  Campaign 01 (Open Interest level) is a clean, sound rejection. The
  Alpha Library is currently empty. Every downstream capability
  (combination, ranking, retirement-in-anger, live trading) is blocked on
  this single fact.

- **Biggest remaining operational gap: zero paper or live trading
  history.** `alpha_engine` has never been wired into `app/` or
  `composition_root/` (verified). The deployment checklist already
  written in `docs/ALPHA_ENGINE.md` is entirely unexecuted — correctly
  so, since there is nothing validated yet to deploy.

- **Where future effort will concentrate: research.** The engineering
  platform is no longer the bottleneck; it has already demonstrated it
  can take a hypothesis from pre-registration to a governance decision
  on real data without any new infrastructure. What is scarce is a
  validated signal itself, and per the vision's own item #13 discipline,
  that can only come from running more pre-registered campaigns — not
  from more platform-building. A secondary concentration of effort will
  eventually be operational (paper → live), but it cannot begin before
  research produces something worth operationalizing.
