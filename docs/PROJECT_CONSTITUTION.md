# Project Constitution

**This document is the project's DNA. It should rarely change, and only
with strong evidence and explicit human authorization.** Where anything
elsewhere in the repository (or in any AI session's memory) disagrees with
this document or with the repository's actual source code, the **source
code is authoritative** — this document describes what the code already
does and why, it does not prescribe unbuilt behavior.

For current state (what phase, what's built, what's next), see
[`PROJECT_DASHBOARD.md`](PROJECT_DASHBOARD.md) and
[`PROJECT_STATUS.md`](PROJECT_STATUS.md). This document is the *why*;
those are the *where-are-we-now*.

---

## 1. Vision

An automated, watchlist-driven trading platform that:

1. Researches new ideas offline, against historical data, before any
   capital is at risk.
2. Continuously expands its knowledge through evidence-based research.
3. Promotes only statistically validated alpha models into live use.
4. Retires alpha models that degrade against their own pre-registered bar.
5. Maintains an approved Alpha Library — a durable, auditable record of
   what has been tried, what works, and what has been retired.
6. Evaluates every asset in a configurable watchlist.
7. Combines multiple approved alpha models' opinions for each asset.
8. Ranks the watchlist by combined evidence.
9. Generates `TradeIntent`s only for the highest-ranked opportunities.
10. Uses the existing Execution Engine for deterministic execution.
11. Preserves replay correctness and auditability throughout.
12. Prioritizes capital preservation over returns.
13. Improves through new research rather than live parameter optimization.

This is the durable target. It is **not** a claim about what is built
today — see `docs/STRATEGIC_GAP_ANALYSIS.md` for the last full item-by-item
assessment against this list, and `PROJECT_DASHBOARD.md` for the current
snapshot.

## 2. Long-term objective

Discover whether any durable, statistically-defensible trading edge exists
across a deliberately widening set of orthogonal information sources —
and, if one does, trade it through a production-grade execution core with
capital preservation as the first-order constraint, never the last.

The project does **not** optimize for "find alpha as fast as possible." It
optimizes for **never fooling itself** into believing a false edge is
real. A rejected hypothesis, honestly reached, is success. A false
positive that reaches live capital is the one failure mode every other
design choice in this repository exists to prevent.

## 3. Success criteria

The project succeeds if, over time, it can honestly answer "yes" to:

- Has every hypothesis been pre-registered before its evidence was seen?
- Can every historical evidence package be reproduced byte-for-byte from
  its recorded inputs (fingerprint, seed, clock)?
- Has every promotion to live trading passed an independent, structurally
  enforced governance review (reviewer ≠ researcher)?
- Has every rejected hypothesis been recorded, never silently discarded or
  quietly re-tried with the bar lowered?
- Has capital preservation been visibly chosen over a larger return, every
  time the two conflicted?
- Does the system currently only trade approved models it can explain,
  from the Alpha Library, with a decision trail back to the evidence that
  justified them?

It does **not** succeed by a win-rate metric alone, a Sharpe ratio, or "the
model looked good in backtest." Those are inputs to the process above, not
the definition of success.

## 4. Architecture — the three-layer split

```
Research Repository  →  Alpha Engine  →  Execution Engine
   (offline lab)         (this repo's       (this repo's
                       alpha_engine/)      frozen core, Modules 1-10
                                           + app/ + composition_root/)
```

- **Research Repository** (`../Turtle-QTS-Research-`, a sibling repo,
  frozen): the original offline backtest/validation lab. Its OHLCV-derived
  conviction family (relative strength, trend, momentum, volume expansion,
  ATR/Donchian squeeze, OBV) was exhaustively tested and found to carry no
  statistically meaningful predictive edge — a **permanent, evidence-based
  rejection**, not abandoned or unfinished work. Its validation
  methodology (walk-forward, purge/embargo, Monte Carlo, permutation,
  attribution, calibration) and portfolio-construction patterns (position
  sizing, risk profiles, heat cap) were the reusable inheritance the Alpha
  Engine's own validation gate is built from.
- **Alpha Engine** (`alpha_engine/`, this repo, actively evolving): the
  system described in this document. Researches orthogonal information
  sources (Open Interest first, then Funding Rate, then further sources
  per `ROADMAP.md`), validates every hypothesis through a five-stage gate,
  seals immutable evidence, and promotes only what clears a structurally
  enforced governance review. It is a **consumer** of the Execution
  Engine's public seam — it does not modify it.
**Production target (source-attested, not new): decentralized perpetual
exchanges exclusively.** Primary venue: **Hyperliquid**. Future supported
venue: **Lighter** — both named explicitly in the frozen
`exchange_adapter`'s own docstring ("A concrete adapter (Hyperliquid,
Lighter, Variational, or any future exchange) implements the abstract
[contract]") as the architecture's intended concrete-adapter targets.
Centralized exchanges (e.g. Binance) are **never a production target** —
where CEX historical data is used at all, it is a research tool only, and
never a substitute for validating against the venue capital will actually
trade on (see §6 and `docs/HISTORICAL_DATA.md`).

