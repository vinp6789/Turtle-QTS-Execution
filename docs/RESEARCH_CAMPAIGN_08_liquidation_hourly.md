# Research Campaign 08 — Hourly Liquidation Density (BTC/ETH/SOL)

**Status: PRE-REGISTRATION LOCKED, NOT YET REGISTERED.** Parameters below
are frozen by the Backlog 3.5 feasibility measurement and must not change
after results are seen. Execution is blocked on one platform decision
(§7) that requires human judgment.

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

## §7 — Blocking decision: this campaign needs a new candidate family

**No liquidation feature or candidate type exists.** `CANDIDATE_CATALOG`
holds exactly three families — `funding_rate_threshold_rule`,
`open_interest_threshold_rule`, `open_interest_extremeness_rule` — and no
feature module references liquidations.

Two paths, and the choice is **not** mine to make unilaterally because it
writes to the permanent evidence record:

**(a) Reuse `funding_rate_threshold_rule`.** Precedented — CAMP-04
(`funding_delta`) and CAMP-05 (`oi_velocity`) both did this. But the
factory reads `feature_name`/`feature_version` from
`FundingRateFeature.metadata()` and **never from the caller**, so every
evidence package would be stamped `feature_name="funding_rate"` while
actually testing liquidation density. `ALPHA_LIBRARY.md`'s
"(feature `oi_velocity`)" annotations are human notes papering over
exactly this. Zero new code, **knowingly false provenance**.

**(b) Add a `liquidation_density_rule` family** — feature module,
candidate type, spec factory, `evaluate_fn`, catalog entry, tests.
Correct provenance; the first new candidate family since Campaign 01.
Roughly 300–400 LOC of platform code, all additive.

**Recommendation: (b).** This is the first campaign whose result could be
promotion-eligible, and Constitution §5's "no abstraction ahead of a
second concrete need" is satisfied — there is a specific, present
requirement, and (a) achieves reuse only by falsifying the record. But
(b) is platform work touching the candidate catalog, so it warrants
explicit authorization rather than being absorbed into a research task.

**Nothing is registered and no experiment has run.** The parameters above
are frozen and independent of which path is chosen — the decision affects
implementation and provenance, not the science.
