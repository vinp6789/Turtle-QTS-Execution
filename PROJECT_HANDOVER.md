> **SUPERSEDED.** This was the "current status" snapshot as of the point
> the Alpha Engine work began. It is retained for history (per
> `docs/PROJECT_CONSTITUTION.md`'s decision-log discipline: never rewrite
> history) but is no longer current. **For current status, see
> [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md) or
> [`docs/PROJECT_DASHBOARD.md`](docs/PROJECT_DASHBOARD.md).** The 820/820
> regression baseline recorded below is still accurate for the Execution
> Engine alone; the full current suite (Execution Engine + Alpha Engine)
> is 1,567 passing.

# Project Status (Latest)

## Overall
Execution Engine + Hyperliquid Adapter + App Layer.

All deterministic engineering work is complete.

Full regression:
820 / 820 passing.

Frozen Modules 1–10 remain untouched except previously authorized additive changes (C2 hook in trading_system execution/scheduling).

---

## Completed fixes

### Capital / Trading
- C1 Accounting wiring
- C2 Hyperliquid quantization
- F1 Crash window healing
- F2 Partial exit handling
- F3 Short-side PnL
- F4 Startup staleness validation
- Levels crash window minimized (ADR-25)
- H-B Multi-fill reduce-only close

### Runtime
- M1 Emergency Stop propagated into ESM
- H1 Control endpoints fail closed
- H2 Cancel-before-revoke emergency stop
- H3 Read snapshot cache (no venue I/O under engine lock)
- H5 Telegram lifecycle

---

## Current architecture

Worker
    ↓
run_one_cycle()
    ↓
AccountingSync
    ↓
run_cycle()
    ↓
Execution
    ↓
OrderManager
    ↓
Hyperliquid Adapter

Read endpoints consume cached snapshots only.

Worker is the single producer.

---

## Known accepted residuals

AD-25 accounting crash window.

Multi-fill closed PositionManager remaining_quantity cosmetic residual.

Partial-close full margin held until completion (conservative).

Latent amend-TIF issue (unreachable runtime).

M2/M3/M7 remain operational, non-blocking.

---

## Remaining work

1. Final independent production audit
2. Hyperliquid testnet validation
3. Multi-day soak test
4. Mainnet rollout

---

## Testnet checklist

- Place order
- Query
- Amend (if enabled)
- Cancel
- Cancel all
- Emergency stop
- Restart
- Replay validation
- Accounting validation
- 24–72 hour soak

---

## Current regression

820 / 820 pass