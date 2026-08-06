# RESEARCH_BACKLOG.md — the executable research program

Companion to [`MECHANISMS.md`](MECHANISMS.md), which holds the master
table. This document holds the **power audit of the closed record**, the
**ranked backlog**, the **twelve-month plan**, and the **gates every
campaign passes before implementation**.

Evidence tags: `[M]` measured here · `[R]` repository/record fact ·
`[E]` external literature · `[I]` inference.

**Relationship to RD-02.** RD-02 forbids numeric success forecasts in
artifacts that *order campaigns*. §2 below contains probability estimates
because they were explicitly requested. They are scoped so they cannot
contaminate science: **no threshold, bar, direction, horizon or
acceptance criterion in any pre-registration may be derived from §2.** It
ranks what to *attempt*; it never touches what is *concluded*. RD-02's
concern — that a "3/5 alpha probability" label becomes an inherited prior
inside an outcome-blind pre-registration — is met by that boundary.

---

## 1 · Power audit of the closed record (Task 3)

Every closed configuration, re-scored through
[`alpha_engine/feasibility.py`](../alpha_engine/feasibility.py).
**History is not rewritten.** Every sealed evidence package, fingerprint,
governance decision and ledger entry stands exactly as recorded. This is
an annotation of what those results could have *meant*.

Inputs, all measured, none assumed:

- Mean |return| by horizon, Hyperliquid BTC/ETH/SOL 1h candles, 200-day
  window `[M]`: **1h 39.8 bp · 24h 218.8 bp · 72h 371.3 bp · 120h 444.1 bp**
- Fees, live from `/info userFees` on 2026-08-06 `[M]`: **taker 4.5 bp,
  maker 1.5 bp** (base tier, no discounts)
- Funding `[M]`: 5.10 %/yr verified 14/14 instruments → **1.40 bp/day**
- Slippage: **0.0 bp — never measured.** Every breakeven below is
  therefore a **lower bound** and every verdict is *optimistic*.
- Cross-symbol return correlation `[M]`: 1h +0.875 · 24h +0.689 (measured
  on the 2023-07→2024-12 window the campaigns used) · CAMP-07 +0.296 and
  CAMP-08 serial retention ×0.654 taken from those campaigns' own reviews

| Campaign | h | Raw signalled | ρ_hit | N_eff | MDE | Breakeven | Best hit rate | **Verdict** |
|---|---|---|---|---|---|---|---|---|
| CAMP-01 pctrank | 24 | 126 | +0.484 | 64 | 0.675 | 0.524 | 0.508 | UNDERPOWERED |
| CAMP-01 zscore | 24 | 167 | +0.484 | 85 | 0.652 | 0.524 | 0.503 | UNDERPOWERED |
| CAMP-02 Binance | 24 | 141 | +0.484 | 72 | 0.666 | 0.524 | 0.560 | UNDERPOWERED |
| CAMP-02 Hyperliquid | 24 | 9 | +0.484 | 5 | 1.155 | 0.524 | 0.667 | UNDERPOWERED |
| CAMP-03 Binance | 24 | 280 | +0.484 | 142 | 0.617 | 0.524 | 0.525 | UNDERPOWERED |
| CAMP-03 Hyperliquid | 24 | 461 | +0.484 | 234 | 0.592 | 0.524 | 0.532 | UNDERPOWERED |
| CAMP-04 Binance | 24 | 354 | +0.484 | 180 | 0.605 | 0.524 | 0.523 | UNDERPOWERED |
| CAMP-04 Hyperliquid | 24 | 450 | +0.484 | 229 | 0.593 | 0.524 | 0.511 | UNDERPOWERED |
| CAMP-05 | 24 | 390 | +0.484 | 198 | 0.600 | 0.524 | 0.515 | UNDERPOWERED |
| CAMP-06 *(deferred)* | 24 | 106 | +0.610 | 48 | 0.703 | 0.524 | — | UNDERPOWERED |
| CAMP-07 72h t040 | 72 | 572 | +0.191 | 414 | 0.569 | 0.518 | 0.512 | UNDERPOWERED |
| **CAMP-07 72h t025** | 72 | 1,035 | +0.191 | 749 | **0.551** | 0.518 | 0.501 | **DISPUTED** — flips to adequately powered under one-sided testing (MDE 0.545) |
| CAMP-07 120h | 120 | 333 | +0.191 | 241 | 0.590 | 0.518 | 0.523 | UNDERPOWERED |
| **CAMP-08 p75** | **1** | **3,678** | **+0.522** | **1,177** | **0.541** | **0.614** | 0.502 | **UNECONOMIC** |
| trend_momentum *(Track B)* | 1 | 726 | +0.679 | 308 | 0.580 | 0.614 | 0.435 | UNECONOMIC + UNDERPOWERED |

