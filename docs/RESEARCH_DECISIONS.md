# RESEARCH_DECISIONS.md — Research Program Decision Log

**Organizational memory: the *why* behind research-program decisions.**
This log records cross-campaign decisions and rationale — which family or
mechanism was prioritized, paused, retired, or deferred, and why — that
the per-campaign scientific record (`RESEARCH_LEDGER.md`), the model
catalog (`ALPHA_LIBRARY.md`), and the software decision logs
(`docs/ARCHITECTURE_DECISIONS.md`, `alpha_engine/DECISIONS.md`) do not
capture. It is the research-program analogue of those two software
decision logs.

**This document is DESCRIPTIVE, never NORMATIVE.** It records what was
decided and why; it does not dictate what must be done. When a decision
hardens into a durable rule, that rule is promoted *into* the Constitution
or the Playbook and this entry references it — the entry never becomes the
rule itself. It is consulted by humans, never consumed by automation, and
it never feeds sizing, promotion, prioritization, or any live path.

**Integrity model:** append-only, enforced by git history + immutable
`RD-NN` IDs + supersede-don't-edit (there is no in-repo checksum — this is
a human-authored narrative, and git is its tamper record). **No entry may
contain a prediction of future performance or an "expected winner"** —
only decisions and their rationale. Reversed and mistaken decisions are
recorded too, never quietly removed.

**Per-entry fields:** ID · date · author · reviewer · category · scope ·
decision · evidence references · revisit triggers · status · supersedes /
superseded-by. Every entry separates *evidence* (what was measured) from
*judgment* (what was concluded).

---

## RD-01 — Alpha Library admission is per-experiment and absolute; independence is a deployment concern

- **Date:** 2026-07-24 · **Author:** researcher (this session) · **Reviewer:** pending human confirmation · **Category:** governance-boundary · **Status:** active
- **Scope:** the meaning of "earns a place in the Alpha Library" vs. "is deployed with capital."
- **Evidence:** governance evaluates a candidate against its own pre-registered acceptance criteria only (`alpha_engine.governance`, verified); `alpha_engine/portfolio/selection.py` contains no correlation/independence logic; `RESEARCH_PLAYBOOK.md` §5 (approval) and §6 (promotion) are distinct gates; `ALPHA_LIBRARY.md` is a knowledge catalog spanning rejected/retired entries.
- **Decision (judgment):** Alpha Library admission (governance approval) is **per-experiment and absolute** — a valid alpha earns a Library place regardless of its correlation with existing alphas, because the Library records *validated knowledge*, not deployed capital. **Correlation/independence is a future portfolio-construction / deployment concern, never a governance-admission criterion,** and is not an enforceable metric until a correlation-measurement capability exists (deferred, `ROADMAP.md` §2).
- **Revisit triggers:** a correlation-measurement / portfolio-construction capability is actually built; or governance is ever proposed to weigh cross-alpha independence at admission (which this entry argues against).
- **Supersedes / superseded-by:** —

## RD-02 — Research planning artifacts carry no numeric success forecasts

