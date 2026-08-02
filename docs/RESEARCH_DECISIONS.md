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

## RD-12 — RD-10 Steps 1 and 2 complete: liquidation archive measured and source implemented

- **Date:** 2026-07-28 · **Author:** researcher · **Reviewer:** pending · **Category:** data-acquisition-capability · **Status:** active
- **Scope:** records the measured outcome of the RD-10 Step 1 probe and the completion of RD-10 Step 2. **Revises two RD-10 premises with measurement.** No campaign, methodology, or governance rule is changed.

### Step 1 — measured facts (authenticated probe, one object)

- **Layout:** `s3://hl-mainnet-node-data/node_fills_by_block/hourly/YYYYMMDD/H.lz4` — one object per hour, hour **unpadded** (`3.lz4`, not `03.lz4`), region `ap-northeast-1`, Requester Pays.
- **Earliest coverage: 2025-07-27** (partial, from hour 10); first complete day 2025-07-28; 367 contiguous date prefixes ≈ **~12 months**.
- **Compression:** LZ4 frame, ~4.8× (10.08 MB → 48.74 MB measured).
- **Volume:** 24 objects/day; ~300 MB–1 GB/day compressed, growing ~3× across the window.
- **Schema:** NDJSON, one block per line — `{local_time, block_time, block_number, events:[[address, fill], …]}`.
- **Liquidation field PRESENT and POPULATED:** 328 of 107,066 fills in the sampled hour (**0.31%**); **100% of occurrences non-null** — the key is absent when inapplicable, never null-filled. Structure `{liquidatedUser, markPx, method}` as documented.
- **One liquidation surfaces as TWO paired fills sharing one `tid`** (liquidator side + liquidated side). This is a structural property of the data, not an artifact.
- **Probe cost:** < $0.01 (2 GETs, ~10 bounded LISTs).

### Premises revised (supersede the RD-10 estimates)

| Premise | RD-10 assumed | **Measured** |
|---|---|---|
| Coverage start | ~Jan 2025 (community-sourced) | **2025-07-27** — ~6 months shorter |
| Archive size | ~2.75 TB (5 GB/day assumption) | **~240 GB** (367 days × ~650 MB) |
| Backfill cost | ~$300 laptop egress | **~$27** laptop, **~$0** same-region |

Cost is confirmed **not** a research blocker. The binding constraint is now **window length**, not money.

### Step 2 — implemented (additive only)

- `LiquidationObservation` — a **third** concrete historical observation type. It cannot reuse the existing scalar shape: a liquidation is irreducibly multi-field (price, size, side, direction, method, liquidated account, venue `tid`), and collapsing that to one `value` would discard the metric's content.
- `alpha_engine/historical/sources/hyperliquid_s3.py` — discovery, incremental download, decode, and a key-ordered checkpoint. Ten plain functions, **zero new classes**; no generic S3 layer, no recorder, no transport abstraction (Constitution §5).
- **`storage.py` extended additively** — honest note: "reuse the pipeline completely" was not fully achievable. The existing CSV is a fixed 6-field single-`value` shape whose merge dedups on `(symbol, observed_at_utc)`; the measured paired fills share both, so that key would have **silently discarded half of every liquidation**. Two concrete row shapes are now enumerated explicitly (`_fieldnames_for`, `_dedup_key`) — not a generic schema mechanism. Existing behaviour byte-identical; all four on-disk series re-verified.
- **Platform independence** (§5): credentials resolve via boto3's default chain, so identical code authenticates from env vars (Railway/Docker/K8s) or a shared credentials file (laptop/VPS). Bucket/prefix/region/checkpoint-path are parameters. No `os.name`/`sys.platform` branch. `boto3`/`lz4` imported lazily.
- **Validated end-to-end on the real archive:** 192 liquidations decoded from one hour = 96 unique `tid`s (exactly 2 rows each), checkpoint resume excluded the processed hour, re-merge added 0. 31 unit tests; full regression 1,633 passed.

### Consequences

- Liquidations remains **Research LOCKED / Data NONE** — the capability exists, **no backfill has been executed**. The blocker is no longer credential- or cost-gated; it is simply **not yet authorized**. **[Corrected by RD-13, 2026-07-29]:** a bounded one-month pilot backfill was subsequently authorized and executed; this sentence was accurate only as of this entry's own date (2026-07-28) — see RD-13 for the measured outcome and the current Data Status.
- **New constraint for any future liquidation campaign:** the ~12-month window is shorter than the 18-month window every prior campaign used, which directly limits achievable statistical power. This must be established in that campaign's mandatory feasibility review before any specification is locked.
- **Undeclared runtime dependencies:** `boto3` and `lz4` are not yet in project dependency metadata. Non-blocking for research; must be declared before any deployment.
- **Revisit triggers:** authorization of a bounded backfill; or a decision that the 12-month window is too short to support a campaign.
- **Supersedes / superseded-by:** revises RD-10's coverage/size/cost estimates (RD-10 otherwise stands).