> **Correction, 2026-08-06.** An earlier version of this table computed
> N_eff from **return** correlation. The pooled statistic is a binary
> **hit indicator**, whose correlation is 2·arcsin(r)/π — materially
> lower. Every N_eff above was ~21 % understated; the table was *more*
> pessimistic than the mathematics warrants. **No verdict changed**, but
> CAMP-07 t025 is now close enough to the bar to be marked DISPUTED
> rather than UNDERPOWERED. Additionally, every row here **also fails the
> tax gate** — the 0.55 bar sits below the after-tax threshold at every
> horizon tested.

### The six questions, answered for the record

1. **Economically meaningful hypothesis?** For 13 of 15, yes — the 24h
   and 72h horizons carry a 0.518–0.524 breakeven, comfortably below the
   0.55 bar. **For CAMP-08 and Track B, no:** at 1h the breakeven is
   **0.614**, above their own bar, so both could have *passed* their gate
   and lost money. CAMP-08's measured mean directional return of **0.4 bp**
   against a **9.4 bp** cost `[M]` settles it arithmetically.
2. **Statistical power sufficient?** **For one of fifteen.** Only CAMP-08
   reached the ~783 effective samples a 0.55 bar requires (1,177). Every
   other configuration was between **1.4× and 235× short**. CAMP-07 t025
   (n_eff 749) is marginal and flips to adequately powered under one-sided
   testing — recorded as DISPUTED, not UNDERPOWERED.
3. **Cost model realistic?** **No campaign had one.** Not one
   pre-registration, evidence package or ledger entry contains a fee,
   slippage or funding assumption. Every `known_limitations` block says
   costs are "not modelled" — accurately, and that was the defect.
4. **Deployment possible?** CAMP-01/05/07 carried a structural
   DEFER-ceiling (no Hyperliquid OI history) `[R]`. CAMP-02/03/04 were
   Binance-screened. **Only CAMP-08 was ever promotion-eligible.**
5. **Conclusion justified?** **For one of fifteen.** CAMP-08's null is
   real: it was powered, and its effect size is 23× below its cost. The
   other fourteen nulls are consistent with "no edge" *and* with "an edge
   of exactly the size we were hoping for, invisible at this sample."
6. **CLOSED or UNRESOLVED?** See below.

### Recommended annotation (governance decision required — **not applied**)

| Campaign | Current | Recommended | Why |
|---|---|---|---|
| CAMP-01, 02, 03, 04, 05, and CAMP-07 t040/120h | CLOSED / REJECTED | **UNRESOLVED — underpowered** | MDE exceeded the pre-registered bar; the test could not see the effect it was looking for. The label must record measured MDE, n_eff and dependence method so it is itself falsifiable |
| CAMP-07 t025 | CLOSED / REJECTED | **DISPUTED** | Verdict flips on the one-sided/two-sided choice (MDE 0.551 vs 0.545 against a 0.55 bar). A judgement call, not arithmetic |
| CAMP-06 | DEFERRED | **DEFERRED** (unchanged) | RD-16 reached the right answer by the right reasoning `[R]` |
| CAMP-08 | CLOSED / REJECTED | **CLOSED — REJECTED (economically, at 1h)** | Powered *and* the effect is 23× below cost. The strongest result in the program |
| trend_momentum | Track B, unrecorded | **CLOSED — REJECTED (Track B)** | z = −3.5 is a real negative finding; also uneconomic |

**Nothing above changes a sealed evidence package, a fingerprint, or a
recorded governance decision.** The Constitution's append-only guarantee
is intact. Applying these labels is a governance act requiring a reviewer
who is not the researcher — it is **proposed here, not performed.**

**Note on the `min_signaled_samples = 100` floor.** `[M]` 100 effective
samples correspond to an MDE of **0.6384**. Detecting the 0.55 bar every
campaign used needs **783**. The floor was never a power criterion, and
was ~7.8× too loose. This is the root cause of finding 2 above, and it is
now enforced in code rather than convention.

