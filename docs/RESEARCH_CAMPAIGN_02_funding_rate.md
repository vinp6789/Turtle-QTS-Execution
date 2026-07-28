# Research Campaign 02 — Funding Rate as a Directional Signal (BTC/ETH/SOL)

**Status: COMPLETE.** Both experiments (contrarian, momentum) REJECTED on
the Binance screen (§6); Production Venue Validation performed on
Hyperliquid (§7) — inconclusive on the hypothesis itself, but decisive on
a distinct, important finding: a raw-magnitude threshold does not
transfer across venues with structurally different funding scales (§9).
Zero approved alphas added. See `docs/RESEARCH_LEDGER.md` CAMP-02 for the
condensed permanent record. Follows Campaign 01 (Open Interest level,
permanently CLOSED/REJECTED, `docs/RESEARCH_LEDGER.md` CAMP-01) — **not
modified, not revisited.**

Funding Rate is a genuinely different hypothesis family from Campaign 01:
Open Interest measures raw positioning *quantity*; Funding Rate measures
the *priced cost* of holding that positioning. It uses an existing,
separately-built candidate mechanism (`funding_rate_threshold_rule`,
M3.2) that has never before been run end-to-end on real data with real
evidence and governance — only Open Interest has (Campaign 01).

**DEX-first requirement in force** (`PROJECT_CONSTITUTION.md` §6,
`docs/HISTORICAL_DATA.md` §0): Binance data screens this hypothesis for
statistical power only. **No promotion decision may be made on Binance
evidence alone.** A dedicated Production Venue Validation phase (§7 below)
replicates the locked specification on Hyperliquid's own funding history
before any governance APPROVE is possible.

---

## 0. Existing infrastructure reused (verified before writing any new code)

- **Candidate**: `alpha_engine.candidates.funding_rate_threshold_rule`
  (M3.2) — unchanged.
- **Feature**: `alpha_engine.features.FundingRateFeature` — unchanged.
- **Catalog entry**: `CANDIDATE_CATALOG["funding_rate_threshold_rule"]` —
  unchanged.
- **Historical collection**: `alpha_engine.historical.collect_funding_rate`
  (both `binance` and `hyperliquid` sources) — unchanged.
- **Mark-price outcomes**: the BTC/ETH/SOL mark-price series already
  collected for Campaign 01 (2023-07-01 → 2025-01-01) — reused verbatim,
  zero new price collection.
- **Validation/evidence/governance**: `run_research_cycle`, the five
  validation stages, `EvidencePackage`, `record_governance_decision` — all
  unchanged, all already proven end-to-end by Campaign 01.

## Genuinely new (small, campaign-specific, not platform infrastructure)

- `research/campaign_02_funding_rate/collect_backfill.py` — a per-month
  chunked, resumable, retry-with-backoff driver, mirroring Campaign 01's
  own driver pattern (`collect_funding_rate` writes only once at the end
  of its range, so long-running interrupted calls persist nothing without
  this wrapper — the identical lesson Campaign 01 learned).
- `research/campaign_02_funding_rate/explore_distribution.py` — outcome-
  blind descriptive statistics on the raw funding series (§1), used only
  to ground the threshold value below.
- `research/campaign_02_funding_rate/build_samples.py` — a lighter
  adaptation of Campaign 01's point-in-time scaffolding: **no rolling
  normalization step** (funding needs none — the candidate consumes the
  raw rate directly, per its own M3.2 design rationale), just point-in-time
  sampling + forward return.
- **No new alpha_engine/ platform code.**

---

## 1. Exploratory distribution study (outcome-blind — no price/return data used)

Computed from the full Binance historical funding series (2023-07-01 →
2024-12-31, 1,650 settlements/symbol, integrity-verified: zero
duplicates, monotonic, zero gaps > 1 interval) via
`explore_distribution.py`:

| Symbol | min | max | median | p01 | p99 | positive freq | negative freq | mean run-length (settlements) | same-sign persistence |
|---|---|---|---|---|---|---|---|---|---|
| BTC | -0.000112 | 0.000881 | 0.000100 | -0.0000679 | 0.000567 | 90.1% | 9.9% | 9.54 | 89.6% |
| ETH | -0.000175 | 0.001017 | 0.000100 | -0.0000464 | 0.000578 | 94.1% | 5.9% | 14.35 | 93.1% |
| SOL | -0.000602 | 0.001193 | 0.000100 | -0.000228 | 0.000727 | 83.4% | 16.6% | 7.14 | 86.1% |

**Pooled |funding rate| percentiles** (BTC+ETH+SOL, n=4,950):
p50=0.000100, p75=0.000100, **p90=0.00023655**, p95=0.000361,
p99=0.000641.

### Findings that directly shape pre-registration (not incidental)

- **Funding is heavily positive-skewed** over this window (83–94%
  positive across symbols) — 2023–2024 was a persistently bullish
  period. A *symmetric* threshold (the only mechanism the existing
  candidate supports — `value > threshold` OR `value < -threshold`) will
  therefore produce a **structurally asymmetric split of upper- vs.
  lower-tail signals per symbol**. Concretely: BTC's historical minimum
  (-0.000112) and ETH's (-0.000175) are both smaller in magnitude than
  the threshold locked below (0.00023655) — **BTC and ETH are expected to
  fire few-to-zero lower-tail (extreme-negative) signals**; SOL's larger
  historical excursions (min -0.000602) mean it will contribute most of
  what lower-tail signal exists. **This is declared here, before any
  outcome is examined, as an honest, expected property of the design —
  not a flaw discovered after the fact.** Per-symbol tail composition is
  reported diagnostically (§6); it is not an acceptance/rejection
  criterion.
