# Research Campaign 08 — Hourly Liquidation Density (BTC/ETH/SOL)

**Status: CLOSED — all four experiments REJECTED on merit (2026-08-05).**
Parameters were frozen by the Backlog 3.5 feasibility measurement before
any result was seen and were not changed afterwards.

**Why this campaign is different from every prior one:** it is the
**first with BOTH feature and outcome Hyperliquid-native**. Campaigns
01–05 and 07 all carried a DEFER-ceiling (Binance data, knowledge-only)
or a venue-transfer caveat. A positive result here would be
**promotion-eligible** under Constitution §6 — the first in project
history.

---

## Pre-registration (LOCKED)

| Experiment ID | Threshold | n_folds | Direction | Role |
|---|---|---|---|---|
| `camp08-p75-f3-contrarian` | p75 | 3 | contrarian | **PRIMARY** |
| `camp08-p75-f3-momentum` | p75 | 3 | momentum | **PRIMARY** |
| `camp08-p75-f5-contrarian` | p75 | 5 | contrarian | robustness (fold count) |
| `camp08-p75-f5-momentum` | p75 | 5 | momentum | robustness (fold count) |

**Feature:** hourly count of unique liquidation events (distinct `tid`)
per symbol, from `liquidation__*__hyperliquid_s3.csv`.
**Signal:** count ≥ the **p75 of that symbol's own hourly distribution**
(Constitution §6 — venue- and instrument-relative, never one absolute
count across symbols).
**Outcome:** 1-hour forward return from
`mark_price__*__hyperliquid_1h.csv` (Backlog 3.6).
**Universe:** BTC/ETH/SOL pooled. **Window:** 2026-01-09T09:00 →
2026-07-28T23:00, **4,815 hourly samples** (bounded by the venue's ~210-day
1h-candle retention, not by the liquidation archive).
**Sampling:** every hour; outcome window 1h, so **non-overlapping by
construction**.
**Locked:** `min_hit_rate = 0.55`; `min_signaled_samples = 100` per fold;
bootstrap `n_resamples = 1000`, `seed = 7`; regime stratification by BTC
bull/bear/chop.

**Direction mapping (the tested structural assumption):** high
liquidation density → SHORT (contrarian: the cascade exhausts) / LONG
(momentum: the cascade continues). Liquidation counts do not reveal which
side was liquidated, so this mapping is what the two directions
**falsify**, not a known fact.

**Not independent evidence (RD-17 §D):** contrarian and momentum hit
rates are algebraically complementary. Four experiments are registered
because Constitution §6 requires it; this campaign reports **two
independent measurements**.

## Excluded on measurement

| Excluded | Effective worst-fold | Reason |
|---|---|---|
| **p90**, folds 3 | 85 | below the floor of 100 |
| **p90**, folds 5 | 53 | below floor |
| **p99**, any | 6 / 3 | far below floor |
| **Daily** specification | 40.2 | remains deferred exactly as RD-16 states |
| Binance cross-venue outcome | — | would forfeit promotion-eligibility (§6) |

## Feasibility (measured on the exact campaign panel, outcome-blind)

4,815 usable samples. Cross-symbol ρ̄ = **+0.731** → N_eff **1.22 of 3**
(haircut ×0.406); serial retention **×0.654** (hourly lag-1 ρ ≈ +0.20).

| Config | total signalled | worst fold | effective (both haircuts) | |
|---|---|---|---|---|
| p75, folds 3 | 3,677 | 951 | **253** | **CLEARS 2.5×** |
| p75, folds 5 | 3,677 | 555 | **147** | **CLEARS** |

## Derivation-scope declaration (RD-11 A)

- **Feature:** raw hourly event count — no normalization.
- **Threshold:** **FULL-SAMPLE** per-symbol p75. This is a recorded
  methodological *impurity*, not a demonstrated bias (RD-11 E), and is
  the same scope CAMP-02/03 carried. A rolling normalization was
  considered and rejected: with 51–65% zero-count hours, a trailing
  percentile rank is dominated by ties at zero.

## Known limitations (into every evidence package)

