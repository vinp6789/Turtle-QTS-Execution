# RESEARCH_CAMPAIGN_06 — Outcome-Blind Feasibility Review (Backlog 1.6)

**Verdict: DEFER Campaign 06.** Not approved for pre-registration on the
current 12-month window.

- **Date:** 2026-08-05 · **Author:** researcher · **Reviewer:** pending
- **Status:** complete — this is the gate defined by
  `PROJECT_CONSTITUTION.md` §6 and `RESEARCH_DECISIONS.md` RD-13 §C.
- **Campaign 06 is NOT pre-registered and has NOT begun.** No hypothesis
  was tested, no return computed, no profitability evaluated.

## 0. What this review did and did not touch

**Strictly outcome-blind.** The analysis
(`research/campaign_06_liquidations/feasibility_review.py`) reads **only**
the liquidation event series. It never opens the mark-price / outcome
series, never computes a forward return, and never adjusts a threshold
against a result. The outcome series remains sealed until (and unless) a
specification is locked.

Governing rules applied as written, not re-derived:

| Rule | Application |
|---|---|
| **RD-14** | Absent `(symbol, day)` rows inside the window materialized as `count = 0` — 8 such cells |
| **RD-15** | 2025-07-27 (16/24 archive hours) **excluded**, per §D option 1 (recommended, assumption-free). RD-14 deliberately not applied to it |
| **Constitution §6** | Thresholds derived per-instrument from Hyperliquid's own distribution; no absolute magnitude carried across venues or symbols |
| **RD-13 §C** | N_eff and cross-symbol correlation reported — **not** raw pooled counts alone |

Acceptance bar tested against, **unchanged**: `min_signaled_samples = 100`,
applied **per fold** (Campaigns 01/02/03); `n_folds = 5` standard with
`n_folds = 3` as the precedented outcome-blind fallback (Campaign 03).

## 1. Runtime

| Stage | Seconds |
|---|---|
| Stage 1 — build audited panel (4,277,522 rows → 1,098 cells) | 13.78 |
| Stage 2 — venue-relative thresholds | 0.00 |
| Stage 3 — feasibility statistics + 1,000-resample bootstrap | 0.04 |
| **Total** | **13.83** |

Consistent with the pre-agreed plan: this was a foreground job, no
detached execution, no checkpointing, no resumability.

## 2. Stage 1 — audited daily panel

Artifact: `data/alpha_engine_research/campaign_06_feasibility/daily_event_counts.csv`
— **366 days × 3 symbols = 1,098 cells**, 2025-07-28 → 2026-07-28,
contiguous. Counts are **unique liquidation events** (distinct `tid`),
not fill rows.

**Pre-flight assertions — 11/11 PASS** (the run refuses to continue on any
failure):

| Assertion | Result |
|---|---|
| `symbol_count` | PASS — 3 |
| `date_coverage[BTC/ETH/SOL]` | PASS — 366 days each |
| `panel_row_count` | PASS — 1,098 (expected 1,098) |
| `contiguous[BTC/ETH/SOL]` | PASS — 2025-07-28..2026-07-28, no gaps |
| `rd14_zero_materialization` | PASS — 8 zero cells: ETH 2026-01-17, 2026-01-24, 2026-07-25; SOL 2025-12-20, 2026-01-17, 2026-04-25, 2026-05-03, 2026-07-25 |
| `rd15_partial_day_excluded` | PASS — 2025-07-27 absent from panel, **present in raw collected data** (proving deliberate exclusion, not a collection gap) |
| `no_negative_counts` | PASS |

Descriptive (events/day, outcome-blind):

| Symbol | min | p25 | median | p75 | max | zero-days |
|---|---|---|---|---|---|---|
| BTC | 1 | 1,108.5 | 2,501.0 | 4,375.0 | 35,460 | 0 |
| ETH | 0 | 282.0 | 776.5 | 1,620.0 | 28,350 | 3 |
| SOL | 0 | 267.5 | 629.5 | 1,251.2 | 19,611 | 5 |

## 3. Stage 2 — venue-relative thresholds (Hyperliquid only)

Per-symbol percentiles of each symbol's **own** daily-count distribution.
Per-instrument derivation is the direct analogue of the venue-relative
rule: BTC/ETH/SOL medians differ ~4×, so a single pooled absolute count
would be a BTC threshold wearing a pooled label.

| Symbol | p60 | p75 | p90 |
|---|---|---|---|
| BTC | 2,973 | 4,375 | 6,972 |
| ETH | 1,053 | 1,620 | 2,966 |
| SOL | 839 | 1,251 | 2,050 |

