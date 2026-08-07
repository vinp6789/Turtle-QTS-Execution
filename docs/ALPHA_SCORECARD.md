# ALPHA_SCORECARD.md — Business Performance Reference

**The permanent, evidence-backed answer to "what was our best alpha?" and
"would removing tax have changed the outcome?"** Reference this document
instead of re-deriving those answers.

Built 2026-08-07 from **sealed evidence only** (`data/alpha_engine_research/`,
86 experiment records, 43 complementary pairs), overlaid with measured
costs. No sealed package, fingerprint, ledger entry, Research Decision or
governance record was read-modify-written; this is an annotation.

Evidence tags: `[M]` measured here · `[R]` repository/record fact.

---

## 0 · The finding that governs every number below

**The project never measured a return.** The five-stage gate measures
*signal* quality. Sealed evidence contains exactly:

```
hit_rate · mean_directional_return · hits · signaled_samples ·
total_samples · flat_samples · unavailable_samples · criteria_results
```

It contains **no** profit factor, payoff ratio, Sharpe, drawdown, equity
curve, fee, slippage or trade simulation. The Historical Validation
Layer — which would have produced those — was never built, correctly,
because its trigger (a SUPPORTED hypothesis) never fired.

**Consequence: Sharpe, max drawdown, profit factor and payoff ratio are
`NOT MEASURED` for every mechanism in project history**, and are marked
so rather than estimated.

## 0.1 · The complementarity identity — read before any other number

`[M]` Across **all 43 sealed contrarian/momentum pairs**, mean
directional returns sum to **exactly 0.00000000 bp**. Hit rates sum to
exactly 1.0 in 41 of 43 (CAMP-08's two pairs sum to 0.998369; the
0.163 % gap is exact-zero-return samples, counted as a hit for neither
direction).

**Therefore the gross expectancy of a direction chosen without
foreknowledge is exactly 0.00 bp, for every configuration ever run.**

This is an algebraic property of the measurement design, not a result.
Any table that shows "the better direction" is showing ex-post selection,
which Constitution §6 and RD-17 §D exist to forbid. **The scorecard below
reports the favourable direction only to make the selection bias visible,
never as an achieved return.**

---

## 1 · The scorecard

Gross = `mean_directional_return` of the **favourable** direction, in bp
per sample — *ex-post selected, therefore an upper bound, not a result*.
Cost `[M]` = round-trip taker at measured Hyperliquid fees (4.5 bp/side)
plus funding 1.40 bp/day, horizon-scaled. Slippage **0.0 — never
measured**, so every net figure is optimistic.

