# MECHANISMS.md — the master research table

**Every future research action comes from this table.** A campaign that
cannot name its row does not get pre-registered.

A **mechanism** is the economic force claimed to produce the return: who
is on the other side, why they trade at a price they would not otherwise
accept, and why that persists. An **information class** is the data used
to observe it. They are independent axes, and conflating them is the
single most expensive error in this project's history — **six of nine
campaigns tested one mechanism (crowding) through four information
classes and were counted as six distinct results.**

Evidence tags: `[M]` measured in this repository · `[R]` repository/record
fact · `[E]` external literature · `[I]` inference.

---

## The table

| Mechanism | Information class | Tested? | Evidence strength | Deployable? | Next action |
|---|---|---|---|---|---|
| **Crowding / positioning extremeness** | Open interest, funding rate, funding delta, OI velocity | **Yes — 6 campaigns, 24 registered models** `[R]` | **Weak-negative.** Hit rates 0.477–0.560, all ≈0.50 `[M]`. But **0 of 6 had power to detect their own 0.55 bar** `[M]` — see `RESEARCH_BACKLOG.md` §1 | No | **CLOSE. Do not retest.** Not because it is disproven — it is not — but because retesting needs ~10× the data it will ever have at 24h on 3 symbols `[M]` |
| **Forced liquidation cascade** | S3 fill archive (`liquidation` field) | **Yes — CAMP-08 (hourly); CAMP-06 deferred** `[R]` | **Weak-negative, uneconomic by construction.** Hit 0.4965/0.5019, mean directional return **0.4 bp** against a **9.4 bp** round-trip cost `[M]` | No | **CLOSE at 1h.** The measured effect magnitude is 23× below cost. No hit rate rescues it |
| **Trend continuation** | OHLCV candles | **Yes — pipeline validation + sibling repo** `[R]` | **Negative.** Hit 0.4353, z = −3.5 `[M]`; permanently rejected in the sibling research repo `[R]` | No | **CLOSED (Constitution §4).** Not an open slot |
| **Cross-sectional relative value** (capacity-constrained dispersion) | OHLCV candles, wide universe | **NO** | **Untested.** `[E]` limits-to-arbitrage is the best-documented reason a retail-size edge can persist | **Yes — no DEFER-ceiling** (HL-native feature and outcome) | **Highest-ranked untested mechanism, but only with ASYMMETRIC payoffs.** `[M]` Panel N_eff 8,460, MDE 0.5152, breakeven 0.5255 — but the after-tax bar is **0.6169** symmetric, which is implausible. At 2:1 win/loss the bar falls to 0.4394 and the gate passes |
| **Volatility regime expansion** | OHLCV candles | **NO** | `[E]` Vol clustering is among the most robust findings in finance — but it forecasts *magnitude*, not *direction* | Partially — usable as a sizing/filter input, not a standalone signal | Queue behind cross-sectional. Test as a **conditioner** on an existing signal, never alone |
| **Short-horizon mean reversion** | OHLCV candles | **NO** | `[I]` Plausible; `[M]` 1h breakeven is **0.614 taker / 0.538 maker** — taker-only execution kills it before it starts | Only with maker fills | **BLOCKED** until maker execution is measured. Do not pre-register a taker-executed 1h campaign |
| **Risk transfer premium** | HLP vault, venue metadata | **MEASURED 2026-08-06** | `[M]` **+16.6 %/yr** trailing 12 m, time-weighted at $398 M TVL (**not** the +42 %/yr all-time figure, which is inflated by the early low-TVL base) | Yes — allocation, not a strategy | **THE BENCHMARK IS SET.** ≈11.4 %/yr after Indian tax. Any campaign that cannot beat it net is negative-EV against a deposit |
| **Protocol mechanics** (fee tiers, staking discount, referral) | `userFees` endpoint | **NO** | `[M]` Verified live today: base taker 4.5 bp, maker 1.5 bp; `activeStakingDiscount` is a real field | Yes, immediately | **AUDIT (2h).** A 4.5 → 1.5 bp shift moves the 24h breakeven from 0.5238 to 0.5169 `[M]` — it improves every future campaign at once |
| **Execution cost reduction** | Own fills | **NO** | `[M]` Not a source of alpha; a multiplier on all of it. Slippage has **never been measured** in this project | Yes | **MEASURE ON TESTNET.** Every net figure in this repository is an upper bound until this exists |
| **Order flow imbalance** | Market-wide L2/trades | **NO** | `[R]` RD-18: frozen adapter is REST-only; `get_fills` returns the account's own fills, not market flow | No — no source | **LOCKED.** Do not build capture against an unverified source |
| **Cross-venue basis** | HL + CEX | **NO** | `[M]` HL spot volume ≈ $0 for the watchlist; no deliverable basis leg | No | **LOCKED** |
| **Calendar / seasonality** | Timestamps | **NO** | `[E]` Weak and widely arbitraged | Yes, trivially | Lowest priority. Cheap enough to run as a by-product of the cross-sectional harness |
| **On-chain / stablecoin / macro** | External free APIs | **NO** | `[R]` No verified PIT-safe free source | No | **LOCKED** pending a source probe |