- **Funding is highly persistent** — mean run-length of 7–14 consecutive
  same-sign settlements (≈2.4–4.8 days at 8-hourly cadence), same-sign
  persistence ratio 86–93%. Consecutive daily-sampled *feature*
  observations are therefore materially autocorrelated (funding "regimes"
  last several days), even though sampled *outcome* windows remain
  strictly non-overlapping (§3). This means the pooled `signaled_samples`
  count should be read as counting *regime-days*, not fully independent
  draws — a real interpretive caveat, stated here rather than discovered
  after seeing results, and not a reason to add new de-correlation
  machinery (block bootstrap, etc.) that isn't required for a first-pass
  screen (avoid unnecessary complexity, per this campaign's own charter).

---

## 2. Pre-registration (LOCKED)

Two separate, independently-registered experiments — never combined into
one tunable candidate:

| Experiment ID | Direction | Hypothesis |
|---|---|---|
| `camp02-combined-contrarian` | contrarian | Extreme funding (crowded positioning cost) → reversal |
| `camp02-combined-momentum` | momentum | Extreme funding → continuation (crowding confirms the trend) |

**Locked parameters (identical across both except direction):**

| Parameter | Value | Justification |
|---|---|---|
| Candidate family | `funding_rate_threshold_rule` (existing, unchanged) | Reuse; M3.2's own fixed-threshold design is appropriate here (funding is stationary — no rolling window needed, unlike OI) |
| Threshold | **0.00023655** (string-encoded Decimal) | Pooled 90th percentile of \|funding rate\| across BTC/ETH/SOL's full historical distribution (§1) — outcome-blind, data-grounded, not an arbitrary guess |
| Threshold methodology | Percentile of absolute value, pooled across the watchlist | Funding's sign-skew (§1) makes a single-sign-tail percentile indefensible as a symmetric cutoff; pooling magnitude across symbols and both signs is the funding-appropriate analog of Campaign 01's data-grounded (not guessed) threshold discipline |
| Universe | BTC, ETH, SOL | Same watchlist as Campaign 01 — direct cross-campaign comparability |
| Holding horizon | 24 hours | Same as Campaign 01 — changing horizon and information-source simultaneously would confound any cross-campaign comparison |
| Sample spacing | 24 hours, non-overlapping | Same non-overlapping-outcome discipline as Campaign 01 |
| Cadence | 86,400 seconds | Matches horizon |
| `min_hit_rate` | 0.55 | Same bar as Campaign 01 — a consistent standard across campaigns, not loosened or tightened per-campaign |
| `min_signaled_samples` | 100 | Same floor as Campaign 01 |
| Walk-forward | `n_folds=5` | Same as Campaign 01 |
| Bootstrap | `n_resamples=1000`, `seed=7` | Same as Campaign 01 |
| Regime stratification | BTC bull/bear/chop, price-derived | Same labeler, reused unchanged |

**Rejection criteria** (any one rejects): single-pass hit rate < 0.55 or
signaled samples < 100; the causality audit reports any duplicate,
ordering violation, or not-verifiable sample; walk-forward clears in
aggregate but fails in the majority of individual folds; the bootstrap
hit-rate distribution straddles 0.50 in a way inconsistent with the
pre-registered bar; the edge is concentrated in a single regime only;
mean directional return ≤ 0 despite a hit rate nominally above 0.55.

**None of the above may be adjusted after any result is observed —
including the Production Venue Validation phase (§7): if Hyperliquid
contradicts a Binance-screened finding, the specification is not
retuned to fit Hyperliquid; the finding is recorded as
venue-non-transferable and treated accordingly (§7, §8).**

## 3. Expected failure modes (stated in advance)

- **Most likely outcome: no edge**, consistent with Campaign 01's
  precedent for OI. A rejection here is a successful, informative
  experiment.
- **Sign-asymmetric tail composition** (§1) — expected and declared, not
  a discovered flaw.
- **Regime persistence / pseudo-replication** (§1) — a real interpretive
  caveat on sample independence, not a design defect.
- **Venue-transfer risk**: any positive Binance finding may not replicate
  on Hyperliquid (different funding formula, cadence — 8-hourly
  historically on Binance vs. 1-hourly on Hyperliquid — different trader
  population). This is exactly what §7 exists to test, not an
  afterthought.
- **Multiple testing**: two directions × pooled/per-symbol reporting is
  the same structural caveat already named in Campaign 01.

---

## 4. Machinery validation (2-month in-memory slice, 2023-07..2023-09)

Verified end-to-end before any full-depth run: PIT correctness (unit
tests, `tests/test_research_campaign_02_build_samples.py`, 9/9 passing —
no look-ahead, non-overlapping outcomes enforced, feature identity
matches the live `FundingRateFeature`, deterministic), sample
construction (162 samples from 180 grid-points, 18 correctly skipped for
missing funding at the window edge), single-pass + causality-audit
execution, evidence sealing, and a real governance decision recorded
(REJECTED — signaled=1, correctly insufficient at 2 months, same pattern
Campaign 01 showed at its own 2-month check). Machinery confirmed sound;
proceeded to full 18-month execution with zero changes to the locked
specification.

## 5. Dataset (full execution)

BTC/ETH/SOL, Binance funding rate (2023-07-01 → 2024-12-31, 1,650
settlements/symbol, integrity-verified: zero duplicates, monotonic, zero
gaps) + the existing Campaign-01 mark-price series (same window) for
outcomes. Pooled non-overlapping daily samples: **1,458** (189 skipped at
each symbol's series start, before any funding history exists to look
back on — correct, not fabricated).

## 6. Results — Binance screen (statistical power; NOT promotion-eligible per §0)

### 6.1 Combined universe (pre-registered, powered analysis)

| Experiment | Signalled | Hit rate | Bootstrap range | % resamples ≥0.55 | single-pass | causality | walk-fwd | regime | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| contrarian | 141 | 0.440 | 0.287–0.587 | 0.6% | FAIL | PASS | FAIL | FAIL | **REJECTED** |
| momentum | 141 | **0.560** | 0.413–0.713 | 58.4% | **PASS** | PASS | FAIL | FAIL | **REJECTED** |

**Momentum cleared single-pass** (hit rate 0.560 ≥ 0.55 bar, 141 signalled
≥ 100 floor) — genuinely different from Campaign 01, where *every*
experiment failed single-pass. It was still correctly rejected overall:

- **Walk-forward**: no individual fold clears its own bar. Folds have
  ~28 signalled samples on average (141/5) — **structurally below the
  100-per-fold floor regardless of the true edge**, since
  `min_signaled_samples=100` is applied identically per fold, not scaled
  to fold size. This is a genuine methodological observation (noted in
  §9 Lessons Learned), not a Campaign 01 revision.
- **Regime stratification** (the more informative check here): of 141
  signalled samples, **132 (93.6%) occur in the `bull` regime alone**
  (hit rate 0.568 there — passes on its own), with only 3 in `bear`
  (100% hit rate, but far too few to mean anything) and 6 in `chop`
  (16.7% hit rate, poor). The "combined" result is almost entirely a
  restatement of the bull-regime result — not evidence of a
  regime-robust edge. This is coherent with §1's funding-skew finding:
  momentum-qualifying extreme funding predominantly occurs when funding
  is very positive, which predominantly occurred during this window's
  bull conditions.

### 6.2 Per-symbol (supplementary — largely underpowered, diagnostic only)

| Symbol | Experiment | Signalled | Hit rate | % resamples ≥0.55 |
|---|---|---|---|---|
| BTC | contrarian | 35 | 0.314 | 0.3% |
| BTC | momentum | 35 | **0.686** | **96.9%** |
| ETH | contrarian | 44 | 0.523 | 37.6% |
| ETH | momentum | 44 | 0.477 | 16.5% |
| SOL | contrarian | 62 | 0.452 | 6.8% |
| SOL | momentum | 62 | 0.548 | 48.8% |

BTC's individual momentum result (0.686, 96.9% of bootstrap resamples
clear the bar) is the strongest single-symbol result across both
campaigns to date — but at 35 signalled samples it is well below the
pre-registered floor and **not a basis for any conclusion on its own**
(§9 discusses this as a Campaign 03 candidate). ETH is close to a coin
flip both ways; SOL is mixed. The combined result is not a simple average
of these three — it is dominated by whichever symbol contributes the
most bull-regime signals.

