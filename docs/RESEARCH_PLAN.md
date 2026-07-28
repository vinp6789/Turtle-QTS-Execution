# Alpha Engine — Research Execution Plan

> **STATUS UPDATE (partially superseded):** §1 (platform capabilities) and
> §2 (historical data source requirements) remain accurate reference
> material. §3 (research roadmap) and §4 (first campaign design) have been
> **executed** — see `docs/RESEARCH_LEDGER.md` (CAMP-01) and
> `docs/RESEARCH_CAMPAIGN_01_open_interest.md` for what actually happened,
> and `ROADMAP.md` for the current forward-looking priority order (which
> has evolved based on CAMP-01's results). §5/§6 (paper/live readiness
> checklists) remain current and unexecuted — see `docs/PROJECT_STATUS.md`.
> This document is retained for its original data-source analysis, not as
> the current plan.

**Original status (as written 2026-07-22):** the Alpha Engine
implementation is feature-complete for its current scope (through R8 +
audit remediation). This document marks the transition from platform
engineering to quantitative research. New infrastructure/architecture
should NOT be added from this point forward unless a genuine need is
discovered during research or live operation — and if it is, that need
must be stated explicitly (see the "New implementation identified"
callouts throughout).

---

## 1. Current platform capabilities

### What it can do today

- **Durable, replayable Experiment Registry** — append-only JSONL,
  per-append exclusive lock, per-entry checksum, torn-tail tolerance,
  full replay-from-log reconstruction. Every hypothesis's specification,
  evidence, governance decision, and lifecycle state is durable and
  auditable.