| Mechanism | Campaign | Info class | h | Signalled | n_eff | Hit | Gross bp | Net-of-cost bp | After-tax | PF | Payoff | Sharpe | MaxDD | MDE | Statistical verdict | Economic verdict | Failure |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Crowding | CAMP-01 pctrank | Open interest | 24 | 126 | 64 | 0.5079 | 38.82 | 28.42 | NOT COMPUTABLE | NOT MEASURED | NOT MEASURED | NOT MEASURED | NOT MEASURED | 0.672 | UNDERPOWERED | Unknown | **G** |
| Crowding | CAMP-01 zscore | Open interest | 24 | 167 | 85 | 0.4970 | 17.87 | 7.47 | NOT COMPUTABLE | NOT MEASURED | NOT MEASURED | NOT MEASURED | NOT MEASURED | 0.650 | UNDERPOWERED | Unknown | **G** |
| Crowding | CAMP-02 Binance | Funding | 24 | 141 | 72 | 0.5603 | 26.01 | 15.61 | NOT COMPUTABLE | NOT MEASURED | NOT MEASURED | NOT MEASURED | NOT MEASURED | 0.663 | UNDERPOWERED | Unknown | **G** |
| Crowding | CAMP-02 Hyperliquid | Funding | 24 | **9** | 5 | 0.6667 | 225.34 | 214.94 | NOT COMPUTABLE | NOT MEASURED | NOT MEASURED | NOT MEASURED | NOT MEASURED | 0.959 | **UNINTERPRETABLE** (n=9) | Unknown | **G** |
| Crowding | CAMP-03 Binance | Funding (venue-rel) | 24 | 280 | 142 | 0.5250 | 19.58 | 9.18 | NOT COMPUTABLE | NOT MEASURED | NOT MEASURED | NOT MEASURED | NOT MEASURED | 0.617 | UNDERPOWERED | Unknown | **G** |
| Crowding | CAMP-03 Hyperliquid | Funding (venue-rel) | 24 | 461 | 234 | 0.5315 | 42.29 | 31.89 | NOT COMPUTABLE | NOT MEASURED | NOT MEASURED | NOT MEASURED | NOT MEASURED | 0.591 | UNDERPOWERED | Unknown | **G** |
| Crowding | CAMP-04 Binance | Funding delta | 24 | 354 | 180 | 0.5226 | 16.91 | 6.51 | NOT COMPUTABLE | NOT MEASURED | NOT MEASURED | NOT MEASURED | NOT MEASURED | 0.604 | UNDERPOWERED | Unknown | **G** |
| Crowding | CAMP-04 Hyperliquid | Funding delta | 24 | 450 | 229 | 0.5111 | 15.34 | 4.94 | NOT COMPUTABLE | NOT MEASURED | NOT MEASURED | NOT MEASURED | NOT MEASURED | 0.592 | UNDERPOWERED | Unknown | **G** |
| Crowding | CAMP-05 | OI velocity | 24 | 390 | 198 | 0.5154 | 25.04 | 14.64 | NOT COMPUTABLE | NOT MEASURED | NOT MEASURED | NOT MEASURED | NOT MEASURED | 0.599 | UNDERPOWERED | Unknown | **G** |
| Liquidation cascade | CAMP-06 | S3 fills | 24 | — | 48 | — | NOT MEASURED | — | — | NOT MEASURED | NOT MEASURED | NOT MEASURED | NOT MEASURED | 0.703 | **NEVER RUN** | Unknown | **F** |
| Crowding | CAMP-07 72h t040 | OI, long horizon | 72 | 572 | 414 | 0.5122 | 20.74 | 7.54 | NOT COMPUTABLE | NOT MEASURED | NOT MEASURED | NOT MEASURED | NOT MEASURED | 0.569 | UNDERPOWERED | Unknown | **G** |
| Crowding | CAMP-07 72h t025 | OI, long horizon | 72 | 1,035 | 749 | 0.5014 | 15.72 | 2.52 | NOT COMPUTABLE | NOT MEASURED | NOT MEASURED | NOT MEASURED | NOT MEASURED | 0.551 | **DISPUTED** | Unknown | **G** |
| Crowding | CAMP-07 120h | OI, long horizon | 120 | 333 | 241 | 0.5225 | 13.35 | **−2.65** | Negative | NOT MEASURED | NOT MEASURED | NOT MEASURED | NOT MEASURED | 0.590 | UNDERPOWERED | Loses to cost | **G** |
| Liquidation cascade | **CAMP-08** | S3 fills | 1 | 3,678 | **1,177** | 0.5019 | **0.40** | **−8.65** | Negative | NOT MEASURED | NOT MEASURED | NOT MEASURED | NOT MEASURED | **0.541** | **ADEQUATELY POWERED** | **Dead — 23× below cost** | **A** |
| Trend continuation | pipeline validation | OHLCV | 1 | 726 | 308 | 0.4353 | −0.86 | −9.92 | Negative | NOT MEASURED | NOT MEASURED | NOT MEASURED | NOT MEASURED | 0.580 | Significant **negative** (z = −3.5) | Dead | **A** |
| Cross-sectional carry | *(screen, 2026-08-06)* | Funding, cross-sec | 720+ | 91,127 settlements | — | — | +11.84 %/yr captured | +10.90 %/yr | **7.67 %/yr** | **1.255** | ~1.0 | NOT MEASURED | NOT MEASURED | — | Persistence ρ 0.26 @30d | **Fails tax (need 1.4535)** | **D** |
| Session boundary | *(screen, 2026-08-07)* | Session structure | 12 | 10,800 settlements | — | — | +0.46…+2.91 %/yr | **−63 %/yr** | Negative | NOT MEASURED | NOT MEASURED | NOT MEASURED | NOT MEASURED | — | Signal real, sign inconsistent | **Cost 30× signal** | **C** |
| Funding-cap binding | *(screen, 2026-08-07)* | Protocol | — | 91,127 | — | — | — | — | — | — | — | — | — | — | **Premise false** — +10.95 %/yr is the default interest component, exceeded by 4.0 % of settlements | Not a mechanism | **G** |