- **Execution Engine** (`config/`, `secrets_boundary/`, `event_store/`,
  `execution_state_machine/`, `exchange_adapter/`, `order_manager/`,
  `position_manager/`, `portfolio_manager/`, `risk_manager/`,
  `hyperliquid_adapter/`, plus `app/`/`composition_root/`/
  `trading_system/`/`orchestration/`, this repo, **frozen**): the
  production-grade, capital-moving core. Deterministic, event-sourced,
  crash-safe, independently audited (`FINAL_PRODUCTION_AUDIT.md`,
  `MODULE_10_FREEZE.md`). It has no knowledge of the Alpha Engine and
  never will — it is consumed only through its public
  `trading_system.strategy.Strategy` / `TradeIntent` seam.

**The relationship is strictly one-directional.** The Alpha Engine depends
on the Execution Engine's public seam; the Execution Engine has zero
dependency on, and zero awareness of, the Alpha Engine. This is verified
by an automated test
(`tests/test_alpha_engine_scaffold.py::TestNoFrozenModuleCoupling` and its
sibling `TestNotYetWiredIntoExistingCode`), not merely asserted in
documentation.

## 5. Design principles

- **Evidence before implementation.** No feature is built to support a
  hypothesis that has not been pre-registered; no hypothesis is judged by
  evidence gathered after the fact.
- **Deterministic replay.** Every timestamped or randomized computation
  takes an injectable clock or an explicit seed. Two runs over identical
  inputs produce byte-identical outputs, always. Canonical UTC timestamp
  handling (`alpha_engine/_time.py`) and content-derived fingerprints
  (SHA-256 over canonical JSON) are applied at every layer — registry,
  evidence packages, historical datasets — so identity and ordering are
  never decided by an ambiguous raw-string comparison.
- **Additive architecture.** Frozen components are never modified except
  through an explicit, authorized critical-defect-correction process (see
  §9). New capability is a new module, package, or function — never a
  rewrite of frozen logic. This is verified, not just practiced: an
  automated test enumerates every alpha_engine file and fails if any of
  them imports a frozen, mutation-capable Execution Engine package.
- **Alpha generation is separate from execution.** The Alpha Engine
  decides *what* to trade and *why*; the Execution Engine decides *how* to
  execute it safely (sizing, risk veto, order lifecycle, crash recovery).
  Neither layer reaches into the other's responsibility.
- **Simplicity over unnecessary complexity.** No framework, abstraction,
  or generalization is built ahead of a second concrete need. (Two
  candidate families existed before a candidate catalog was built; two
  data sources existed before a shared fetch pattern was named; a Feature
  ABC remains deliberately unbuilt because two examples alone don't
  reveal what a third would actually need.) Complexity is added only when
  a specific, present requirement demands it — see `DECISIONS.md`
  (Alpha Engine) for the recurring form this restraint takes.
