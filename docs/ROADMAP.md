# ROADMAP.md

**Future work only — this document answers "where are we going," nothing
else.** For current state, completed milestones, backlog, blockers and
risks, see `PROJECT_STATE.md` — the single authoritative execution-state
document. `CHANGELOG.md` and `docs/RESEARCH_LEDGER.md` are the permanent
record of what has already shipped.

**Organised by track, not by campaign** (2026-08-06). Campaigns are now
historical references; the unit of forward planning is a track. Ordered by
**value**, not implementation difficulty, per `PROJECT_CONSTITUTION.md`.
**An item's presence here is not authorization to build it now** — each
still needs its own proposal and approval per `REVIEW_PROTOCOL.md`, and
per Constitution §5 nothing is built ahead of a concrete, present need.
Every trigger condition stated below is the actual gate, not a suggestion.

## The tracks

Tracks are **ownership boundaries, not parallel workstreams.** This is a
single-developer project; **exactly one track is active at a time**, and
`PROJECT_STATE.md` records which. Tracks exchange outputs and never modify
each other's work.

| Track | Purpose | Consumes | Produces |
|---|---|---|---|
| **A · Research Framework** | Scientific methodology | — | Gates, statistics, acceptance criteria |
| **B · Alpha Discovery** | Find mechanisms | A's gates, D's candidates, E's data | Ledger entries, approved candidates |
| **C · Trading Engineering** | Deploy validated alpha | B's approved candidates | Execution, risk, sizing |
| **D · Reverse Engineering** | Study working systems | Public information only | Mechanism candidates for B |
| **E · Data Platform** | Best free dataset possible | — | Datasets for B |

**Track D never implements. Track C never discovers alpha. Track E never
does research.**

---

## Track A — Research Framework

**Owns:** statistics, power analysis, MDE, bootstrap, permutation, cost
model, slippage model, tax model, acceptance criteria, research
governance, campaign template, review methodology. Everything here must be
reusable across every future campaign.

**Already built — do not rebuild:** the five-stage validation gate
(single-pass, causality audit, walk-forward, bootstrap, regime
stratification), evidence sealing with content fingerprints, the
experiment registry, governance decision recording, degradation
assessment, and the feasibility gate (cost, power, tax).

### A1. Expectancy / profit-factor gate with bootstrap power — **NEXT**

The current gate scores a binomial hit rate. The VDA tax gate makes
symmetric-payoff designs untradeable, so every design worth running is
asymmetric — and an asymmetric design's power cannot be derived from a hit
rate. Required before any new pre-registration is locked.

### A2. Derive the acceptance bar; retire the inherited 0.55

`min_hit_rate = 0.55` was copied unexamined into all eight
pre-registrations and appears in no derivation anywhere in the repository.
It is simultaneously **too low to be tradeable** (below the after-tax
threshold at every horizon tested) and **too high to be detectable** at
the sample sizes available. Future bars are derived from measured cost and
tax, per campaign, before any outcome is seen.

### A3. Permutation test

The only validation stage named in the project's methodology that has no
implementation (`grep permutation` → zero hits). Build when a campaign
needs it, not before.

### A4. Campaign template

Extract from CAMP-08's harness — the newest and cleanest — once a ninth
campaign exists to justify it. The eight existing harnesses (4,735 lines)
are **immutable scientific record and are never refactored.**

### A5. Historical Validation Layer (HVL)

**Trigger: the first campaign producing a SUPPORTED hypothesis. Nothing is
built before that.** Recorded scope (RD-11's deferred set, refined by the
liquidation pilot), carried forward unchanged:

- True chronological walk-forward recalculation (rolling
  thresholds/normalizations, no future-derived quantities).
- Trade simulation: frozen stop-loss methodology (never widened during
  evaluation), frozen take-profit methodology, fixed risk assumptions.
