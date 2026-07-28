# ROADMAP.md

**Future work only.** Completed work is not listed here — see
`PROJECT_STATUS.md` for current state and `docs/RESEARCH_LEDGER.md` /
`docs/ALPHA_ENGINE.md` §8 for what has already shipped. Ordered by
**value**, not implementation difficulty, within each category, per
`PROJECT_CONSTITUTION.md`. Do not build ahead of a concrete, present need
(§5, Simplicity principle) — an item's presence here is not authorization
to build it now; each still needs its own proposal and approval per
`REVIEW_PROTOCOL.md`.

The prior version of this file was Execution-Engine-only and predates
Module 10, the app layer, and the entire Alpha Engine — all of that work
is now complete (see `PROJECT_STATUS.md`) and has been removed from this
list. `CHANGELOG.md` and `docs/RESEARCH_LEDGER.md` are the permanent
record of what shipped.

---

## 1. Research (highest overall value — see rationale below)

Until at least one alpha model clears governance, every other capability
in this roadmap (library curation, model combination, watchlist ranking,
paper/live trading) has nothing to operate on. Research is therefore the
project's single highest-value lever right now, and it is also the
**cheapest** remaining work — the research harness (`run_research_cycle`,
the five validation stages, the historical pipeline) is already built and
proven end-to-end by Campaign 01.

Campaign 01 (Open Interest level), Campaign 02 (Funding Rate, absolute
threshold), and Campaign 03 (Funding Rate, venue-relative threshold) are
all closed and REJECTED — see `docs/RESEARCH_LEDGER.md`. Campaign 03
removed Campaign 02's venue-transfer confound (each venue tested against
its own correctly-derived threshold) and still found no edge — funding
*level* has now been tested twice, both venues, both threshold
methodologies, which directly shapes priority #1 below.

1. **BTC-only Funding momentum, properly powered** (Campaign 03's own
   evidence-based recommendation, highest priority). The strongest
   single-symbol reading across both funding campaigns (CAMP-02 Binance
   0.686/n=35; CAMP-03 Hyperliquid 0.580/n=138), both underpowered or
   sub-bar in isolation — Binance's deeper (2020+) BTC-only history could
   resolve whether it is real, under its own fresh pre-registration
   (including its own feasibility review — see CAMP-03's lessons on
   per-fold chronological clustering).
2. **Open Interest velocity/change.** Distinct from the now-closed
   OI-*level* hypothesis (Campaign 01): tests whether the *rate of
   build-up/unwind* carries information the static level does not.
   Requires a new (small) rolling-delta feature, following the same
   pattern as the existing percentile-rank/z-score features.
3. **Longer-horizon OI hypotheses** (3–7 day forward return). Campaign 01
   tested only 24h; a distinct, separately pre-registered horizon may
   reveal information the short horizon does not.
4. **Combined OI + Funding.** Only after both individual sources have
   their own evidence — testing a combination before either component is
   understood in isolation is not a meaningful experiment. First trigger
   for building a multi-feature candidate type (and, subsequently, the
   attribution validation stage, which needs ≥2 ablatable features).
5. **Stablecoin flows, on-chain metrics, macro liquidity, cross-asset
   data** — in that priority order, per `docs/RESEARCH_PLAN.md` §3. Each
   requires a new provider/feature/candidate triple (no code exists for
   any of them yet) and, for on-chain/macro specifically, extra
   point-in-time discipline (vendor data revision risk — see
   `docs/RESEARCH_PLAN.md` §2).

**DEX-first note on sourcing (`PROJECT_CONSTITUTION.md` §6,
`docs/HISTORICAL_DATA.md` §0):** the venue-relative-threshold discipline
applies to items 1–4 above — all exchange-native metrics (funding, open
interest) where a CEX/DEX distinction is meaningful. It does not
meaningfully apply to item 5 — stablecoin flows, on-chain metrics, macro
liquidity, and cross-asset data are venue-agnostic by nature, not sourced
from any particular exchange, so there is no equivalent "venue's own
history" to derive a relative threshold against for those sources.

