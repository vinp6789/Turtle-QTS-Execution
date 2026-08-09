# PLATFORM_QUALIFICATION.md

**The permanent record that the measurement platform — not any strategy —
is qualified to judge economic performance.**

This document qualifies the *instrument*. It says nothing about whether
any strategy makes money, and a strategy's failure here is evidence the
instrument works, not that it is broken.

Executed 2026-08-07 against the simulated execution environment (real
Hyperliquid market data, deterministic local fills). Commit `930fc77`.
Regression at time of qualification: **2,087 passed, 0 failed**.

---

## 0 · Reuse audit — what performed the verification

**No verification logic was written for this qualification.** Every check
below is an existing capability, invoked:

| Capability | Provided by | Pre-existing |
|---|---|---|
| Order/position lifecycle | `event_store.replay()` event stream | Yes |
| Replay + corruption detection | `event_store.read_events()` → `RecoveryReport` | Yes |
| Accounting correctness | `PortfolioManager._assert_invariant` (raises on any violation) | Yes |
| Venue reconciliation | `ExchangeAdapter.reconcile()` | Yes |
| Equity persistence + restart | `measurement.EquityLog` recovery-on-open | Task 1 |
| Metrics | `measurement.metrics.compute()` | Task 2 |
| Scoreboard | `measurement.scoreboard.build()` | Task 3 |
| Validity | `measurement.validity.classify()` | Task 4 |
| Health | `scripts/recorder_health.py`, `pipeline_validation_smoke.py` | Yes |

---

## 1 · Qualification result

**10 of 12 QUALIFIED. 2 NOT QUALIFIED — stated plainly rather than
claimed.**

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | **Trade lifecycle — open** | ✅ QUALIFIED | `ORDER_SUBMITTED 6 → ORDER_ACKNOWLEDGED 3 → ORDER_FILLED 3 → POSITION_OPENED 3`. The 6→3 gap is the engine's own duplicate-order suppression working, not a loss |
| 2 | **Trade lifecycle — close** | ❌ **NOT QUALIFIED** | **Zero `POSITION_CLOSED` events.** ATR stops were not reached in the observation window. Every trade-level metric therefore remains unexercised end-to-end |
| 3 | **Replay correctness** | ✅ QUALIFIED | 42 events replayed. `RecoveryReport(valid_event_count=42, tail_truncated=False, discarded_byte_count=0)` |
| 4 | **Accounting correctness** | ✅ QUALIFIED | `_assert_invariant` runs on *every* event application and raises on any imbalance. 42 applications, zero raises. Assets = Liabilities + Equity held throughout |
| 5 | **Equity persistence** | ✅ QUALIFIED | 8 rows, 8 cycles, **0 duplicate keys**, 19 fields per row |
| 6 | **Metrics engine** | ✅ QUALIFIED | 26 metrics computed; formulas unit-tested against hand-derived values (41 tests) |
| 7 | **Scoreboard** | ✅ QUALIFIED | 35 fields produced; contains no business calculation (test-enforced) |
| 8 | **JSON API** | ✅ QUALIFIED | `GET /scoreboard` → HTTP 200 in **4.0 ms**; calculates nothing |
| 9 | **Restart recovery** | ✅ QUALIFIED | Store reopened: 42 events, no truncation. Equity log reopened: `last_cycle_seq=7`, row count identical, idempotency preserved |
| 10 | **Metric validity framework** | ✅ QUALIFIED | 26/26 metrics carry `value / status / reason`. Correctly flagged Sharpe as `INSUFFICIENT_DATA (6 returns < 30)` |
| 11 | **Fee reconciliation** | ✅ QUALIFIED | **Portfolio `6.1007021235` = simulator `6.1007021235`, exactly.** Two independent computations agree to the last decimal |
| 12 | **Funding reconciliation** | ❌ **NOT QUALIFIED** | `funding_cumulative = 0`. No funding settlement occurred in the window, so the path is **untested, not proven** |

---

## 2 · The strongest single piece of evidence

**Fee reconciliation.** `SimulatedTransport` computes fees at fill time
(`price × size × 0.00045`). `PortfolioManager` accrues them independently
through `AccountingSync` from the fill records. The two never consult
each other.

