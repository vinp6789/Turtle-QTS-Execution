# Research Campaign 01 — Open Interest as a Directional Signal (BTC/ETH/SOL)

**Status:** COMPLETE. Pre-registration LOCKED (below); platform additions
built and tested; executed end-to-end on 18 months of real BTC/ETH/SOL
data. **All four pre-registered hypotheses REJECTED on merit** — Open
Interest *level* carries no reliable 24h directional edge. §9 (Readiness)
records why the one required addition was built; **§10 records the final
results, governance decisions, and the evidence-based next direction.**

---

## Pre-registration (LOCKED — approved; thresholds frozen, never changed after results)

Four separate, independently-registered experiments. **Percentile-rank is
the PRIMARY normalization** (Open Interest is heavy-tailed and regime-
dependent, so a distribution-free rank is the more defensible primary
decision criterion); **z-score is a ROBUSTNESS comparison**, not an
independent bite at significance. Crossed with the two direction
conventions the campaign's charter requires be tested separately:

| Experiment ID | Normalization | Signal (30-day trailing, PIT) | Direction | Hypothesis |
|---|---|---|---|---|
| `camp01-pctrank-contrarian` | percentile rank (PRIMARY) | rank ≥99th (upper) / ≤1st (lower) | contrarian | mean reversion |
| `camp01-pctrank-momentum`   | percentile rank (PRIMARY) | rank ≥99th / ≤1st | momentum | continuation |
| `camp01-zscore-contrarian`  | z-score (robustness) | \|z\| ≥ 2.0 | contrarian | mean reversion |
| `camp01-zscore-momentum`    | z-score (robustness) | \|z\| ≥ 2.0 | momentum | continuation |

Locked parameters (identical across all four except normalization and
direction): 30-day trailing window; 24-hour forward-return horizon;
non-overlapping daily samples; point-in-time only; universe BTC/ETH/SOL
pooled; `min_hit_rate = 0.55`; `min_signaled_samples = 100`; walk-forward
`n_folds = 5`; bootstrap `n_resamples = 1000`, `seed = 7`; regime
stratification by BTC bull/bear/chop (price-derived, independent of OI).
Implemented in `research/campaign_01_open_interest/run_campaign.py`; the
constants there are the pre-registration and MUST NOT change after
results are observed.

Direction mapping (the tested structural assumption): upper-tail OI
extreme → SHORT (contrarian) / LONG (momentum); lower-tail → the mirror.
OI magnitude does not reveal positioning side, so this mapping is what the
two direction experiments FALSIFY, not a known fact.

---

**Original readiness analysis (retained for the record):**

**Information source under test (priority #1):** Open Interest, in
isolation. Funding rate, OI+Funding, and all other sources are out of
scope for this campaign by design — they are separate campaigns, run only
after OI is evaluated.

This campaign registers **two separate, independent hypotheses** with
**separate evidence packages**. They are opposite directional claims about
the same signal and must never be combined into one experiment or one
"tunable" candidate:

- **EXP-01A** — Extreme OI → **mean reversion** (contrarian).
- **EXP-01B** — Extreme OI → **trend continuation** (momentum).

The platform's `direction_convention` parameter (`"contrarian"` vs
`"momentum"`) exists precisely so these are two pre-registered
experiments, not one experiment with a knob turned after seeing results.

---

## 0. Why this is the first campaign

Open Interest was named the highest-priority untested orthogonal source by
the frozen Research repository's own prior sessions
(`../Turtle-QTS-Research-/05_Research_Findings.md`: *"identified in prior
research sessions as the highest-priority untested orthogonal data
source"*). It is fully wired end-to-end in the Alpha Engine (provider,
feature, candidate) and the historical pipeline collects it. Testing it
first requires the least new work and answers the highest-value open
question.

---

## EXP-01A — Extreme Open Interest → Mean Reversion (contrarian)

### Hypothesis
When Open Interest for a symbol becomes **extreme relative to its own
recent history** (a large positive z-score over a trailing window), the
subsequent forward return over a fixed holding horizon is, on average,
**negative** — i.e. an OI extreme marks over-crowded positioning that
mean-reverts. Trade: OI-high → SHORT.