### 6.3 Verdict (Binance screen)

**Both experiments REJECTED.** Contrarian shows no edge in either
direction. Momentum shows a real, single-pass-clearing signal that
evaporates under walk-forward and regime scrutiny — concentrated almost
entirely in one market regime, not a durable, regime-robust edge. Per
`docs/RESEARCH_PLAYBOOK.md` §6's venue-replication gate, **neither result
is promotion-eligible even before considering Hyperliquid** — a Binance
screen that fails to clear all locked criteria cannot be rescued by a
favorable Hyperliquid replication (that would be venue-shopping for a
pass, exactly what the gate exists to prevent). Production Venue
Validation (§7) is nonetheless performed on both, diagnostically, per the
explicit requirement to record this outcome and to inform Campaign 03.

Sealed evidence-package fingerprints (combined, Binance):
contrarian `02d0e0db30439934…` · momentum `1fd5d92a2fb9da51…`
(`data/alpha_engine_research/campaign_02_binance_combined.jsonl`;
governance: both REJECTED, reviewer ≠ researcher, evidence-fingerprint
verified).

## 7. Production Venue Validation (Hyperliquid — zero retuning)

**Dataset:** BTC/ETH/SOL, Hyperliquid `fundingHistory`, 2023-07-01 →
2024-12-31 (the venue's real native coverage for the entire campaign
window), 13,197 hourly settlements/symbol, integrity-verified (zero
duplicates, monotonic, 3 tiny 2-hour single-settlement gaps/symbol —
benign). Same mark-price outcomes reused. **Identical locked
specification** — threshold 0.00023655, 24h horizon, same acceptance
criteria — applied with **zero changes**.

