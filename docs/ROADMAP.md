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

## ARCHITECTURE FROZEN — 2026-08-07

**The project architecture is frozen as of this document.** Tracks A–D,
the governance pipeline, the five-stage gate, the feasibility gate and
the execution stack are settled. No further restructuring, renaming, new
tracks or process redesign — unless a future reviewer demonstrates the
architecture itself is broken.

**The default answer to any proposed architectural change is:**

> *"Can this be accomplished within the existing architecture?"*

Only a demonstrable **no** reopens the question.

**The next phase is execution, not framework design.** Priorities, in
order: produce new evidence · build missing capabilities · ship a
deployable product · validate ideas with data · improve through measured
results rather than redesign.

**This freeze governs architecture, not knowledge.** Track D continues to
recommend improvements; mechanisms continue to be screened, rejected and
recorded; the Ledger continues to grow. What is frozen is the *shape* of
the project, not its content.

---

## The tracks

Project Alpha has **two equally important outputs**: validated scientific
knowledge, and a deployable systematic trading platform. They are
different deliverables and neither waits for the other.

| Track | Purpose | Output | Cadence |
|---|---|---|---|
| **A · Alpha Research** | Discover, screen and reject mechanisms under unchanged governance | Validated knowledge; occasionally an approved model | Slow, rigorous |
| **B · Product Development** | Deliver a usable trading system that improves over time | A deployable platform | Continuous |
| **C · Reverse Engineering** | Structured competitive intelligence on working systematic businesses | Evidence-backed mechanism candidates for A, design patterns for B | Continuous, low intensity |
| **D · Continuous Learning** | Extract knowledge from everything the platform does | Ranked, evidence-backed recommendations — **never a deployment** | Continuous, automated |

**Research feeds Product. Product does not wait for Research to finish.**

**Track D feeds Research. It never feeds Execution.** Self-improving does
not mean self-modifying: the system may discover improvements, and may
never silently deploy them (Constitution §8/§10).

**How three parallel tracks work with one developer.** Tracks run in
parallel as *streams of work*, not as simultaneous engineering. The
operating rule: **at most one track holds an active engineering task at a
time**; the other two progress through analysis, reading, or unattended
jobs, which need attention in minutes rather than hours. This is the
honest reconciliation of "parallel tracks" with a single-operator
project, and it is why Track C's output contract is a document rather
than a system.

**Tracks exchange outputs and never modify each other's work.** Track C
never implements. Track B never invents alpha — it consumes what governance
approves and improves everything around it. Track A's standards are
unchanged: same five-stage gate, same pre-registration, same
reviewer ≠ researcher, same evidence sealing.

**Supersedes the previous A–E structure (2026-08-06).** That scheme split
methodology from mechanisms and execution from data, which put two tracks
in permanent idle. The mapping, so no work is lost:

| Old | New |
|---|---|
| A Research Framework | **A · Alpha Research** (methodology, A1–A5) |
| B Alpha Discovery | **A · Alpha Research** (mechanisms, A6–A7) |
| C Trading Engineering | **B · Product Development** (execution, B1–B4) |
| E Data Platform | **B · Product Development** (data, B5–B7) |
| D Reverse Engineering | **C · Reverse Engineering** (unchanged) |

**Naming hazard, resolved here.** "Track B" previously also referred to the
2026-08-06 science-vs-engineering split in which a gate-rejected strategy
was used as a pipeline-validation harness. That usage is **historical
only** and is now written as "pipeline validation" wherever it appears.
Track letters in this document refer solely to the three tracks above.


---

## Track A — Alpha Research

**Governance is unchanged.** Everything in `RESEARCH_PLAYBOOK.md`, `PROJECT_CONSTITUTION.md` §6 and `RESEARCH_DECISIONS.md` applies exactly as before. Negative results remain the expected outcome and remain valuable.

### A-i · Methodology


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

### A5-M. MILESTONE — First Measured Equity Curve

**The transition from signal science to business science.** `[M]` Project
Alpha has run eight campaigns and measured a return **zero times**
(`ALPHA_SCORECARD.md` §0). This milestone ends that.

**Definition of done — one complete sequence of trades producing:**
equity curve · profit factor · payoff ratio · expectancy · CAGR ·
Sharpe · max drawdown · trade distribution · trade count · win rate ·
return after costs · return after tax.