- **Deployment-platform independence.** The same codebase must run
  unchanged on a local laptop, Railway, Docker, a VPS, or a cloud VM. The
  deployment target may change; **business logic never changes with it.**
  Concretely: no platform-specific implementation or code path (no
  Railway-, Windows-, or Linux-specific branches); configuration only
  through the existing configuration/environment mechanisms; all state
  persisted outside process memory; every long-running component supports
  clean restart and resume; and every component exposes a **CLI entry
  point**, so any scheduler (cron, systemd, Task Scheduler, Docker,
  Kubernetes, Railway) invokes the exact same executable. This is a
  statement of an existing property, not new machinery —
  `trading_system/scheduling/cycle.py` already declares itself
  *"deployment-agnostic by construction… no opinion on whether it is
  called from a laptop's `__main__`, a cron entry, a Docker CMD, a FastAPI
  route handler, or a Telegram command handler"*, and no
  platform-specific import exists anywhere in the business-logic packages
  (verified). **Known gap (2026-07-28):** campaign `run_campaign` modules
  lack `__main__` entry points and are currently invoked programmatically;
  they are to be given CLI entry points as each next campaign harness is
  written — not retrofitted across closed campaigns.
- **Every predictive claim requires evidence.** No candidate specification
  is trusted because it "looks right"; it must clear the five-stage
  validation gate (single-pass, causality audit, walk-forward, bootstrap
  resampling, regime stratification) against pre-registered acceptance
  criteria, and the result — pass or fail — is sealed into an immutable
  evidence package before any promotion decision is even possible.

## 6. Research philosophy

- Every hypothesis is registered — data required, candidate mechanism,
  acceptance criteria, rejection criteria — **before** its evidence is
  gathered or inspected. Thresholds are never adjusted after seeing a
  result.