**Benchmark:** HLP vault `[M]` **+16.6 %/yr** trailing 12 m ⇒ **≈11.4 %/yr
after 31.2 % VDA tax.** Zero effort, no execution risk.

---

## 2 · Failure classification — one category each

| Cat | Definition | Count | Which |
|---|---|---|---|
| **A** | No statistical edge | **2** | CAMP-08 (powered, effect 23× below cost); trend continuation (z = −3.5, significant negative) |
| **B** | Edge existed, died out-of-sample | **0** | *Never observed — no campaign ever established an in-sample edge at its pre-registered direction* |
| **C** | Positive edge, costs destroyed it | **1** | Session boundary (2 %/yr signal vs 65.7 %/yr cost) |
| **D** | Survived costs, failed VDA tax | **1** | Cross-sectional funding carry (PF 1.255 vs 1.4535 required) |
| **E** | Viable but inferior to HLP | **0** | *No mechanism ever reached economic viability* |
| **F** | Blocked before conclusion | **1** | CAMP-06 (deferred at feasibility gate, RD-16) |
| **G** | Unknown — required measurements do not exist | **12** | CAMP-01 ×2, 02 ×2, 03 ×2, 04 ×2, 05, 07 ×3, plus funding-cap (false premise) |

**12 of 17 outcomes are category G.** The dominant failure mode of this
project was never a bad mechanism — it was **measurements that could not
support a conclusion either way**.

---

## 3 · The counterfactuals

### 3.1 If Indian VDA tax were removed entirely, what was the best mechanism?

**Answer: none — and the data supports this exactly, not approximately.**

`[M]` Gross expectancy at a direction chosen without foreknowledge is
**exactly 0.00 bp** for all 43 pairs. Tax is levied on gains; removing a
tax on zero changes nothing.

**One qualification, stated so it is not mistaken for a result:** the
*ex-post favourable* direction of CAMP-03 Hyperliquid shows +42.29 bp
gross per 24 h sample. Its MDE was 0.591 against an observed 0.5315 — the
measurement could not distinguish that from noise. It is the largest
adequately-sampled favourable reading in the record and it is **not
evidence of anything**.

**The one mechanism with power to answer** — CAMP-08 — measured a gross
effect of **0.40 bp**. Removing tax leaves 0.40 bp against a 9.06 bp
cost. Still dead by 23×.

### 3.2 If both tax and trading costs were removed?

**Answer: still none, and for the same reason.** Gross expectancy is
exactly zero *before* any cost is subtracted. Costs were never the
binding constraint on the campaign record — **the absence of a
directional edge was**, wherever power existed to check.

Costs *were* binding for the two 2026-08 screens: session boundary (C)
and, jointly with tax, carry (D). Those are the only two cases in project
history where a measured positive gross was destroyed by costs or tax.

### 3.3 What killed what — quantified

| Killed primarily by | Count | Confidence |
|---|---|---|
| **Insufficient power** | **12** | `[M]` High — MDE > pre-registered bar in every case |
| Statistics (genuine null) | **2** | `[M]` High — CAMP-08 powered; trend significant negative |
| Costs | **1** | `[M]` High — session boundary, 30× gap |
| Tax | **1** | `[M]` High — carry, PF 1.255 vs 1.4535 |
| Governance | **1** | `[R]` CAMP-06 deferred at the gate — a *correct* block, not a failure |
| Benchmark comparison | **0** | Nothing reached viability |