---

## Rules this table enforces

1. **One mechanism per campaign, declared by name before pre-registration.**
   A campaign whose mechanism already has a row marked *CLOSE* or
   *CLOSED* is cancelled at the novelty gate.
2. **A new information class is not a new mechanism.** Testing crowding
   through liquidations after testing it through open interest is a
   robustness check, not a new result — and must be reported as such.
3. **Contrarian and momentum are one measurement, not two** (RD-17 §D)
   `[M]` — every pair in the closed record sums to exactly 1.0000.
4. **Mechanisms are retired only with power.** A null from an
   underpowered campaign closes nothing. It is recorded `UNRESOLVED`.

## Independence, measured — why the universe was never the problem

`[M]` Cross-symbol correlation of returns, and the effective sample size
it implies:

`[M]` N_eff from the **eigenvalue participation ratio** (Σλ)²/Σλ² of the
**sign**-correlation matrix. Both choices matter and an earlier version of
this table got both wrong — see the correction note below.

| Design | k | N_eff (cross-section) | Panel N_eff |
|---|---|---|---|
| BTC/ETH/SOL, 24h, directional | 3 | **1.61** | 632 |
| BTC/ETH/SOL, 24h, market-neutral | 3 | 2.41 | 946 |
| 30 liquid perps, 24h, **directional** | 30 | **4.54** | 1,781 |
| 30 liquid perps, 24h, **market-neutral residual** | 30 | **21.58** | **8,460** |

Two separate levers, measured independently:

- **Widening the universe: 1.61 → 4.54, a 2.8× gain.** Real, but bounded —
  λ₁ explains 63.2 % of variance, so 30 correlated perps carry far less
  than 30 series' worth of information.
- **Removing market beta: 4.54 → 21.58, a 4.75× gain.** Larger, and the
  reason is structural: with one dominant factor, k series carry ≈1 factor
  plus k idiosyncratic components. Projecting the factor out leaves a
  (k−1)-dimensional residual space where information scales with k instead
  of saturating. Residual structure survives — λ₁ still explains 17.7 %.

Combined, 3-symbol directional → 30-symbol market-neutral is **13.4×**.

**Two things the gain is not.** It is not free: the residual move is
203.6 bp against 332 bp raw `[M]`, so cost bites ~1.6× harder per unit of
signal. And it is not the same hypothesis — "does X predict direction" and
"does X predict relative performance" are different economic claims, so
part of the power gain comes from asking an easier question.

> **Correction, 2026-08-06.** An earlier version of this table reported
> N_eff 1.26 → 1.63 and claimed a wider universe "buys almost nothing"
> and that beta removal was worth **20×**. Both were wrong. They came from
> applying the equicorrelation formula k/(1+(k−1)ρ̄) to **return**
> correlations, when the pooled statistic is a binary **hit indicator**
> (correct input: 2·arcsin(r)/π) and the correlation matrix has real
> eigenstructure that equicorrelation ignores. The formula also returns
> N_eff = 73 for k = 30 at negative ρ̄ — impossible as an information
> count. Both defects are now fixed and test-pinned in
> [`alpha_engine/feasibility.py`](../alpha_engine/feasibility.py).
