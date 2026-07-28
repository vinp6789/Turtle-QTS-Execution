# Research Campaign 05 — Open Interest Velocity

**Status: PRE-REGISTERED — locked, no experiment run yet.**

Tests a genuinely new mechanism in the Open Interest family: the *rate of
change* of OI (build-up / unwind velocity), distinct from the rejected OI
*level* (CAMP-01). Per the hypothesis-vs-implementation rule
(`RESEARCH_PLAYBOOK.md` §1), velocity uses a different feature — not a
re-parameterization of level — so it is a new hypothesis.

**Governance ceiling — DEFER, not APPROVE (read first).** Open Interest
has **no Hyperliquid historical source** (`docs/HISTORICAL_DATA.md` §1),
so per `RESEARCH_PLAYBOOK.md` §5 this hypothesis **cannot be APPROVED** —
its terminal governance state is **REJECT or DEFER only**. A positive
result is validated *knowledge*, never a promotable alpha, until a live
OI recorder accumulates Hyperliquid-native history. This is a
single-venue (Binance) knowledge campaign by construction; there is no
Hyperliquid replication step (none is possible).

## 0. Existing infrastructure reused (unchanged)

`alpha_engine.validation` (all five stages), `alpha_engine.governance`,
`alpha_engine.registry`, `alpha_engine.research.run_research_cycle`, the
`funding_rate_threshold_rule` candidate **mechanism** (signed threshold +
direction convention — feature-agnostic), `alpha_engine.historical`
(Binance OI + mark price, already collected), and the Campaign-02/03/04
`build_samples` / regime-labeler pattern. Genuinely new: the `oi_velocity`
feature (24h fractional OI change) and a Campaign-05 harness.

## 1. Mandatory pre-registration feasibility review (outcome-blind) — PASSED

Feature = `oi_velocity[T] = OI(latest ≤ T) / OI(latest ≤ T−24h) − 1`
(fractional / scale-free — required because CAMP-01 verified raw OI is
strongly non-stationary; a raw delta would inherit that non-stationarity).
Sampled on the 24h non-overlapping grid. Measured outcome-blind (Binance
OI on disk, no forward returns):

| Axis | Result |
|---|---|
| Distinctness from OI level (30d %-rank) | \|vel\|~rank Pearson 0.08–0.12, Spearman 0.05–0.13 — nearly independent (cleanest distinctness tested) |
| Autocorrelation / N_eff | daily lag-1 −0.003 to 0.125 → **N_eff ≈ 405–523** |
| Sign symmetry | ~50/50 build-up vs unwind (both directions testable) |
| Stationarity | \|vel\| p50 0.020→0.021, p90 0.056→0.068 (H1→H2) — stable |
| Threshold feasibility | **p75 / n_folds=3** → per-fold [169,113,108], all ≥100 (p80, n_folds=5 infeasible) |
| Regime coverage | 57% bull at p75 (bear/chop well-represented) |

**Verdict: PASS.** Viable, distinct, well-powered.

## 1a. Outlier / data-validity investigation (outcome-blind) — LOCKED RULE

Investigation of the extreme \|velocity\|≈1.0 observations [VERIFIED]:
every one is a single **OI = 0.0** reading at the 00:00 daily boundary,
surrounded by normal values (e.g. BTC 2024-07-14: 85453 → 0.0 → 85645;
ETH 2024-07-11: 914092 → 0.0 → 914566). OI **cannot be zero while the
instrument trades** — these are **impossible values from missing/corrupt
archive snapshots**, not genuine market events, not rollover, not
exchange-methodology. The archive contains hundreds of exact-zero OI
values (BTC 317, ETH 63, SOL 50). The next-largest velocities (≤0.24,
smooth neighbourhoods) are **genuine deleveraging/build-up events** and
are retained.

**LOCKED, PERMANENT OI DATA-VALIDITY RULE (no future OI campaign may
modify it):** an `oi_velocity` sample at time T is constructed **only if
both** the current OI observation (latest ≤ T) **and** the prior OI
observation (latest ≤ T−24h) are **strictly positive (> 0)**. If either
is ≤ 0, the sample is **skipped** (never fabricated, never clamped),
counted in diagnostics as `skip_nonpositive_oi`. The rule filters on
**data validity**, not on velocity magnitude, so it removes exactly the
impossible values without touching any genuine move. Effect (measured):
5 samples skipped; max \|velocity\| drops 1.000 → 0.2405; per-fold counts
and threshold unchanged.

