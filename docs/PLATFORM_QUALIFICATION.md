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