- Realistic fees, realistic slippage, liquidity constraints — and,
  specifically for any liquidation-triggered strategy,
  **event-conditional** slippage/liquidity (a liquidation fires precisely
  when liquidity is worst; average-book assumptions would be
  systematically optimistic).
- Profit factor · expectancy · average R multiple · max drawdown · equity
  curve · before-vs-after walk-forward comparison.
- **Episode-level metrics and effective sample size as first-class
  reported statistics**, not footnotes.
- **Block bootstrap under dependence** (or an explicit recorded
  limitation) wherever resampled events are not exchangeable.
- Every validation report carries **both signal metrics and trade metrics,
  reported separately**.
- The existing reporting caveat (RD-11 D) stays **exactly as worded**
  until true rolling out-of-sample walk-forward exists to justify
  strengthening it.
- The deferred Constitution no-hindsight amendment lands with this layer,
  not before.
- **Not a separate "Robustness Validation" layer.** Monte Carlo and
  parameter sensitivity belong to Research; fee/slippage/spread/fill
  stress to the HVL; execution delay and randomized fills to Paper
  Trading. A fourth layer built on zero concrete instances would be the
  exact premature abstraction Constitution §5 forbids.

---

## Track B — Alpha Discovery

**Owns:** mechanisms, campaigns, `RESEARCH_LEDGER.md`, `ALPHA_LIBRARY.md`.
Every idea goes Mechanism → Evidence → Candidate → Review. No direct
implementation.

**The master mechanism table is `docs/MECHANISMS.md`.** The ranked backlog,
power audit and pre-registration gates are `docs/RESEARCH_BACKLOG.md`.
Neither is duplicated here.

### B1. Cross-sectional relative value — highest-ranked untested mechanism

`[M]` Clears power (panel N_eff 8,460, MDE 0.5152) and cost (breakeven
0.5255). **Must be specified with asymmetric payoffs** — a symmetric
design needs a 0.6169 hit rate and is a foregone failure. Blocked on **A1**
and **E1**.

### B2. Then, one at a time

Liquidity provision · volatility as a conditioner (never a standalone
signal) · calendar effects as a by-product of the cross-sectional harness.
**One mechanism at a time**, each gated by Track A.

### Closed — never reopen

| Mechanism | Why it stays closed |
|---|---|
| **Crowding** (OI level/velocity/long-horizon, funding level/venue-relative/delta) | Six campaigns, four information classes, ~0.50 throughout. RD-05, RD-17 |
| **Trend / OHLCV-derived conviction** | Permanently rejected, Constitution §4. EMA, SMA, Supertrend, Donchian are **one mechanism**, not four — Playbook §1 names this exact case |
| **Horizon as a rescue** | RD-17 §C. Extending a rejected mechanism's horizon does not convert a null into an edge |
| **Binance liquidation archive** | RD-06, live-verified: zero objects, endpoint decommissioned |

### Blocked — revisit only on the stated trigger

| Item | Trigger |
|---|---|
| **Campaign 06 (daily liquidations)** | ≈**264** worst-fold raw signalled samples at p60/n_folds=3 versus 106 today — roughly **18 further months** of archive (RD-16 §D). **Prohibited on revisit:** lowering `min_signaled_samples`, choosing a more permissive threshold to clear the bar, or dropping the N_eff requirement. Any of those turns the gate into a formality |
| **Open Interest Divergence** | The sole untested OI mechanism, under an unchanged DEFER-ceiling — knowledge-only until the live recorder has accumulated enough Hyperliquid-native OI history (prior campaigns needed 12–18 months; recording began 2026-08-05) |
| **Order flow** | RD-07's "verify HL historical order-flow" precondition remains unverified. The frozen adapter is REST-only and `get_fills` reads the account's own fills, not market flow (RD-18 §C) |
| **Combined OI + Funding** | Only after both components show independent edge; first trigger for a multi-feature candidate type and the attribution stage |
| **Stablecoin flows, on-chain, macro liquidity, cross-asset** | Each needs a verified free, PIT-safe source. On-chain and macro additionally need point-in-time discipline against vendor revision |