---

## 2 · Ranked mechanism backlog (Task 5)

EV = P(real alpha) × P(retail captures) × P(free data) × P(survives
costs) × P(deployable). Every probability is `[I]` judgement unless
tagged otherwise; each is justified, and stated to one significant figure
because that is the honest precision.

| # | Mechanism | P(real) | P(retail) | P(free data) | P(costs) | P(deploy) | **EV** |
|---|---|---|---|---|---|---|---|
| 1 | **Execution cost reduction** | **1.0** `[M]` arithmetic, not a hypothesis | 0.9 | **1.0** own fills | — *(it is the cost term)* | 0.9 | **0.81** |
| 2 | **Protocol mechanics** | 0.95 `[M]` fee tiers verified live | 0.9 | **1.0** | 1.0 reduces cost | 0.9 | **0.77** |
| 3 | **Payoff asymmetry** *(design choice, not a discovery)* | **1.0** `[M]` arithmetic | 0.9 | **1.0** | 1.0 moves the tax bar 0.6169 → 0.5132 at 1.5:1 | 0.9 | **0.81** |
| 4 | **Risk transfer (vault)** | 0.8 `[M]` **+16.6 %/yr** measured, trailing 12 m | 0.9 | **1.0** | 0.9 | 0.95 | **0.62** |
| 5 | **Cross-sectional relative value** | 0.5 `[E]` limits-to-arbitrage | 0.7 small size *is* the edge | **1.0** | **0.45** `[M]` breakeven 0.5255, MDE 0.5152 — but tax forces an asymmetric design | 0.8 no DEFER-ceiling | **0.126** |
| 6 | Volatility expansion | 0.6 `[E]` | 0.7 | 1.0 | 0.3 | 0.5 no options venue | **0.063** |
| 7 | Short-horizon mean reversion | 0.4 | 0.7 | 1.0 | **0.25** `[M]` 1h taker breakeven 0.614 | 0.8 | **0.056** |
| 8 | Calendar / seasonality | 0.2 `[E]` heavily arbitraged | 0.6 | 1.0 | 0.3 | 0.8 | **0.029** |
| 9 | Crowding (any variant) | **0.1** `[R]` 6 campaigns, no signal | 0.7 | 1.0 | 0.2 | 0.6 | **0.008** |
| 10 | Order flow | 0.6 `[E]` | 0.4 | **0.1** `[R]` no source | 0.3 | 0.2 | **0.001** |

**P(survives costs) is the binding term for every predictive mechanism**
— 0.25–0.45 against 0.9–1.0 for the non-predictive ones. That is the
direct consequence of measured breakevens of 0.518–0.614 against measured
edges near 0.50.

**The honest asymmetry: rows 1–4 total 3.01 of EV and require no
prediction at all; rows 5–10 total 0.28 between them.** A research program
that spends 90 % of its effort on rows 5–10 is misallocated. Two of the
top four — execution and payoff asymmetry — are *design choices* that
improve every future campaign at once, not discoveries that might fail.

---

## 3 · Twelve-month plan (Task 6)

**Rule: every month eliminates a mechanism forever, or promotes one
toward deployment.** No month ends without increasing knowledge.

| Month | Work | Knowledge gained |
|---|---|---|
| **1** (Aug 2026) | ✅ Feasibility gate in code. Protocol-mechanics audit (fee tier, staking discount, referral). Measure the HLP vault benchmark as the hurdle every campaign must beat | **ELIMINATES** protocol mechanics as an open question; establishes the hurdle rate |
| **2** (Sep) | Collect 30-symbol daily history. Outcome-blind feasibility review for the cross-sectional campaign. Lock pre-registration | **PROMOTES** cross-sectional to a locked specification, or kills it at the gate |
| **3** (Oct) | Execute **CAMP-09 — cross-sectional relative value**. Five-stage gate, governance decision | **ELIMINATES or PROMOTES** the highest-EV predictive mechanism |
| **4** (Nov) | Measure realised slippage at real size on testnet | **ELIMINATES or CONFIRMS** P(survives costs) ≈ 0.3 — the binding term for every future campaign |
| **5** (Dec) | If CAMP-09 died: volatility-conditioned cross-sectional (vol as a filter, not a signal). If it lived: build the HVL net-of-cost gate | **ELIMINATES** volatility-as-conditioner, or promotes CAMP-09 |
| **6** (Jan 2027) | Unattended stability: 48 h clean run, restart recovery, reconciliation against a live venue | Confirms the platform under real conditions |
| **7–8** (Feb–Mar) | Mean reversion — **only if** month 4 showed maker fills are achievable. Otherwise skip and state why | **ELIMINATES** mean reversion, or removes it from the backlog as unexecutable |
| **9–10** (Apr–May) | Portfolio allocation policy (required before a 2nd model) or the next surviving mechanism | Promotes toward a portfolio |
| **11** (Jun) | Paper trading of whatever survived, at minimum size | Confirms live behaviour vs. backtest |
| **12** (Jul 2027) | Scale, or terminate and write the negative record | Decision |

