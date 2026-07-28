# Research Campaign 04 — Funding Delta (change in funding)

**Status: PRE-REGISTERED — locked, no experiment run yet.**

Follows Campaign 03 (Funding Rate, venue-relative threshold — closed,
REJECTED). Campaign 04 tests a genuinely different **mechanism** within
the Funding family: the *change* in funding between consecutive
settlements (a shock / rate-of-change feature), not its level or its
persistence. Per the hypothesis-vs-implementation rule
(`RESEARCH_PLAYBOOK.md` §1), delta uses a different feature — not a
re-parameterization of level — so it is a new hypothesis, not a barred
retry.

**Funding Persistence was evaluated first and DEFERRED** (outcome-blind
feasibility: effective sample size N_eff ≈ 4–18 due to intrinsic
within-run autocorrelation ≈ 0.98; negative-persistence tail absent).
Funding Delta was then evaluated by the identical outcome-blind method
and **passed** — differencing removes the ramp autocorrelation
(N_eff ≈ 247–526), restores sign symmetry, and is rank-orthogonal to
level on Binance. See §1.

## 0. Existing infrastructure reused (unchanged)

`alpha_engine.validation` (all five stages), `alpha_engine.governance`,
`alpha_engine.registry`, `alpha_engine.research.run_research_cycle`, the
`funding_rate_threshold_rule` candidate **mechanism** (signed threshold +
direction convention — fed the delta feature value; the mechanism is
feature-agnostic), `alpha_engine.historical` (both venues' funding +
Binance mark price, already collected), and the Campaign-02/03
`build_samples` / regime labeler pattern. Genuinely new: the
**`funding_delta` feature** (first-difference of consecutive funding
settlements) and a Campaign-04 harness.

## 1. Mandatory pre-registration feasibility review (outcome-blind)

Performed via scratchpad feature-only analysis (funding series + trailing
BTC mark-price for regime labels; **no forward returns**). Feature:
`funding_delta[T] = funding[T] − funding[prev settlement]`, computed
point-in-time, sampled on the 24h non-overlapping grid (latest delta
≤ T, tolerance 8h).

**Distinctness from level [VERIFIED]:** |delta| vs |level| Pearson
0.38–0.51; **Spearman −0.11 to +0.06 (Binance — rank-orthogonal)**,
0.49–0.60 (Hyperliquid). Delta is genuinely distinct (Binance
rank-independent of level); the Pearson is a scale artifact.

**Statistical viability [VERIFIED]:** raw-delta lag-1 autocorrelation is
**negative** (−0.12 to −0.34; deltas mean-revert). Daily-grid |delta|
lag-1 autocorrelation 0.02–0.38 → **N_eff ≈ 247–526** (vs. persistence's
4–18). Viable.

**Sign symmetry [VERIFIED]:** positive/negative deltas balanced
(~33–37% each); both directions testable (unlike persistence).

**Threshold / per-fold feasibility [VERIFIED]:** |delta| is continuous
(exact-ties at any percentile = 0 — no clamped plateau, unlike CAMP-03's
level threshold). Per-venue percentile sweep of |delta|, per-fold
signalled counts under the **real chronological split**:

| Percentile | Binance n_folds=3 | Hyperliquid n_folds=3 | Both ≥100/fold? |
|---|---|---|---|
| p75 | [146, 134, 124] | [140, 186, 124] | **YES** |
| p80 | [112, 114, **96**] | [119, 152, **96**] | No |
| p90 | [56, 66, 38] | [60, 68, 41] | No |

n_folds=5 is infeasible on Binance at any extreme percentile (a fold
falls below 100 even at p60). **p75 is the most-extreme percentile that
satisfies the ≥100-per-fold floor on both venues at n_folds=3** — locked
below. This threshold/fold selection was made entirely from the
outcome-blind counts above; zero outcome data was examined.

## 2. Pre-registration (LOCKED)

### Parameters fixed FROM FEASIBILITY (this campaign, outcome-blind)

| Field | Value |
|---|---|
| Feature | **`funding_delta`** — first difference of consecutive funding settlements, point-in-time (uses only settlements ≤ T); sampled as the delta of the latest settlement ≤ sample time |
| Threshold methodology | Per-venue **75th percentile of \|funding_delta\|**, derived from that venue's own full historical \|delta\| distribution (zeros included) — venue-relative |
| Threshold value — Binance | **0.00005239** |
| Threshold value — Hyperliquid | **0.00001205** |
| Walk-forward folds | **`n_folds = 3`** (max fold count clearing ≥100 signalled/fold at p75 on both venues; n_folds=5 infeasible on Binance) |
| Zero-delta rule | Zeros are **included** in the percentile base (honest full distribution) and are **non-signals by construction** (\|0\| < threshold) — no separate exclusion step |