### Rationale
Open interest measures the total notional of open leveraged positions. A
rapid build-up to an extreme level is a classic marker of crowded,
over-leveraged consensus that is vulnerable to a liquidation cascade /
squeeze that reverses price. This is the derivatives-market analogue of
"everyone is already positioned, so who is left to buy." It is a *prior*,
not a fact — the point of the experiment is to falsify or support it.

### Required data
- **Feature input:** Open Interest, 5-minute resolution, BTC/ETH/SOL,
  Binance USDⓈ-M perpetuals (`historical.sources.binance`). Full
  available coverage: BTC from ~2020-09, ETH/SOL from ~late 2021/2022.
- **Outcome input:** forward return derived from the *same* metrics files
  via `price = sum_open_interest_value / sum_open_interest` (a clean mark
  price — OI cancels, empirically verified to match spot BTC to the
  dollar; see this campaign's evidence table). **No new data source
  required.**

### Candidate specification (pre-registered parameters)
- **Family:** OI threshold rule (`open_interest_threshold_rule`),
  **operating on a rolling-normalized extremeness feature** (see §9 — the
  one required addition; the existing raw-OI feature is empirically
  invalid for "extreme," proven below).
- `direction_convention = "contrarian"`
- `threshold = 2.0` (z-score units; |z| ≥ 2 ≈ the ~2.3% tail — "extreme")
- `universe = (BTC, ETH, SOL)`
- `cadence_seconds` = the holding horizon (below), so signals do not
  overlap.
- Normalization: **trailing 30-day z-score** of 5-minute OI, computed
  point-in-time (window at time T uses only data with observed_at_utc
  ≤ T — no look-ahead). 30 days ≈ 8,640 five-minute samples: enough to
  estimate a stable mean/σ, short enough to adapt to the secular OI
  growth the evidence table exposes.
- Holding horizon (label): **24 hours** forward return.

### Acceptance criteria (pre-registered, locked before any result is seen)
- `min_hit_rate = 0.55` — a modest, non-cherry-picked edge over the 0.50
  coin-flip null. (Set *before* seeing data; not tuned to pass.)
- `min_signaled_samples = 100` — the hit rate must rest on ≥100
  **non-overlapping** signaled samples to mean anything.
- **Plus** (inspected in the evidence package at governance review, since
  the platform gates only on the two keys above): mean directional return
  must be positive and the effect must survive walk-forward and bootstrap
  (below). A >55% hit rate with negative expectancy is a rejection, not a
  pass.

### Rejection criteria (any one of these rejects the hypothesis)
- Single-pass hit rate < 0.55, or fewer than 100 signaled samples.
- The causality audit reports **any** duplicate, ordering violation, or
  not-verifiable sample (auto-fail — never assume an unverified sample is
  clean).
- Walk-forward: the rule clears its bar in aggregate but **fails in the
  majority of individual folds** (a lucky-period artifact, not a durable
  edge).
- Bootstrap: the resampled hit-rate distribution's confidence interval
  **includes 0.50** (the observed edge is within sampling noise).
- Regime stratification: the edge exists in **only one** BTC regime
  (bull/bear/chop) — a materially different, riskier, and far less
  credible claim than a regime-robust one.
- Mean directional return ≤ 0 despite hit rate > 0.55 (payoff-asymmetry
  trap).

### Validation methodology
All five existing stages, via `run_research_cycle(...)`, deterministic
(fixed `seed`, injected fixed `clock`):
1. **single_pass** — hit rate + mean directional return vs. the
   pre-registered criteria.
2. **leakage_causality_audit** — duplicate detection + outcome-strictly-
   after-feature ordering.
3. **walk_forward** — `n_folds = 5` chronological folds; must clear its
   bar in every fold, not just in aggregate.
4. **bootstrap_resampling** — `n_resamples = 1000`, `seed` fixed; hit-rate
   sampling distribution.
5. **regime_stratification** — labelled by BTC trend regime
   (bull/bear/chop) derived independently of OI.

Sample construction discipline (in campaign prep code, point-in-time):
- **Non-overlapping samples.** With a 24h holding horizon, sample no more
  than once per 24h per symbol (sparse sampling). Sampling every 5 minutes
  with a 24h horizon would make consecutive outcome windows ~99.6%
  overlapping → severe autocorrelation that fakes statistical
  significance. This is the single most important discipline in the whole
  campaign.
- **Trailing-only normalization.** The z-score at T uses only OI ≤ T.
- **Honest outcome timestamps.** `outcome_observed_at_utc = T + 24h`,
  strictly after `computed_at_utc = T`, so the causality audit can
  actually verify no look-ahead.

### Expected failure modes (what would make this experiment *wrong*, or its
result untrustworthy)
- **Most likely outcome: no edge.** OI extremes may carry no directional
  information at 24h. That is a successful experiment.