**Strategy-agnostic framework (principle, not a scheduled campaign).**
The research framework is deliberately **strategy-agnostic**: any
tradable idea — exchange-native microstructure, on-chain/macro, or a
price-derived technical indicator — is just another *research family*
and competes under the exact same pipeline (pre-registration →
five-stage validation → sealed evidence → reviewer-separated governance
→, only if approved, the promotion path). Indicators get no special
treatment and no exemption; an approved alpha of any family emits only
direction + (future) confidence + evidence, and the frozen Execution
Engine alone owns sizing, leverage, risk, and capital allocation
(`PROJECT_CONSTITUTION.md` §5, §7). This is already how the platform is
built (a generic `Strategy` seam and candidate catalog), so it is
recorded here as an explicit anti-bias principle, not new scope.
**Important constraint — technical-indicator families are NOT an open
research slot today.** The OHLCV-derived conviction family (relative
strength, trend, momentum, volume expansion, ATR/Donchian squeeze, OBV —
i.e. essentially the EMA/RSI/MACD/ATR/Supertrend/Donchian space) was
**already exhaustively tested and permanently rejected on evidence**
(`PROJECT_CONSTITUTION.md` §4). Per the rejected-hypothesis rule
(`docs/RESEARCH_PLAYBOOK.md` §1, `PROJECT_CONSTITUTION.md` §6), such a
family may be revisited **only** with a specifically-argued,
pre-registered justification that the context is materially different
from the original rejection (e.g. DEX-perp venue, this specific
watchlist, a current regime, or a specific indicator/combination
provably outside the original sweep) — never as a blanket "indicators
are just another family, test them all." Any per-token "best strategy"
knowledge (Token Intelligence) is likewise built only from
independently governance-approved per-(alpha, token) evidence, never by
selecting each token's backtest winner (which, across ~10 tokens × many
families, would be chosen by chance).

## 2. Engineering (build only when a specific campaign needs it)

1. **Live sample recorder.** The single most-leveraged remaining piece of
   infrastructure: captures live provider readings + realized outcomes
   into a durable research dataset automatically. Unblocks real
   degradation testing (currently untested against real live data),
   live-validated rolling-window features, and eventually paper trading
   with genuine (not backfill-proxy) samples. Build when a campaign or
   paper-trading effort actually needs it — not preemptively.
2. **Historical Validation Layer** — the net-of-cost gate between
   Research Campaigns and Paper Trading. **Trigger: the first campaign
   producing a SUPPORTED hypothesis.** Nothing is built before that; this
   entry exists so the sequencing gap is not lost (today the roadmap runs
   campaigns → paper trading with no step establishing that a *gross*
   signal edge survives *net* of costs). Recorded scope
   (`docs/RESEARCH_DECISIONS.md` RD-11 deferred set): true chronological
   walk-forward recalculation (rolling thresholds/normalizations) · trade
   simulation · frozen stop methodology · frozen take-profit methodology ·
   realistic fees · slippage · liquidity constraints · profit factor ·
   expectancy · average R · max drawdown · equity curve · before/after
   comparison · realistic capital preservation · **a strict prohibition on
   widening a stop-loss during evaluation**.

   When this layer exists, every validation report should carry: win rate ·
   profit factor · expectancy · average R · max drawdown · equity curve ·
   walk-forward comparison · before-vs-after comparison — and the caveat
   *"Backtests flatter. The fixed matrix shows uglier, truer numbers —
   those are the only ones worth trading."* (This stronger wording
   **replaces** the interim caveat in `RESEARCH_PLAYBOOK.md` §3 only once
   genuinely rolling out-of-sample walk-forward exists to justify it.) The
   deferred Constitution no-hindsight amendment lands with this layer, not
   before.

3. **Alpha Library formalization** (a thin, mostly-documentation layer
   over data the registry already durably holds). Worth building once 2–3
   models are approved; not before, since there is currently nothing to
   curate beyond the two rejected campaigns already recorded in
   `docs/RESEARCH_LEDGER.md` and `docs/ALPHA_LIBRARY.md`.
4. **Watchlist-driven automatic evaluation + a scheduler.** Wait until ≥2
   proven candidate families justify automating a loop around them —
   automating a loop around zero-to-one approved models is premature.
5. **Model-combination/weighting policy** (upgrading
   `portfolio/selection.py` beyond dedupe-or-refuse). Meaningless until
   ≥2 approved models can actually agree or disagree on the same asset —
   already named as deferred, governance-owned future work in that
   module's own docstring.