## RD-13 — One-month liquidation pilot: measured feasibility signal; RD-12's "no backfill executed" corrected; governance-inspection clause restored

- **Date:** 2026-07-29 · **Author:** researcher · **Reviewer:** pending · **Category:** data-acquisition-capability, methodology-refinement · **Status:** active
- **Scope:** records the measured outcome of the bounded, outcome-blind, one-month liquidation pilot backfill authorized after RD-12; corrects RD-12's now-stale claim that "no backfill has been executed"; records a decayed governance practice found and restored. **No campaign is pre-registered here. No hypothesis is tested. No methodology is changed beyond what §C below states.**

### A — Pilot execution (measured facts)

Bounded backfill, watchlist symbols only (BTC/ETH/SOL), full calendar
month **2026-06-01 → 2026-06-30**, executed via a one-off scratchpad
driver against the already-implemented `hyperliquid_s3` source and
`storage.merge_and_write`. Interrupted mid-run by a hard process kill;
resumed cleanly from the last durable checkpoint after the RD-12 §Step-2
durability fix; completed 30/30 days.

| Metric | Measured |
|---|---|
| Total fills scanned | 47,280,012 (resume window alone) |
| Liquidation rows written (watchlist) | 416,972 |
| Unique liquidation events (by `tid`) | **208,486** |
| Rows per event | **exactly 2.00** — perfect fill-pairing, zero orphans |
| Duplicate rows | **0** |
| Decode errors | **0** |
| Missing hours | **0** |
| All-symbol liquidation density | **0.337%** of all fills (RD-12's Step-1 single-hour probe measured 0.31% — consistent) |
| Method | 100% `market`, 0% `backstop` |
| Side balance | exactly 37,114 / 37,114 |
| Per-symbol split | BTC 141,356 (67.8%) · ETH 38,264 (18.4%) · SOL 28,866 (13.8%) |
| Per-day range | min 1,006 · median 5,021 · mean 6,950 · max 22,941 (every one of 30 days had ≥1 event) |

### B — Statistical structure (measured, outcome-blind — no return or profitability inspected)

- **Within-symbol lag-1 autocorrelation of daily event counts:** BTC
  +0.525, ETH +0.463, SOL +0.362.
- **Cross-symbol correlation of daily event counts:** BTC–ETH +0.853,
  BTC–SOL +0.899, ETH–SOL +0.874 — i.e. the three watchlist symbols behave
  as roughly **1.1 effective independent symbols, not 3**, on this metric.
- **Concentration:** the top 1 day carries 11.0% of the month's events,
  top 3 = 29.6%, top 5 = 43.2%, top 10 = 65.2%.
- **Projected, at a p60 daily-count threshold, 3-symbol pooled, n_folds=3:**
  ~146 nominal signalled/fold (clears the existing `min_signaled_samples =
  100` floor unchanged) but **≈53/fold after applying the measured
  cross-symbol correlation as a haircut** (does not clear it). The gap
  between these two numbers is the finding — raw pooled counts overstate
  true statistical power for this metric by roughly 2.5–3×, the same
  failure shape as RD-04's Funding Persistence deferral, one level up
  (there: within-symbol autocorrelation; here: cross-symbol).

### C — Consequences and rule changes

- **RD-12's "no backfill has been executed" is corrected by this entry.**
  A one-month, outcome-blind pilot has been executed and is recorded here
  in full. The 12-month full backfill remains **not executed**.
- **Liquidations family Data Status updated:** LOCKED / **NONE** →
  LOCKED / **COLLECTING** (see Appendix table below).
- **New feasibility-review requirement (methodology refinement,
  effective immediately, self-activating exactly like RD-11 B):** any
  future feasibility review for a metric whose samples may share
  cross-instrument dependence (this pilot is the first measured instance)
  must report **effective sample size (N_eff) and cross-symbol/
  cross-instrument correlation**, not raw pooled signalled counts alone.
  This does not change `min_signaled_samples = 100` or any existing
  campaign's already-closed result — it adds a reporting requirement to
  the feasibility review stage (`RESEARCH_PLAYBOOK.md` §2) that Campaigns
  01–05 did not need, since none pooled across instruments with measured
  dependence of this magnitude.
- **Governance-inspection clause restored (`RESEARCH_PLAYBOOK.md` §5):**
  independently of the pilot, this session's review found that Campaign
  01's pre-registered acceptance criteria required governance to inspect
  `mean_directional_return` alongside hit rate ("a >55% hit rate with
  negative expectancy is a rejection, not a pass") — a practice not
  carried forward into a written Playbook rule and not consistently
  reapplied in Campaigns 02–05's governance write-ups, even though
  `PROJECT_CONSTITUTION.md` §7 states the same requirement in general
  terms. Restored as an explicit Playbook §5 clause. **Not retrofitted**
  onto Campaigns 01–05's already-closed, immutable verdicts — each was
  independently reviewed under its own pre-registered criteria at the
  time, and none would change: all five were rejected outright on hit
  rate, not on a marginal magnitude call this clause would have altered.
- **Considered and rejected: mechanizing this as a `runner.py` acceptance
  key (`min_mean_directional_return`).** Would migrate judgment out of
  the one deliberately human-owned gate in the pipeline
  (`RESEARCH_PLAYBOOK.md` §5's own stated design). The evidence package
  already carries `mean_directional_return`; the fix is a reviewing
  practice, not new machinery.
- **Full 12-month backfill: still not authorized.** Sequencing per
  `ROADMAP.md` §1.1 unchanged by this entry — storage durability, CLI
  entry point, and a Hyperliquid-native (not Binance-only) outcome series
  for 2025-07-27→present remain the prerequisites before the full
  backfill runs. When it does, it runs **single pass, all symbols
  retained** — a staged/partial backfill was considered and rejected:
  walk-forward validation requires chronological contiguity, and
  selecting which months to sample would itself be an un-pre-registered
  researcher judgment call.
- **Revisit triggers:** authorization and completion of the full
  12-month backfill; the feasibility review itself (may reject Campaign
  06 outright — the cheapest possible outcome of the gate, not a failure
  of it).
- **Supersedes / superseded-by:** corrects RD-12's "no backfill has been
  executed" claim; RD-12's archive measurements (coverage, size, cost)
  otherwise stand unchanged.

---

## RD-14 — A liquidation day with no rows is a VERIFIED ZERO-EVENT day, not a missing observation

- **Date:** 2026-08-02 · **Author:** researcher · **Reviewer:** pending · **Category:** data-interpretation-rule · **Status:** active
- **Scope:** how absence of rows for a `(symbol, day)` pair must be read in `liquidation__{SYMBOL}__hyperliquid_s3.csv`. **No campaign is pre-registered here, no hypothesis tested, no implementation changed.** This entry exists because the distinction is invisible in the stored data — an absent day and an unobserved day look identical on disk — and choosing wrongly silently biases any downstream sample.

### A — What prompted it (measured facts)

Mid-collection inspection of the Backlog 1.5 backfill showed the
per-symbol contiguous-day runs disagreeing: BTC covered every day of the
collected window, while ETH and SOL each showed two interior gaps.

| Day | BTC rows | ETH rows | SOL rows |
|---|---|---|---|
| 2025-12-20 | 20 | 8 | **0** |
| 2026-01-17 | 2 | **0** | **0** |
| 2026-01-24 | 22 | **0** | 4 |

For scale, over the collected window: BTC median **4,960** rows/day
(min 2, max 70,920); ETH median 1,996 (min 2); SOL median 1,644 (min 4).
The gap days are therefore 200–2,500× below normal **for every symbol
simultaneously**, not for the symbol with the gap alone.

### B — Evidence that this is real absence, not lost data

Three independent checks, each capable of falsifying the conclusion:

1. **Cross-symbol coincidence.** On every gap day BTC itself collapses to
   2–22 rows. A per-symbol collection fault cannot explain a
   market-wide collapse; a genuinely quiet market can.
2. **Archive completeness (source-of-truth listing).** Listed the S3
   prefix for each gap day and its immediate neighbours —
   `20251219`, `20251220`, `20251221`, `20260116`, `20260117`,
   `20260118`, `20260123`, `20260124`, `20260125` — **24/24 hourly
   objects present for all nine**. No hour was absent upstream, so none
   could have been silently skipped.
3. **Re-decode from source (decisive).** Re-fetched and re-decoded
   2026-01-17 directly from the archive: **zero liquidation rows for any
   watchlist symbol**. The adjacent normal day 2026-01-18, decoded
   identically, returned rows (BTC 18, SOL 2 in the sampled hours). The
   archive genuinely contains no liquidations for the gap day.

**Mechanistic corroboration:** `collect_liquidations()` processes an
entire calendar day's hours and only advances the checkpoint after that
day's rows are durably flushed (the Backlog 1.3 H1 invariant). Any day
at or before the checkpoint therefore had every existing archive hour
processed — which is independently confirmed above by BTC holding rows
on those same days.

**Consistency with prior measurement:** RD-13 measured extreme
concentration on the pilot month (top-10 days = 65.2% of all events).
A heavy-tailed, bursty process is expected to produce genuinely empty
days for lower-activity symbols. This finding is the same phenomenon
seen at its lower tail, not a contradiction of RD-13 (whose pilot month
happened to have ≥1 event on all 30 days).

### C — Decision (judgment)

**Within the checkpoint-covered window, absence of rows for a
`(symbol, day)` pair means that symbol had ZERO liquidation events that
day. It is an observation with value zero, not a missing observation.**

Consequently, for Campaign 06 and any later liquidation work:

- **Zero-event days MUST be materialized as `count = 0`** when building
  a daily-count series — never dropped, never left as NA, never
  forward-filled, never interpolated.
- **Threshold derivation must include zero days in the distribution.**
  Excluding them inflates every percentile: a p60 threshold computed on
  active-days-only is not the p60 of the actual daily-count
  distribution, which silently breaks the venue-relative-threshold rule
  (permanent, post-CAMP-02) that a threshold be derived from that
  venue's own full distribution.
- **Dropping empty days conditions the sample on activity**, biasing it
  toward volatile regimes — precisely the regime-coverage failure the
  pre-registration feasibility review (permanent, post-CAMP-02) exists
  to catch.
- **N_eff and signalled-count estimates must count zero days as
  legitimate non-signal days**, not as absent sample rows.

### D — Scope limits (what this entry does NOT license)

This rule holds **only** for days at or before the durable checkpoint,
where the archive's hourly objects were themselves complete. It does
**not** apply to:

- days beyond the checkpoint (never attempted — genuinely unknown);
- any day where the archive lacks hourly objects (under-covered — the
  distinction is then real and matters).

Archive completeness was verified on nine days, not on all 233 collected
to date, and the 2026-01-17 re-decode sampled 4 of 24 hours. **A
whole-window coverage audit (assert 24 hourly objects per collected day)
is therefore a prerequisite before final analysis** — the mechanistic
argument above makes systematic under-coverage unlikely, but "unlikely"
is not "measured", and the entire value of this rule is that it makes an
otherwise-invisible distinction explicit.

- **Evidence references:** live S3 prefix listings (nine days, 24/24
  objects each); live re-decode of 2026-01-17 vs 2026-01-18 via
  `sources/hyperliquid_s3.fetch_hour`/`decode_liquidations`; per-day row
  counts from the in-progress Backlog 1.5 series; `collect_liquidations()`
  day-flush/checkpoint ordering (Backlog 1.3 H1); RD-13 §B concentration
  measurements.
- **Revisit triggers:** the whole-window coverage audit in §D returning
  any day with fewer than 24 hourly objects; any future venue or archive
  whose absence semantics differ (an archive that omits empty periods
  rather than containing no matching fills would invert this rule);
  discovery of a decode path that could drop rows without raising.
- **Supersedes / superseded-by:** — (complements RD-13; contradicts
  nothing)

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
| Liquidations | LOCKED | **COLLECTING** | — | **RD-13:** One-month outcome-blind pilot backfill (2026-06) executed — 208,486 events, 0 duplicates, 0 decode errors. Measured cross-symbol correlation of daily counts +0.85–0.90 (≈1.1 effective independent symbols, not 3) — full 12-month backfill and a proper N_eff/correlation-aware feasibility review still required before any pre-registration; may reject Campaign 06 outright. Full backfill: 2025-07-27 → present (~12 months), ~240 GB, ~$27 (~$0 same-region), **in progress**. **RD-14:** within the checkpoint-covered window an absent `(symbol, day)` row means **zero events**, not a missing observation — materialize as `count = 0` before any threshold or N_eff work. |
| Order Flow | LOCKED | NONE | — | Unlock: verify HL historical order-flow (or capture via recorder) |
| Stablecoin flows | LOCKED | NONE | — | Unlock: verify a free, reliable, PIT-safe source |
| On-chain | LOCKED | NONE | — | Unlock: source + PIT-revision handling |
| Macro liquidity | PAUSED | NONE | — | Resume: enough history for ≥1 full liquidity cycle |
| Cross-asset | PAUSED | NONE | — | Resume: a specific falsifiable pairing pre-registered |
| Combined OI+Funding | LOCKED | READY (components) | cap | Unlock: both components show independent edge + multi-feature candidate exists |