## 2. Pre-registration (LOCKED)

### Parameters fixed FROM FEASIBILITY (this campaign, outcome-blind)

| Field | Value |
|---|---|
| Feature | **`oi_velocity`** — 24h fractional OI change, point-in-time, both endpoints OI > 0 (data-validity rule §1a) |
| Threshold | **0.037901** — 75th percentile of \|oi_velocity\|, pooled BTC/ETH/SOL, from the OI>0-filtered distribution |
| Walk-forward folds | **`n_folds = 3`** (max clearing ≥100 signalled/fold at p75; n_folds=5 infeasible) |
| Outlier / data-validity rule | OI > 0 on both endpoints, else skip (§1a — locked, permanent) |

### Parameters fixed BY PRIOR METHODOLOGY (constant across campaigns)

| Field | Value |
|---|---|
| Candidate mechanism | `funding_rate_threshold_rule` (signed threshold + direction convention), fed the `oi_velocity` value |
| Signed application | `velocity > +threshold` → extreme build-up; `velocity < −threshold` → extreme unwind; direction set by convention |
| Universe | BTC, ETH, SOL |
| Venue | Binance only (no Hyperliquid OI history — single-venue by necessity; DEFER-ceiling) |
| Holding horizon | 24 hours |
| Sample spacing | 24 hours, non-overlapping |
| Cadence | 86,400 seconds |
| `min_hit_rate` | 0.55 |
| `min_signaled_samples` | 100 |
| Bootstrap | `n_resamples = 1000`, `seed = 7` |
| Regime stratification | BTC bull/bear/chop, price-derived labeler (reused unchanged) |
| Outcome source | Binance mark price (unchanged) |
| Direction conventions | **Two experiments registered separately: contrarian and momentum** |
| Determinism | Fixed clock + fixed seed |

### Two experiments (registered separately)

- **Contrarian:** extreme build-up (`velocity > +threshold`) → SHORT;
  extreme unwind → LONG. (Fast OI build-up = over-extension that reverts.)
- **Momentum:** extreme build-up → LONG; extreme unwind → SHORT. (Fast OI
  change confirms a developing move.)

## 3. Declared limitations

1. **DEFER-ceiling (governance):** no Hyperliquid OI → cannot be APPROVED
   (`RESEARCH_PLAYBOOK.md` §5); terminal state REJECT or DEFER only. The
   evidence package's `known_limitations` must state this explicitly.
2. **Single-venue:** no venue replication is possible; a positive result
   is CEX-only knowledge, not venue-validated.
3. **~70% bull-regime tilt** at p75 (57% bull, with bear/chop present) —
   a regime confound the stratification stage scrutinizes.
4. **Single 18-month window** — all conclusions conditional on it.
5. **OI archive data-quality:** hundreds of exact-zero snapshots exist;
   the §1a rule excludes them deterministically.

## 4. Acceptance criteria (a direction is SUPPORTED only if ALL hold)

- Single-pass hit rate ≥ 0.55 **and** signalled ≥ 100.
- Causality audit passes.
- Walk-forward: every one of the 3 folds clears its own bar.
- Regime stratification: edge not concentrated in a single regime.
- Bootstrap: hit-rate distribution consistent with clearing 0.55.
- Mean directional return > 0.

**Even if all hold, the terminal governance state is DEFER, not APPROVE**
(§3.1) — "SUPPORTED" here means "validated knowledge, promotion-blocked."

## 5. Rejection criteria (any one rejects)

Single-pass below bar; causality failure; walk-forward fails in the
majority of folds; single-regime concentration; bootstrap straddles 0.50
inconsistent with the bar; mean directional return ≤ 0.

## 6. Reviewer requirements