### 7.1 Result: the operationalization does not transfer — decisively, and for a specific, confirmed reason

| Experiment | Signalled (combined) | Hit rate | Verdict |
|---|---|---|---|
| contrarian | 9 | 0.333 (n=9, uninformative) | REJECTED (insufficient samples) |
| momentum | 9 | 0.667 (n=9, uninformative) | REJECTED (insufficient samples) |

Pooled signalled samples collapsed from **141 (Binance) to 9
(Hyperliquid)** — far below the pre-registered floor, on the *identical*
threshold and *identical* 1,647 grid points. This is not ambiguous noise;
it was checked mechanically (§7.2) and fully explained.

### 7.2 Why: confirmed via the same outcome-blind exploratory method as §1

Hyperliquid's own funding-rate distribution over the identical window:

| Symbol | Hyperliquid median | Hyperliquid p99 | Binance median | Binance p99 |
|---|---|---|---|---|
| BTC | 0.0000125 | 0.000149 | 0.000100 | 0.000567 |
| ETH | 0.0000125 | 0.000139 | 0.000100 | 0.000578 |
| SOL | 0.0000125 | 0.000215 | 0.000100 | 0.000727 |

Hyperliquid pooled |funding| percentiles: p50=0.0000125, p90=0.0000755,
**p99=0.000174** — still *below* the Binance-calibrated locked threshold
(0.00023655). **The threshold is above Hyperliquid's own 99th
percentile** — it was, unknowingly at lock time, an even more extreme cutoff
on Hyperliquid's scale than on Binance's. Hyperliquid's funding rate runs
roughly 3–8× smaller in typical magnitude than Binance's for the same
assets and period — a real, structural difference between the two
venues' funding formulas/cadence (Hyperliquid: hourly; Binance: 8-hourly
historically), not sampling noise.

### 7.3 Precise, honest conclusion (read carefully — two different claims, not one)

- **What this result does NOT show**: it does **not** show that funding
  momentum/contrarian "fails on Hyperliquid" — n=9 is far too small to
  conclude anything about the underlying hypothesis one way or the other
  on this venue.
- **What this result DOES show**: a **fixed absolute-magnitude threshold
  calibrated on one venue's historical distribution does not transfer to
  a second venue with a structurally different funding scale** — the
  operationalization itself, not the hypothesis, is what failed to
  transfer. This is a distinct, general, and important finding for any
  future exchange-native threshold-based research (§9, §10).
- **Governance**: both experiments recorded REJECTED (reviewer ≠
  researcher, evidence-fingerprint verified) — correctly, since neither
  the Binance screen (§6) nor this replication clears the pre-registered
  bar. **Moot for promotion regardless**: the Binance screen alone
  already disqualified both experiments (§6.3) before Hyperliquid was
  even considered — this replication was performed for completeness and
  to inform Campaign 03, not because either experiment was pending a
  promotion decision.

Sealed evidence-package fingerprints (combined, Hyperliquid): contrarian
`051df9d90ed8e0d0…` · momentum `f99575814fb8e18a…`
(`data/alpha_engine_research/campaign_02_hyperliquid_combined.jsonl`).

## 8. Governance summary

Four governance decisions recorded (reviewer `reviewer-campaign02` ≠
researcher `researcher-campaign02`, evidence-fingerprint verified in
every case), all **REJECT**:

| Experiment | Source | Lifecycle state |
|---|---|---|
| `camp02-binance-combined-contrarian` | Binance | REJECTED |
| `camp02-binance-combined-momentum` | Binance | REJECTED |
| `camp02-hyperliquid-combined-contrarian` | Hyperliquid | REJECTED |
| `camp02-hyperliquid-combined-momentum` | Hyperliquid | REJECTED |

No experiment reached APPROVE. `docs/ALPHA_LIBRARY.md` remains empty of
approved models.

## 9. Lessons learned