## 4. Stage 3 — feasibility statistics

### 4.1 Cross-symbol dependence (the binding constraint)

| Pair | Pearson r |
|---|---|
| BTC–ETH | **+0.758** |
| BTC–SOL | **+0.799** |
| ETH–SOL | **+0.898** |
| **Mean pairwise ρ** | **+0.818** |

**N_eff = 3 / (1 + 2ρ̄) = 1.14 effective independent series**, not 3.
Effective-sample haircut **×0.379**.

This **confirms the pilot projection on 12× the data.** RD-13 measured
ρ = +0.85–0.90 on one month and projected ≈1.1 effective symbols; the
full year gives ρ̄ = +0.818 and 1.14. The dependence is structural, not a
small-sample artifact.

Within-symbol lag-1 autocorrelation: BTC +0.308, ETH +0.224, SOL +0.258 —
**additional** serial dependence not included in the haircut below
(see §4.4).

### 4.2 Per-fold signalled samples vs the floor

Floor: **100 per fold**, unchanged.

| Threshold | n_folds | worst raw | mean raw | worst **effective** | mean **effective** | raw clears? | **effective clears?** |
|---|---|---|---|---|---|---|---|
| p60 | 3 | 106 | 147.0 | **40.2** | 55.7 | YES | **no** |
| p60 | 5 | 49 | 88.2 | 18.6 | 33.4 | no | **no** |
| p75 | 3 | 57 | 92.3 | 21.6 | 35.0 | no | **no** |
| p75 | 5 | 20 | 55.4 | 7.6 | 21.0 | no | **no** |
| p90 | 3 | 14 | 37.0 | 5.3 | 14.0 | no | **no** |
| p90 | 5 | 1 | 22.2 | 0.4 | 8.4 | no | **no** |

**Not one configuration clears the floor on an effective-sample basis.**
The single best case — p60 at the most permissive fold count — reaches
40.2 against a floor of 100, short by a factor of **2.5**. This is not
marginal.

### 4.3 Bootstrap stability (moving-block, b=7d, n=1000, seed=7)

A moving-block bootstrap was used rather than an i.i.d. day bootstrap
because the series is serially dependent (§4.1); an i.i.d. resample would
understate variance and flatter the result.

| Config | mean | 90% CI | P(raw ≥ 100) | **P(effective ≥ 100)** |
|---|---|---|---|---|
| p60, 3 folds | 146.9 | [117, 180] | 0.99 | **0.00** |
| p60, 5 folds | 86.9 | [63, 111] | 0.20 | **0.00** |
| p75, 3 folds | 92.0 | [62, 125] | 0.33 | **0.00** |
| p75, 5 folds | 54.8 | [32, 78] | 0.00 | **0.00** |
| p90, 3 folds | 37.5 | [20, 58] | 0.00 | **0.00** |
| p90, 5 folds | 22.4 | [8, 39] | 0.00 | **0.00** |

**P(effective ≥ 100) = 0.00 in every configuration.** The failure is not
sampling noise; it is structural.

### 4.4 Why the reported effective counts are *optimistic*

The ×0.379 haircut corrects for **cross-symbol** dependence only. The
measured **serial** dependence (lag-1 ≈ +0.22 to +0.31) further reduces
effective sample size within each series. A standard first-order
correction, `(1−ρ₁)/(1+ρ₁)` ≈ 0.59 at ρ₁ ≈ 0.26, would take the best
case from 40.2 to roughly **24** effective samples per fold. That
combination is an approximation and is **not** the basis of the verdict —
it is stated because it moves the conclusion further from approval, never
toward it.

### 4.5 Regime coverage (outcome-blind proxy)

Signalled samples by quarter — normalized for unequal quarter lengths
(2025Q3 = 65 days, 2026Q3 = 28 days):

| Quarter | p60 count | per day |
|---|---|---|
| 2025Q3 (65d) | 88 | 1.35 |
| 2025Q4 (92d) | 140 | 1.52 |
| 2026Q1 (90d) | 110 | 1.22 |
| 2026Q2 (91d) | 76 | 0.84 |
| 2026Q3 (28d) | 27 | 0.96 |

**Regime coverage is adequate and is NOT the binding constraint.**
Signals appear in every period with no severe concentration. The failure
is sample size alone.

*Formal BTC-trend-regime labelling (the Campaign 01 convention) requires
the price series and therefore belongs to the validation stage after
pre-registration; temporal dispersion is the strictly outcome-blind
substitute available at this gate.*

## 5. Interpretation

The decision turns on one point, and it is the exact point RD-13
anticipated:

- Counted as **raw pooled samples**, the best configuration (p60,
  n_folds=3) *passes*: 106 worst-fold, P(≥100) = 0.99.
- Counted as **effective samples**, it *fails decisively*: 40.2, with
  P(≥100) = 0.00.

RD-13 §C made N_eff reporting **mandatory for exactly this situation** —
"any future feasibility review for a metric whose samples may share
cross-instrument dependence must report effective sample size, not raw
pooled signalled counts alone." Pooling BTC/ETH/SOL daily liquidation
counts is close to counting **one** market-wide process three times: at
ρ̄ = +0.818, three symbols supply 1.14 series' worth of independent
information.

Approving on the raw count would satisfy the letter of
`min_signaled_samples = 100` while violating the reason it exists. That
is the "weakening the bar to preserve momentum" failure this gate was
built to prevent.

**What would change the answer.** To reach 100 *effective* samples in the
worst fold at p60/n_folds=3, raw worst-fold count must reach
100 / 0.379 ≈ **264**, versus 106 today — roughly **2.5× more data**.
Since the archive extends only forward in time (RD-15: nothing exists
before 2025-07-27T08:00Z), that implies a window of ≈**30 months**, i.e.
approximately **18 further months** of accumulation.

## 6. Risks and limitations of this review

- **Not a verdict on the mechanism.** Nothing here says liquidation
  cascades carry no signal. The hypothesis was never tested — this is a
  **testability** failure. Recording it as REJECTED would enter an
  untested hypothesis into the ledger as rejected, which would be false.
- **Threshold grid is illustrative, not exhaustive.** p60/p75/p90 × {3,5}
  folds follows Campaigns 01–03. A more permissive threshold than p60
  would raise counts but degrade toward "signal on most days," which is
  not a discriminating rule. Nothing in the grid was chosen after seeing
  an outcome, because no outcome was inspected.
- **Daily cadence is an assumption of this review, not a law.** The one
  live alternative that could plausibly change feasibility is a
  **finer-grained (e.g. hourly) specification**, which would multiply raw
  sample counts by up to ~24×. This is **not** a recommendation and
  **not** feasible-by-assertion: hourly data would have materially higher
  serial autocorrelation and possibly different cross-symbol dependence,
  both of which attack N_eff directly. It would require **its own
  feasibility review** before any pre-registration.
- **N_eff formula.** The equicorrelated form `n / (1 + (n−1)ρ̄)` matches
  the method RD-13 used (and reproduces its ≈1.1). It assumes roughly
  equal pairwise correlation; measured pairs span +0.758 to +0.898, so
  the assumption is reasonable but not exact.
- **§4.4's combined haircut is approximate** and deliberately excluded
  from the verdict basis.

## 7. Recommendation

**DEFER Campaign 06** — do not pre-register on this window.

DEFER rather than REJECT, following the **RD-04 precedent** (Funding
Persistence, deferred on non-viable N_eff — recorded as a *deferred
pre-registration*, not a rejected hypothesis). The mechanism is untested;
only its testability failed, and the constraint is one that time relaxes.

**Revisit trigger (measurable, not calendar-based):** re-run this exact
review when the archive supports a window in which the worst-fold raw
signalled count at p60/n_folds=3 reaches ≈264 — currently projected at
roughly 18 further months of accumulation. The review is a 14-second
foreground job and can be re-run at any time at zero cost.

**Do not** re-run it with a lowered floor, a more permissive threshold
chosen to clear the bar, or the N_eff requirement dropped. Any of those
would convert this gate from a control into a formality.

This is the cheapest possible outcome of the gate — a campaign correctly
not started, at a cost of 14 seconds of compute — and per `ROADMAP.md`
§1.1 it is the intended, designed result, not a failure.

## 8. Final verdict

> **DEFER Campaign 06.**
> Cross-symbol correlation ρ̄ = +0.818 gives N_eff = 1.14 effective
> independent series from 3 symbols. No threshold/fold configuration
> reaches the locked `min_signaled_samples = 100` per fold on an
> effective-sample basis; the best case reaches 40.2, and
> P(effective ≥ 100) = 0.00 across all six configurations under a
> 1,000-resample moving-block bootstrap. The 12-month window is
> insufficient by roughly 2.5×. Regime coverage is adequate; sample size
> alone is binding. The mechanism remains untested and is not rejected.

---

**Artifacts:**
`research/campaign_06_liquidations/feasibility_review.py` ·
`data/alpha_engine_research/campaign_06_feasibility/daily_event_counts.csv` ·
`data/alpha_engine_research/campaign_06_feasibility/feasibility_statistics.json`