Governance decision recorded with `proposed_by != reviewed_by`
(structurally enforced) and evidence-fingerprint match. The reviewer must
additionally confirm the DEFER-ceiling is honored — a passing result is
recorded as **DEFER**, never APPROVE, and the `known_limitations` state
the no-Hyperliquid-OI blocker (`RESEARCH_PLAYBOOK.md` §5).

**No parameter above may be adjusted after any outcome is observed.**

---

## 7. Machinery validation (2-month in-memory slice, 2023-07..2023-09)

Verified before full-depth execution, on the same slice Campaigns 02–04
used: PIT sample construction (93 grid points → 93 built, zero skips on
the clean slice), causality audit **passed**, all five stages present,
evidence sealed (fingerprint `4d03f53d74c06c81…`), and the **DEFER-ceiling
exercised directly** — forcing the cleared-all-stages branch emitted
`DEFERRED`, never `APPROVED`. Unit tests
(`tests/test_research_campaign_05_build_samples.py`, 17/17 passing) cover
PIT correctness, no-look-ahead, non-overlap, fractional-change
arithmetic, the OI>0 rule and its diagnostic, determinism, the
spacing/horizon guard, and feature identity. Machinery confirmed sound;
proceeded to full execution with zero changes to the locked
specification.

## 8. Dataset (full execution)

BTC/ETH/SOL, Binance Open Interest + Binance mark price, 2023-07-01 →
2024-12-31 (already collected; no new collection). Pooled non-overlapping
daily samples: **1,555** from 1,560 grid points. The locked OI>0
data-validity rule (§1a) fired exactly as pre-registered:
**`skip_nonpositive_oi` = 5** (BTC 3, ETH 2, SOL 0) — every skip an
impossible zero-OI archive snapshot, none fabricated or clamped. Maximum
\|velocity\| after the rule: **0.2405** (vs. 1.000 unfiltered).

## 9. Results

### 9.1 Combined universe (pre-registered, powered analysis)

| Experiment | Signalled | Hit rate | Mean dir. return | single-pass | causality | walk-fwd | regime | Verdict |
|---|---|---|---|---|---|---|---|---|
| contrarian | 390 | 0.5154 | +0.00250 | FAIL | PASS | FAIL | FAIL | **REJECTED** |
| momentum | 390 | 0.4846 | −0.00250 | FAIL | PASS | FAIL | FAIL | **REJECTED** |

### 9.2 Per-symbol (diagnostic only — not governance-bearing)

| Symbol | Direction | Signalled | Hit rate | single-pass | Verdict |
|---|---|---|---|---|---|
| BTC | contrarian | 108 | **0.5556** | **PASS** | REJECTED |
| BTC | momentum | 108 | 0.4444 | FAIL | REJECTED |
| ETH | contrarian | 107 | 0.5140 | FAIL | REJECTED |
| ETH | momentum | 107 | 0.4860 | FAIL | REJECTED |
| SOL | contrarian | 175 | 0.4914 | FAIL | REJECTED |
| SOL | momentum | 175 | 0.5086 | FAIL | REJECTED |

BTC contrarian cleared single-pass in isolation (0.5556, 108 signalled)
but is an underpowered per-symbol slice, not the pre-registered analysis;
it is recorded as a diagnostic reading only and was **not** acted on.

### 9.3 Walk-forward (combined, n_folds=3)

Per-fold signalled counts **[169, 113, 108]** — reproducing the
pre-registered feasibility projection exactly, with **every fold clearing
the 100-sample floor.** Walk-forward therefore failed on **hit-rate merit
per fold**, not on sample starvation:

| Fold | Signalled | Contrarian hit | Momentum hit |
|---|---|---|---|
| 1 | 169 | 0.526 | 0.473 |
| 2 | 113 | 0.495 | 0.504 |
| 3 | 108 | 0.518 | 0.481 |

No fold, in either direction, reached the 0.55 bar.

### 9.4 Bootstrap resampling (combined, 1,000 resamples, seed 7)

| Experiment | Mean hit rate | Observed range | Fraction meeting 0.55 |
|---|---|---|---|
| contrarian | 0.5147 | 0.435 – 0.594 | **0.079** |
| momentum | 0.4852 | 0.406 – 0.565 | **0.009** |