**Profitability is NOT required. Measurement is.**

**Achievable now, and that is the point.** It needs no approved alpha —
the gate-rejected pipeline-validation strategy is a perfectly valid
input, because the deliverable is the *measurement capability*, not the
result. This deliberately decouples "can we measure a business outcome"
from "have we found alpha", which have been entangled for eight months.

**Scope boundary vs A5, stated so the RD-11 trigger is not quietly
broken.** RD-11 defers the **full** HVL until the first SUPPORTED
hypothesis. This milestone requires a **strict subset**: deterministic
trade simulation over a fixed, pre-declared rule, plus the metrics above.
It explicitly does **not** include rolling threshold recalculation,
rolling normalisation, stop/TP optimisation, or event-conditional
slippage — all of which remain deferred under RD-11's unchanged trigger.
Building the subset is Constitution §5-compliant (a present, concrete
need); building the rest would not be.

**If a formal amendment to RD-11's trigger is wanted, that is a separate
governance act requiring a new RD — proposed here, not performed.**

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


### A-ii · Mechanism discovery


**Owns:** mechanisms, campaigns, `RESEARCH_LEDGER.md`, `ALPHA_LIBRARY.md`.
Every idea goes Mechanism → Evidence → Candidate → Review. No direct
implementation.

**The master mechanism table is `docs/MECHANISMS.md`.** The ranked backlog,
power audit and pre-registration gates are `docs/RESEARCH_BACKLOG.md`.
Neither is duplicated here.

### A6. Cross-sectional relative value — highest-ranked untested mechanism

`[M]` Clears power (panel N_eff 8,460, MDE 0.5152) and cost (breakeven
0.5255). **Must be specified with asymmetric payoffs** — a symmetric
design needs a 0.6169 hit rate and is a foregone failure. Blocked on **A1** and **B5**.

### A7. Then, one at a time

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


---

## Track B — Product Development

**Purpose: deliver a usable trading system now, and improve it as research delivers.** This track does not wait for an approved alpha. It owns execution, risk, sizing, portfolio construction, monitoring, paper trading, deployment and the data platform that feeds all of them.

**It never invents alpha.** Signal admission remains governance's decision alone (Constitution §4/§7).

### B-i · Execution, risk and operations


**Owns:** execution, ATR exits, maker/taker routing, risk management,
position sizing, volatility targeting, portfolio construction, slippage,
daily limits, circuit breakers. **Track C consumes approved candidates; it
never discovers alpha.**

**Modules 1–10, `app/`, `trading_system/`, `orchestration/` and
`composition_root/` are FROZEN** (Constitution §9). Modification is
permitted only to correct an explicitly authorized
correctness/security/capital-protection defect. Everything below is
additive work outside the frozen boundary, or an operator action.

### B1. Commit the D6 extension

Built and tested; additive only. No frozen module's public API changed.

### B2. Measure realised slippage at size — **blocked on operator action**

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

### B3. Maker/taker routing

`[M]` Moves the 24 h breakeven from 0.5238 to 0.5169 and the 1 h from
0.6138 to 0.5377. Deterministic, requires no hypothesis. Build when a
candidate is approaching deployment.

### B4. Deferred until there is something to operate

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


### B-ii · Data platform


**Owns:** the best free historical dataset obtainable. **No research, no
strategy, no indicators — data quality only.**

**Already held:** Binance funding 77 months (BTC/ETH from 2020-01, SOL
from 2020-09) · Binance OI + mark price from 2021-01/2022-01 · Hyperliquid
funding ~37 months · Hyperliquid liquidations 367/367 days audited
(2,138,761 events, rows/event exactly 2.0000) · Hyperliquid 1h candles
~200 days · live recorder running since 2026-08-05.

### B5. Wide-universe candle collection + point-in-time universe reconstruction

Track B's hard dependency. The 30-symbol panel used in the cross-sectional
feasibility work was selected by **today's** volume, which is survivorship
bias — the universe must be reconstructed point-in-time before any
pre-registration relies on it.

### B6. Route `data/alpha_engine_historical` through `config/loader.py`

With an environment override, and declare a persistent Railway volume
(`railway.json` currently declares none — `data/` is ephemeral there,
which will affect live trading, not just research, if left unfixed).

### B7. Probe additional free sources

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


---

## Track C — Reverse Engineering


