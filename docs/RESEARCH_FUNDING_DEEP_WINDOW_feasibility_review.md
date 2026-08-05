# Funding Deep-Window Feasibility Review (Backlog 3.2)

**Verdict: DEFER.** No funding campaign is approved for pre-registration
on the current data, on either venue.

- **Date:** 2026-08-05 · **Author:** researcher · **Reviewer:** pending
- **Status:** complete — outcome-blind gate per `PROJECT_CONSTITUTION.md` §6
  and `RESEARCH_DECISIONS.md` RD-13 §C.
- **No campaign is pre-registered. No hypothesis tested. No return
  computed. No threshold tuned against a result.**

## 0. Scope and discipline

Reads **only** funding-rate series. The mark-price / outcome series was
never opened. Two questions, both mandated by the governing documents:

- **Q1 — RD-04 revisit.** RD-04 deferred **Funding Persistence** as
  statistically non-viable (daily-grid lag-1 ρ ≈ 0.94–0.99 → **N_eff ≈
  4–18**) on the then-18-month window, with an explicit revisit trigger:
  *"a materially longer data window."* Backlog 2.1 took Binance to 69.5
  months of 3-symbol-common coverage. **Trigger fired — so measure it.**
- **Q2 — ROADMAP §1.2.** *"BTC-only Funding momentum, properly powered"*
  is the strongest funding candidate not yet retried (CAMP-02 Binance
  n=35; CAMP-03 Hyperliquid n=138, both underpowered). Does the extended
  window clear `min_signaled_samples = 100` per fold?

Acceptance bar **unchanged**: `min_signaled_samples = 100` per fold;
`n_folds = 5` standard, `n_folds = 3` the precedented fallback (CAMP-03).

## 1. Runtime

**0.56s total** (load 0.24s, statistics 0.24s). Foreground, as with
Backlog 1.6. No infrastructure built.

## 2. Pre-flight assertions — 20/20 PASS

| Assertion | Result |
|---|---|
| `nonempty` × 6 | PASS — Binance 7,119/7,119/6,424; Hyperliquid 27,153 each |
| `ascending` × 6 | PASS |
| `unique` × 6 | PASS — 0 duplicate timestamps anywhere |
| `cadence[binance]` | PASS — modal 8h |
| `cadence[hyperliquid]` | PASS — modal 1h |
| `venue_overlap_nonempty` | PASS — 2023-07-01..2026-06-30, **1,096 days** |
| `hyperliquid_current` | PASS — last settlement 0.03 days ago (Backlog 3.1 confirmed) |
| `window_len` × 2 | PASS — Binance 2,117 common days; Hyperliquid 1,132 |

**Coverage and windows**

| Venue | Common 3-symbol window | Span |
|---|---|---|
| Binance | 2020-09-13 → 2026-06-30 | **2,117 days (69.5 months)** |
| Hyperliquid | 2023-07-01 → 2026-08-05 | **1,132 days (37.2 months)** |
| **Venue overlap** | 2023-07-01 → 2026-06-30 | **1,096 days** — the ceiling on any DEX-first replication |

**Methodology validation:** the Binance p75 threshold measured here is
**0.00010000**, reproducing CAMP-03's published Binance p75 of
`0.0001000000` exactly. The venue-relative derivation is consistent with
the closed campaign record.

## 3. Q1 — RD-04 Funding Persistence revisit

Feature exactly as RD-04 defined it: **elapsed hours since the funding
rate last changed sign**, sampled on a daily grid. `N_eff = N(1−ρ₁)/(1+ρ₁)`
— the same form RD-04 used to obtain 4–18.

| Venue | Symbol | N (days) | lag-1 ρ₁ | **N_eff** | neg. runs (median) |
|---|---|---|---|---|---|
| Binance | BTC | 2,117 | +0.9831 | **18.1** | 482 (8.0h) |
| Binance | ETH | 2,117 | +0.9868 | **14.1** | 486 (8.0h) |
| Binance | SOL | 2,117 | +0.9847 | **16.3** | 591 (16.0h) |
| Hyperliquid | BTC | 1,132 | +0.9366 | **37.1** | 785 (2.0h) |
| Hyperliquid | ETH | 1,132 | +0.9334 | **39.0** | 955 (2.0h) |
| Hyperliquid | SOL | 1,132 | +0.9707 | **16.9** | 1,094 (2.0h) |

**Every value remains far below the floor of 100.**

### 3.1 The central finding: the revisit trigger was based on a false premise

RD-04 measured N_eff ≈ 4–18 on ~540 days and inferred that *more data*
would fix it. The window has since grown **3.9×** (540 → 2,117 days on
Binance). N_eff went from ≈4–18 to **14.1–18.1** — essentially
unchanged.

The reason is visible in the measurement: **autocorrelation rose as the
window grew**, from ρ ≈ 0.94–0.99 to ρ ≈ 0.983–0.987 on Binance. Because
`N_eff = N(1−ρ₁)/(1+ρ₁)`, a 3.9× increase in N against a rise in ρ from
0.94 to 0.983 very nearly cancels:

- N=540, ρ=0.94 → N_eff ≈ 16.7
- N=2,117, ρ=0.983 → N_eff ≈ 18.1

**Quadrupling the data bought roughly +8% effective sample size.** This
is not a data-quantity problem. "Elapsed time since sign flip" is a
slowly-varying state variable whose serial dependence scales with the
observation window; collecting more of it adds calendar time, not
independent information.

**One RD-04 concern is relieved, and it does not change the conclusion.**
RD-04 also noted negative-persistence runs were "near-absent (median
duration 0–1h)". On the longer window they are plainly present — 482–591
negative runs on Binance (median 8–16h), 785–1,094 on Hyperliquid
(median 2h). The direction-asymmetry objection no longer holds; the
N_eff objection is decisive on its own.

**RD-04's own remedy is already exhausted.** RD-04 recorded a durable
lesson: *"differencing converts a within-run-ramp (low-information,
high-autocorrelation) feature into a high-information, low-autocorrelation
one."* That remedy was applied — it became **Funding Delta, Campaign 04,
which was REJECTED** on well-powered evidence. The natural fix for
persistence has therefore already been tried and failed on its own merits.

## 4. Cross-symbol dependence (RD-13 §C, mandatory)

Daily |funding|:

| Venue | BTC–ETH | BTC–SOL | ETH–SOL | mean ρ̄ | **N_eff symbols** | haircut |
|---|---|---|---|---|---|---|
| Binance | +0.863 | +0.378 | +0.429 | +0.557 | **1.42** of 3 | ×0.473 |
| Hyperliquid | +0.503 | +0.386 | +0.476 | +0.455 | **1.57** of 3 | ×0.524 |

Materially *weaker* than the liquidation family's ρ̄ = +0.818 (RD-16), so
pooling across symbols is less punitive here. It is reported because
RD-13 §C requires it; **it does not drive this verdict**, because Q2's
candidate is BTC-only and therefore takes no cross-symbol haircut.

## 5. Q2 — BTC-only funding momentum vs the floor

Thresholds are percentiles of **that venue's own** |funding| distribution
(Constitution §6). BTC-only ⇒ no pooling ⇒ no cross-symbol haircut.

| Venue | Threshold | folds | total signalled | worst fold | mean | Clears 100? |
|---|---|---|---|---|---|---|
| Binance | p75 | 3 | 986 | **140** | 328.7 | **YES** |
| Binance | p75 | 5 | 986 | 46 | 197.2 | no |
| Binance | p90 | 3 | 212 | 6 | 70.7 | no |
| Binance | p90 | 5 | 212 | 0 | 42.4 | no |
| **Hyperliquid** | **p75** | **3** | **283** | **20** | **94.3** | **no** |
| Hyperliquid | p75 | 5 | 283 | 12 | 56.6 | no |
| Hyperliquid | p90 | 3 | 114 | 2 | 38.0 | no |
| Hyperliquid | p90 | 5 | 114 | 0 | 22.8 | no |

Moving-block bootstrap (b=7d, n=1000, seed=7):

| Config | mean | 90% CI | P(≥100) |
|---|---|---|---|
| binance p75 folds3 | 329.1 | [283, 375] | **1.00** |
| binance p75 folds5 | 196.9 | [159, 235] | 1.00 |
| binance p90 folds3 | 71.0 | [45, 101] | 0.06 |
| **hyperliquid p75 folds3** | **93.2** | **[68, 121]** | **0.35** |
| hyperliquid p75 folds5 | 56.2 | [37, 76] | 0.00 |
| hyperliquid p90 folds3 | 37.6 | [22, 55] | 0.00 |

### 5.1 The binding constraint is venue transfer, not raw power

**Binance is now adequately powered** at p75/n_folds=3 — 140 worst-fold,
bootstrap P(≥100) = 1.00. The deep-history backfill did its job.

**Hyperliquid is not, at any configuration.** Its best case is
p75/n_folds=3 at 20 worst-fold (mean 94.3), with only a 0.35 bootstrap
probability of clearing even on a mean basis.

Constitution §6 is explicit: a centralized-exchange source *"may be used
to reach statistical power, but a positive finding is a research
hypothesis only until it is replicated — same locked specification, no
re-tuning — against Hyperliquid's own historical data… A finding that
exists only on CEX data is never promotion-eligible."*

So a BTC-only funding campaign could be *run* on Binance but could not
complete its promotion path. That is the same **DEFER-ceiling** shape as
Campaigns 01 and 05.

**Backlog 3.1 cannot be repeated to fix this.** Hyperliquid funding now
starts 2023-07-01, at the venue's own coverage boundary — there is no
earlier data to collect. Hyperliquid depth grows only forward, in real
time.

### 5.2 A measured non-stationarity worth recording