**By month 4 the project knows whether any predictive mechanism survives
costs at retail size.** That is the single most valuable unknown, and
nothing else on this plan reaches it faster.

**If every mechanism dies:** that is *Scientific Success* under the
mission's own definition, and the correct action is to stop researching
and allocate to the vault benchmark. That outcome is planned for, not
feared.

---

## 4 · Pre-registration gates (Task 7)

**All ten must pass before implementation. Any failure cancels the
campaign.** Gates 3, 4 and 5 are enforced in code by
`alpha_engine.feasibility.assess()`; the rest are reviewed.

| # | Gate | Test |
|---|---|---|
| 1 | **Mechanism novelty** | Names a row in `MECHANISMS.md` not marked CLOSE/CLOSED. A new information class over a tested mechanism is a robustness check, not a campaign |
| 2 | **Economic justification** | One paragraph: who is on the other side, why they accept a worse price, why it persists. "The indicator looked predictive" fails |
| 3 | **Statistical power** | `mde(n_eff) ≤ bar`. N_eff uses measured cross-instrument ρ̄ and serial retention, never raw counts |
| 4 | **Cost viability** | `bar > breakeven` at measured fees, funding and horizon. Slippage stated explicitly, even when zero |
| 5 | **Deployment feasibility** | Specification carries every execution parameter the bridge requires (RD-11 C). No DEFER-ceiling, or the ceiling is declared |
| 6 | **Data completeness** | Every fetch asserts expected vs. received row counts and fails loudly. `[M]` Four analyses have been silently degraded by truncation; none was caught by inspection |
| 7 | **Free-data availability** | Source is free, keyless or already-credentialed, and PIT-safe |
| 8 | **Retail executable** | Position sizes clear venue minimums at ₹2–10 lakh capital, on instruments whose depth supports them |
| 9 | **Pre-registration** | Thresholds, direction, horizon, bar and kill criteria locked before any outcome is inspected. Cumulative K recorded for family-wise error |
| 10 | **Kill criteria** | Written in advance: what result ends this mechanism forever, versus what marks it UNRESOLVED |

---

## 5 · The next campaign — CAMP-09, cross-sectional relative value

**`[M]` The first configuration to clear the power and cost gates — but
only in an ASYMMETRIC form. A symmetric CAMP-09 must not be run.**

| Gate | Result |
|---|---|
| Mechanism novelty | **PASS** — untested; not crowding, not trend, not liquidation |
| Economic justification | **PASS** — `[E]` limits to arbitrage: dispersion among mid-cap perps persists because correcting it is capacity-constrained, which is precisely the constraint retail size does not have |
| Statistical power | **PASS** — panel N_eff **8,460**, MDE **0.5152** `[M]` |
| Cost viability | **PASS** — breakeven **0.5255** (10.4 bp cost / 203.6 bp mean residual move) `[M]` |
| **Tax viability** | **FAIL if symmetric, PASS if asymmetric** — see below |
| Deployment feasibility | **PASS** — Hyperliquid-native feature and outcome; no DEFER-ceiling |
| Data completeness | Pending — assertion to be added with the collector |
| Free-data availability | **PASS** — `candleSnapshot`, free, keyless |
| Retail executable | **CONDITIONAL** — verified for the top ~20 by volume; the tail needs depth measurement |
| Pre-registration | Not yet locked |
| Kill criteria | Not yet written |

**Design.** Outcome is the **cross-sectionally demeaned** forward return
(symbol return minus universe mean), removing the single dominant market
factor. `[M]` Cross-sectional N_eff rises from 4.54 to 21.58 — a **4.75×**
gain — and from 1.61 (3 symbols, directional) a **13.4×** gain overall.
See [`MECHANISMS.md`](MECHANISMS.md) for the full decomposition; it is not
repeated here.