1. **Zero-inflation:** 51.4% (BTC), 63.3% (ETH), 65.1% (SOL) of hours have zero events. CAMP-05's "continuous threshold, zero ties" criterion is **not** met; the threshold is well-defined only because p75 lies above the zero mass.
2. **Window bounded by venue retention**, not by data: 200 usable days of a 366-day liquidation archive, because Hyperliquid retains 1h candles ~210 days. The Live Recorder (RD-18) removes this constraint for future data only.
3. **Cross-symbol dependence is high** (ρ̄ +0.731, N_eff 1.22 of 3) — pooling three symbols buys ~1.2 symbols' worth of information.
4. **Short window:** ~6.5 months, versus the 18-month windows Campaigns 01–05 used. Regime coverage is correspondingly narrow.
5. Liquidation counts do not reveal the liquidated side (see direction mapping).
6. **Reporting caveat (RD-11 D), verbatim:** *Backtests flatter. Single-pass results are the most optimistic number here and should carry the least weight. The walk-forward stage in this campaign checks whether one fixed, pre-registered rule holds consistently across chronological periods — it is not an out-of-sample generalization test: no parameter is refit per fold, and thresholds may be derived from the full-sample feature distribution (see the campaign's derivation-scope declaration). Treat every number as an upper bound on what live trading would deliver, before fees, slippage, and execution costs — none of which are modelled.*

## Mandatory reporting (RD-13 §C)

N_eff and cross-symbol correlation, alongside raw signalled counts.

---

## §7 — Platform decision (RESOLVED)

Path **(b)** was authorized and taken: a dedicated `liquidation_density_rule`
family was added (commit `e938dc4`) — feature module, candidate type, spec
factory, `evaluate_fn`, catalog entry, 29 tests. Every Campaign 08 evidence
package records `feature_name = liquidation_density_hourly`, verified in the
run output. Path (a) — reusing `funding_rate_threshold_rule` — would have
stamped `funding_rate_raw`, the misstatement CAMP-04 and CAMP-05 carry.

One deliberate semantic difference from the family it mirrors: funding is
signed and fires on `rate > threshold` **or** `rate < -threshold`; a
liquidation count is non-negative, so `-threshold` is unreachable and the
rule is **one-tailed** (`count >= threshold` → signal, else FLAT). A test
pins this so a later "consistency" refactor cannot reintroduce the dead
branch. No existing family was modified.

**Implementation note (mathematically identical to the locked rule).** The
platform applies one threshold to all samples, but the rule is per-symbol.
The normalization is therefore carried in the value —
`feature value := count / p75(symbol)`, `threshold := 1.0` — which is
exactly `count >= p75(symbol)` and, unlike a percentile-rank transform, is
tie-safe (material here: 51–65% of hours are zero-count). Measured
per-symbol p75: **BTC 77, ETH 6, SOL 5** counts/hour.

---

## Results (FINAL)

**Status: CLOSED — all four experiments REJECTED on merit.**

Executed 2026-08-05, fixed clock `2026-08-05T00:00:00+00:00`, seed 7.
**14,449 samples** (4,816 hours × 3 symbols), **3,678 signalled (25.5%)**.
Governance recorded through the frozen module for all four.

| Experiment | Role | Signalled | Hit rate | mean_directional_return | Boot. frac ≥ bar | Verdict |
|---|---|---|---|---|---|---|
| `camp08-p75-f3-contrarian` | **PRIMARY** | 3,678 | **0.5019** | +0.0000404 | 0.000 | **REJECTED** |
| `camp08-p75-f3-momentum` | **PRIMARY** | 3,678 | **0.4965** | −0.0000404 | 0.000 | **REJECTED** |
| `camp08-p75-f5-contrarian` | robustness | 3,678 | 0.5019 | +0.0000404 | 0.000 | **REJECTED** |
| `camp08-p75-f5-momentum` | robustness | 3,678 | 0.4965 | −0.0000404 | 0.000 | **REJECTED** |

Stage results identical across all four: **causality/leakage audit PASSED**
(no look-ahead), single-pass FAILED, walk-forward FAILED, regime FAILED.

**Provenance verified:** every experiment recorded
`feature recorded in evidence: liquidation_density_hourly`.

### Mandatory reporting (RD-13 §C)

Cross-symbol correlation of hourly counts on the campaign panel:
BTC–ETH +0.713, BTC–SOL +0.719, ETH–SOL +0.761 → **ρ̄ = +0.731**,
**N_eff = 1.22 of 3 symbols**. Serial retention ×0.654 (hourly lag-1
ρ ≈ +0.20). Effective per-fold signalled samples: **253** (folds=3) and
**147** (folds=5) — both clearing the floor of 100 by 2.5× and 1.5×.

**This was a well-powered merit rejection, not a power failure.**

### Final verdict

All four **REJECTED**. Hit rates **0.4965–0.5019** — the tightest
clustering around a coin flip the program has produced. Only **two
independent measurements** exist (the contrarian/momentum pair is
algebraically complementary; the small departure from summing to exactly
1.0 is the FLAT/zero-return hours).

**Hourly liquidation density carries no 1-hour directional edge**, on the
first campaign in project history where feature and outcome were both
venue-native and a positive result would have been promotion-eligible.

### Honest note on what this does and does not close

It closes the **hourly** specification that RD-16 §E named and Backlog 3.5
approved. It does **not** close the liquidation family: the window was
200 days (venue retention, not data), regime coverage was narrow, and only
the 1-hour horizon was tested. Multi-hour horizons on this feature remain
untested — though RD-17 is standing counter-evidence that horizon
extension alone rescues a null.