The Hyperliquid p75 threshold measured here is **0.00001507**, against
CAMP-03's published Hyperliquid p75 of **0.000038592350** on its
18-month window — typical funding magnitude has **compressed ~2.6×** as
the window extended. A full-sample venue-relative threshold is therefore
not stable across this window. This is an instance of the impurity RD-11 E
already names (outcome-blind full-sample derivation is a recorded
methodological impurity, not a demonstrated bias) and must be declared
under RD-11 A by any campaign that uses a full-sample threshold here.

Note also the fold imbalance on Hyperliquid: worst fold 20 against a mean
of 94.3 — signals are strongly concentrated in time, which is a
regime-coverage concern independent of the count shortfall.

## 6. Interpretation — why this differs from prior expectation

`ROADMAP.md` §1.2 anticipated that the deep-history backfill would make
BTC-only funding momentum *"properly powered."* The measurement shows
that expectation was **half right, and the wrong half mattered**:

- It **did** deliver Binance power (worst fold 140 vs 100 floor, from
  CAMP-02's n=35).
- It did **not** — and structurally could not — deliver Hyperliquid
  power, because Backlog 2.1 deepened Binance only, and Hyperliquid's own
  history cannot be extended backwards past its venue launch.

And the RD-04 revisit refutes its own trigger: more data does not rescue
a feature whose autocorrelation grows with the window.

## 7. Risks and limitations

- **Not a verdict on either mechanism.** Neither persistence nor
  BTC-only momentum was tested for edge. Both are **testability**
  failures. Recording either as REJECTED would enter a false negative
  into the permanent ledger.
- **Threshold grid is p75/p90 only**, following CAMP-02/03. A threshold
  below p75 would raise counts but degrade toward "signal on most days,"
  which is not a discriminating rule. No threshold was chosen after
  seeing an outcome, because no outcome was inspected.
- **Daily-grid sampling is an assumption**, matching RD-04. A finer grid
  would raise raw counts but, on this evidence, would also raise serial
  autocorrelation — the same trap RD-16 §E flagged for liquidations.
  It would need its own review.
- **`N_eff = N(1−ρ₁)/(1+ρ₁)` is a first-order AR(1) approximation**,
  used because it is the exact form RD-04 used, so the comparison is
  like-for-like. It is not exact for a non-AR(1) process.
- **The Binance/Hyperliquid overlap is 1,096 days**, so any replication
  study is bounded by that regardless of Binance's 2,117-day depth.

## 8. Recommendation

**DEFER.** Do not pre-register a funding campaign on the current data.

1. **Funding Persistence — defer, and correct RD-04's revisit trigger.**
   The "materially longer data window" trigger has been fired, tested,
   and **refuted by measurement**: 3.9× the data yielded +8% N_eff. The
   trigger should be replaced with a **feature-construction** trigger
   (a formulation whose N_eff does not degrade with window length),
   noting that RD-04's own proposed remedy — differencing — already ran
   as Campaign 04 and was rejected.
2. **BTC-only funding momentum — defer on venue transfer, not on power.**
   Binance clears at p75/n_folds=3; Hyperliquid does not, and cannot be
   deepened retroactively. Revisit trigger is **calendar-bound and
   measurable**: re-run this review when Hyperliquid's own history
   supports ≥100 worst-fold BTC-only signalled samples at p75/n_folds=3.
   At the observed rate (283 signalled over 1,132 days, worst fold 20),
   roughly **3–5× more Hyperliquid history** is required — i.e. several
   further years, accumulating only in real time.
3. **A knowledge-only Binance campaign is *possible* but is not
   recommended.** Campaigns 01 and 05 established the DEFER-ceiling
   precedent, so it would be legitimate. But RD-05 already records the
   funding family as **NEAR-EXHAUSTED** — level (CAMP-02, CAMP-03) and
   delta (CAMP-04) are all rejected on real data — and this would spend
   a full campaign on a variant that cannot be promoted even if it
   succeeds. Recorded as an option; the evidence does not support taking
   it.

**Do not** clear this gate by lowering `min_signaled_samples`, by
choosing a threshold below p75 to raise counts, by dropping the
venue-transfer requirement, or by treating Binance-only power as
sufficient.

## 9. Final verdict

> **DEFER.**
> **Funding Persistence:** N_eff = 14.1–18.1 (Binance) / 16.9–39.0
> (Hyperliquid) against a floor of 100 — essentially unchanged from
> RD-04's 4–18 despite 3.9× more data, because lag-1 autocorrelation
> rose from ~0.94 to ~0.985 as the window grew. The "more data" revisit
> trigger is refuted by measurement.
> **BTC-only funding momentum:** Binance now clears (worst fold 140,
> P(≥100) = 1.00) but Hyperliquid does not at any configuration (best
> worst-fold 20, P = 0.35), and Hyperliquid's history cannot be extended
> backwards. Under Constitution §6 the finding could never become
> promotion-eligible.
> Both mechanisms remain **untested, not rejected**.

---

**Artifacts:**
`research/funding_deep_window_feasibility/feasibility_review.py` ·
`data/alpha_engine_research/funding_deep_window_feasibility/feasibility_statistics.json`