- **Overlapping-sample artifact** — mitigated by sparse sampling above; if
  someone re-runs with dense sampling, apparent significance is fake.
- **Regime confounding** — an apparent edge that is really just "2022 was
  a bear market and shorting worked," not an OI effect. Caught by regime
  stratification.
- **Price-proxy noise** — the val/OI mark has small rounding noise vs a
  true close; immaterial at a 24h horizon but noted.
- **Venue mismatch** — this is *Binance* OI, not Hyperliquid OI. A result
  here is a hypothesis about derivatives markets generally, not a proven
  fact about the live venue. Must be recorded in `known_limitations`.
- **Multiple testing** — testing contrarian AND momentum AND 3 symbols is
  effectively 6 tests; a single "significant" result at p≈0.05 is expected
  by chance. Interpreted with that in mind at governance review.

---

## EXP-01B — Extreme Open Interest → Trend Continuation (momentum)

Identical in every structural respect to EXP-01A, with **one** difference,
which is the entire point of registering it separately:

### Hypothesis
When OI becomes extreme relative to its recent history, the subsequent 24h
forward return **continues** in the direction of the move — an OI extreme
marks conviction/participation that *confirms* the trend rather than
exhausting it. Trade: OI-high → LONG.

### Rationale
The opposite prior: rising OI into an extreme means real capital is
committing to the move (new money, not just churn), and flows persist.
Rising OI + rising price is a textbook "healthy trend" reading; this tests
whether that folk wisdom is real.

### Candidate specification
Identical to EXP-01A **except** `direction_convention = "momentum"`.
Everything else — threshold 2.0, 30-day z-score, 24h horizon, universe,
acceptance/rejection criteria, validation methodology — is byte-identical,
so the *only* thing that differs between the two evidence packages is the
directional claim. Same data, same bar, opposite bet.

### Acceptance / rejection criteria / validation / failure modes
Identical to EXP-01A (see above), applied to the momentum direction.

### Note on mutual exclusivity
EXP-01A and EXP-01B are near-mutually-exclusive: they cannot both be
strongly true at 24h on the same samples. It is entirely possible (and the
most honest prior) that **both are rejected** — OI extremes carrying no
reliable 24h directional edge in *either* direction. That is a clean,
valuable result: it closes the "raw OI level as a 24h timing signal"
question and directs effort to OI *changes*, longer horizons, or other
sources — without any temptation to "improve" a failed rule.

---

## 4. Required historical dataset (both experiments share it)

| Field | Value |
|---|---|
| Metric | Open Interest (+ its val/OI-derived mark price for outcomes) |
| Symbols | BTC, ETH, SOL |
| Source | Binance USDⓈ-M bulk archive (`historical.sources.binance`), PRIMARY |
| Resolution | 5-minute (native) |
| Depth | Full available: BTC ~2020-09→present; ETH/SOL ~late-2021/2022→present |
| Format | CSV per (metric, symbol, source), already implemented |
| Storage | `data/alpha_engine_historical/` (git-ignored) |
| Approx size | ~105k rows/symbol/year × ~3–4 yrs × 3 symbols ≈ 1M rows total (tens of MB CSV) |
| Quality gate | `assess_quality(...)` clean report (no duplicates, monotonic, no gaps beyond tolerance) before any sample is built |
| New data sources required | **None** — outcomes derive from the same OI files |

---

## 5. Expected outputs
- Two sealed, content-fingerprinted `EvidencePackage`s (one per
  experiment), each with all five stage results, each bound to its exact
  `sample_set_fingerprint`.
- Two experiment records in the registry, each carrying
  `known_limitations` = (Binance-not-Hyperliquid venue caveat; synthetic-
  free but proxy-price caveat; 24h-horizon scoping).