**Any campaign using the deep Binance window must declare, as
`known_limitations` under RD-11 A:** survivorship bias (a 2026-chosen
watchlist tested against 2020–21 conditions), non-stationarity (two
halvings, LUNA, FTX, the ETF era), and asymmetric per-symbol start dates.

---

## Track C — Trading Engineering

**Owns:** execution, ATR exits, maker/taker routing, risk management,
position sizing, volatility targeting, portfolio construction, slippage,
daily limits, circuit breakers. **Track C consumes approved candidates; it
never discovers alpha.**

**Modules 1–10, `app/`, `trading_system/`, `orchestration/` and
`composition_root/` are FROZEN** (Constitution §9). Modification is
permitted only to correct an explicitly authorized
correctness/security/capital-protection defect. Everything below is
additive work outside the frozen boundary, or an operator action.

### C1. Commit the D6 extension

Built and tested; additive only. No frozen module's public API changed.

### C2. Measure realised slippage at size — **blocked on operator action**

The single most valuable unmeasured input in the project. Every breakeven
is a lower bound until this exists. Requires:

1. Move the plaintext `env` file to `.env`; decide on wallet-key rotation
   before any mainnet use (`FINAL_PRODUCTION_AUDIT.md` SEC-1).
2. Testnet spot→perp balance transfer + a live-mode testnet config
   (`FINAL_PRODUCTION_AUDIT.md` §4).
3. Fix `AppState.last_error` never clearing (OBS-1) before gating a soak
   test's pass/fail criterion on it.
4. Execute the full testnet checklist and a 24–72 h soak
   (`docs/PRODUCTION_CHECKLIST.md`).
5. Mainnet rollout — **NO-GO** until 1–4 are complete.

### C3. Maker/taker routing

`[M]` Moves the 24 h breakeven from 0.5238 to 0.5169 and the 1 h from
0.6138 to 0.5377. Deterministic, requires no hypothesis. Build when a
candidate is approaching deployment.

### C4. Deferred until there is something to operate

- **Alpha Library formalization** — worth building once 2–3 models are
  approved; nothing to curate before then.
- **Watchlist-driven automatic evaluation + scheduler** — wait until ≥2
  proven candidate families justify automating a loop.
- **Model-combination/weighting policy** (`portfolio/selection.py` beyond
  dedupe-or-refuse) — meaningless until ≥2 approved models can agree or
  disagree on the same asset. Must remain "refuse if uncertain," never
  "guess and proceed" (Constitution §7).
- **Watchlist ranking + rank-based TradeIntent generation** — lowest
  priority; nothing to rank with a zero-to-one-model library.
- **Telegram Operations Console** — build only when paper/live trading is
  imminent. Four-tier design carried forward unchanged: **Monitoring**
  (read-only) → **Notifications** (event fan-out, including a
  heartbeat/liveness alert, since silence itself is the danger signal) →
  **Operations** (capital-affecting, two-step typed confirmation) →
  **Explainability** (deterministic retrieval only; the LLM formats
  retrieved facts, **never infers them**).
  **Hard constraints, non-negotiable:** one path only — every channel goes
  through the existing Operations Service and engine-routed `AppState`
  control methods, never a parallel path around order/risk managers.
  **Forbidden via any operational channel, structurally:** approving or
  rejecting alpha, changing thresholds/specs/validation rules, bypassing
  Risk Manager or Governance, overriding sizing/leverage, and **switching
  to Live Mode** — which stays a deliberate out-of-band operator action.
  **Operating principle: the human supervises, the system operates.**
  Watch item: notification volume must never degrade into de facto
  unsupervised operation through alert fatigue.
- **Paper trading**, **monitoring routing**, and an agreed
  **degradation-review cadence** — each gated on a first approved model.

