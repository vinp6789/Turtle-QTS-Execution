# ROADMAP.md

**Future work only — this document answers "where are we going," nothing
else.** For current state, completed milestones, backlog, blockers, and
risks, see `PROJECT_STATE.md` — the single authoritative execution-state
document. `CHANGELOG.md` and `docs/RESEARCH_LEDGER.md` are the permanent
record of what has already shipped.

Ordered by **value**, not implementation difficulty, within each
category, per `PROJECT_CONSTITUTION.md`. **An item's presence here is not
authorization to build it now** — each still needs its own proposal and
approval per `REVIEW_PROTOCOL.md`, and per Constitution §5 (Simplicity),
nothing is built ahead of a concrete, present need. Every trigger
condition stated below is the actual gate — not a suggestion.

---

## 1. Research (highest overall value)

Until at least one alpha model clears governance, every other capability
on this roadmap (library curation, model combination, watchlist ranking,
paper/live trading) has nothing to operate on. Research remains the
project's single highest-value lever, and the cheapest remaining work —
the research harness is already built and proven across five campaigns.

### 1.1 Liquidations (Campaign 06) — in the prerequisite chain now

Sequenced exactly (see `PROJECT_STATE.md` Immediate Backlog for full
detail and dependencies):

1. Storage durability fix + evidence-store git tracking (engineering
   prerequisite, not research).
2. `collect_liquidations()` + CLI entry point + declared dependencies.
3. Outcome series 2025-07-27 → present: **Hyperliquid-native daily
   candles as the primary outcome reference** (DEX-first, Constitution
   §4/§6 — CEX is never the production reference), Binance metrics as a
   secondary cross-venue check only.
4. Full 12-month liquidation backfill — **single pass, all symbols
   retained**. A staged/partial backfill was considered and rejected:
   walk-forward validation requires chronological contiguity, and
   selecting which months to sample would itself be an un-pre-registered
   researcher judgment call.
5. Outcome-blind feasibility review reporting **effective sample size
   (N_eff) and cross-symbol correlation** — not raw signalled counts.
   Measured on the one-month pilot: cross-symbol correlation of daily
   liquidation counts is **+0.85 to +0.90**, meaning BTC/ETH/SOL behave as
   roughly **1.1 effective independent symbols, not 3**. **This review may
   reject Campaign 06 outright — that is the intended, cheapest possible
   outcome of the gate, not a failure of it.**
6. Pre-registration — **only if** step 5 passes, following
   `RESEARCH_PLAYBOOK.md` in full, including the restored
   governance-inspection clause (§1.5 below).

### 1.2 Next Funding/OI campaign — deep-history backfill first

**BTC-only Funding momentum, properly powered** remains the strongest
funding candidate not yet retried (CAMP-02 Binance 0.686/n=35, CAMP-03
Hyperliquid 0.580/n=138 — both underpowered in isolation). Before its
fresh pre-registration:

- **Deep-history backfill** — funding rate back to 2020-01 (BTC/ETH) /
  2020-09 (SOL); OI + mark-price metrics back to 2021-01 (BTC) / ~2022-01
  (ETH/SOL). Verified free and available via Binance's public archive,
  zero new code (existing `collect_funding_rate`/`collect_metrics`).
  Roughly triples usable funding history.
- Any campaign using the deep window **must declare, as `known_limitations`
  under RD-11 A**: (a) **survivorship bias** — a 2026-chosen watchlist
  tested against 2020–21 conditions where SOL fell ~96% and was widely
  considered terminal; (b) **non-stationarity** — the window spans two
  halvings, LUNA, FTX, and the ETF era, which bears on any full-sample
  threshold derivation; (c) **asymmetric per-symbol start dates** — a
  compositional break that sample construction must not silently pool
  across.
- This backfill is **orthogonal to Campaign 06** and does not gate it —
  it gates only the next funding/OI campaign.

### 1.3 Remaining OI mechanisms

- **Open Interest Divergence** — the sole untested OI mechanism (per
  RD-05), under the same DEFER-ceiling as Campaigns 01/05 (no Hyperliquid
  OI history → knowledge-only until a live OI recorder lifts it).
- **Longer-horizon OI hypotheses** (3–7 day forward return) — Campaign 01
  tested only 24h.

### 1.4 Combined-feature and future families

- **Combined OI + Funding** — only after both individual sources have
  independent evidence; first trigger for a multi-feature candidate type
  and the attribution validation stage (needs ≥2 ablatable features).