- Related hypotheses (e.g. "extreme signal → reversion" vs. "extreme
  signal → continuation") are always registered as **separate**
  experiments with **separate** evidence packages — never combined into
  one tunable candidate where a human could quietly pick the direction
  that happened to work.
- A rejected hypothesis is **valuable knowledge**, recorded permanently in
  `RESEARCH_LEDGER.md`, never deleted, never silently re-tried with the
  bar lowered. Research Campaign 01 (Open Interest level, four
  experiments, all rejected on merit) is the load-bearing precedent for
  this discipline — see the ledger entry.
- Priority order for new information sources is set by expected
  information value, not by implementation ease (`ROADMAP.md`).
- One information source is tested in isolation before combinations are
  attempted — a combined-source hypothesis is only meaningful once its
  individual components have their own evidence to compare against.
- **Venue-transfer discipline (DEX-first).** For any exchange-native
  metric (funding rate, open interest, order flow — not venue-agnostic
  sources like on-chain or macro data), a centralized-exchange historical
  source may be used to reach statistical power, but a positive finding
  is a research hypothesis only until it is replicated — same locked
  specification, no re-tuning — against Hyperliquid's own historical
  data, and later confirmed through Hyperliquid paper trading. A finding
  that exists only on CEX data is never promotion-eligible. See
  `docs/HISTORICAL_DATA.md` and `docs/RESEARCH_PLAYBOOK.md` §6.
- **Venue-relative thresholds (permanent methodology rule, confirmed by
  Campaign 02).** Absolute-magnitude thresholds are not considered
  transferable across exchanges. Every future exchange-native metric
  (funding rate, open interest, order flow, liquidations, or any future
  metric measured natively by an exchange) must derive its threshold
  independently for each venue, from that venue's own historical
  distribution — never one raw magnitude carried across venues. This
  was elevated from a documented risk to a binding rule after Campaign
  02's Production Venue Validation showed Hyperliquid funding runs
  ~3–8× smaller in typical magnitude than Binance's for the same
  assets/period, so a Binance-calibrated absolute threshold produced a
  near-empty signal set on Hyperliquid — an operationalization failure,
  independent of whether the underlying hypothesis has any edge. See
  `docs/RESEARCH_LEDGER.md` CAMP-02, `docs/HISTORICAL_DATA.md` §0, and
  `docs/RESEARCH_PLAYBOOK.md` §2.
- **Pre-registration feasibility review (permanent methodology rule,
  added after Campaign 02's methodology review).** Before a
  specification is locked, the expected signal count, expected
  walk-forward fold size, expected bootstrap stability, and expected
  regime coverage must be checked against the planned validation
  methodology's own requirements (e.g. `min_signaled_samples` must be
  achievable *per fold*, not only in aggregate). This is a
  research-governance check on whether the specification is testable as
  configured — it never permits adjusting a locked parameter based on
  its outcome. See `docs/RESEARCH_PLAYBOOK.md` §2 for the full checklist.

## 7. Capital preservation philosophy

Capital preservation is prioritized over returns, structurally, not just
as a stated value:

- **Conflict refusal, not majority vote.** When approved candidates
  disagree on a symbol's direction, every signal for that symbol is
  dropped (`alpha_engine/portfolio/selection.py`) — "in doubt, do
  nothing" is the system's one consistent tie-break, never a guess at
  which model to trust.
- **Freeze, never compensate.** A degraded live model is frozen (stops
  emitting new signals); existing positions exit through the Execution
  Engine's own frozen risk/exit machinery. The system never doubles down
  or attempts to "fix" a degrading position itself.
- **Stop levels are declared, never fabricated.** Every `TradeIntent`'s
  stop/T1/T2 levels come from the candidate specification's own
  pre-registered parameters; the bridge refuses to invent a default.
- **The Execution Engine's own risk layer is independent and
  non-negotiable.** `risk_manager` vetoes trades on leverage, liquidation
  buffer, funding-rate extremity, correlation, and data staleness,
  regardless of what the Alpha Engine proposes. The Alpha Engine cannot
  bypass it.
- **The research culture enforces this too.** Optimizing for a maximized
  historical win rate is explicitly rejected in favor of maximizing
  long-term risk-adjusted return — a candidate with a favorable hit rate
  but non-positive expectancy is still a rejection (see the acceptance
  criteria discipline in `RESEARCH_PLAYBOOK.md`).

## 8. Definition of "self-improving"

**The system does not self-improve by changing live parameters.** There
is, deliberately, no online learning and no live threshold tuning
anywhere in the codebase — verified structurally, not merely asserted: no
code path adjusts a `CandidateSpecification`'s parameters after
registration. The only way a threshold changes is a **new**, separately
pre-registered experiment.

Self-improvement means this loop, and only this loop:

```
New data
  ↓
New hypothesis (pre-registered, before evidence is seen)
  ↓
Research (five-stage validation gate)
  ↓
Evidence (sealed, immutable, fingerprinted)
  ↓
Governance (independent review, reviewer ≠ researcher)
  ↓
Approved Alpha Library grows (or the hypothesis is rejected and recorded)
  ↓
Watchlist evaluation improves (more/better approved models to evaluate
each asset against)
```

The full end-to-end architecture this loop feeds into, at its intended
completion:

```
Watchlist
  ↓
Evaluate every approved alpha
  ↓
Combine evidence
  ↓
Rank assets
  ↓
Portfolio construction
  ↓
TradeIntent
  ↓
Execution Engine
  ↓
Live performance
  ↓
New research
```

This distinction — research-driven improvement vs. live parameter
optimization — is fundamental and non-negotiable. A future contributor
proposing "let the system adjust its own thresholds based on live
performance" is proposing a different project, not an extension of this
one.

## 9. Frozen components

**Execution Engine (Modules 1–10 + `app`/`composition_root`/
`trading_system`/`orchestration`):** production-frozen. Modification is
permitted **only** to correct a genuine, explicitly authorized
correctness/security/capital-protection defect, following the freeze
process in `docs/DEVELOPMENT_WORKFLOW.md` — never self-initiated, never
for a stylistic or architectural preference. See
`docs/ARCHITECTURE_DECISIONS.md` for the permanent record of why each
frozen design choice was made, and `docs/CLAUDE_ONBOARDING.md` §10 for the
explicit "what must never be modified" list.

**Alpha Engine (`alpha_engine/`, `research/`):** additive-evolving, not
frozen in the same sense — new modules, features, and candidates are
added as research demands them — but never by modifying the Execution
Engine, and never by weakening a prior audit finding's fix (see
`alpha_engine/DECISIONS.md` for the Alpha Engine's own decision record,
including the post-implementation adversarial-audit remediation, D1–D9).