- **Two wired, orthogonal data sources**: funding rate (via the
  sanctioned `MarketDataView.get_funding_rate` seam — real Hyperliquid
  data when connected) and open interest (independent HTTP to
  Hyperliquid's public `/info` endpoint, response shape live-verified).
  Both fail-safe (never raise for a data condition; degrade to an
  `available=False` reading with a reason, now logged).
- **Two pure feature transforms** (`funding_rate_raw` v1,
  `open_interest_raw` v1) — deterministic pass-throughs of a single
  reading. `WARMUP_PERIODS = 0` for both: **no historical windowing
  exists anywhere in the platform.**
- **Two rule-based candidate families** (`funding_rate_threshold_rule`,
  `open_interest_threshold_rule`) — fixed, pre-registered threshold +
  direction-convention (contrarian/momentum) rules. No fitted,
  statistical, or ML candidate type exists.
- **Five independent validation stages**, composable over any caller-
  supplied `ValidationSample` sequence: single-pass (hit rate + mean
  directional return vs. pre-registered acceptance criteria),
  leakage/causality audit (duplicate detection, outcome-after-feature
  ordering), walk-forward (n-fold chronological split, same bar per
  fold), bootstrap resampling (metric distribution across resamples),
  regime stratification (per-label subgroup pass/fail).
- **Immutable, content-fingerprinted EvidencePackage** — one entry per
  stage, extensible without redesign, now also binding a
  `sample_set_fingerprint` and covering `known_limitations` in its
  content hash.
- **Governance** — `GovernanceDecision` requires `proposed_by !=
  reviewed_by` and an evidence-fingerprint match; the only path into
  APPROVED/REJECTED/DEFERRED.
- **Ten-state lifecycle**, structurally fenced against bypassing
  governance.
- **Degradation** — `assess_degradation()` judges a live experiment
  against its OWN pre-registered acceptance criteria (no invented drift
  thresholds); `freeze_degraded()` stops emission. With the A1 fix, a
  bridge wired with `registry=` re-checks liveness every cycle, not just
  at reload.
- **Portfolio signal selection** — conflict-refusing reduction across
  multiple approved candidates (no capital sizing — that is the frozen
  `RiskManager`'s job).
- **Execution bridge** — `ApprovedFundingAlphaStrategy`, a real
  `trading_system.strategy.Strategy`, funding-family only. Now enforces
  each spec's `cadence_seconds`, resolves evaluation via the candidate
  catalog, and optionally gates on a `Watchlist`.
- **Watchlist** — named, ordered, duplicate-free symbol set, loadable
  from JSON, now actually enforced (research-cycle and bridge
  construction) rather than merely existing.
- **Research orchestration** — `run_research_cycle()` runs one
  hypothesis through all 5 stages + evidence attachment in one call;
  `compare_experiments()` produces a deterministic, informational ranking
  (it ranks, it never decides).
- **Full determinism/replay discipline**: injectable clocks, explicit
  seeds, canonical UTC timestamp handling (`alpha_engine._time`),
  content-derived fingerprints throughout.
- 1,448 passing tests (628 Alpha-Engine-specific), zero coupling to
  frozen Execution Engine internals (test-enforced).

### What it cannot yet do

- **No historical time-series storage.** This is the single largest gap.
  Every feature computes from exactly one reading — no rolling mean, no
  percentile rank, no z-score, no lookback of any kind is possible until
  a sample store exists.
- **No live sample recorder.** `ValidationSample` sequences must be
  hand-assembled by the caller today; nothing captures live provider
  readings + realized outcomes into a durable research dataset
  automatically. Every test to date uses synthetic fixture data.
- **Only two data sources are wired.** Stablecoin flows, on-chain
  metrics, macro liquidity, and cross-asset data have zero provider,
  feature, or candidate code — nothing has been built for them.
- **No fitted/statistical/ML candidate type.** Only two hand-coded,
  fixed-threshold rules exist. This blocks: calibration (needs
  probabilistic output), attribution (needs a multi-feature candidate),
  purge/embargo (needs a fitted candidate with a training set that can
  leak).
- **No Monte Carlo / risk-of-ruin machinery** (needs portfolio
  equity-curve accounting not yet built).
- **No scheduler.** Research cycles and degradation checks are invoked,
  not self-running.
- **Open Interest cannot trade live** — the bridge purity constraint
  (`DECISIONS.md` D6) means OI candidates can be researched, validated,
  and approved, but not executed, until a context-extension or
  injected-snapshot design is consciously chosen.
- **No authenticated identity for governance** — reviewer separation is
  enforced on plain strings.
- **Nothing has actually traded** — the platform has never been run
  against a live or paper venue with an approved hypothesis; every
  milestone to date is pipeline-proof, synthetic-fixture validated.

---

## 2. Historical data requirements

These are practitioner-default starting points to calibrate against real
vendor availability, not hard requirements — treat depth/frequency as the
first hypothesis to confirm, not a fact already established.

### Funding Rate

| | |
|---|---|
| **Historical depth** | ≥2–3 years / one full market cycle (bull/bear/chop), to get regime-diverse evidence and ≥6–8 usable walk-forward folds. Hyperliquid perpetuals realistically limit this to whatever the venue has traded. |
| **Sampling frequency** | At settlement cadence (Hyperliquid: hourly) — the value doesn't change between settlements, so sub-cadence polling is wasted. |
| **Storage format** | Flat, append-only, timestamped `(symbol, rate, settlement_utc)` — CSV/JSONL is more than sufficient (~8,760 rows/year/symbol). |
| **Quality checks** | Monotonic non-decreasing timestamps per symbol; no duplicate settlements; range sanity (flag outlier magnitudes rather than accept silently); gap detection; no settlement in the future relative to capture time (mirrors `FundingRateProvider`'s own live fail-safes). |
| **Point-in-time** | Genuinely PIT-safe by nature — a settled rate at T was knowable at T and is not restated. The only risk is a data vendor that backfills/republishes; verify none does, or pin a capture-time snapshot. |

### Open Interest

| | |
|---|---|
| **Historical depth** | Same order as funding; OI is noisier, so more history helps establish a real baseline distribution for threshold calibration. |
| **Sampling frequency** | No natural settlement cadence — OI is continuously changing. A fixed interval (5–15 min) is a reasonable default; whatever is chosen now caps the finest resolution any future rolling-window feature could ever use, so decide deliberately. |
| **Storage format** | Timestamped `(symbol, open_interest, captured_at_utc)` — still flat-file scale (~35k–100k rows/year/symbol at 15 min); Parquet becomes worth it once multi-symbol sub-hourly sampling accumulates. |
| **Quality checks** | Non-negative (mirrors `OpenInterestReading`'s own domain constraint); flag implausible single-sample spikes/drops for review rather than silently including; gap detection; cross-check against a second source periodically (single-source risk today — only Hyperliquid's own endpoint is used). |
| **Point-in-time** | The most PIT-fragile of the two currently-wired sources — any historical archive must document exactly how each point was captured and confirm it was never reconstructed after the fact from another metric. |

### Stablecoin Flows

| | |
|---|---|
| **Historical depth** | ≥2 years, realistically starting when Hyperliquid itself gained material volume. |
| **Sampling frequency** | Daily is the practical starting default (most on-chain aggregators report daily); intraday exists from some vendors but adds cost not yet justified. |
| **Storage format** | Daily timestamped rows per stablecoin (optionally per chain/venue) — trivially small; CSV/JSONL. |
| **Quality checks** | Reconciliation against total supply (mint − burn + transfers internally consistent); flag known vendor issues (bridge double-counting, wrapped-token conflation); gap/duplicate detection. |
| **Point-in-time** | On-chain data is immutable and PIT-safe once confirmed, BUT third-party **derived aggregates** (e.g. "exchange netflow") can be silently revised as a provider improves its address-labeling heuristics. Pin a vendor version/snapshot date — do not re-pull "current" history and back-apply it. |

### On-chain Metrics

| | |
|---|---|
| **Historical depth** | As far back as the metric/venue supports, gated to material overlap with the instruments actually traded — don't over-invest in pre-instrument history. |
| **Sampling frequency** | Daily is the practitioner default for most aggregates (active addresses, exchange balances, realized cap); some support hourly but add limited value for a daily-or-slower strategy. |
| **Storage format** | Daily timestamped rows per metric per asset; flat files. |
| **Quality checks** | Same provider-revision risk as stablecoin flows, arguably worse (heuristic entity-clustering is more common here); check for gaps around known chain outages/upgrades. |
| **Point-in-time** | **Highest PIT risk of the six categories.** Many on-chain analytics platforms silently restate historical series as their labeling algorithms improve. Snapshot data on ingestion; never re-pull the same historical window later and assume it's unchanged. |

### Macro Liquidity

| | |
|---|---|
| **Historical depth** | Multi-year, ideally spanning multiple Fed/global-liquidity cycles — a short window risks aliasing one cycle as "the pattern." |
| **Sampling frequency** | Daily or weekly (most proxies — global M2, Fed balance sheet, reverse repo, DXY — publish no faster); do not attempt sub-daily. |
| **Storage format** | Daily/weekly rows, tiny volume, flat files. |
| **Quality checks** | Publication-lag awareness matters more than integrity checks per se — these are official, revision-tracked series. |
| **Point-in-time** | **The other high-risk category, for a different reason:** official macro series are published with a lag AND later revised (e.g. M2). Using the most-revised value as if known on the historical date is a classic look-ahead bug. Use vintage (as-originally-published) data, or shift every observation by its true publication lag — the existing causality audit's "outcome strictly later than computed_at_utc" pattern extends naturally if lag is folded into `computed_at_utc`. |

### Cross-Asset Data

| | |
|---|---|
| **Historical depth** | Set by the shorter of the two series being compared (e.g. BTC vs. an equity index — match the equity side's available window). |
| **Sampling frequency** | Daily close is the standard default for correlation/lead-lag work; only go intraday for a specific, named microstructure hypothesis. |
| **Storage format** | Daily OHLC(V)-per-asset rows; flat files. |
| **Quality checks** | Timezone/session alignment (traditional markets close weekends/holidays; crypto trades 24/7 — pick and document one convention); corporate-action adjustments if equities are involved. |
| **Point-in-time** | Relatively low risk for exchange-traded closes (not revised) — the main hazard is an accidental look-ahead from session/timezone misalignment (pairing a crypto timestamp with a "same calendar day" close that actually printed AFTER it). |

---

## 3. Research roadmap (priority order, by expected information value)

1. **Open Interest** — the frozen Research repository's own prior
   sessions already named this the highest-priority untested orthogonal
   source (`05_Research_Findings.md`). Fully wired today — provider,
   feature, candidate all exist. Zero new infrastructure. **Test first.**
2. **Funding Rate** — wired via the sanctioned `MarketDataView` seam,
   zero new infrastructure, essentially free to test in parallel with
   or immediately after (1).
3. **Combined OI + Funding** (a two-feature candidate: e.g. OI extreme
   AND funding extreme, same direction) — tests whether the two
   orthogonal-but-related derivatives signals compound. Still zero new
   *provider* infrastructure, but requires a new multi-feature candidate
   type — the natural, justified trigger for finally building the
   attribution stage (already documented as blocked on "≥2 ablatable
   features").
4. **Historical windowing on OI/funding** (rolling mean, percentile
   rank, z-score of the existing two sources vs. raw level) — zero new
   *data source*, but requires the historical sample store that
   currently does not exist anywhere. High expected value: tests whether
   "relative to own history" beats a flat threshold, a plausible richer
   hypothesis.
5. **Stablecoin Flows** — new data source, moderate build cost (one new
   provider + feature + candidate, following the exact OI/funding
   pattern already established). Plausible thesis: flows into venues
   often precede directional pressure.
6. **On-chain Metrics** — similar build cost to (5), but real PIT risk
   (provider revision, see §2) demands more careful validation. Test
   after stablecoin flows as a related but noisier family.
7. **Macro Liquidity** — slower-moving thesis, needs longer history and
   vintage-data discipline. Reasonable to research in parallel with
   the above (low data-maintenance cost) but expect a longer
   time-to-evidence.
8. **Cross-Asset** — broadest possible hypothesis space (many pairs,
   many lags). Lowest priority: without a specific, falsifiable pairing
   chosen up front, this becomes an unbounded fishing expedition.

Priorities (1)–(2) require no new code at all — go straight to
hypothesis testing. Priorities (3)–(4) each require one small, explicitly
justified addition (see §7 of `docs/ALPHA_ENGINE.md` discipline: additive,
built only once a second concrete need exists). Priorities (5)–(8) each
require a full new provider/feature/candidate triple, explicitly because
zero code exists for any of those four sources today.

---

## 4. First research campaign

Uses only what exists today — Open Interest, single source, zero new
infrastructure.

- **Hypothesis:** extreme Open Interest (crossing a pre-registered
  threshold) on the current watchlist (BTC) predicts a directional
  forward return over the acceptance criteria's holding horizon. Register
  the **contrarian** convention (OI far above its typical range signals
  over-leveraged consensus that unwinds → SHORT) as one experiment, and
  the **momentum** convention (extreme OI confirms the trend → LONG) as a
  separate, independent experiment — `direction_convention` exists
  precisely so this is an empirical question, never an assumption baked
  into one candidate.
- **Required data:** Open Interest readings for the watchlist symbol(s),
  paired with realized forward-return outcomes over the holding horizon,
  each carrying an honest `outcome_observed_at_utc` strictly later than
  `computed_at_utc` (required for the causality audit to pass rather than
  report "not verifiable").
- **Validation methodology:** the full existing 5-stage gate via
  `run_research_cycle` — single-pass (hit rate / mean directional return
  vs. pre-registered criteria), causality audit, walk-forward (N≥4
  folds), bootstrap resampling, regime stratification (at minimum
  bull/bear/chop; ideally also high/low-volatility labels).
- **Acceptance criteria** (pre-registered *before* samples are gathered):
  e.g. `min_hit_rate ≥ 0.55` (a modest edge over coin-flip, appropriate
  for a first-pass rule — not tuned to guarantee a pass) and
  `min_signaled_samples ≥ 30–50` (enough for the hit rate to mean
  something).
- **Rejection criteria:** single-pass fails its own bar; OR the causality
  audit reports any duplicate, ordering violation, or not-verifiable
  sample (auto-fail, per this platform's existing "never assume a
  criterion cleared when unverified" discipline); OR walk-forward clears
  in aggregate but fails in a majority of individual folds (a lucky-
  period artifact); OR the edge is concentrated in a single regime only
  (a materially different, riskier claim than regime-robust).
- **Expected outputs:** a sealed, fingerprinted `EvidencePackage`
  attached to the experiment record; an `IN_REVIEW` state with a
  reviewer-facing `compare_experiments()` ranking; and — pass or fail — a
  documented, falsifiable conclusion that either earns priority (2)/(3)
  work or closes this specific hypothesis (an OI threshold rule on the
  current watchlist) cleanly, without blocking the next one.

---

## 5. Paper trading readiness

- At least one experiment reaching **APPROVED** via a real governance
  decision (reviewer ≠ researcher) over **real, non-synthetic** samples —
  every test to date uses fixture data; this is the largest current gap.
- A historical sample store / live sample recorder must exist by this
  point (even a minimal one) so "real samples" means captured provider
  readings + realized outcomes, not synthetic data dressed up as real.
  *(New implementation identified — justification: nothing in the
  platform today records a live reading into a durable dataset; every
  `ValidationSample` sequence so far has been hand-assembled.)*
- `stop_fraction` (and optional `t1_fraction`/`t2_fraction`) reviewed and
  genuinely sane for the approved specification(s) — already structurally
  required by the bridge; readiness means this was a real reviewed
  decision, not a placeholder.
- Bridge wired with `registry=` (live liveness re-checking, A1) and
  `watchlist=` (C4) per `docs/ALPHA_ENGINE.md` §9.
- Confirm end-to-end that the paper-mode Execution Engine deployment
  (`composition_root.build_engine` with a paper adapter) is the one
  `AppState.create` wires the approved strategy into — verify once,
  don't assume.
- An agreed, actually-operated degradation cadence (who re-validates
  paper samples, how often) — the mechanism exists; readiness means a
  real cadence is chosen and owned.
- A planned minimum paper-trading duration covering at least one full
  walk-forward fold's worth of time before evaluating results — stopping
  too early can't distinguish "no edge" from "not enough data yet" (the
  same lesson the OHLCV research phase learned only after *exhaustive*
  testing, not a quick look).
- Confirm the platform's new `logging` output (audit finding B4) actually
  reaches somewhere a human watches during the paper window.

---

## 6. Live deployment readiness (even small capital)

Everything in §5, plus:

- A completed, observed paper-trading track record over a real time
  window that itself clears the SAME pre-registered acceptance criteria
  the offline evidence used — re-validated with `run_validation` on live
  results, not "it felt fine."
- A second, independent reviewer confirms the paper-trading evidence
  before any capital is at risk — the same reviewer-separation discipline
  already enforced for the original governance decision, applied again
  to the live-readiness decision.
- Explicit, reviewed answers to: maximum capital at risk, the kill/
  withdraw plan if live conditions diverge from paper (slippage, real
  funding payments, real liquidation risk), and who holds authority to
  freeze/retire.
- Independent confirmation that the Execution Engine's own production
  checklist (`docs/PRODUCTION_CHECKLIST.md`, unchanged by the Alpha
  Engine) is completed — the Alpha Engine strategy is only as safe as
  the frozen execution/risk stack it plugs into.
- Confirmation that the target venue's real secrets/signing-key/account
  wiring has cleared the Execution Engine's own final audit (env secrets
  rotation, testnet spot→perp transfer, live-testnet config, the
  `last_error` fix before soak) — these are Execution-Engine-side items,
  independent of the Alpha Engine, but they gate any live capital
  regardless of which strategy is trading.
- A written, dated go/no-go decision record — the existing
  `DECISIONS.md` pattern extends naturally to "why this capital amount,
  this date, this reviewer."
- Explicit, written acknowledgment that the Open-Interest-family
  candidate **cannot** be part of this deployment unless the context-
  extension/snapshot-injection design (bridge purity constraint, D6) has
  been consciously chosen and implemented first — flagged so it is never
  accidentally assumed available.

---

## New implementation identified in this plan (not built now)

Per the instruction to identify explicitly, rather than build, anything
the existing platform cannot yet do:

1. **Historical sample store / live reading recorder** — needed before
   paper trading (§5) and before any rolling-window feature (roadmap
   priority 4). Justification: no such storage exists anywhere in the
   platform today; every sample sequence has been hand-assembled.
2. **A multi-feature candidate type** — needed for roadmap priority 3
   (OI+funding combination) and the attribution validation stage.
   Justification: only two single-feature, fixed-threshold candidates
   exist; there is no shape today for a candidate that consumes more
   than one feature.
3. **New provider/feature/candidate triples for stablecoin flows,
   on-chain metrics, macro liquidity, and cross-asset data** (roadmap
   priorities 5–8). Justification: zero code exists for any of these
   four sources — this is new data ingestion, not a gap in existing code.
4. **Portfolio equity-curve accounting** — needed for Monte Carlo /
   risk-of-ruin (a §6-adjacent future need once multiple approved
   experiments are live simultaneously). Justification: today's
   portfolio layer only selects which signals survive conflict
   resolution; it has no equity-curve or capital-at-risk model.

None of the above should be built until the specific research step that
needs it is actually reached.