Both distributions centre near 0.50 and rarely clear the pre-registered
bar.

### 9.5 Regime stratification (combined)

| Regime | Signalled | Contrarian hit | Momentum hit |
|---|---|---|---|
| bull | 224 | 0.535 | 0.464 |
| chop | 95 | 0.473 | 0.526 |
| bear | 71 | 0.507 | 0.492 |

No regime cleared the bar in either direction. Notably the failure is by
**even, edgeless spread across all three regimes** (57% bull, with bear
and chop both well represented) — not by the single-regime concentration
that drove CAMP-02's rejection.

### 9.6 Verdict

**Both directions REJECTED.** Neither reached the 0.55 single-pass bar
(0.5154 / 0.4846); walk-forward failed on merit with every fold fully
powered; bootstrap cleared the bar in 0.9–7.9% of resamples; no regime
carried an edge. Causality passed for all experiments (no leakage).

## 10. Evidence fingerprints

| Experiment | Fingerprint |
|---|---|
| Combined contrarian | `ccc56cd026521f56b29db92f9231ecebdb5ca5f15e78384745f62e469f8ce9e1` |
| Combined momentum | `6fbce5305a663a32ead901e363ffd19e605bd582abe04035d0f179ebce9039aa` |

All sealed and durably recorded; causality audit passed for both.

## 11. Governance decisions

**REJECT** recorded for both combined experiments
(`proposed_by="researcher-campaign05"` ≠ `reviewed_by="reviewer-campaign05"`,
evidence-fingerprint verified) — durable lifecycle state **`REJECTED`**.

The **DEFER-ceiling was not exercised** because neither experiment
cleared all stages: REJECT is the correct terminal state for a failed
hypothesis, and DEFER applies only to a passing-but-unpromotable result.
APPROVE remained **unreachable by construction** throughout — the
harness constructs only `REJECT` or `DEFER`
(`research/campaign_05_oi_velocity/run_campaign.py`), never `APPROVE`,
per `RESEARCH_PLAYBOOK.md` §5.

## 12. Lessons learned

1. **A feature can be statistically excellent and still carry no edge.**
   OI Velocity passed every feasibility axis more cleanly than any prior
   feature (near-independence from level, N_eff 405–523, sign-symmetric,
   stationary, continuous threshold, balanced regimes) and still produced
   a flat rejection. Feasibility quality predicts *testability*, never
   *profitability* — the two are independent, and the program should not
   read a strong feasibility as a favourable prior.
2. **The fractional transform worked as designed.** Converting OI's
   non-stationary level (CAMP-01: ~3.4× secular growth) into a 24h
   fractional change produced a stationary, scale-free feature —
   confirming the CAMP-01 lesson that OI must be normalized, and
   generalizing it: *fractional* change is the correct normalization for
   a non-stationary level series.
3. **A data-validity filter is the right instrument for impossible
   values.** Filtering on OI > 0 (validity) rather than on velocity
   magnitude (outlier size) removed exactly the 5 corrupt snapshots while
   retaining every genuine move up to 0.2405 — a deterministic,
   pre-registered rule that required no judgment at execution time.
4. **The per-fold feasibility projection is now reproducible in
   execution.** The locked [169, 113, 108] projection was reproduced
   exactly, so walk-forward failed on merit rather than on the structural
   sample-floor artifact that confounded CAMP-02 and partially CAMP-03.
   The CAMP-02/03-derived feasibility discipline is fully effective.
5. **Regime-balanced failure is a stronger negative result than
   concentrated failure.** Unlike CAMP-02 (93.6% bull), this rejection
   holds across bull, chop, and bear with comparable per-regime hit
   rates, so it cannot be attributed to a single market condition.

## 13. Recommendation for the next campaign

Open Interest *level* (CAMP-01) and *velocity* (this campaign) are both
rejected; **Divergence** remains the sole untested OI mechanism, subject
to the same standing DEFER-ceiling (no Hyperliquid OI history). Per the
research operating model, the OI family's remaining value is
knowledge-only until a live OI recorder lifts that ceiling. See
`docs/RESEARCH_DECISIONS.md` for the current family state.