- A `compare_experiments(...)` ranking of the two.
- A written, dated conclusion per hypothesis: **supported → advance to
  governance review**, or **rejected → record and stop** (no "improving"
  a rejected rule, per campaign discipline).

## 6. Estimated runtime
- **Data collection (one-time):** BTC ~1,700 daily files + ETH/SOL shorter
  windows, one HTTP request per file, checksum-verified ≈ **30–60 min**
  wall (network-bound; fully incremental thereafter — reruns fetch only
  new days).
- **Sample construction + 5-stage validation ×2 experiments:** seconds to
  a few minutes (sparse, non-overlapping samples → only a few hundred to
  ~1–2k samples per symbol; the compute is trivial).
- **Total first run:** ~1 hour, dominated by the one-time download.

## 7. Risks
- **Non-stationarity (proven).** Raw OI swings 3.4× over the sample for
  reasons unrelated to the signal — hence the mandatory rolling
  normalization (see evidence table and §9).
- **Overlapping-window autocorrelation** — the biggest silent trap;
  mitigated only by the sparse-sampling discipline. If violated, every
  significance number is inflated and untrustworthy.
- **Hit-rate-only gating** — the platform gates on hit rate and sample
  count, not expectancy; a favourable hit rate with poor payoff must be
  caught by inspecting mean directional return in the evidence, not
  assumed away.
- **Venue mismatch** (Binance vs live Hyperliquid) — a transferability
  risk, recorded, not silently ignored.
- **Multiple testing** across 2 directions × 3 symbols — a lone
  "significant" cell is expected by chance; judged accordingly.
- **Regime concentration** — an edge that only exists in one market regime
  is a weak, non-durable claim; explicitly tested for.
- **Purge/embargo absent** — the platform's walk-forward does not purge
  label-overlapping samples (it has no fitted model, so there is nothing
  to leak *into*), which is fine *only because* samples are non-
  overlapping by construction; if that discipline lapses, this becomes a
  real leakage vector.

---

## 8. Empirical evidence motivating the design (not assumed — measured)

Live-pulled BTC OI metrics, first row of Jan 15 each year:

| Year | Raw OI (BTC) | price = val/OI | Actual BTC | Intraday OI range |
|---|---|---|---|---|
| 2021 | 27,255 | $39,173 | ~$39k | 26,985–33,165 |
| 2022 | 74,484 | $43,048 | ~$43k | 74,273–76,935 |
| 2023 | 93,687 | $20,962 | ~$21k | 92,039–96,867 |
| 2024 | 77,082 | $41,740 | ~$42k | 73,448–77,292 |
| 2025 | 84,478 | $96,482 | ~$96k | 84,478–87,480 |

- **Cross-year OI range (27k→94k) dwarfs the intraday range (~few %).** A
  fixed absolute OI threshold is meaningless: it encodes *what year it is*,
  not *whether OI is extreme*. → relative (z-score/percentile)
  normalization is mandatory.
- **val/OI recovers the true mark price exactly** (matches spot to the
  dollar) → forward-return outcomes are available with zero new data and
  zero feature-outcome contamination (OI cancels out of the price).

---

## 9. Readiness recommendation (deliverable #8)

**Not ready to execute *soundly* this instant. One small, explicitly
justified addition is required first. Returns need no new data.**

Two gaps were assessed against real data:

1. **Forward-return outcomes — NO gap.** The `sum_open_interest_value /
   sum_open_interest` ratio is a clean mark price (proven above). Outcomes
   are derivable from the OI files already collected, with no
   feature-outcome contamination. ✅

2. **"Extreme" operationalization — a real gap.** The existing OI
   candidate thresholds a **fixed absolute** OI level. The evidence table
   proves that is invalid over a multi-year sample (a fixed threshold
   encodes the calendar, not extremeness). "Extreme relative to recent
   history" requires a **rolling-normalized (z-score) OI feature**, which
   the platform does not have (features are `WARMUP_PERIODS = 0`, no
   historical windowing — a limitation already flagged in
   `docs/RESEARCH_PLAN.md`). ❌