- **Stablecoin flows, on-chain metrics, macro liquidity, cross-asset
  data** — in that priority order (`docs/RESEARCH_PLAN.md` §3). Each
  needs a new provider/feature/candidate triple; on-chain/macro
  additionally need point-in-time discipline against vendor data
  revision.
- **Strategy-agnostic framework principle (unchanged):** any tradable
  idea competes under the identical pipeline; no family gets exemption.
  **Technical-indicator families (OHLCV-derived conviction) remain
  permanently rejected** (Constitution §4) and are not an open research
  slot — revisit only with a specifically-argued, pre-registered
  justification that context materially differs from the original
  rejection.

### 1.5 Governance-inspection clause (documentation, precedes everything above)

Constitution §7 requires that "a candidate with a favorable hit rate but
non-positive expectancy is still a rejection," citing an acceptance
discipline in `RESEARCH_PLAYBOOK.md` that does not currently exist there
in that form — the inspection was applied at CAMP-01's governance review
and silently dropped from CAMP-02–05. Restoring this as an explicit
Playbook §2 clause (governance inspects mean directional return /
expectancy sign, not just hit rate, at review time) must land **before**
any future campaign's pre-registration, including Campaign 06's.

---

## 2. Engineering (build only when a specific campaign needs it)

1. **Historical Validation Layer (HVL)** — the net-of-cost gate between
   Research Campaigns and Paper Trading. **Trigger: the first campaign
   producing a SUPPORTED hypothesis. Nothing is built before that.**
   Recorded scope (RD-11 deferred set, refined by the liquidation pilot):
   - True chronological walk-forward recalculation (rolling
     thresholds/normalizations, no future-derived quantities).
   - Trade simulation: frozen stop-loss methodology (never widened during
     evaluation), frozen take-profit methodology, fixed risk assumptions.
   - Realistic fees, realistic slippage, liquidity constraints — and,
     specifically for any liquidation-triggered strategy, **event-conditional**
     slippage/liquidity (a liquidation fires precisely when liquidity is
     worst; average-book assumptions would be systematically optimistic).
   - Profit factor · expectancy · average R multiple · max drawdown ·
     equity curve · before-vs-after walk-forward comparison.
   - **Episode-level metrics and effective sample size as first-class
     reported statistics**, not footnotes — added after the pilot showed
     top-10 days can carry 65% of a month's liquidation events; trade
     count/win rate/profit factor alone would silently overstate
     confidence under that concentration.
   - **Block bootstrap under dependence** (or an explicit recorded
     limitation) wherever resampled events are not exchangeable — the
     existing IID bootstrap stage would otherwise report intervals
     narrower than reality whenever cross-sample correlation is material.
   - Every validation report carries **both signal metrics and trade
     metrics, reported separately** — this is what keeps the Research
     Validation / Historical Validation boundary sharp at reporting time,
     not just at build time.
   - The existing reporting caveat (RD-11 D) stays **exactly as worded**
     until true rolling out-of-sample walk-forward exists to justify
     strengthening it — reviewed and reaffirmed, not a placeholder.
   - The deferred Constitution no-hindsight amendment lands with this
     layer, not before.
   - **Not a separate "Robustness Validation" layer.** Monte Carlo and
     parameter sensitivity belong to Research (nothing is fitted, so this
     is threshold-choice sensitivity); fee/slippage/spread/fill stress
     belong to the HVL (they require the same trade simulator this layer
     already builds); execution delay and randomized fills belong to
     **Paper Trading**, where real execution conditions are actually
     observed. A fourth layer built on zero concrete instances would be
     the exact premature abstraction Constitution §5 forbids — if HVL's
     stress checks ever need their own lifecycle/governance/cadence, that
     is the second concrete need and the honest moment to split, not now.

2. **Live Sample Recorder.** Captures live provider readings + realized
   outcomes into a durable research dataset automatically. Genuinely
   high-leverage in the long run — it is the only mechanism that
   converts a `Data: NONE` family into `COLLECTING`, and the only
   prerequisite that can ever lift the OI DEFER-ceiling — but its payoff
   has a long lead time: every archive-based campaign to date has needed
   12–18 months of history before being testable, so a recorder started
   today enables its first campaign roughly that far out. **Build when a
   campaign or paper-trading effort actually needs it — deliberately
   scheduled last in this section, not preemptively promoted.**

3. **Alpha Library formalization** (thin, mostly-documentation layer over
   data the registry already durably holds). Worth building once 2–3
   models are approved; nothing to curate before then beyond the closed,
   rejected campaigns already in `RESEARCH_LEDGER.md`/`ALPHA_LIBRARY.md`.