```
simulator  fees_paid          = 6.1007021235
portfolio  fees_cumulative    = 6.1007021235
difference                    = 0
```

Two independent paths agreeing to ten decimal places is a stronger
statement about the accounting layer than any single-path assertion.

---

## 3 · What this qualification does NOT establish

Stated explicitly, because a qualification document that overclaims is
worse than none:

- **The close path is unproven end-to-end.** Positions opened and were
  marked to market, but none closed. `profit_factor`, `payoff_ratio`,
  `win_rate`, `expectancy`, `average_win/loss` and
  `average_holding_seconds` have unit-test coverage and **no live
  confirmation**.
- **The `FAIL` verdict has never fired.** The scoreboard has only ever
  returned `INSUFFICIENT_DATA`. The claim *"the platform will correctly
  identify a losing strategy"* remains **untested in production**, though
  the verdict classifier is unit-tested.
- **Funding was never charged**, so cost attribution is qualified for
  fees only.
- **Slippage is zero by construction** (Phase 1 simulator). Every cost
  figure is a lower bound.
- **The simulated venue fills every order in full at its limit price.**
  Real fills will differ, and the gap is unmeasured.

---

## 4 · Reproduction

```bash
EXECUTION_MODE=simulated \
ENGINE_CONFIG_PATH=config/simulated.toml \
ENGINE_STORE_PATH=data/qual/events \
PORTFOLIO_INITIAL_DEPOSIT=10000 \
python -m scripts.run_platform
```

Then `GET /scoreboard`.

---

## 5 · Verdict

**The measurement platform is QUALIFIED for the open, mark, persist,
compute, report and restart paths, and NOT YET QUALIFIED for the close
and funding paths.**

Every number this platform reports about a strategy is now produced by a
single engine, labelled with its own validity, and reconciled against an
independent computation where one exists. What it cannot yet certify, it
says so.

**Closing the two open items requires only a longer observation window —
no further engineering.** They are recorded here rather than waived, and
this document is amended when they close.

---

## Addendum A — 2026-08-08 · the close path was unreachable, not untriggered

**Everything above is preserved exactly as written on 2026-08-07.** This
addendum corrects an *interpretation* in it. No original figure, verdict
or line has been altered, and none of the measured evidence changes.

**The claim being corrected.** §1 item 2 states: *"Zero `POSITION_CLOSED`
events. **ATR stops were not reached in the observation window.**"*

**Why it is unsupported.** A repository-wide audit on 2026-08-08 found
that no production component can close a position at all:

| Evidence | Finding |
|---|---|
| `grep reduce_only=True` across production | **Zero occurrences.** Only capability declarations (`mock_adapter.py:43`, `hyperliquid_adapter/capabilities.py:29`) |
| `alpha_engine/execution_bridge/candle_strategy.py:281` | emits `reduce_only=False` — entries only, never exits |
| `hyperliquid_adapter/capabilities.py:51-55` | `supports_trigger_orders=False` — *"the venue supports trigger orders, but they are unexpressible through [the contract]"* |
| `exchange_adapter.OrderType` | `MARKET`, `LIMIT` only — no stop/trigger type exists |
| `intent.stop_price` consumers | `sizing/calculator.py` and `risk_manager/manager.py` **only — never transmitted to the venue** |
| Stop-breach monitor | none exists |
| `auto_flatten_enabled` | `false` in every shipped config |

**Even if every ATR stop had been breached, nothing would have closed
anything.** The original sentence attributes the absence to market
conditions; the actual cause is an absent capability.

**The correct historical statement.** *"Zero `POSITION_CLOSED` events. No
production component emits a reduce-only exit intent, and no venue-side
stop exists, so the close path was unreachable during qualification —
not merely untriggered."*

**Does the qualification verdict change? No.** Item 2 was already
`NOT QUALIFIED` and item 12 already `NOT QUALIFIED`. The measured results
— 42 events, 8 equity rows, fee reconciliation to ten decimal places —
are unaffected and were re-verified on 2026-08-08 as byte-identical.

