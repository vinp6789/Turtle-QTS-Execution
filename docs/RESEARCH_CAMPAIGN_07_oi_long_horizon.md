# Research Campaign 07 — Longer-Horizon Open Interest (BTC/ETH/SOL)

**Information source under test:** Open Interest, Binance, in isolation.
Every other source is out of scope by design.

**What is new versus CAMP-01:** the **forward-return horizon**. CAMP-01
tested 24h and rejected. Every campaign in the program to date
(CAMP-01–05, 18 registered models) used a 24-hour horizon; no campaign has
ever measured another. This campaign tests **72h and 120h** with strictly
non-overlapping outcome windows.

---

## Pre-registration (LOCKED — thresholds frozen, never changed after results)

| Experiment ID | Horizon | Signal (30-day trailing, PIT, centered rank) | Direction | Role |
|---|---|---|---|---|
| `camp07-h72-t40-contrarian` | 72h | \|centered rank\| ≥ 0.40 ⟺ rank ≥0.90 or ≤0.10 | contrarian | **PRIMARY** |
| `camp07-h72-t40-momentum` | 72h | same | momentum | **PRIMARY** |
| `camp07-h72-t25-contrarian` | 72h | \|centered rank\| ≥ 0.25 ⟺ rank ≥0.75 or ≤0.25 | contrarian | robustness (threshold axis) |
| `camp07-h72-t25-momentum` | 72h | same | momentum | robustness (threshold axis) |
| `camp07-h120-t40-contrarian` | 120h | \|centered rank\| ≥ 0.40 | contrarian | robustness (horizon axis) |
| `camp07-h120-t40-momentum` | 120h | same | momentum | robustness (horizon axis) |

**Locked parameters (identical across all six except horizon, threshold
and direction):** 30-day trailing window; **non-overlapping** samples
(`sample_spacing_hours == horizon_hours`, enforced by assertion in
`build_samples`); point-in-time only; universe BTC/ETH/SOL pooled;
`min_hit_rate = 0.55`; `min_signaled_samples = 100`; walk-forward
`n_folds = 3`; bootstrap `n_resamples = 1000`, `seed = 7`; regime
stratification by BTC bull/bear/chop (price-derived, independent of OI).
Implemented in `research/campaign_07_oi_long_horizon/run_campaign.py`;
the constants there **are** the pre-registration and MUST NOT change
after results are observed.

**Primary decision criterion.** Only the two **PRIMARY** experiments
decide the campaign. The robustness arms vary exactly one axis each from
PRIMARY (threshold, or horizon) so that a difference is attributable to
that axis alone. This mirrors CAMP-01's "pctrank PRIMARY / z-score
robustness" structure.

**Direction mapping (the tested structural assumption):** upper-tail OI
extreme → SHORT (contrarian) / LONG (momentum); lower-tail → the mirror.
OI magnitude does not reveal positioning side, so this mapping is what the
two direction experiments FALSIFY, not a known fact. Identical to CAMP-01.

**Mandatory disclosure — the two directions are NOT independent evidence.**
Contrarian and momentum hit rates are algebraically complementary; verified
in the closed record (CAMP-04 Binance 0.477/0.523; CAMP-04 Hyperliquid
0.511/0.489; CAMP-05 0.5154/0.4846 — every pair sums to exactly 1.0000).
Constitution §6 *requires* registering them separately to prevent
post-hoc direction-picking, so six experiments are registered — but this
campaign reports **three independent measurements**, not six. Earlier
campaigns' "four hypotheses rejected" framing overstated the count ~2×;
this campaign does not repeat that.

---

## Design choices resolved before locking

**1. Tails — both, per CAMP-01 precedent.** The platform feature is
`percentile_rank_centered`, so `|centered| ≥ t` is symmetric by
construction (upper and lower tail together). No new methodology; CAMP-01
used exactly this with `t = 0.49`.

**2. Threshold arm retained, with PRIMARY declared.** CAMP-01's own
threshold (`t = 0.49`, rank ≥0.99/≤0.01) is **infeasible at these
horizons** — ~2% selectivity against 1,664 pooled samples yields far below
the per-fold floor. Two changes from CAMP-01 (horizon *and* selectivity)
are therefore unavoidable. Declaring `t = 0.40` PRIMARY and varying one
axis per robustness arm makes the attribution explicit rather than
confounded.