### The binding constraint is tax, not power

`[M]` Indian VDA tax is levied on **gross gains with no loss set-off**, so
viability needs a gross profit factor above **1.4535**. A winner realises
(w − c) and a loser (l + c), so the required hit rate is
**p > R(l + c) / [R(l + c) + (w − c)]**.

| Win : loss | Required hit rate | Verdict |
|---|---|---|
| **1 : 1 (symmetric)** | **0.6169** | **Implausible** — an 11.7-point edge over a coin flip |
| 1.5 : 1 | 0.5132 | Plausible |
| 2 : 1 | 0.4394 | Comfortable |
| 3 : 1 | 0.3413 | Comfortable |

**A symmetric CAMP-09 is a foregone failure.** MDE 0.5152 and breakeven
0.5255 are both far below 0.6169, so power and cost are fine — but no
cross-sectional strategy plausibly delivers a 0.6169 hit rate on symmetric
payoffs. **The specification must use asymmetric payoffs (≥1.5 : 1).**

**Methodological consequence:** an asymmetric design must be gated on
**expectancy and profit factor**, with power derived by bootstrap over the
payoff distribution — not on a binomial hit rate. That method does not yet
exist and is Track A's first task.

> **Correction, 2026-08-06.** An earlier version of this section reported
> the tax bar as **0.5924** and panel N_eff as **11,790**. The first
> omitted fees from the profit factor (understating the bar by 2.44
> percentage points); the second used the equicorrelation formula where
> the eigenstructure was required. Both are fixed and test-pinned in
> [`alpha_engine/feasibility.py`](../alpha_engine/feasibility.py).

**Consequence for the closed record:** the 0.55 bar sat below the
after-tax threshold in **every** campaign this project has run, at every
horizon tested.

### The hurdle rate the campaign must beat

`[M]` HLP vault, time-weighted from `vaultDetails` on 2026-08-06:

| Window | Annualised | Median TVL |
|---|---|---|
| Trailing 12 months | **+16.6 %/yr** | $398 M |
| Trailing 24 months | +16.3 %/yr | $356 M |
| All time (1,184 d) | +42.2 %/yr | $208 M |

**Use 16.5 %/yr, not 42 %.** The all-time figure is inflated by the early
low-TVL period — the same small-base bias that produces a flattering
number whenever a percentage return is compounded across a growing
capital base. `[I]` This also corrects an external ~20–22 % figure I
previously cited: the measured trailing figure is lower.

After 30 % + cess on gains, ~16.6 % gross ≈ **11.4 % net**. **Any research
outcome must beat 11.4 %/yr net, at comparable drawdown, or depositing to
the vault dominates it.** That comparison belongs in month 1, not year 2.

**Declared limitations, before any result is seen:**

1. **Survivorship.** The 30 symbols were selected by *today's* volume.
   The universe must be reconstructed point-in-time, or survivorship
   declared as a known limitation under RD-11 A.
2. **Slippage is zero in the cost model** because it has never been
   measured. Mid-cap perps at $5 M/day volume will not fill like BTC.
   Breakeven 0.5255 is a **lower bound**.
3. **Residual structure survives demeaning.** λ₁ still explains 17.7 % of
   residual variance, so N_eff is 21.58 of 30, not 30. The gate never
   credits more independent information than there are series.
4. **Two-sided by construction** — long-leg and short-leg are one
   measurement, not two (RD-17 §D).
5. **Hit rate is the wrong statistic for the design that must be used.**
   The tax gate forces asymmetric payoffs, and `feasibility.assess()`
   scores a binomial hit rate. An asymmetric CAMP-09 needs an
   expectancy/profit-factor gate with bootstrap power — Track A's first
   task, and a prerequisite to locking this pre-registration.

---

## 6 · Blocker requiring human judgement

**Month 4 — slippage measurement — cannot proceed without
credentials.** It needs `TURTLE_DEPLOYMENT_ACCOUNT_ADDRESS`, a testnet
`TURTLE_SECRET_HYPERLIQUID_WALLET_KEY_V1`, a funded wallet and a
spot→perp transfer `[R]`.

This does not block months 1–3. It does mean **every cost figure in this
document stays a lower bound until it is done**, and it is the single
input that most changes the ranking in §2.