- **Date:** 2026-07-24 · **Author:** researcher · **Reviewer:** pending · **Category:** methodology-discipline · **Status:** active
- **Scope:** how campaigns and mechanisms are ranked in planning artifacts (portfolio map, family state).
- **Evidence:** the no-predictions rule adopted for organizational memory (this document's own header); the observed contamination risk (a "3/5 alpha probability" label becomes an inherited prior that violates outcome-blind pre-registration).
- **Decision (judgment):** research planning ranks candidates only by **verifiable properties** (novelty, data-readiness, engineering cost, DEX-transferability, N_eff-viability) — **never by a numeric estimate of the probability of finding alpha.** Ordering is justified, not forecast.
- **Revisit triggers:** none anticipated — this is a direct application of the pre-registration discipline.
- **Supersedes / superseded-by:** —

## RD-03 — Campaign selection is research-state-machine-driven; campaign numbers are documentation-only

- **Date:** 2026-07-24 · **Author:** researcher · **Reviewer:** pending · **Category:** operating-model · **Status:** active
- **Scope:** how the "next campaign" is chosen.
- **Evidence:** `RESEARCH_LEDGER.md` records campaigns append-per-completed in run order (numbers are labels applied after the fact, not a pre-committed queue).
- **Decision (judgment):** the next campaign is always the **highest-priority executable candidate** computed at runtime from the research family state machine (LOCKED / ACTIVE / PAUSED / EXHAUSTED, with a `production_capped` attribute), not a pre-committed roadmap item. Campaign numbers are historical labels. The current family-state table is maintained in this document's appendix.
- **Revisit triggers:** the state machine grows tooling (defer until campaign volume justifies it — currently documentation-only).
- **Supersedes / superseded-by:** —

## RD-04 — Funding Persistence deferred (statistically non-viable); Funding Delta chosen for Campaign 04

- **Date:** 2026-07-24 · **Author:** researcher · **Reviewer:** reviewer-campaign04 · **Category:** mechanism-prioritization · **Status:** active
- **Scope:** the choice of Campaign 04's mechanism within the Funding family.
- **Evidence (measured, outcome-blind):** Funding Persistence (elapsed-time-since-sign-flip) daily-grid lag-1 autocorrelation ≈ 0.94–0.99 → **N_eff ≈ 4–18**; negative-persistence runs near-absent (median duration 0–1h). Funding Delta (first difference) raw-delta autocorrelation negative (mean-reverting); daily-grid |delta| lag-1 0.02–0.38 → **N_eff ≈ 247–526**; sign-symmetric; rank-orthogonal to level on Binance (Spearman ≈ 0).
- **Decision (judgment):** **defer** Funding Persistence — it is economically plausible but statistically non-viable on the 18-month window (N_eff too low for the five-stage gate; one direction untestable). **Promote Funding Delta** to Campaign 04 pre-registration instead. This is a deferral (revisitable), *not* a retirement — persistence was never testably powered, so it must not be recorded as a negative result.
- **Durable methodological lesson:** **differencing converts a within-run-ramp (low-information, high-autocorrelation) feature into a high-information, low-autocorrelation one.** Any duration/state feature should be N_eff-screened outcome-blind before pre-registration; a change/difference variant is the natural remedy when N_eff is fatal. Generalizes beyond funding.
- **Revisit triggers (persistence):** a materially longer data window yielding enough independent long runs to reach adequate N_eff, or an event-per-run design on such a window.
- **Supersedes / superseded-by:** —

## RD-05 — Funding-family mechanisms near exhaustion after CAMP-02/03/04

- **Date:** 2026-07-24 · **Author:** researcher · **Reviewer:** reviewer-campaign04 · **Category:** family-status · **Status:** active
- **Scope:** the Funding research family's remaining testable mechanisms.
- **Evidence:** Funding *level* (absolute — CAMP-02; venue-relative — CAMP-03) and *delta* (CAMP-04) all REJECTED, both venues, both directions, on real 18-month data; *persistence* deferred (RD-04). CAMP-04 was well-powered (per-fold floors substantially cleared, regime-balanced) and still edgeless.
- **Decision (judgment):** the funding family's readily-testable mechanisms on the current data are **near exhaustion** (not formally EXHAUSTED — persistence remains deferred-revisitable, and regime-interaction remains untestable-on-this-window rather than rejected). Advance the research program to the next family per the operating model, rather than seeking further funding variants.
- **Revisit triggers (funding family EXHAUSTED):** persistence and regime-interaction both become testable (longer/fresh data) and are then rejected — only then does the Level-1 retirement rule apply.
- **Supersedes / superseded-by:** —

## RD-06 — Liquidations kept LOCKED: no free historical data on either venue (live-verified)

- **Date:** 2026-07-24 · **Author:** researcher · **Reviewer:** pending · **Category:** family-unlock-feasibility · **Status:** active
- **Scope:** the Liquidations family's data-availability unlock gate.
- **Evidence (live-verified read-only probe, outcome-blind):**
  - **Binance public archive** (`data.binance.vision`) `.../daily/liquidationSnapshot/BTCUSDT/` S3 listing returns **zero objects** (`IsTruncated=false`, no `Contents`) — vs. the `fundingRate` prefix which returns real zip files back to 2020-01. No liquidation data in the free archive.
  - **Binance REST** `allForceOrders` (historical liquidations) returns `{"code":400,"msg":"The endpoint has been out of maintenance"}` — decommissioned.
  - **Hyperliquid** `/info` `{"type":"liquidations"}` returns HTTP 422 "Failed to deserialize" — no aggregate liquidations request type exists.
- **Decision (judgment):** **Keep Liquidations LOCKED.** No free historical liquidation dataset exists on either venue today. Binance offers only a *live, throttled* `forceOrder` WebSocket (≤1 event/symbol/sec — a biased subset), and Hyperliquid liquidations are on-chain L1 events with no packaged historical feed. A scientifically valid campaign cannot be supported now — there is no historical data to run even an outcome-blind feasibility on.
- **NOT permanently rejected:** the family is economically strong (causal, uncrowded, DEX-native) and the data *exists* in streamable/on-chain form — only free *historical backfill* is missing. This is a data-accumulation problem, not a fundamental impossibility.
- **Unlock triggers (either):** (a) a live liquidation recorder is built and has accumulated sufficient native history (couples this family's unlock to the roadmap's live-sample-recorder engineering item; note Binance capture would still be throttled/biased — Hyperliquid on-chain capture is the sound path); or (b) a paid/free third-party historical liquidation source is verified (accepting the vendor/credential dependency the project has so far avoided).
- **Supersedes / superseded-by:** **superseded-by RD-10 — conclusion only.** RD-10 supersedes this entry's *inference* that no historical liquidation dataset exists. **The evidence recorded above (no WS liquidation channel, no REST liquidation request type) remains valid and was independently re-confirmed.** This entry is otherwise unmodified, as the permanent record of a real but scope-limited finding.

## RD-07 — Two-state research-family model (Research Status × Data Status)

- **Date:** 2026-07-24 · **Author:** researcher · **Reviewer:** pending · **Category:** operating-model · **Status:** active · **Extends:** RD-03
- **Scope:** how a research family's state is represented in the operating model.
- **Decision (judgment):** every family carries **two independent state dimensions**, never collapsed into one:
  - **Research Status** ∈ {LOCKED, ACTIVE, PAUSED, EXHAUSTED} — where the *hypothesis work* stands.
  - **Data Status** ∈ {NONE, COLLECTING, READY} — where the *historical dataset* stands.
  A family may be **LOCKED (Research) while COLLECTING (Data)** — i.e., a long-running recorder accumulates history passively while active research proceeds on other families. Insufficient historical data is therefore never a reason to abandon a family; it moves the family to `Data: COLLECTING`, not to abandonment. `cap` (production-capped) remains an orthogonal attribute (no Hyperliquid-native history → DEFER-ceiling per `RESEARCH_PLAYBOOK.md` §5).
- **Why:** decouples data accumulation (an engineering-workstream, calendar-driven activity) from hypothesis testing (a research-workstream activity), so the two never block or context-switch each other.
- **Revisit triggers:** none anticipated — this is an organizational refinement, not a methodology change (governance, validation, evidence standards, and campaign ordering are unchanged).
- **Supersedes / superseded-by:** extends RD-03's single-state family machine.

---

## RD-08 — Open Interest Velocity accepted into the program as Campaign 05 (pre-registered, DEFER-ceiling)

- **Date:** 2026-07-24 · **Author:** researcher · **Reviewer:** reviewer-campaign05 (governance at run) · **Category:** mechanism-acceptance · **Status:** active
- **Scope:** acceptance of OI Velocity as a pre-registered campaign (Campaign 05). (Promoted from the prior pending note now that the pre-registration is locked — `docs/RESEARCH_CAMPAIGN_05_oi_velocity.md`.)
- **Evidence (measured, outcome-blind; Binance OI on disk):** feature = 24h fractional OI change (scale-free — CAMP-01 verified raw OI non-stationary). Distinctness from OI level (30d %-rank): Pearson 0.08–0.12, Spearman 0.05–0.13 (nearly independent — cleanest tested). Autocorrelation daily lag-1 −0.003 to 0.125 → **N_eff ≈ 405–523**. Sign-symmetric. Stationary. Threshold-feasible at **p75 / n_folds=3** ([169,113,108] per fold).
- **Locked outlier / data-validity rule:** investigation showed the \|velocity\|≈1.0 outliers are **OI = 0.0 snapshots** (impossible values / missing-data artifacts), not genuine events; the next-largest (≤0.24) are genuine. **Rule (permanent, no future OI campaign may modify): construct a velocity sample only if both endpoint OI values are strictly > 0, else skip.** Measured effect: 5 samples skipped, max \|velocity\| 1.000→0.2405, threshold `0.037901` and folds unchanged.
- **Decision (judgment):** ACCEPTED as Campaign 05, pre-registered and locked. **Governance ceiling DEFER-only** [VERIFIED — `RESEARCH_PLAYBOOK.md` §5]: no Hyperliquid OI → cannot be APPROVED; a passing result is validated knowledge, not a promotable alpha.
- **Revisit / unlock (promotability):** a live OI recorder accumulating Hyperliquid-native history would lift the DEFER-ceiling (same blocker as OI generally).
- **Supersedes / superseded-by:** —

## RD-09 — Campaign 05 closure: no new methodological rule created

- **Date:** 2026-07-24 · **Author:** researcher · **Reviewer:** reviewer-campaign05 · **Category:** campaign-closure · **Status:** active
- **Scope:** durable methodological output of Campaign 05 (OI Velocity).
- **Decision (explicit):** **Campaign 05 produced NO new methodological rule.** It was executed entirely under the existing frozen methodology — mandatory outcome-blind feasibility (RD-04/CAMP-02 lineage), venue-relative/per-venue threshold derivation, hypothesis-vs-implementation distinction, per-fold chronological feasibility (CAMP-03 lesson), and the DEFER-ceiling already established by `RESEARCH_PLAYBOOK.md` §5. No rule was added, amended, or relaxed. This entry records that absence deliberately, so a future reader does not search for a missing rule.
- **Durable *empirical* findings (knowledge, not rules):**
  1. **Feasibility quality does not predict profitability.** OI Velocity passed every feasibility axis more cleanly than any prior feature (near-independence from level, N_eff 405–523, sign-symmetric, stationary, zero threshold ties, balanced regimes) and still produced a flat rejection. A strong feasibility establishes *testability*, never a favourable prior on outcome — the two are independent.
  2. **Fractional change is the correct normalization for a non-stationary level series** — it removed OI's ~3.4× secular drift (CAMP-01), generalizing that campaign's "normalize, never threshold the raw level" lesson to a specific transform.
  3. **Impossible values should be filtered on data validity, not outlier magnitude** — the OI>0 rule removed exactly 5 corrupt zero-OI snapshots while retaining every genuine move (max |velocity| 0.2405). Magnitude-based filtering would have been a judgment call; validity-based filtering is deterministic and pre-registrable.
  4. **The CAMP-02/03-derived feasibility discipline is now demonstrably effective** — the locked per-fold projection [169, 113, 108] was reproduced exactly in execution, so walk-forward failed on hit-rate merit rather than the structural sample-floor artifact that confounded CAMP-02 and partially CAMP-03.
- **Why no rule follows:** each finding above either confirms an existing rule working as intended (3, 4) or is an empirical property of a feature/series (1, 2). None identifies a gap in the methodology, so per the frozen operating model no rule is created.
- **Revisit triggers:** none.
- **Supersedes / superseded-by:** —

## RD-10 — Liquidations: historical data DOES exist via official S3 fill archives (supersedes RD-06's conclusion only)

- **Date:** 2026-07-28 · **Author:** researcher · **Reviewer:** pending · **Category:** family-unlock-feasibility · **Status:** active
- **Scope:** the Liquidations family's data-availability finding. **Supersedes RD-06's *conclusion*; RD-06's *evidence* stands.**
- **Corrected finding — the structural fact RD-06 missed:** **Hyperliquid liquidations are not a standalone event stream.** They are represented as a **documented optional `liquidation` field on fill records** — `FillLiquidation { liquidatedUser?, markPx, method: "market" | "backstop" }` on `WsFill`. RD-06 searched for a liquidation *stream* and correctly found none; it did not examine the *fill schema*, where liquidations actually live.
- **Evidence (official documentation + empirical probe):**
  - Liquidation data appears in three documented per-user channels: `userEvents` (`WsLiquidation { lid, liquidator, liquidated_user, liquidated_ntl_pos, liquidated_account_value }`), `userFills` (`liquidation` field on each fill), and `userNonFundingLedgerUpdates` (`WsLedgerLiquidation`). All require a `user` address — **no market-wide live feed exists.**
  - **Official first-party historical S3 archives exist:** `s3://hl-mainnet-node-data/node_fills_by_block` (fills, documented as matching the API format, therefore carrying the `liquidation` field), plus `node_fills`, `node_trades`, `replica_cmds`, `explorer_blocks`, and `s3://hyperliquid-archive/` (L2 book, asset contexts).
  - `node_trades` schema carries **no** liquidation field — confirming **fills, not trades, are the correct source**, and that no trade-level heuristic is needed or permitted.
  - **Empirically verified access gate:** anonymous listing of both buckets returns `AccessDenied — "Anonymous users cannot invoke requests against Requester Pays buckets. Please authenticate."` The buckets exist; access is authenticated and requester-pays.
- **Decision (judgment):** the historical research path for Liquidations is **official, first-party, and research-grade** — static, immutable, block-ordered, reproducible, point-in-time-safe files. The blocker has changed category: **not an absence of data, but an unacquired dependency.**
- **Verified blockers (all three must be cleared before any ingestion):**
  1. **AWS credentials required** — authenticated access only.
  2. **Requester Pays billing** — the project bears transfer costs; every data source to date has been free and key-less, so this is a genuine standing-constraint change requiring an explicit human decision.
  3. **Earliest coverage date UNVERIFIED** — official documentation states no start date; community sources suggest ~Jan 2025 but this is **not** first-party confirmed and must be established empirically before any campaign is scoped.
- **What is NOT superseded:** RD-06's live-verified evidence — no WS liquidation subscription channel (10 candidates enum-rejected identically to a deliberately fake channel while `allMids` was accepted) and no REST liquidation request type (HTTP 422 vs. 200 for `meta`). Both were independently re-confirmed during this investigation and remain the correct account of the *public real-time* surface.
- **Revisit triggers:** the credential/cost decision is made (either way); or the earliest-coverage probe returns a date that makes a campaign infeasible.
- **Supersedes / superseded-by:** **supersedes RD-06 (conclusion only).**

### RD-10 appendix — smallest implementation plan (documentation only; NOT approved to build)

Contingent on the human decision to accept a credentialed, paid AWS
dependency. **Nothing below may be built until Step 1 succeeds.**

**Step 1 — Authenticated probe of exactly ONE `node_fills_by_block`
object. Build nothing.** Verify empirically: (a) the `liquidation` field
is present *and populated* in real fill records; (b) the real payload
schema (field names, types, block/time ordering); (c) the **earliest
available date** (blocker 3); (d) that requester-pays access works and
its cost is acceptable. This mirrors the live-verification discipline
applied before every prior family (Binance/Hyperliquid funding and OI
were each probed before any collector was written). If any of (a)–(d)
fails, **stop** — Liquidations stays `LOCKED / NONE` and the finding is
recorded.

**Step 2 — Only if Step 1 succeeds.** Additive, pattern-reuse only:
- add **one** historical model (`LiquidationObservation`) to
  `alpha_engine/historical/models.py`;
- add **one** source module (`alpha_engine/historical/sources/`) for the
  Hyperliquid S3 fills archive;
- **reuse the existing historical pipeline unchanged** (`storage.py`
  CSV append/merge, validation, integrity checks).

**Explicitly forbidden** (Constitution §5 — no generalization ahead of a
second concrete need): no generic S3 abstraction, no recorder framework,
no transport layer, no new architecture. The `models + sources/<venue>`
shape is already instantiated twice (Binance, Hyperliquid), so this is
pattern-reuse, not new abstraction.

**After Step 2:** bounded backfill → integrity verification → *then* the
mandatory outcome-blind feasibility review before any liquidation
hypothesis is pre-registered. The live recorder (RD-06 trigger (a)) is
**re-classified as production infrastructure**, deferred alongside the
live-sample recorder — it is not the research-unlock path.

## RD-11 — Historical-validation methodology refinements (accepted subset; remainder deferred to the Historical Validation Layer)

- **Date:** 2026-07-28 · **Author:** researcher · **Reviewer:** pending · **Category:** methodology-refinement · **Status:** active
- **Scope:** documentation-only refinements to pre-registration, promotion, and reporting. **No frozen methodology is changed, no campaign is reopened, no machinery is built.**

### A — Derivation scope declaration (accepted, effective immediately)

Every future campaign's pre-registration must state, **for each derived
quantity** (thresholds, normalizations, rolling statistics), whether it is
derived **full-sample**, **rolling**, or **expanding-window**. The same
declaration must appear in the evidence package's `known_limitations`.
Documentation only — it imposes no derivation method, it makes the choice
explicit and auditable.

### B — Immutable research assumptions (accepted, self-activating)

**If** a campaign declares any of: stop methodology · stop distance ·
take-profit methodology · fee assumptions · slippage assumptions ·
liquidity assumptions — those values are **frozen once pre-registration is
complete**. Changing any after observing results **invalidates the
campaign**. This is the existing "no parameter changes after registration"
rule applied to trade-economics parameters; no new principle.

**Explicitly excluded — position sizing and portfolio allocation.** These
belong to the Execution Engine, not research
(`PROJECT_CONSTITUTION.md` §7; `alpha_engine/portfolio/selection.py`:
*"Capital sizing does NOT happen here… the Execution Engine's own frozen
RiskManager/portfolio-construction stack sizes every TradeIntent"*).
Freezing them as research parameters would breach the §4/§5 separation.

### C — Promotion prerequisite (accepted; verified repository finding)

**[VERIFIED]** `alpha_engine/execution_bridge/strategy.py` requires
`stop_fraction` (`required=True`) on any approved specification and
explicitly refuses to substitute one (*"the bridge never fabricates a risk
level; declare it in the pre-registered …"*). **All five completed
campaigns declare `parameters={threshold, direction_convention}` only** —
no execution parameters. This is intentional and correct: Campaigns 01–05
validate **signals**, not executable strategies.

**Consequence recorded:** a campaign specification as written today would
be **structurally undeployable** if approved — the bridge would raise.

**Rule (promotion only):** no future hypothesis may reach **APPROVED**
unless every execution-required risk parameter the bridge requires exists
in its specification. **Campaigns 01–05 are NOT retrofitted** — they are
immutable scientific history and were never promotion-candidates.

### D — Reporting caveat (accepted; wording matched to current machinery)

Added to `docs/RESEARCH_PLAYBOOK.md` §3 and required in every campaign
report and evidence `known_limitations`. Wording deliberately does **not**
claim today's walk-forward is fully rolling out-of-sample validation — see
the Playbook for the exact text.

### E — Corrected methodological finding (accepted; supersedes an earlier overstatement)

An earlier review characterised full-sample threshold derivation as an
"active violation with optimistic bias." **That was overstated.** The
corrected, evidence-grounded finding:

- Full-sample, feature-derived thresholds are an **outcome-blind
  methodological impurity**.
- **Not a demonstrated optimism bias** — with an outcome-blind derivation
  over a non-fitted rule, no mechanism preferentially selects profitable
  samples; it selects a marginally different definition of "extreme."
- **No return leakage has been observed** — the causality audit passed on
  every experiment in Campaigns 01–05.
- **Would not have changed Campaigns 01–05** — all rejected, hit rates
  0.44–0.56, bootstrap bar-clearance 0.9–7.9%.
- **Becomes important once the Historical Validation Layer exists**, when
  fitted and outcome-touching quantities (stops, exits, costs) appear.

### Deferred items — activation trigger: **the first campaign producing a SUPPORTED hypothesis**

Recorded, **not implemented**: rolling threshold recalculation · rolling
normalization · Historical Validation Layer · trade simulation · stop
optimization · TP optimization · equity curve · drawdown · profit factor ·
expectancy · average R · slippage model · fee model · liquidity model ·
strategy validation · **Constitution amendment** (the no-hindsight bullet
lands with rolling recalculation, not before — it has nothing to govern
until then).

- **Constitution §5 check:** no abstraction is built. A/B/D are
  documentation; C closes a **verified present** structural gap; the
  roadmap entry is a name, not a build.
- **Revisit triggers:** the first SUPPORTED campaign result (activates the
  deferred set).
- **Supersedes / superseded-by:** — (E corrects an in-review overstatement
  that was never recorded as a decision.)

---

## Appendix — Research Family State (current)

Maintained per RD-07 (two-state model). **Research Status** ∈ {LOCKED,
ACTIVE, NEAR-EXHAUSTED (a qualified ACTIVE), PAUSED, EXHAUSTED};
**Data Status** ∈ {NONE, COLLECTING, READY}. `cap` = production-capped
(no Hyperliquid-native history → DEFER-ceiling, not promotable today).

| Family | Research | Data | Cap | Next distinct mechanism / unlock |
|---|---|---|---|---|
| Funding Rate | **NEAR-EXHAUSTED** | READY | — | Level, venue-relative, and Delta rejected; Persistence deferred (RD-04); regime-interaction untestable on this window — no cheap distinct mechanism remains |
| Open Interest | ACTIVE | READY (Binance only) | cap | Level (CAMP-01) and **Velocity (CAMP-05)** both rejected. **Divergence** is the sole untested mechanism — same DEFER-ceiling (knowledge-only until a live OI recorder lifts it) |
| Liquidations | LOCKED | **NONE** | — | **RD-10:** Historical data exists through official Hyperliquid S3 archives but has not been acquired. Access requires authenticated AWS Requester Pays credentials. Earliest coverage remains unverified. |
| Order Flow | LOCKED | NONE | — | Unlock: verify HL historical order-flow (or capture via recorder) |
| Stablecoin flows | LOCKED | NONE | — | Unlock: verify a free, reliable, PIT-safe source |
| On-chain | LOCKED | NONE | — | Unlock: source + PIT-revision handling |
| Macro liquidity | PAUSED | NONE | — | Resume: enough history for ≥1 full liquidity cycle |
| Cross-asset | PAUSED | NONE | — | Resume: a specific falsifiable pairing pre-registered |
| Combined OI+Funding | LOCKED | READY (components) | cap | Unlock: both components show independent edge + multi-feature candidate exists |