**What does change is §5's remedy.** The statement *"Closing the two open
items requires only a longer observation window — no further
engineering"* is **wrong for item 2**. No observation window of any
length could have closed a position. Closing item 2 requires engineering:
a component that emits `reduce_only=True`. Item 12 (funding) is
unaffected — that genuinely does require only elapsed time.

**Why this is recorded as an addendum.** §1 is point-in-time evidence.
The original wording is preserved so the error, and its correction,
remain auditable. Reviewers should read item 2 together with this
addendum.

---

## Addendum B — 2026-08-09 · the close path is now reachable and live-proven, and item 2 is still NOT QUALIFIED

**Everything above, Addendum A included, is preserved exactly as
written.** This addendum records new evidence. It alters no original
figure, status, verdict or line, and it changes no count: **10 of 12
QUALIFIED; items 2 and 12 remain `NOT QUALIFIED`.**

**The triggering event.** Addendum A concluded that closing item 2
*"requires engineering: a component that emits `reduce_only=True`"*. That
component was built, and two supervised lifecycles were then executed
against the Hyperliquid **testnet** with `strategy_kind = engine_test`.
The first failed for a reason a capability audit could not have found;
the second succeeded.

**Lifecycle #1, 2026-08-08 — the exit was emitted, and refused.** A
canonical-path entry filled a real position. The automated reduce-only
close was then rejected by `RiskManager` with
`FAIL_SAFE / STALE_DATA`, violated limit
`position:pm:default:1:position(age=344.576899s)`. The position could not
be closed through the engine at all and was **closed by hand at the
venue** (`cloid = None`). Addendum A had found **one** obstruction — no
emitter. There were **two**.

**Root cause.** `PositionSnapshot.updated_at_utc` records the last
position-state **mutation**, not an observation: nothing refreshes it
between open and close, because `AccountingSync.update_marks()` pushes
fresh marks to the *portfolio*, never to the position. `RiskManager`
carried it in its observation-freshness set, so every position became
permanently stale `max_stale_data_seconds` after opening, and every later
intent for it was `FAIL_SAFE`-rejected — **including its own reduce-only
close**. Treating a mutation stamp as freshness data was the
architectural defect.

**The correction — Option B, `788729e`.** Position-state timestamps were
removed from `RiskManager`'s observation-freshness set. Every genuine
observation check is intact: `portfolio_snapshot.updated_at_utc`,
`funding_info.as_of_utc`, `correlation_info.as_of_utc`, and the
future-timestamp guard all still `FAIL_SAFE`.

**Regression evidence.** Ten dedicated stale-position tests were added;
**six were confirmed failing against the pre-fix implementation** with
the live signature above, and four prove that genuine freshness
protection still fires while an open position is present. Total
regression at the time of the fix: **2,152 passed, 0 failed**.

**Lifecycle #2, 2026-08-09 — live evidence.** ENGINE_TEST only, testnet
only, executed through the canonical path by a supervised runner
(`9a1f142`, 54 tests; full regression **2,206 passed**; no frozen-module
change). The probe was enabled solely through a temporary
out-of-repository configuration; shipped `config/strategies.toml` was
never modified.

| Measured | Value |
|---|---|
| Entry | `0.00025` BTC filled through the canonical path |
| Ageing before the close | **≈195 s of real elapsed time**, past the **150 s** `max_stale_data_seconds` threshold — no clock injection, no timestamp manipulation |
| Risk decision on the aged close | **`APPROVED`** — the exact condition that returned `FAIL_SAFE / STALE_DATA` in lifecycle #1 |
| Close intent | `reduce_only=True`, canonical path, engine-generated `cloid` (`0x1ce3e84b…`); the venue clamped the deliberately over-asked size to the remaining position |
| Close outcome | filled; **`POSITION_CLOSED` recorded — the first in this project's history** |
| Venue after | **flat**: positions `0`, `openOrders` `0` |
| Reconciliation | local ↔ venue **matched** |
| Operator involvement | **no manual close, no retry, no direct `adapter.place_order`, no risk bypass**; clean shutdown, no process left running |