### Parameters fixed BY PRIOR METHODOLOGY (constant across campaigns)

| Field | Value |
|---|---|
| Candidate mechanism | `funding_rate_threshold_rule` (signed threshold + direction convention), fed the `funding_delta` value |
| Signed application | `delta > +threshold` → extreme up-shock; `delta < −threshold` → extreme down-shock; direction set by convention |
| Universe | BTC, ETH, SOL |
| Holding horizon | 24 hours |
| Sample spacing | 24 hours, non-overlapping |
| Cadence | 86,400 seconds |
| `min_hit_rate` | 0.55 |
| `min_signaled_samples` | 100 |
| Bootstrap | `n_resamples = 1000`, `seed = 7` |
| Regime stratification | BTC bull/bear/chop, price-derived labeler (reused unchanged) |
| Outcome source | Binance mark price (unchanged — price outcomes independent of funding source) |
| Venues | Binance screen + Hyperliquid replication, **each scored against its own venue-relative threshold** (no shared absolute threshold) |
| Direction conventions | **Two experiments registered separately: contrarian and momentum** |
| Determinism | Fixed clock + fixed seed |

### Two experiments (registered separately, never one tunable candidate)

- **Contrarian:** extreme up-shock (`delta > +threshold`) → SHORT; extreme
  down-shock → LONG. (A funding jump is an overreaction that reverts.)
- **Momentum:** extreme up-shock → LONG; extreme down-shock → SHORT. (A
  funding shock signals a continuing move.)

## 3. Declared limitations (from feasibility, outcome-blind)

1. **Moderate non-stationarity [VERIFIED]:** |delta| magnitude rose
   ~40–70% H1→H2; under a fixed full-sample threshold, later folds signal
   somewhat more than earlier ones.
2. **~70% bull-regime concentration [VERIFIED]:** high-|delta|
   observations are 71% (Binance) / 69% (Hyperliquid) bull — a regime
   confound the stratification stage must scrutinize. (Milder bear/chop
   representation than persistence, but still bull-heavy.)
3. **Residual level correlation [VERIFIED]:** delta is rank-orthogonal to
   level on Binance (Spearman ≈0) but moderately correlated on Hyperliquid
   (Spearman ~0.5) — a Hyperliquid positive would carry a mild
   level-confound.
4. **High zero-delta mass [VERIFIED]:** ~30% (Binance) / ~40%
   (Hyperliquid) of settlements show no change (clamped/repeated funding);
   zeros are non-signals, lowering the effective signalling rate.
5. **Reduced fold count [VERIFIED]:** `n_folds = 3` (not the standard 5)
   to satisfy per-fold sample adequacy — fewer, larger walk-forward folds.
6. **Residual sampling autocorrelation [VERIFIED]:** daily |delta| lag-1
   0.02–0.38 (N_eff 247–526) — far better than persistence, not zero;
   signalled samples retain mild dependence.
7. **DEX-first [VERIFIED]:** Binance is a research screen only; Hyperliquid
   is the production-venue replication. A Binance-only positive is never
   promotion-eligible.

## 4. Acceptance criteria (a direction is SUPPORTED only if ALL hold, per venue)

- Single-pass hit rate ≥ 0.55 **and** signalled ≥ 100.
- Causality audit passes (no duplicate, ordering violation, or
  non-verifiable sample).
- Walk-forward: every one of the 3 folds clears its own bar
  (hit rate ≥ 0.55 and signalled ≥ 100 per fold).
- Regime stratification: the edge is **not** concentrated in a single
  regime (holds across regimes, not bull-only).
- Bootstrap: the hit-rate distribution is consistent with clearing the
  0.55 bar (not straddling 0.50).
- Mean directional return > 0.

## 5. Rejection criteria (any one rejects)

Single-pass below the bar; causality failure; walk-forward fails in the
majority of folds; edge concentrated in a single regime only; bootstrap
straddles 0.50 inconsistent with the bar; mean directional return ≤ 0.
**Venue-replication rule:** a positive Binance screen is not
promotion-eligible until replicated on Hyperliquid under Hyperliquid's own
locked threshold (0.00001205), with no retuning.

**No parameter above may be adjusted after any outcome is observed.** Each
venue is an independent test under its own locked threshold; a
disappointing venue result is recorded, never retuned.

---

*(Sections 6 onward — machinery validation, dataset, results, governance,
lessons learned — appended as the campaign executes.)*