**Owns:** the study of systems that demonstrably make money, to generate
mechanism candidates for Track B. **Not started.**

**Output contract — the whole track.** Track C produces **rows in
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

## Track D — Continuous Learning & Self-Improvement

**Purpose: continuously extract knowledge from everything the platform
does, and turn it into ranked, evidence-backed recommendations.**

**Track D never changes trading logic. It produces evidence; Research
decides what to adopt; Governance decides what deploys.**

### D0. The governance boundary — read before anything else

`PROJECT_CONSTITUTION.md` §8 already defines self-improvement, and §10
names the absence of live parameter optimisation as *"the single most
important invariant in the entire system."* **Track D requires no
Constitution amendment**, because it is not a new philosophy — it is
*instrumentation of the loop §8 already mandates*:

```
Track D (new)                          Constitution Section 8 (unchanged)
Observe -> Measure -> Explain ->       New hypothesis (pre-registered)
Generate -> Estimate EV -> Rank ->  ->   -> Research (five-stage gate)
Recommend                                -> Evidence (sealed)
                                         -> Governance (reviewer != researcher)
                                         -> Library grows
```

Track D is the **front half**. It stops at *Recommend*. Everything after
that is the existing pipeline, unchanged.

**Four structural rules, not norms:**

1. **Track D emits no `TradeIntent`, ever**, and has no import path to
   the execution bridge. Enforceable by the same test that already
   fences `alpha_engine` from frozen modules.
2. **Track D writes only to its own surface.** It never edits
   `RESEARCH_LEDGER.md`, `RESEARCH_DECISIONS.md`, `ALPHA_LIBRARY.md`, a
   campaign report, or any sealed evidence package. New evidence
   *references* earlier work; the immutable record is never rewritten.
3. **Generation is free; testing is budgeted.** Track D may propose
   without limit, but any candidate entering pre-registration increments
   cumulative **K**, and the acceptance bar is Bonferroni-corrected for
   it. `[M]` The cost is real but survivable: a 0.55 bar needs 783
   effective samples at K=1, 1,569 at K=28 (today), 1,865 at K=100 and
   2,235 at K=500 — against 8,460 achievable in the best measured
   configuration. **An unbudgeted scanner would silently invalidate the
   research program; a budgeted one does not.**
4. **RD-02 boundary.** Track D's expected-value scores rank what to
   *attempt*. No threshold, bar, direction, horizon or acceptance
   criterion in any pre-registration may be derived from them — the same
   fence `RESEARCH_BACKLOG.md` §2 already operates under.

### D1. What already exists — reuse, do not rebuild

Roughly 60 % of Track D is built. Rebuilding any of it would be the
duplication this restructure exists to prevent.

| Track D capability | Already provided by |
|---|---|
| "Is a strategy degrading?" | `alpha_engine/lifecycle/degradation.py` — and it holds a model to **its own pre-registered bar**, inventing no drift threshold |
| Immutable experiment graph substrate | `alpha_engine/registry/` — append-only, content-fingerprinted, 86 experiments |
| Organisational memory / the "why" graph | `RESEARCH_DECISIONS.md` — 19 RD entries, append-only |
| Mechanism ↔ information-class relationships | `MECHANISMS.md` |
| Expected-value ranking | `RESEARCH_BACKLOG.md` §2 |
| Cost / power / tax arithmetic | `alpha_engine/feasibility.py` |
| Observability pattern | `scripts/recorder_health.py` |

**Genuinely missing:** execution-quality attribution, performance
decomposition, the opportunity scanner, and the cross-linking layer that
turns isolated records into a graph.

### D2. Staged activation — each stage gated on its inputs existing

Constitution §5 forbids building ahead of a concrete need. **Track D's
entire input list is currently empty**: zero approved models, zero live
trades, zero fills, zero paper-trading history. Building the measurement
system before the thing it measures would be the exact premature
abstraction §5 prohibits.

| Stage | Trigger | Scope |
|---|---|---|
| **D-0 · Defined** | **Now** | This section. Zero code. Track D exists as a contract |
| **D-1 · Execution quality** | First paper deployment producing fills | Slippage, fill quality, spread capture, latency, rejected/missed orders. **This is the measurement B2 is blocked on** — Track D's first stage and the product track's first unknown are the same thing |
| **D-2 · Performance attribution** | First approved model trading | Decompose into alpha, beta, execution, costs, slippage, funding, portfolio construction, leverage, diversification, regime, timing, and **luck vs persistent edge** |
| **D-3 · Knowledge graph + scanner** | ≥3 campaigns run under the post-restructure methodology | Cross-linking, contradiction surfacing, stale-assumption detection, opportunity scanning with EV scoring |