---

## Feasibility (measured with the real sample builder, outcome-blind)

Pooled samples and signalled counts at `n_folds = 3`, floor = 100:

| Horizon | Samples | Threshold | Signalled | Worst fold | Verdict |
|---|---|---|---|---|---|
| **72h** | 1,664 | **0.40** | 573 | **183** | **REGISTERED (PRIMARY)** |
| **72h** | 1,664 | **0.25** | 1,036 | **337** | **REGISTERED (robustness)** |
| **120h** | 988 | **0.40** | 335 | **107** | **REGISTERED (robustness)** |
| 120h | 988 | 0.25 | 607 | 194 | excluded — varies two axes at once, adds no attribution |
| 168h | 700 | 0.40 | 226 | **66** | **excluded — below floor** |
| 168h | 700 | 0.25 | 425 | 135 | excluded — outside the approved horizon scope |

---

## Acceptance criteria (locked before any result is seen)

- `min_hit_rate = 0.55` — the hit rate must exceed this on single-pass **and** in every walk-forward fold.
- `min_signaled_samples = 100` — **per fold**, not only in aggregate.
- Causality/leakage audit must pass.
- Regime stratification must not confine the edge to one regime.
- **Governance inspects `mean_directional_return`** — a favourable hit rate with non-positive expectancy is a rejection, not a pass (`RESEARCH_PLAYBOOK.md` §5, restored per RD-13).

## Rejection criteria (any one rejects)

Single-pass hit rate < 0.55 · any fold below the signalled floor · any
fold failing hit rate · edge confined to a single regime · causality audit
failure · non-positive expectancy at governance.

---

## Derivation-scope declaration (RD-11 A)

- **Feature:** ROLLING — 30-day trailing percentile rank, strictly
  point-in-time.
- **Threshold:** FIXED CONSTANT on the normalized rank — **not** derived
  from the sample. RD-11 E's full-sample impurity does not apply, and the
  threshold is venue-relative by construction.

## Known limitations (carried into every evidence package)

