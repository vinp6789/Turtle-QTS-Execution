# RESEARCH_PLAYBOOK.md

**Process documentation, not implementation.** This describes the stages
every hypothesis moves through and what a human decides at each gate —
the *why* and *when* of the research process. For the concrete API calls
that implement each stage, see `docs/ALPHA_ENGINE.md` §4 ("Operating
workflow"). For the permanent record of every campaign that has already
gone through this process, see `docs/RESEARCH_LEDGER.md`.

```
Idea
  ↓
Registration
  ↓
Validation
  ↓
Evidence
  ↓
Governance
  ↓
Promotion
  ↓
Retirement
  ↓
Post-mortem
```

---

## 1. Idea

Where a hypothesis comes from: a named information source
(`ROADMAP.md` §1's priority order), a specific prior (a stated,
falsifiable belief — e.g. "extreme Open Interest predicts reversal"), and
a rationale for why that prior is plausible *before* looking at any data.

**Decision point:** is this a genuinely new hypothesis, or a rejected one
being quietly re-tried? If the latter — stop. Per
`PROJECT_CONSTITUTION.md` §6, a rejected hypothesis is not revisited
without new evidence that specifically justifies revisiting it (a new
data source, a materially different market regime, a flaw found in the
original methodology — not "let's try slightly different numbers").

**Related priors are separate ideas.** "Extreme signal → reversion" and
"extreme signal → continuation" are two ideas, never one idea with a
direction to be decided later by looking at results.

**Classify by economic hypothesis, not by implementation.** The unit that
governance retires or revisits is the *economic hypothesis* — the claim
about the world (Family + Mechanism in the three-level model: e.g.
"trend following works," "funding persistence predicts returns"), never
its *implementation* (the specific formula, indicator, or parameter — a
Level-3 Specification). Consequences, both permanent:
- **An implementation change is never a new hypothesis.** EMA → SMA →
  Supertrend → Donchian, or threshold 0.0001 → 0.0002, are all
  re-implementations of the same claim. If that claim was rejected, none
  of them reopens it — this is the same "not 'let's try slightly
  different numbers'" rule, stated at the level of measurement formula
  as well as parameter value. (This is precisely why the OHLCV-derived
  conviction family — trend, momentum, relative strength, volume
  expansion, ATR/Donchian, OBV — recorded as permanently rejected in
  `PROJECT_CONSTITUTION.md` §4, cannot be reopened by proposing a
  different indicator: those are all implementations of already-rejected
  economic hypotheses.)
- **A different *feature/mechanism* IS a new hypothesis**, even within
  one data family — funding *level* vs. funding *persistence* vs. funding
  *delta* use genuinely different information, not different parameters,
  so each is separately testable.

**Hybrid (multi-source) hypotheses are governed by attribution, not by
novelty of pairing.** A hybrid ("trend conditioned on funding
persistence," "liquidations + macro") is a genuinely new hypothesis only
if it (a) states a distinct, pre-registered economic rationale for the
*interaction itself* — never merely "combine two signals" — and (b) where
any component is an already-rejected hypothesis, demonstrates through the
attribution validation stage that its edge is **not** attributable to the
rejected component alone (the surviving component or the genuine
interaction must carry it). A hybrid is never a backdoor to relitigate a
rejected family by pairing it with a second source. Whether a claimed new
hypothesis is genuinely new or a relabeled retry is a **governance
judgment (reviewer ≠ researcher)**, not the researcher's to assert.

## 2. Registration

Every idea becomes a formal, pre-registered specification **before** any
sample is gathered or inspected:

- The exact candidate mechanism and its parameters (thresholds, direction
  convention, cadence). **For any exchange-native metric (funding rate,
  open interest, order flow, liquidations, or any future metric measured
  natively by an exchange), the threshold must be derived independently
  per venue, from that venue's own historical distribution — never one
  absolute magnitude asserted to hold across venues.** This is a
  permanent methodology rule, not a per-campaign choice: Campaign 02
  confirmed, with live evidence, that an absolute funding-rate threshold
  calibrated on Binance did not transfer to Hyperliquid (~3–8× smaller
  typical magnitude for the same assets/period) — see
  `docs/RESEARCH_LEDGER.md` CAMP-02 and `docs/HISTORICAL_DATA.md` §0.
- The exact universe (which watchlist symbols).
- The exact acceptance criteria (e.g. minimum hit rate, minimum sample
  count) and the exact rejection criteria — both locked now, checked
  later, never adjusted after a result is seen.
- The exact validation methodology to be applied (which stages, how many
  folds/resamples, what seed).
- The expected failure modes — what would make this hypothesis wrong, or
  its result untrustworthy, stated in advance.

**Campaign-type declaration (mandatory, first line of every
pre-registration). Exactly one classification. This is not a new
distinction — `RESEARCH_DECISIONS.md` RD-11 C already recorded that
"Campaigns 01–05 validate **signals**, not executable strategies." That
observation is hereby made a forward, binding declaration.**

| | **Type 1 — Signal Validation** | **Type 2 — Strategy Validation** |
|---|---|---|
| Asks | Does this information source contain predictive information? | Is this complete strategy economically deployable? |
| Declares | Feature, threshold, direction, horizon, universe | Everything in Type 1 **plus** entry rules, exit rules, holding period, position sizing, leverage, transaction costs, slippage, funding, tax model, portfolio construction, benchmark |
| May report | Hit rate, information coefficient, significance, MDE, N_eff, bootstrap, permutation, robustness | All of Type 1 **plus** CAGR, profit factor, payoff ratio, expectancy, Sharpe, max drawdown, win rate, trade count, equity curve, return after costs, return after tax, comparison vs HLP |
| May conclude | Supported / not supported / unresolved | **deploy · reject economically · inferior to benchmark · commercially viable** |
| May **never** conclude | Anything about profitability | — |

**A Type 1 campaign must state verbatim in its pre-registration and in
its evidence `known_limitations`:**

> *"This campaign has not answered the business question."*

**Only a Type 2 campaign may reach a deployment conclusion.** A Type 1
result is never sufficient grounds to allocate capital, however strong
its statistics.

`[R]` **All eight closed campaigns are Type 1.** None declared entry
rules, exits, sizing, costs or a benchmark — see `ALPHA_SCORECARD.md` for
the per-campaign classification and what each therefore proved.

**Derivation-scope declaration (mandatory, `RESEARCH_DECISIONS.md`
RD-11 A).** For **each derived quantity** in the specification
(thresholds, normalizations, rolling statistics), the pre-registration
must state whether it is derived **full-sample**, **rolling**, or
**expanding-window**. The same declaration is carried into the evidence
package's `known_limitations`. This imposes no derivation method — it
makes the choice explicit and auditable. (A full-sample, outcome-blind
derivation is a recorded methodological *impurity*, not a demonstrated
bias — see RD-11 E.)

**Immutable research assumptions (mandatory where declared,
`RESEARCH_DECISIONS.md` RD-11 B).** If a campaign declares any of —
**stop methodology · stop distance · take-profit methodology · fee
assumptions · slippage assumptions · liquidity assumptions** — those
values are **frozen once pre-registration is complete**, exactly like the
threshold and acceptance criteria. Changing any of them after observing
results **invalidates the campaign**. **Position sizing and portfolio
allocation are explicitly excluded** — they belong to the Execution
Engine's frozen risk/portfolio stack (`PROJECT_CONSTITUTION.md` §7), never
to a research specification.

**Pre-registration feasibility review (mandatory, added after Campaign
02's methodology review — see `docs/RESEARCH_LEDGER.md` CAMP-02).**
Before locking the specification, explicitly estimate and record:

- **Expected signal count** — a rough, outcome-blind estimate of how many
  samples will actually signal (not merely how many samples exist), from
  the exploratory distribution study.
- **Expected walk-forward fold size** — expected signal count ÷
  `n_folds`. This must clear `min_signaled_samples` **per fold**, not just
  in aggregate — `alpha_engine.validation.walk_forward` checks every
  fold against the same acceptance criteria as the full sample
  (`alpha_engine/validation/walk_forward.py`'s own stated intent: clear
  the bar "in EVERY period, not just in aggregate"). A specification
  whose expected per-fold count cannot clear the floor is not validly
  testable by walk-forward as configured — either the floor, the fold
  count, or the universe/depth must be reconsidered *before* locking, not
  discovered after running.
- **Expected bootstrap stability** — is the expected signal count large
  enough that a 1,000-resample bootstrap will produce a meaningfully
  narrow range, rather than one so wide it cannot discriminate a real
  edge from noise?
- **Expected regime coverage** — a rough sense (from the exploratory
  study or prior campaigns' regime labeler output) of whether signals are
  likely to concentrate heavily in one market regime, which would make an
  aggregate "pass" potentially non-robust before regime stratification is
  even run.

This is a **research-governance requirement**, not a strategy
optimization — it does not permit adjusting the threshold or any other
locked parameter based on this estimate's outcome; it only permits
reconsidering whether the *validation configuration itself* (fold count,
universe, depth) is appropriately matched to the expected sample size
before anything is locked. If the estimate suggests infeasibility, the
specification is redesigned (e.g. more depth, fewer folds, wider
universe) and the *whole* registration step is redone — never patched
after seeing partial results.

**Decision point:** is the acceptance bar genuinely a test, or has it been
quietly set low enough to guarantee a pass? A bar set after seeing
preliminary data is not a pre-registration — restart the process.
Separately: does the feasibility review above show this specification is
even testable by the planned validation methodology? If not, the
specification is not locked yet — restart from the feasibility review,
not from a partial run.

## 3. Validation

The registered specification is run through the validation gate: does the
mechanism clear its own declared bar on the supplied samples, does it
survive a leakage/causality check, does it hold up across independent
time periods (not just in aggregate), is the apparent edge distinguishable
from sampling noise, and is it concentrated in one market regime or
robust across several.

**Decision point:** none — this stage is mechanical once registered. Its
entire value is that no human judgment enters between "the criteria were
locked" and "the criteria were checked."

**Mandatory reporting caveat (`RESEARCH_DECISIONS.md` RD-11 D).** Every
campaign report, and every evidence package's `known_limitations`, must
carry this caveat. Its wording is deliberately matched to what the
current pipeline actually does and **must not be strengthened** until a
genuinely rolling, out-of-sample walk-forward exists:

> **Backtests flatter.** Single-pass results are the most optimistic
> number here and should carry the least weight. The walk-forward stage
> in this campaign checks whether one fixed, pre-registered rule holds
> consistently across chronological periods — it is **not** an
> out-of-sample generalization test: no parameter is refit per fold, and
> thresholds may be derived from the full-sample feature distribution
> (see the campaign's derivation-scope declaration). Treat every number
> as an upper bound on what live trading would deliver, before fees,
> slippage, and execution costs — none of which are modelled.

## 4. Evidence

Every stage's result is sealed into one immutable, content-fingerprinted
package — a durable, tamper-evident record of exactly what was tested,
against exactly what data, with exactly what result. Known limitations
(data-source caveats, methodology caveats) are recorded as part of the
evidence, not as a separate, easily-lost footnote.

**Decision point:** none for the researcher. The evidence package is
generated, not authored — a researcher does not get to selectively omit
an unfavorable stage result.

## 5. Governance

An independent reviewer — structurally required to be a different
identity than the researcher — examines the sealed evidence and decides:
**approve**, **reject**, or **defer** (more evidence needed before a
decision can be made responsibly). The reviewer checks the evidence
against the *original* pre-registered criteria, not against what would
have made the result look better in hindsight.

**Venue-replication check (DEX-first — `PROJECT_CONSTITUTION.md` §6,
`docs/HISTORICAL_DATA.md` §0):** for any hypothesis built on a
centralized-exchange historical source (Binance), the reviewer must
additionally confirm the finding was re-checked — same locked
specification, no re-tuning — against Hyperliquid's own historical data,
where one exists for the metric in question. A hypothesis that has not
been through this check, or that contradicts direction when it is,
**cannot be APPROVE** — it is REJECT or DEFER (pending the replication
check) regardless of how strong the CEX-only evidence looks. Where no
Hyperliquid historical source exists for the metric at all (e.g. Open
Interest, as of this writing — see `docs/HISTORICAL_DATA.md` §0), this
is a standing structural blocker to promotion, not a checkbox to satisfy
later; the evidence package's `known_limitations` must say so explicitly.

**Expectancy-sign inspection (restored — `PROJECT_CONSTITUTION.md` §7).**
Constitution §7 states plainly: "a candidate with a favorable hit rate but
non-positive expectancy is still a rejection." The reviewer must inspect
`mean_directional_return` (sealed into every evidence package by the
five-stage gate, `alpha_engine/validation/models.py`) alongside hit rate
at every governance decision — a hit rate clearing `min_hit_rate` with a
non-positive or negligible mean directional return is not a pass on
magnitude grounds, even though the runner's own recognized acceptance
keys (`min_hit_rate`, `min_signaled_samples`) do not encode this
mechanically. **This restores, as an explicit rule, a practice Campaign
01's own pre-registered acceptance criteria already applied** ("a >55%
hit rate with negative expectancy is a rejection, not a pass" —
`RESEARCH_CAMPAIGN_01_open_interest.md`, "Acceptance criteria" §, the
"Plus" clause) but which was not carried forward into a written Playbook
rule and was not consistently reapplied in Campaigns 02–05.
Deliberately a **human inspection at this one judgment gate**, not a new
`runner.py` acceptance key — mechanizing it would migrate judgment out of
the one deliberately human-owned stage in the pipeline (see the trade-off
recorded in `RESEARCH_DECISIONS.md`).

**Execution-parameter prerequisite for APPROVE (`RESEARCH_DECISIONS.md`
RD-11 C).** No hypothesis may reach **APPROVED** unless its specification
contains every execution-required risk parameter the execution bridge
structurally requires — today, `stop_fraction`
(`alpha_engine/execution_bridge/strategy.py`, `required=True`; the bridge
refuses to fabricate a risk level). **[VERIFIED]** Campaigns 01–05 declare
`{threshold, direction_convention}` only, so a specification of that shape
would be structurally undeployable if approved. That is intentional and
correct — those campaigns validate **signals**, not executable
strategies — and they are **not retrofitted**. This is a **promotion**
requirement only; it places no obligation on signal-validation campaigns
that are not promotion candidates.

**Decision point:** this is the one stage in the whole pipeline that is a
genuine human (or explicitly-separate-identity) judgment call, and it is
deliberately isolated to exactly this one gate — every stage before it is
mechanical, and every stage after it only executes what governance
approved.

## 6. Promotion

An approved model becomes eligible to generate live signals through the
execution bridge. Promotion is never automatic on approval alone —
promotion additionally requires the operational readiness described in
`ROADMAP.md` §3 (paper-trading track record, agreed monitoring, an
authorized capital amount) before real capital is at risk. Approval
answers "is this a statistically sound hypothesis"; promotion answers "are
we ready to actually run it."

**Decision point:** a second, later human decision — approval and
"deploy this now" are not the same decision, and should not be collapsed
into one.

## 7. Retirement

A live-approved model is retired when it degrades against **its own**
pre-registered acceptance criteria (never against an invented drift
threshold decided after the fact) — assessed by re-running the same
validation the original evidence used, over recent live samples.
Retirement freezes new signal emission; it never force-closes or
"manages" an existing position, which continues to exit through the
Execution Engine's own frozen risk/exit machinery
(`PROJECT_CONSTITUTION.md` §7).

**Decision point:** is the degradation real (fails its own bar on recent
data) or a normal, expected variance the original evidence already
accounted for? This distinction is exactly why retirement re-runs the
same validation methodology rather than eyeballing a performance chart.

## 8. Post-mortem

Every closed campaign — approved, rejected, or retired — gets a permanent
entry in `docs/RESEARCH_LEDGER.md`: what was tested, what the evidence
showed, what was learned (including about the *process*, not just the
hypothesis), and what direction it points to next. This step is not
optional and is not skipped for a rejected hypothesis — Research Campaign
01's ledger entry is the working example: a clean rejection recorded with
the same rigor as an approval would have received, plus explicit lessons
(raw OI non-stationarity, per-symbol underpowering) that shaped the next
campaign's design.

**Two separate verdicts are mandatory (2026-08-07). Neither substitutes
for the other, and they are recorded separately so a strong one cannot
launder a weak one.**

**Scientific Verdict** — is the evidence statistically reliable? How much
uncertainty remains? Would replication likely change the conclusion?
Which assumptions dominate the result?

**Business Verdict** — would this make money? Would I deploy it? Would I
allocate capital? Does it beat HLP (`[M]` 11.4 %/yr after tax — see
`MECHANISMS.md`, not restated here)? Does it beat cash? Does it justify
the engineering complexity? What is the expected business value?

**A Type 1 campaign's Business Verdict is always
"NOT ANSWERED — signal validation only."** Writing anything else in it is
the specific error this rule exists to prevent: `[M]` eight campaigns
produced signal statistics that were repeatedly discussed as though they
were business outcomes, and the project measured a return exactly zero
times (`ALPHA_SCORECARD.md` §0).

**Decision point:** none — this stage is a recording obligation, not a
judgment call. The only failure mode here is skipping it.

---

## What this playbook is not

This is the conceptual process, not a tutorial. For the actual function
calls (`run_research_cycle`, `compare_experiments`,
`record_governance_decision`, `assess_degradation`, `freeze_degraded`)
and their exact signatures, see `docs/ALPHA_ENGINE.md` §4 and the
`alpha_engine.research` / `alpha_engine.governance` / `alpha_engine.
lifecycle` module docstrings. For the review responsibilities that apply
to the *engineering* work behind each stage (not the research decisions
described here), see `docs/REVIEW_PROTOCOL.md`.