4. **Watchlist-driven automatic evaluation + a scheduler.** Wait until
   ≥2 proven candidate families justify automating a loop around them.

5. **Model-combination/weighting policy** (`portfolio/selection.py` beyond
   dedupe-or-refuse). Meaningless until ≥2 approved models can actually
   agree or disagree on the same asset.

6. **Watchlist ranking + rank-based TradeIntent generation.** Lowest
   engineering priority — nothing to rank with a zero-to-one-model
   library.

---

## 3. Operations

1. **First paper-trading deployment**, once (if) a model is approved.
   Cannot be scheduled ahead of research success.
2. **Monitoring routing.** Structured logging already exists throughout
   the Alpha Engine; nothing routes it to a real destination yet — needed
   once anything runs unattended.
3. **An agreed degradation-review operating cadence** (who re-validates
   live samples, how often) — an operational decision, needed before the
   first live-approved model.
4. **Telegram Operations Console (tiered, gated).** Evolve today's
   notification/emergency-stop Telegram layer (`app/telegram/`) into a
   remote monitoring + operations surface. **Build only when paper/live
   trading is actually imminent** — nothing trades today, so a full ops
   console has nothing to operate yet. Four-level maturity model, carried
   forward unchanged:
   - **Monitoring** (read-only) — portfolio/positions/orders/PnL/heat/
     health/explainability views.
   - **Notifications** (event fan-out) — trade/risk/system events, plus a
     **heartbeat/liveness alert** ("no cycle completed in N minutes") as
     the single most important notification for an unattended system,
     since silence itself is the danger signal; reconciliation
     discrepancies and alpha degradation/freeze events belong in the same
     set (zero new logic — the underlying data already exists).
   - **Operations** (capital-affecting, confirmation-gated) — close %,
     cancel order, pause/resume; two-step typed confirmation echoing the
     exact consequence, ideally a second factor beyond chat-id.
   - **Explainability** — deterministic retrieval of evidence/decision/
     risk records only; the LLM formats retrieved facts, **never infers
     them**.

   **Hard constraints, non-negotiable, carried forward verbatim:**
   - **One path only.** Every channel (Telegram, REST, any future web
     dashboard/mobile app/CLI) goes through the existing single
     Operations Service (`app.api.service` today) and engine-routed
     `AppState` control methods — never a parallel path around
     order/risk managers, never duplicated business logic in a client.
     The service owns no state: a read facade over the Execution Engine
     (capital/execution) and, strictly read-only, the Alpha Engine
     registry (display governance/lifecycle/regime/campaign state; never
     a write/approve/mutate path — preserving Constitution §4's
     one-directional dependency).
   - **Forbidden via any operational channel, structurally, not just by
     policy:** approving/rejecting alpha, changing thresholds/specs/
     validation rules/research parameters, bypassing Risk Manager or
     Governance, overriding sizing/leverage, and **switching to Live
     Mode** — which stays a deliberate out-of-band operator action
     (Constitution §9).
   - **Operating principle: the human supervises, the system operates.**
     Normal operation requires no human intervention (already true of
     `app/runtime/worker.py`'s `CycleWorker` loop); the operator's role is
     to observe, intervene, and stop — never to be a required step.
     **Watch item:** notification volume must never degrade into de
     facto unsupervised operation through alert fatigue.

---

## 4. Deployment (Execution Engine — independent of Alpha Engine research)

Gated on operator action, not on any Alpha Engine research outcome; can
proceed in parallel with the research track:

1. Move the plaintext `env` file to `.env` and decide on wallet-key
   rotation before any mainnet use (`FINAL_PRODUCTION_AUDIT.md` SEC-1).
2. Testnet spot→perp balance transfer + a live-mode testnet config
   (`FINAL_PRODUCTION_AUDIT.md` §4) — required before any testnet
   validation run.
3. Fix `AppState.last_error` never clearing (`FINAL_PRODUCTION_AUDIT.md`
   OBS-1) before gating a soak test's pass/fail criterion on it.
4. Execute the full testnet checklist and a 24–72h soak
   (`docs/PRODUCTION_CHECKLIST.md`).
5. Mainnet rollout — **NO-GO** until items 1–4 above are complete.
6. Route `data/alpha_engine_historical` through `config/loader.py` with an
   environment override; declare a persistent Railway volume
   (`railway.json` currently declares none — `data/` is ephemeral there,
   which will affect live trading, not just research, if left unfixed).

---

## 5. Long-term architecture (destination, not current work)

```
Data Acquisition
        ↓
Research Validation   (signal quality: hit rate, magnitude, causality,
        ↓              bootstrap, walk-forward, regime robustness, power)
Historical Validation  (trade quality: entries/exits, SL/TP, fees,
        ↓              slippage, liquidity, expectancy, profit factor,
        ↓              R-multiple, equity curve, drawdown)
Governance             (independent review, reviewer ≠ researcher —
        ↓              the one deliberate human-judgment gate)
Paper Trading          (includes real execution-condition stress: delay,
        ↓              randomized fills, spread widening)
Live Trading  ⟷  Execution Engine (independent, frozen, veto authority —
        ↓         owns sizing, leverage, portfolio exposure, kill
        ↓         switches, max drawdown enforcement, max daily loss,
        ↓         correlation limits; never moves into HVL or Research)
Monitoring / Degradation / Retirement
        ↺
   [back to New Hypothesis — this loop IS "self-improving" per
    Constitution §8: there is no live parameter learning, only a new,
    separately pre-registered experiment]
```

**Data Acquisition is named here as a first-class concern**, not an
implementation detail — six of nine research families are currently
`Data: NONE`, and every campaign to date has ultimately been limited by
whether history existed and how correlated it was, not by a shortage of
hypotheses.

**Token Intelligence / Portfolio Intelligence** (further downstream, not
yet triggered by anything): `Research → Approved Alpha Library → Token
Intelligence → Portfolio Intelligence → Execution Engine → Paper Trading
→ Production`. Token Intelligence accumulates validated per-token/per-
regime alpha evidence (read-only, grown only through research and paper
trading, never live mutation). Portfolio Intelligence makes
portfolio-level decisions atop that evidence. The Execution Engine
remains sole owner of sizing, leverage, liquidation protection, portfolio
heat, correlation management, and risk — an alpha never produces
leverage, only research opinions and evidence.

- **Portfolio Memory** (Portfolio Intelligence sub-capability): learn
  portfolio-level interactions — which alphas diversify each other, which
  tokens become highly correlated, historical portfolio drawdown
  behavior. Prerequisite: ≥2 approved alphas trading/paper-trading
  simultaneously.
- **Confidence Calibration** (future risk-layer input, never a sizing
  decision itself): before any alpha's stated confidence influences
  leverage/sizing, verify via paper trading that it is historically
  calibrated. Prerequisite: ≥1 approved alpha with a long-enough
  paper-trading track record.

## 6. Other long-term ideas (not yet scheduled; recorded so they aren't lost)

- Authenticated reviewer identity for governance (today enforced on plain
  strings — a real but narrow limitation).
- SQLite (or similar) `RegistryStorage` backend, if concurrent-writer
  needs ever emerge (today's file-based storage is acceptable for the
  current single-operator posture).
- Monte Carlo / risk-of-ruin validation at the **portfolio** level (needs
  portfolio equity-curve machinery not yet built — once multiple approved
  models trade simultaneously).
- Calibration + purge/embargo validation stages (need a probabilistic or
  fitted candidate type — today's candidates are fixed-threshold rules
  only).
- A concrete adapter for **Lighter** — the future supported venue named
  in the frozen `exchange_adapter`'s own docstring alongside Hyperliquid —
  if/when the strategy needs a second DEX venue. The production target
  remains decentralized perpetual exchanges exclusively; a centralized
  exchange is never a live candidate.

---

## Integration rules for any future Execution Engine work (unchanged)

Per `docs/DEVELOPMENT_WORKFLOW.md` and `docs/CLAUDE_ONBOARDING.md`:
additive-only, no change to any frozen module's public API, depend only
on already-frozen lower-numbered modules, persist state through the event
store, ship a dedicated test file, no dependency cycles, full regression
green plus explicit approval before freeze.

## Integration rules for any future Alpha Engine work (unchanged)

Per `PROJECT_CONSTITUTION.md` and `alpha_engine/DECISIONS.md`: additive
only, zero import of a frozen Execution Engine package (test-enforced),
deterministic (injectable clock/seed, canonical timestamps, content
fingerprints), every new capability ships comprehensive tests, and no
architecture/infrastructure is built ahead of a concrete, currently-active
need.

> Nothing in this roadmap is scheduled or committed by the mere fact of
> being listed here — each item still requires its own proposal,
> pre-registration (for research) or plan (for engineering), and explicit
> approval before work begins.