**What this proves.** The **execution half** of the close path is
live-proven on testnet: an exit intent can be emitted, approved for an
**aged** position, routed through the canonical path, filled, recorded as
`POSITION_CLOSED`, and reconciled flat. **Option B (`788729e`) is
live-proven for the stale-position freshness defect.** Addendum A's
sentence *"Even if every ATR stop had been breached, nothing would have
closed anything"* was true of the 2026-08-07 run and is now superseded
prospectively: something can close something.

**What this does NOT prove — item 2 remains `NOT QUALIFIED`.** The
lifecycle **narrows** item 2's remaining scope; it does not satisfy it.

- **A · Measurement half — unexercised.** §1 item 2 requires that
  trade-level metrics stop being *"unexercised end-to-end"*, and §3 names
  `profit_factor`, `payoff_ratio`, `win_rate`, `expectancy`,
  `average_win/loss` and `average_holding_seconds` as having **no live
  confirmation**. That is still true. The measurement layer was not in
  this lifecycle's path — `EquityLog` is constructed only in
  `scripts/run_platform.py`, the platform was never started, and no
  scoreboard was produced. Events and attribution existing is **not** the
  same as the metrics being exercised end-to-end.
- **B · Production-emitter criterion — unmet.** The only
  `reduce_only=True` emitter in this lifecycle was the **ENGINE_TEST**
  lifecycle probe, which is **disabled in shipped configuration**. Six of
  Addendum A's seven audit rows were re-verified on 2026-08-09 and are
  **unchanged**: `candle_strategy.py:281` still emits `reduce_only=False`;
  `supports_trigger_orders=False`; `exchange_adapter.OrderType` is still
  `MARKET`, `LIMIT` only; no stop-breach monitor exists;
  `auto_flatten_enabled = false` in every shipped config. Only the
  *"zero `reduce_only=True` in production"* row is superseded, and only by
  an ENGINE_TEST plugin. **No production strategy can autonomously close a
  position, and no production close/trigger path has been demonstrated.**
- **C · Sample.** One close, one symbol, one direction. The ✅ rows in §1
  rest on populations — 42 events, 8 rows, 26 metrics — not on a single
  observation.

**Item 12 (funding) — unchanged, `NOT QUALIFIED`.** The hold was ≈199
seconds and `cumFunding` was **0**: no funding settlement occurred, so the
path is still **untested, not proven**. Addendum A's judgment that item 12
*"genuinely does require only elapsed time"* stands.

**Other §3 statements — unchanged, with one narrowing.** The **`FAIL`
verdict has still never fired**; no verdict of any kind was produced here.
*"Slippage is zero by construction (Phase 1 simulator)"* remains true of
the simulated run. *"The simulated venue fills every order in full at its
limit price… the gap is unmeasured"* is now **incomplete rather than
false**: real fills were partial and executed inside the limit, giving
**several observed legs — not a statistical distribution**, and no
performance or profitability inference may be drawn from them.

**Research boundary.** `strategy_kind = engine_test` throughout. This
evidence is recorded in **no** Alpha Library entry, **no** Research
Ledger entry, **no** Research Decisions entry, **no** Alpha Scorecard and
**no** campaign. It is **execution-infrastructure qualification evidence
only**, and establishes nothing about alpha, edge, profitability,
execution quality, or mainnet readiness.

**Explicit qualification status after this addendum.**

| | |
|---|---|
| Overall | **10 of 12 QUALIFIED** — unchanged |
| Item 2 · close | ❌ **NOT QUALIFIED** — *partially resolved*: execution half live-proven, measurement half unexercised, production-emitter criterion unmet |
| Item 12 · funding | ❌ **NOT QUALIFIED** — unchanged |
| All other items | unchanged |

**A note on §5's remedy.** Addendum A was right to retract *"no further
engineering"* for item 2. The engineering has now been done twice — an
exit emitter, then the `788729e` freshness correction — and item 2 is
still open, because it additionally requires the measurement layer and a
production emitter.

**Why this is recorded as an addendum.** For the same reason Addendum A
was: §1 is point-in-time evidence, and it is preserved so that the
sequence — failure, root cause, fix, regression, live proof — remains
auditable. Reviewers should read item 2 together with **both** addenda.