**Nothing in D-1..D-3 is authorised by appearing here** — each needs its
own proposal per `REVIEW_PROTOCOL.md`.


### D-scope. Track D is not a strategy generator

**Track D improves every layer of the platform, not only trading
strategies.** Its standing question is:

> *"What is the single highest-value improvement for the project right now?"*

Layers it observes and improves: **data quality · research quality ·
experimental design · statistical methodology · deployment quality ·
execution quality · portfolio construction · performance attribution ·
documentation quality · research prioritisation.**

The guiding loop — every layer improves, not just the last one:

```
Data -> Research -> Knowledge -> Product -> Live Validation
  ^                                                  |
  +------------------ Self Improvement <-------------+
```

`[R]` This is why Track D is worth having at all. The project's most
expensive error was never a bad strategy — it was eight campaigns run
with a sample gate that was not a power criterion. That is a
*methodology* defect, in a layer no strategy generator would ever look at.

### D4. The Knowledge ROI Gate — Track D's prioritisation engine

**Every Track D recommendation must carry all eight fields. A
recommendation missing any of them is not a recommendation.**

| Field | Meaning |
|---|---|
| Expected engineering effort | Build cost, in developer-days |
| Expected research effort | Design, screening and analysis cost |
| Expected execution effort | Operational cost to run and monitor it |
| **Evidence quality** | `[M]` measured · `[R]` repository fact · `[E]` external · `[I]` inference |
| **P(changing project direction)** | Would the answer alter what we do next? A result that changes nothing scores zero |
| Expected business impact | Effect on deployable, after-cost, after-tax return |
| **Scientific value if negative** | What a null result closes permanently |
| **Knowledge ROI** | The composite priority |

**Composition** (a convention, not a law — the inputs are ordinal
judgements, so the output ranks and never measures):

```
Knowledge ROI = ( P(direction change) x business impact
                  + scientific value if negative )
                / ( engineering + research + execution effort )
```

**The numerator's second term is the point.** A negative result carries
value here, so a cheap experiment that permanently closes a mechanism can
outrank an expensive one that might pay. `[R]` That is the arithmetic
behind killing carry, session-boundary and funding-cap in roughly one day
each — high scientific value, near-zero cost, and each removed a month of
prospective engineering.

**Hard limits.** Knowledge ROI exists **only to order work**. It never
changes a scientific conclusion, never bypasses governance, never edits a
Research Decision, and never enters a pre-registration. It answers one
question and no other:

> *"If there is time for only one experiment this week, which creates the most value?"*

This is the same RD-02 fence `RESEARCH_BACKLOG.md` §2 already operates
under: **rank what to attempt; never touch what is concluded.**

### D5. Prohibitions — structural, not advisory

Nothing in Track D may: generate a `TradeIntent` · modify execution ·
deploy a strategy · modify a parameter · alter a Research Decision ·
alter a campaign result · modify sealed evidence · bypass reviewer
separation · bypass the five-stage scientific gate.

**Track D proposes. The scientific process disposes.**

### D3. Success criterion

Track D succeeds when **the next experiment is chosen by evidence rather
than by argument**. `[R]` Eight campaigns were selected by reasoning from
a family list; the power audit later showed none could answer its own
question. A Track D that would have caught that before the campaign ran
has paid for itself.


---

## Long-term architecture (destination, not current work)

```
Data Acquisition                    (Track B-ii)
        ↓
Research Validation                 (Track A-i gates, A-ii campaigns)
        ↓   signal quality: hit rate, magnitude, causality, bootstrap,
        ↓   walk-forward, regime robustness, power, cost, tax
Historical Validation               (Track A-i — HVL, not yet triggered)
        ↓   trade quality: entries/exits, SL/TP, fees, slippage,
        ↓   liquidity, expectancy, profit factor, R-multiple, drawdown
Governance                          (reviewer ≠ researcher — the one
        ↓                            deliberate human-judgment gate)
Paper Trading                       (Track B-i — real execution-condition
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