---

## Track D — Reverse Engineering

**Owns:** the study of systems that demonstrably make money, to generate
mechanism candidates for Track B. **Not started.**

**Output contract — the whole track.** Track D produces **rows in
`docs/MECHANISMS.md` and nothing else.** No code, no campaign, no separate
report series. This contract exists because an unbounded literature review
is the most likely way this track fails.

For each system, answer only: How does it actually make money? What
mechanism? What assumptions? Can it be reproduced? Does it require paid
data, private flow, privileged infrastructure, or exchange relationships?
**If yes → mark NOT COMPATIBLE and stop.**

**Standing constraint:** no paid datasets, no paid APIs, no paid software.
Free, open-source and public resources only.

**Study order** (see `WATCHLIST.md` § Reverse Engineering for the full
target list): **HLP first** — the only system whose mechanism and returns
are both directly measurable from public data, and the project's own
hurdle rate at `[M]` +16.6 %/yr.

---

## Track E — Data Platform

**Owns:** the best free historical dataset obtainable. **No research, no
strategy, no indicators — data quality only.**

**Already held:** Binance funding 77 months (BTC/ETH from 2020-01, SOL
from 2020-09) · Binance OI + mark price from 2021-01/2022-01 · Hyperliquid
funding ~37 months · Hyperliquid liquidations 367/367 days audited
(2,138,761 events, rows/event exactly 2.0000) · Hyperliquid 1h candles
~200 days · live recorder running since 2026-08-05.

### E1. Wide-universe candle collection + point-in-time universe reconstruction

Track B's hard dependency. The 30-symbol panel used in the cross-sectional
feasibility work was selected by **today's** volume, which is survivorship
bias — the universe must be reconstructed point-in-time before any
pre-registration relies on it.

### E2. Route `data/alpha_engine_historical` through `config/loader.py`

With an environment override, and declare a persistent Railway volume
(`railway.json` currently declares none — `data/` is ephemeral there,
which will affect live trading, not just research, if left unfixed).

### E3. Probe additional free sources

Yahoo, Ken French, CFTC. **Probe first, build nothing until a specific
pre-registered hypothesis needs the data.** Each must be verified free,
keyless or already-credentialed, and point-in-time safe.

### Data constraints, standing

- **No paid datasets, APIs or software.** Anything requiring payment is
  marked **NOT COMPATIBLE**. Coinalyze remains excluded on this basis
  (requires registration/credential), as recorded in `HISTORICAL_DATA.md`.
- **Hyperliquid history cannot be extended backwards** — the venue's own
  coverage boundary was reached. Data not captured now is unrecoverable,
  which is why the live recorder runs continuously.
- **Requester-pays S3 archives carry no published retention guarantee**,
  unlike Binance's decade-plus public archives.

---

## Long-term architecture (destination, not current work)

```
Data Acquisition                    (Track E)
        ↓
Research Validation                 (Track A gates, Track B campaigns)
        ↓   signal quality: hit rate, magnitude, causality, bootstrap,
        ↓   walk-forward, regime robustness, power, cost, tax
Historical Validation               (Track A — HVL, not yet triggered)
        ↓   trade quality: entries/exits, SL/TP, fees, slippage,
        ↓   liquidity, expectancy, profit factor, R-multiple, drawdown
Governance                          (reviewer ≠ researcher — the one
        ↓                            deliberate human-judgment gate)
Paper Trading                       (Track C — real execution-condition
        ↓                            stress: delay, randomized fills)
Live Trading  ⟷  Execution Engine   (frozen, veto authority — owns sizing,
        ↓         leverage, exposure, kill switches, drawdown and daily
        ↓         loss enforcement, correlation limits)
Monitoring / Degradation / Retirement
        ↺
   [back to New Hypothesis — this loop IS "self-improving" per
    Constitution §8: no live parameter learning, only a new,
    separately pre-registered experiment]
```