1. **A raw-magnitude threshold does not transfer across venues** — the
   single most important finding of this campaign. Even with the
   candidate mechanism, direction, horizon, and criteria held perfectly
   fixed, the *operationalization* (an absolute Decimal threshold) failed
   to transfer because Hyperliquid's funding scale differs structurally
   from Binance's (§7.2). Future exchange-native threshold research
   should default to a venue-relative methodology (e.g., a percentile of
   *that venue's own* historical distribution) from the start, rather
   than assuming a raw magnitude is portable — this is a direct,
   evidence-based refinement to the DEX-first venue-replication process
   itself (`docs/RESEARCH_PLAYBOOK.md` §5), not a change to this
   campaign's own (correctly non-retuned) locked specification.
2. **The five-stage gate caught a result single-pass alone would have
   missed.** Momentum (combined, Binance) cleared single-pass outright —
   the first time any Campaign 02 experiment did — and was still
   correctly rejected once walk-forward and regime stratification showed
   the apparent edge was concentrated in 93.6% one regime (bull). This is
   exactly the scenario the multi-stage design exists to catch, and it
   worked.
3. **The per-fold `min_signaled_samples=100` criterion is likely
   miscalibrated for walk-forward specifically.** With ~141 pooled
   signalled samples split across 5 folds (~28/fold), no fold could ever
   clear a 100-sample floor regardless of the true edge — walk-forward
   failure here may partly reflect this structural mismatch rather than
   genuine fold-to-fold inconsistency. Worth a dedicated review before
   Campaign 03 (a methodology question, not an implementation one — see
   `ROADMAP.md`).
4. **Funding's sign-skew and persistence, flagged outcome-blind in §1,
   played out exactly as anticipated**: BTC and ETH contributed almost no
   lower-tail signals (as predicted from their historical minima), and
   the high settlement-to-settlement persistence meant the "combined"
   result was dominated by a small number of underlying regime-episodes,
   not many independent observations — both declared before any outcome
   was examined, both confirmed after.
5. **BTC's individual momentum result (0.686 hit rate, 96.9% of bootstrap
   resamples clearing the bar, though only 35 signalled samples) is the
   strongest single-symbol result across both campaigns to date.** Too
   underpowered to act on alone, but a specific, named candidate for a
   properly-powered, separately pre-registered follow-up.

## 10. Recommendation for Campaign 03

Two independent, well-motivated directions, not mutually exclusive:

1. **Fix the venue-transfer methodology, then re-attempt Funding Rate.**
   Re-run this same hypothesis (contrarian/momentum funding-rate
   threshold) with a **venue-relative threshold** (percentile of each
   venue's own distribution, computed separately for Binance and
   Hyperliquid) rather than one raw magnitude carried across venues. This
   directly tests whether the underlying hypothesis has any edge at all
   on Hyperliquid — something this campaign correctly could not
   determine (§7.3) — without violating the "no retuning after results"
   rule, since the venue-relative *methodology* would be decided and
   locked *before* looking at outcomes on either venue, exactly as this
   campaign's own threshold was derived from an outcome-blind exploratory
   pass (§1).
2. **A dedicated, properly-powered BTC-only momentum follow-up.** The
   single strongest result in either campaign so far (§9 item 5) is
   underpowered at 35 samples; a longer BTC-only backfill (Binance
   history goes back to 2020-01, far deeper than the 18 months used here)
   could resolve whether it is real or a small-sample artifact, as its
   own separately pre-registered experiment — never as a retroactive
   change to this campaign's already-closed record.

Both are **new, separately pre-registered campaigns** — this campaign
(CAMP-02) is closed and, per standing discipline, will not be reopened,
retuned, or revisited without new evidence justifying it.

---

**Status: COMPLETE.** Both experiments (contrarian, momentum) REJECTED on
the Binance screen; Production Venue Validation performed and recorded;
zero approved alphas added to the library; the campaign's process and
platform performed correctly throughout (no code changes were required
mid-campaign beyond the pre-planned, pre-registered harness).