6. **Watchlist ranking + rank-based (top-N-only) TradeIntent generation.**
   Lowest engineering priority: ranking among approved opportunities has
   no content with a zero-to-one-model library. Conceptually simple to
   build later; correctly last because it has nothing to rank today.

## 3. Operations

1. **First paper-trading deployment**, once (if) a model is actually
   approved. Cannot be scheduled ahead of research success.
2. **Monitoring routing.** Structured logging exists throughout the Alpha
   Engine (audit finding B4); nothing routes it to a real destination yet
   — needed once anything is actually running unattended.
3. **An agreed degradation-review operating cadence** (who re-validates
   live samples, how often) — an operational decision, not a build; needs
   to exist before the first live-approved model, not before.
4. **Telegram Operations Console (tiered, gated).** Evolve today's
   notification/emergency-stop Telegram layer (`app/telegram/`) into a
   remote monitoring + operations surface — **build only when paper/live
   trading is actually imminent** (nothing trades today, so a full ops
   console has nothing to operate; building it now would be premature per
   §5's simplicity principle). A natural four-level maturity model:
   *Monitoring* (read-only) → *Notifications* (event fan-out) →
   *Operations* (capital-affecting, confirmation-gated) →
   *Explainability* (deterministic retrieval of evidence/decision/risk
   records — the LLM formats retrieved facts, never infers them). Hard
   constraints, non-negotiable:
   - **One path only — the shared Operations Service.** Every channel
     (Telegram, REST, any future web dashboard / mobile app / CLI) must
     go through the existing single service layer (`app.api.service`
     today) and engine-routed `AppState` control methods — never a
     parallel path around the order/risk managers, and never any
     duplicated business logic in a client. A "close position" is itself
     a trade and must take the same `order_manager`/`risk_manager` route
     as any order. This Operations Service **owns no state**: it is a
     read *facade* over two authoritative stores — the Execution Engine
     (capital/execution state) and, for research/alpha monitoring, the
     Alpha Engine registry — the latter accessed **strictly read-only**
     (display governance/lifecycle/regime/campaign state; never a write,
     approve, or mutate path into `alpha_engine`, preserving the
     one-directional dependency of `PROJECT_CONSTITUTION.md` §4).
   - **Tiers.** *Read-only* (portfolio/positions/orders/PnL/heat/health/
     explainability) — chat-id gate sufficient; mostly formatters over
     existing `service` dicts. *Emergency* (stop, soft-pause) —
     asymmetric-safe, already exists, keep easy. *Capital-affecting
     operations* (close %, cancel order, pause/resume) — require two-step
     typed confirmation echoing the exact consequence, ideally a second
     factor beyond chat-id.
   - **Forbidden via any operational channel** (structurally, not by
     policy alone): approving/rejecting alpha, changing thresholds/specs/
     validation rules/research parameters, bypassing Risk Manager or
     Governance, overriding sizing/leverage — **and switching to Live
     Mode**, which stays a deliberate out-of-band operator action
     (`PROJECT_CONSTITUTION.md` §9, human approval before production).
     The app layer's current zero coupling to `alpha_engine` already
     makes the research/governance items structurally impossible — keep
     it that way; never wire the console into the research path.
   - **Explainability answers must be deterministic retrieval** from
     evidence/decision/execution records, never generative inference.
   - **Operating principle: the human supervises, the system operates.**
     Normal operation (data collection, running approved alphas,
     TradeIntent generation, sizing/leverage, order/position management,
     continuous risk monitoring) requires no human intervention — this is
     already true of `app/runtime/worker.py`'s continuous `CycleWorker`
     loop, not a new capability. The operator's role is to observe
     everything, intervene, and stop at any time — never to be a required
     step in a normal cycle. This restates `PROJECT_CONSTITUTION.md` §9/
     §10 operationally; it grants no new authority and removes none.
     **Watch item, not solved by design:** notification volume must never
     be allowed to degrade into de facto unsupervised operation through
     alert fatigue — a heartbeat/liveness alert ("no cycle completed in N
     minutes") is the single most important notification for an
     unattended system, since silence itself is the danger signal.
     Reconciliation-discrepancy and alpha degradation/freeze events
     belong in the notification set alongside the trade/risk/system
     events already implied above — all zero-new-logic, since the
     underlying data (`reconciliation.discrepancies`,
     `assess_degradation`/`freeze_degraded`) already exists.

## 4. Deployment (Execution Engine — independent of Alpha Engine research)

These are gated on operator action, not on any Alpha Engine research
outcome, and can proceed in parallel with the research track:

1. Move the plaintext `env` file to `.env` (already git/docker-ignored)
   and decide on wallet-key rotation before any mainnet use — outstanding
   from `FINAL_PRODUCTION_AUDIT.md` (SEC-1).
2. Testnet spot→perp balance transfer + a live-mode testnet config
   (`FINAL_PRODUCTION_AUDIT.md` §4) — required before any testnet
   validation run.
3. Fix `AppState.last_error` never clearing (`FINAL_PRODUCTION_AUDIT.md`
   OBS-1) before gating a soak test's pass/fail criterion on it.
4. Execute the full testnet checklist (place/query/amend/cancel/
   cancel-all/emergency-stop/restart/replay/accounting validation) and a
   24–72h soak, per `docs/PRODUCTION_CHECKLIST.md`.
5. Mainnet rollout — **NO-GO** until items 1–4 above are complete, per
   `FINAL_PRODUCTION_AUDIT.md`'s explicit verdict.

## 5. Long-term ideas (not yet scheduled; recorded so they aren't lost)

- **Approved long-term architecture (destination, not current work):**
  `Research → Approved Alpha Library → Token Intelligence → Portfolio
  Intelligence → Execution Engine → Paper Trading → Production`. Token
  Intelligence accumulates validated per-token/per-regime alpha evidence
  (read-only, grown only through research and paper trading, never live
  mutation). Portfolio Intelligence makes portfolio-level decisions atop
  that evidence. The Execution Engine remains sole owner of sizing,
  leverage, liquidation protection, portfolio heat, correlation
  management, and risk — an alpha never produces leverage, only research
  opinions and evidence. None of this is built now; each layer activates
  only once the layer below it has real content to operate on (see the
  two items below for the nearest examples). This entry exists so the
  approved destination survives beyond this conversation, not as new
  scope.
  - **Portfolio Memory** (future Portfolio Intelligence sub-capability):
    learn portfolio-level interactions — which alphas diversify each
    other, which tokens become highly correlated, historical portfolio
    drawdown behavior, interaction between simultaneous positions.
    Prerequisite: ≥2 approved alphas trading (or paper-trading)
    simultaneously — there is nothing to observe interacting before
    then. Build only when Portfolio Intelligence itself is triggered.
  - **Confidence Calibration** (future risk-layer input, not a sizing
    decision): before any alpha's stated confidence is allowed to
    influence leverage or sizing, verify through paper trading that the
    confidence is historically calibrated (i.e., "high confidence"
    predictions actually hit more often). Confidence remains an INPUT to
    the Execution Engine's risk layer, never a direct sizing output of
    an alpha. Prerequisite: at least one approved alpha with a
    paper-trading track record long enough to check calibration against.
- Authenticated reviewer identity for governance (today, reviewer
  separation is enforced on plain strings — a real but narrow limitation).
- SQLite (or similar) `RegistryStorage` backend, if concurrent-writer
  needs ever emerge (today's `FileRegistryStorage` is per-append-locked
  but not session-held, which is acceptable for the current
  single-operator posture — see `docs/ALPHA_ENGINE.md` §5).
- Monte Carlo / risk-of-ruin validation (needs portfolio equity-curve
  machinery not yet built — needed once multiple approved models trade
  simultaneously).
- Calibration + purge/embargo validation stages (need a probabilistic or
  fitted candidate type — today's candidates are fixed-threshold rules
  only).
- A concrete adapter for **Lighter** — the future supported venue named
  in the frozen `exchange_adapter`'s own docstring alongside Hyperliquid
  (`PROJECT_CONSTITUTION.md` §4) — if/when the strategy needs a second DEX
  venue. No current driver for this; the production target remains
  decentralized perpetual exchanges exclusively (Hyperliquid primary,
  Lighter future) — a centralized exchange is never a candidate here.

## Integration rules for any future Execution Engine work (unchanged)

Per `docs/DEVELOPMENT_WORKFLOW.md` and `docs/CLAUDE_ONBOARDING.md`:
additive-only, no change to any frozen module's public API, depend only
on already-frozen lower-numbered modules, persist state through the event
store, ship a dedicated test file, no dependency cycles, full regression
green plus explicit approval before freeze.

## Integration rules for any future Alpha Engine work

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