---

## 4 · The three rankings

**Ranking 1 — highest raw alpha, ignoring costs and tax.**
`[M]` **All configurations tie at exactly 0.00 bp** at a pre-registered
direction. Ranking by ex-post favourable direction (**not evidence**):
CAMP-02 HL 225.34 bp *(n = 9, uninterpretable)* → CAMP-03 HL 42.29 →
CAMP-01 pctrank 38.82 → CAMP-02 Binance 26.01 → CAMP-05 25.04.

**Ranking 2 — highest realistic alpha after costs.**
`[M]` **All tie at −cost**: −9.06 bp at 1 h, −10.40 bp at 24 h,
−13.20 bp at 72 h, −16.00 bp at 120 h. No configuration is positive.

**Ranking 3 — highest business value after costs, tax and benchmark.**

| Rank | Item | After-tax | vs HLP |
|---|---|---|---|
| **1** | **HLP vault (the benchmark itself)** | **11.4 %/yr** | — |
| 2 | Cross-sectional funding carry | 7.67 %/yr | **−33 %** |
| 3– | Everything else | Negative or NOT COMPUTABLE | — |

**Nothing Project Alpha has measured beats the benchmark it measured.**

---

## 5 · Why did we fail? — attribution

| Cause | Contribution | Basis |
|---|---|---|
| **Insufficient statistical power** | **~70 %** | `[M]` 12 of 17 outcomes are category G. `min_signaled_samples = 100` was a count, not a power criterion: 100 effective samples ⇒ MDE 0.6384, while a 0.55 bar needs 783 |
| **Wrong mechanism (too narrow)** | **~15 %** | `[R]` 6 of 8 campaigns tested one mechanism — crowding — through four information classes, and counted it as six results |
| **Alpha never existed** | **~10 %** | `[M]` Supportable *only* for CAMP-08 and trend. Two clean nulls out of seventeen is not a basis for a general claim |
| **Costs** | **~3 %** | `[M]` Binding in exactly one case (session boundary). Never binding on the campaign record, because gross was zero |
| **Tax** | **~2 %** | `[M]` Binding in exactly one case (carry) |
| **Engineering limitations** | **0 %** | `[R]` The platform never blocked a campaign. 1,942 tests; every campaign ran end-to-end |

**Percentages are `[I]` judgement over `[M]` counts** — the category
counts are measured; the weighting between them is not, and no data can
make it so.

### The honest summary

**We did not fail because alpha does not exist. We failed because we
could not tell.** Fifteen of seventeen outcomes are consistent both with
"no edge" and with "an edge of exactly the size we hoped for, invisible
at this sample."

`[M]` Only **one** campaign in project history could answer its own
question — CAMP-08 — and its answer was a clean, well-powered no.

**The most expensive single defect was a sample-size gate that was never
a power calculation**, applied unchanged across eight campaigns and eight
months.

---

## 6 · What this scorecard cannot tell you

Stated plainly, because the gaps matter as much as the numbers:

- **No return series, ever.** Every "return" here is a per-sample signal
  expectancy, not a traded PnL. There is no equity curve to inspect.
- **Sharpe, drawdown, profit factor and payoff ratio do not exist** for
  any campaign. They became computable only on 2026-08-07 (commit
  `c93c088`); recovering them for closed campaigns requires re-running
  each harness, which would create new evidence packages, not amend
  sealed ones.
- **Slippage is 0.0 everywhere** — never measured. Every net figure is a
  lower bound on cost and therefore optimistic.
- **After-tax is `NOT COMPUTABLE`** for the campaign record, because tax
  needs the win/loss decomposition the sealed packages do not carry. It
  is marked *Negative* only where gross already lost to cost, where the
  sign is certain.