## 10. What must never change without strong evidence

- The one-directional Research → Alpha Engine → Execution Engine
  dependency (§4). Reversing or blurring it is an architectural
  regression, not a feature.
- The determinism guarantees (§5): injectable clocks/seeds, canonical
  timestamps, content fingerprints. Any change that makes two identical
  runs diverge is a defect, not a feature, regardless of what it enables.
- **Deployment-platform independence (§5).** The same codebase runs
  unchanged across laptop/Railway/Docker/VPS/cloud VM; no
  platform-specific code path may be introduced, and business logic never
  varies with deployment target.
- The pre-registration discipline (§6): acceptance criteria set before
  evidence is seen, never adjusted after.
- The reviewer-separation requirement in governance (proposed_by ≠
  reviewed_by), structurally enforced, not just a norm.
- The absence of live parameter optimization (§8). This is the
  single most important invariant in the entire system.
- The frozen Execution Engine's public API, on-disk formats,
  state-machine tables, and existing tests (§9, and
  `docs/CLAUDE_ONBOARDING.md` §10 in full).
- The conflict-refusal default in portfolio selection (§7) — replacing it
  with a weighting/combination policy is legitimate future work (see
  `ROADMAP.md`) but must remain "refuse if uncertain," never "guess and
  proceed," as its own fallback.

Changing any of the above requires: a written proposal, the evidence that
motivates it, explicit human authorization, and a new dated entry in the
relevant decision log (§11) — never a silent edit.

## 11. Decision logs — two, by design

There are **two** separate architectural decision logs, and this is
intentional, not an unresolved duplication:

- **`docs/ARCHITECTURE_DECISIONS.md`** — the frozen Execution Engine's
  decisions (AD-1 through AD-25 and onward). This log is closed to new
  entries except for an authorized critical-defect correction or an
  explicitly-authorized additive evolution of a frozen module (e.g. AD-19
  and AD-20/21's `wallet_key_ref` addition) — see
  `docs/DEVELOPMENT_WORKFLOW.md`.
- **`alpha_engine/DECISIONS.md`** — the Alpha Engine's decisions (D1
  onward), which evolves as research and platform work proceeds.

Keeping them separate mirrors, and reinforces, the frozen/evolving
boundary in §4 and §9: merging them into one file would blur exactly the
distinction this project depends on. Consult both when the "why" of a
design choice isn't evident from the code and its docstrings.

There is also `docs/ADR_ACCOUNTING_CRASH_WINDOWS.md`, a single detailed
ADR (AD-25's full analysis) kept as its own document because of its
length and its self-contained crash-timeline argument — referenced from,
not duplicated in, `ARCHITECTURE_DECISIONS.md`.

## 12. Review workflow (overview)

Every change follows: **Implementation → Independent Review → Security
Audit → Approval → Merge.** Full responsibilities (Claude, ChatGPT, Fable,
the repository itself, the human owner) are defined in
`docs/REVIEW_PROTOCOL.md`. The Execution-Engine-specific engineering
discipline that predates and feeds into this (additive-only, full
regression, explicit freeze approval) is `docs/DEVELOPMENT_WORKFLOW.md`
and `docs/CLAUDE_ONBOARDING.md`; `REVIEW_PROTOCOL.md` is the newer,
project-wide layer that names who does what across multiple AI tools and
the human owner, and applies to Alpha Engine research work as much as to
Execution Engine changes.

## 13. Document map

This Constitution is the top of the documentation tree. See
`docs/MASTER_INDEX.md` for the full list of documents and their
individual responsibilities, and `PROJECT_DASHBOARD.md` for the
single-page current-state summary a new reader should look at right after
this document.