1. Binance USDT-perp data as a cross-venue proxy for the live Hyperliquid venue — not venue-exact.
2. **DEFER-CEILING: knowledge-only.** No Hyperliquid OI history exists at all, so a positive result is **not promotion-eligible** under Constitution §6.
3. **Outcome/feature share an upstream field.** Outcome is derived as `price = sum_open_interest_value / sum_open_interest`; the feature's raw field is `sum_open_interest`. Algebraic cancellation was verified against an independent price source (Hyperliquid daily candles) over 367 days: agreement within ±0.03 in every symbol and volatility stratum, r = +0.89–0.92 between sources, and the observed coupling is **positive** where a measurement artifact would be negative. Contemporaneous ΔOI–Δprice coupling of +0.11 to +0.32 is genuine market co-movement, not contamination. **Independent-source validation covers 18% of the campaign window** (367 of 2,036 days); a SOL high-volatility coupling of −0.32 in the uncovered 2022–2025 period could not be cross-validated.
4. **Survivorship bias** — BTC/ETH/SOL selected in 2026, tested from 2021/2022.
5. **Non-stationarity** — window spans two halvings and the ETF era; partially mitigated by the trailing normalization.
6. **Asymmetric per-symbol starts** — BTC 2021-01, ETH/SOL 2022-01.
7. OI magnitude does not reveal positioning side — the tail→direction mapping is a tested structural assumption.
8. **Reporting caveat (RD-11 D), verbatim:** *Backtests flatter. Single-pass results are the most optimistic number here and should carry the least weight. The walk-forward stage in this campaign checks whether one fixed, pre-registered rule holds consistently across chronological periods — it is not an out-of-sample generalization test: no parameter is refit per fold, and thresholds may be derived from the full-sample feature distribution (see the campaign's derivation-scope declaration). Treat every number as an upper bound on what live trading would deliver, before fees, slippage, and execution costs — none of which are modelled.*

## Mandatory reporting (RD-13 §C)

Effective sample size (N_eff) and cross-symbol correlation must be
reported alongside raw signalled counts.

---

## Required data

`open_interest__{BTC,ETH,SOL}__binance.csv` and
`mark_price__{BTC,ETH,SOL}__binance.csv` — already collected
(BTC 2021-01-01, ETH/SOL 2022-01-01 → 2026-07-29). **No new collection.**

## Results (FINAL)

**Status: CLOSED — all six experiments REJECTED on merit.**

Executed 2026-08-05, fixed clock `2026-08-05T00:00:00+00:00`, seed 7.
Governance decisions recorded through the frozen governance module
(reviewer ≠ researcher, evidence fingerprint verified) for all six.

| Experiment | Role | Signalled | Hit rate | mean_directional_return | Boot. frac ≥ bar | Verdict |
|---|---|---|---|---|---|---|
| `camp07-h72-t040-contrarian` | **PRIMARY** | 572 | **0.4878** | −0.002074 | 0.000 | **REJECTED** |
| `camp07-h72-t040-momentum` | **PRIMARY** | 572 | **0.5122** | +0.002074 | 0.036 | **REJECTED** |
| `camp07-h72-t025-contrarian` | robustness-threshold | 1,035 | 0.4986 | −0.001572 | 0.000 | **REJECTED** |
| `camp07-h72-t025-momentum` | robustness-threshold | 1,035 | 0.5014 | +0.001572 | 0.000 | **REJECTED** |
| `camp07-h120-t040-contrarian` | robustness-horizon | 333 | 0.4775 | −0.001335 | 0.005 | **REJECTED** |
| `camp07-h120-t040-momentum` | robustness-horizon | 333 | 0.5225 | +0.001335 | 0.152 | **REJECTED** |

Stage results were identical across all six: **causality/leakage audit
PASSED** (no look-ahead detected), single-pass FAILED, walk-forward
FAILED, regime stratification FAILED.

Pooled non-overlapping samples: **1,664** at 72h, **988** at 120h.

### Mandatory reporting — N_eff and cross-symbol correlation (RD-13 §C)

Cross-symbol correlation of the centered percentile-rank feature
(grid-independent daily series, n = 1,641 common dates):

| Pair | r |
|---|---|
| BTC–ETH | +0.396 |
| BTC–SOL | +0.194 |
| ETH–SOL | +0.299 |
| **mean ρ̄** | **+0.296** → **N_eff = 1.88 of 3 symbols**, haircut ×0.628 |

At 120h, measured directly on the aligned sample grid (n = 305):
ρ̄ = +0.301, N_eff = 1.87 — consistent. Lag-1 autocorrelation on the
120h sample grid: BTC +0.357, ETH +0.518, SOL +0.541.

**Effective signalled samples after the cross-symbol haircut:**

| Configuration | Raw | Effective | vs floor 100 |
|---|---|---|---|
| 72h / 0.40 (PRIMARY) | 572 | **≈359** | clears 3.6× |
| 72h / 0.25 | 1,035 | ≈650 | clears 6.5× |
| 120h / 0.40 | 333 | ≈209 | clears 2.1× |

**This campaign was genuinely well-powered.** Unlike Campaign 06
(deferred at N_eff 1.14 with effective per-fold samples of 40 against a
floor of 100), Campaign 07's effective sample size clears the floor by
2–6×. **These are merit rejections, not power failures.**

### Final verdict

All six experiments **REJECTED**. Hit rates span **0.4775–0.5225** — the
same coin-flip cluster every prior campaign produced. Only three
independent measurements exist (each contrarian/momentum pair sums to
exactly 1.0000, as pre-registered): **0.4878/0.5122**, **0.4986/0.5014**,
**0.4775/0.5225**.

**The horizon hypothesis is falsified.** Extending the forward-return
window from 24h to 72h and 120h — the one dimension every prior campaign
held fixed — does not rescue OI extremeness. Neither does relaxing
selectivity from CAMP-01's rank ≥0.99 to ≥0.90 or ≥0.75.

### Honest limitation found during execution

The 120h robustness arm was **marginal on power**: one walk-forward fold
returned 93 signalled samples, below the 100 floor (the pre-execution
feasibility census projected a worst fold of 107; the live run applies
the regime labeler and drops a few samples). It failed on hit rate
regardless, so the verdict is unaffected — but the arm should be read as
power-marginal, and the 72h PRIMARY result carries the campaign.