**Data Acquisition is a first-class concern, not an implementation
detail** — six of nine research families are `Data: NONE`, and every
campaign to date was limited by whether history existed and how correlated
it was, never by a shortage of hypotheses.

**Token Intelligence / Portfolio Intelligence** (further downstream, not
triggered by anything): accumulates validated per-token/per-regime
evidence (read-only, grown only through research and paper trading, never
live mutation), with Portfolio Intelligence making portfolio-level
decisions atop it. The Execution Engine remains sole owner of sizing,
leverage, liquidation protection, portfolio heat, correlation management
and risk — an alpha never produces leverage, only research opinions.

- **Portfolio Memory** — prerequisite: ≥2 approved alphas trading
  simultaneously.
- **Confidence Calibration** — before any alpha's stated confidence
  influences sizing, verify via paper trading that it is historically
  calibrated. Prerequisite: ≥1 approved alpha with a paper-trading record.

---

## Other long-term ideas (recorded so they aren't lost; not scheduled)

- Authenticated reviewer identity for governance (today enforced on plain
  strings — a real but narrow limitation).
- SQLite (or similar) `RegistryStorage` backend, if concurrent-writer
  needs emerge.
- Monte Carlo / risk-of-ruin validation at the **portfolio** level.
- Calibration + purge/embargo validation stages (need a probabilistic or
  fitted candidate type; today's candidates are fixed-threshold rules).
- A concrete adapter for **Lighter**, the future supported venue named in
  the frozen `exchange_adapter`'s own docstring. The production target
  remains decentralized perpetual exchanges exclusively; a centralized
  exchange is never a live candidate.

---

## Future strategic evaluation gates (NOT active backlog items)

### Evaluate External MCP Data Providers

**Status: FUTURE EVALUATION GATE — not an active backlog item. Do not
begin. Purpose: evaluate, not integrate.**

**Trigger (all must hold):** (1) at least one alpha model has cleared
governance — today **zero** — *or* a pre-registered campaign names a data
requirement no existing source can satisfy; **and** (2) the multi-asset /
equities direction is an actual stated objective rather than hypothetical
— today the production target is decentralized perpetuals exclusively;
**and** (3) the evaluation is scoped as a written comparison, not a spike
or prototype integration.

When it runs, it must answer: incremental value versus existing sources ·
historical depth per asset class · real-time capability and PIT safety ·
equity/fundamental coverage · **Hyperliquid relevance** (decisive under
Constitution §6 — another CEX/equity source does not lift the
venue-transfer ceiling) · licensing · reliability · rate limits · caching ·
architectural fit without a new framework · point-in-time discipline ·
and the gate itself: **a written argument that a specific, pre-registered
hypothesis becomes testable *only* with this data. Absent that, the answer
is no.**

**Out of scope until the trigger fires:** any credential setup, dependency
declaration, adapter code, schema design, or proof-of-concept. **The
default outcome of this gate is "not yet."**

---

## Integration rules (unchanged)

**Execution Engine work** — per `docs/DEVELOPMENT_WORKFLOW.md` and
`docs/CLAUDE_ONBOARDING.md`: additive-only, no change to any frozen
module's public API, depend only on already-frozen lower-numbered modules,
persist state through the event store, ship a dedicated test file, no
dependency cycles, full regression green plus explicit approval before
freeze.

**Alpha Engine work** — per `PROJECT_CONSTITUTION.md` and
`alpha_engine/DECISIONS.md`: additive only, zero import of a frozen
Execution Engine package (test-enforced), deterministic (injectable
clock/seed, canonical timestamps, content fingerprints), every new
capability ships comprehensive tests, and no architecture or
infrastructure is built ahead of a concrete, currently-active need.

> Nothing in this roadmap is scheduled or committed by the mere fact of
> being listed here — each item still requires its own proposal,
> pre-registration (for research) or plan (for engineering), and explicit
> approval before work begins.