**The required addition** is minimal and follows the existing pattern
exactly — a rolling-normalized OI "extremeness" feature plus a candidate
that thresholds the z-score (mirroring `open_interest_feature.py` /
`open_interest_candidate.py`). It is **new data-prep/feature code, not new
architecture**: no change to the registry, validation stages, evidence,
governance, or execution layers. It is strictly required because *without
it, the only executable OI experiment is one the evidence has already
proven unsound* — and running a known-unsound experiment to manufacture a
result is exactly what the "optimize for truthful conclusions" mandate
forbids.

**Two decisions need your sign-off before I build it and execute** (they
are genuine research-design choices that determine the pre-registered
spec, and pre-registration integrity means they must be locked *before* I
see any result):

- **Normalization:** rolling **z-score** over a **30-day** trailing window
  (my recommendation), vs. percentile rank, vs. a different window.
- **Holding horizon + threshold:** **24h** forward return, **|z| ≥ 2.0**
  (my recommendation), vs. alternatives.

On approval, the sequence is turnkey and fully deterministic: build the
z-score feature + candidate (small) → collect the OI backfill (~30–60 min,
one-time) → construct non-overlapping PIT samples → `run_research_cycle`
×2 → two sealed evidence packages → report supported/rejected per
hypothesis.

**Alternative if you want an execution with zero new code sooner:** the
**funding-rate** source (campaign priority #2) is *naturally stationary*
(it oscillates around zero and does not grow secularly), so a fixed
threshold *is* a valid operationalization of "extreme funding" — the
existing funding candidate could test "extreme funding → reversion/
continuation" today with no new feature. That would mean running priority
#2 before #1. I do **not** recommend reordering unilaterally, but flag it
so the choice is yours: build the one small OI-normalization feature to do
OI first (as prioritized), or execute a funding campaign immediately with
what exists. Either way, the price-return proxy above unblocks outcomes
for both.

---

## 10. Results (FINAL)

**Dataset:** BTC/ETH/SOL Binance USDⓈ-M perpetual Open Interest + derived
mark price, 5-minute resolution, **2023-07-01 → 2024-12-31 (18 months)**,
~158k rows/series, integrity-verified (zero duplicates, monotonic, no
gap > 1 day; one venue-wide 10.5h outage + scattered single-bar misses,
handled by skipping the affected samples). Pooled non-overlapping daily
samples: **1,557** (zero skips at the sample-construction stage). Fully
deterministic (fixed seed 7, fixed clock). Data collected via the
resumable chunked backfill after a transient-network-error recovery; no
threshold, criterion, or validation setting was changed at any point.

### 10.1 Combined universe (the pre-registered, statistically-powered analysis)

All four cleared the `min_signalled_samples ≥ 100` floor, so these are
**per-merit verdicts**, not data-shortfall artifacts.

| Experiment | Signalled | Hit rate | Bootstrap hit-rate range (1000×) | % resamples ≥ 0.55 | single-pass | causality | walk-fwd | regime | Verdict | Governance |
|---|---|---|---|---|---|---|---|---|---|---|
| pctrank / contrarian (PRIMARY) | 126 | **0.508** | 0.356 – 0.632 | 16.5% | FAIL | PASS | FAIL | FAIL | **REJECTED** | **REJECTED** |
| pctrank / momentum (PRIMARY)   | 126 | **0.492** | 0.368 – 0.644 | 9.0%  | FAIL | PASS | FAIL | FAIL | **REJECTED** | **REJECTED** |
| zscore / contrarian (robustness) | 167 | **0.497** | 0.372 – 0.663 | 8.5%  | FAIL | PASS | FAIL | FAIL | **REJECTED** | **REJECTED** |
| zscore / momentum (robustness)   | 167 | **0.503** | 0.337 – 0.628 | 10.8% | FAIL | PASS | FAIL | FAIL | **REJECTED** | **REJECTED** |

Hit rates sit at **0.49–0.51 — indistinguishable from a coin flip.** The
pre-registered 0.55 bar is cleared in only **8.5–16.5%** of bootstrap
resamples, and every bootstrap range straddles 0.5. The causality audit
**passes** for all four (no leakage; every outcome strictly post-dates its
feature). Governance recorded a real **REJECT** decision for each
(reviewer ≠ researcher, evidence-fingerprint verified) — the experiments
now sit durably in lifecycle state REJECTED.

Sealed evidence-package fingerprints (SHA-256, combined):
`pctrank/contrarian 33569639aa91185f…` · `pctrank/momentum 1b3d713954af4feb…`
· `zscore/contrarian 9489c0e973da9ae2…` · `zscore/momentum fca4ffff3521967b…`

### 10.2 Per-symbol results (supplementary — UNDERPOWERED at this depth)

Every per-symbol slice has **fewer than 100 signalled samples**
(pre-registered floor), so each is REJECTED on `min_signalled_samples`
and carries no per-merit weight. Reported for completeness and to
demonstrate *why* the pooled analysis is the honest one:

| Symbol | Experiment | Signalled | Hit rate | % resamples ≥ 0.55 |
|---|---|---|---|---|
| BTC | pctrank/contrarian | 35 | 0.629 | 81% |
| BTC | pctrank/momentum | 35 | 0.371 | 2% |
| BTC | zscore/contrarian | 48 | 0.563 | 58% |
| BTC | zscore/momentum | 48 | 0.438 | 6% |
| ETH | pctrank/contrarian | 50 | 0.500 | 24% |
| ETH | pctrank/momentum | 50 | 0.500 | 26% |
| ETH | zscore/contrarian | 73 | 0.534 | 42% |
| ETH | zscore/momentum | 73 | 0.466 | 8% |
| SOL | pctrank/contrarian | 41 | 0.415 | 5% |
| SOL | pctrank/momentum | 41 | 0.585 | 70% |
| SOL | zscore/contrarian | 46 | 0.370 | 1% |
| SOL | zscore/momentum | 46 | 0.630 | 86% |

**Why these are noise, not signal:** the direction that "looks good"
is **inconsistent across symbols** — BTC favours *contrarian*, SOL
favours *momentum*, ETH is ~0.50 both ways. A real edge would point the
same way across symbols; this points different ways, the signature of
sampling noise on small n. (Within any symbol, contrarian and momentum
hit rates are mechanical mirror images summing to ~1.0, so one always
looks good — that is not evidence.)

### 10.3 Final verdict

**All four pre-registered hypotheses are REJECTED on merit.** Open
Interest *level* extremes — whether normalised by 30-day percentile rank
(primary) or z-score (robustness), in either the mean-reversion or the
continuation direction — carry **no reliable 24-hour directional edge**
on BTC/ETH/SOL over the 18-month sample. This is a clean, sound null
result: the causality audit passed (so it is not a leakage artifact), the
sample floor was cleared (so it is not a data-shortfall artifact), and the
robustness normalisation agrees with the primary.

Per campaign discipline, these hypotheses will **not** be "improved" or
re-tuned. The question "does raw OI level time 24h direction" is closed.

### 10.4 Recommended next research direction (evidence-based)

1. **OI *velocity/change*, not level.** The build-up/unwind *dynamics* of
   OI (Δ open interest, rate-of-change) are a distinct, orthogonal
   hypothesis this campaign did not test — a rapidly *rising* OI may
   inform even though the *level* does not. This is a new pre-registered
   campaign, not a tuning of the rejected one.
2. **Longer horizons.** 24h may be too short for positioning dynamics to
   resolve; a 3–7 day horizon is a distinct hypothesis worth its own
   pre-registration.
3. **Proceed to priority #2 — Funding Rate.** Funding is naturally
   stationary (a fixed threshold *is* a valid "extreme"), directly
   reflects positioning cost, and is the live venue's own tradeable
   series. Given OI *level* is now cleanly closed, a Funding-Rate campaign
   is the highest-value next step and needs no new normalization
   infrastructure.

The platform itself is validated end-to-end by this campaign: real data
in, deterministic PIT samples, five validation stages, sealed immutable
evidence, and recorded governance decisions — all produced without a
single post-hoc threshold change.

## What this campaign deliberately does NOT do
- It does not combine OI with funding or any other source (separate,
  later campaigns).
- It does not "tune" a rejected hypothesis — rejection is recorded and we
  move on.
- It does not build new architecture — at most one small feature+candidate
  pair, only after sign-off, only because the evidence proves the existing
  fixed-threshold rule cannot honestly express "extreme."
