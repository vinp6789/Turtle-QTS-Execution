# Final Independent Production Audit

**Date:** 2026-07-21
**Scope:** full uncommitted production diff (app layer + authorized trading_system
additions), deployment surface, regression verification, testnet readiness.
**Method:** verified from source; no reliance on prior audit conclusions except
where re-checked. Frozen Modules 1–10 confirmed untouched (`git status` clean on
every frozen package; the only frozen-adjacent changes are the pre-authorized
additive seams in `trading_system/execution` and `trading_system/scheduling`,
all defaulted to `None`/`()` so prior behavior is byte-identical).

---

## 1. Regression — independently verified

`python -m pytest tests -q` on this machine (Windows 11, Python 3.13.7,
pytest 9.1.1): **820 passed, 5 subtests passed, 0 failed** (12.15s).
Matches the handover claim exactly.

Notes:
- The machine had no pytest installed (installed fresh for this run); there is
  no `requirements-dev.txt` pinning test tooling. See ENV-1.
- Bare `python -m pytest` (no path) fails: collection sweeps `scratchpad/` and
  chokes on a binary file. There is no pytest config scoping `testpaths`.
  Use `pytest tests`, or add a minimal config. See ENV-2.

## 2. Fix-by-fix source verification (all closed items re-checked)

| Fix | Verified implementation | Verdict |
|---|---|---|
| C1 accounting wiring | `app/runtime/accounting.py` + cycle bracketing in `state.py`; fixed-id initial deposit seed | sound |
| C2 quantization | `trading_system/execution/quantization.py` (ROUND_DOWN size, directional price, 5 sig figs / 6−szDecimals, integer-always-legal — matches Hyperliquid's published rules); fail-closed on missing symbol rules; fail-fast metadata fetch (`venue_rules.py`) with event-store lock released on failure | sound |
| F1 crash-window healing | portfolio legs always attempted, amounts recomputed from the fill, durable fill-id-keyed dedup | sound |
| F2/H-B multi-fill close | per-fill PnL with `leg_id=fill_id`; in-memory close accumulation rebuilt from venue fill history; single terminal `record_exit(CLOSE)`; margin released only at full close (conservative) | sound |
| F3 short-side PnL | side-aware direction applied in both realized and unrealized paths; frozen long-only figures never fed to the ledger | sound |
| F4 staleness | boot-fails unless `RISK_MAX_STALE_DATA_SECONDS > CYCLE_INTERVAL_SECONDS` | sound |
| AD-25 (levels + mapping windows) | `docs/ADR_ACCOUNTING_CRASH_WINDOWS.md`: both windows one-append wide, conservative, loud, operator-recoverable | remains **accepted** |
| H-A open-order suppression | `(symbol, reduce_only)` filter in `cycle.py`; UNKNOWN counts as live; reduce-only never suppressed by a resting entry; surfaced in `CycleResult.suppressed_by_open_orders` | sound (see DOC-2) |
| M1 durable stop | ESM `EMERGENCY_KILL_TRIGGERED` propagation; boot-time restore from replayed ESM state; cycle gate raises before any I/O | sound |
| H1 fail-closed control | 503 when API_KEY unset/whitespace; `hmac.compare_digest` when set | sound |
| H2 cancel-before-revoke | best-effort bounded `cancel_all()` strictly before one-way revocation; failure recorded, revocation proceeds | sound |
| H3 read isolation | all read endpoints + metrics use `snapshot_for_reads()` (no lock, no venue I/O); `adapter.health()` confirmed flag-only (adapter.py:212); snapshot refreshed by the single producer and on stop | sound |
| H5 telegram lifecycle | bot tied to app lifespan; fail-clear settings validation when explicitly enabled | sound |
| Module 3.1 `O_BINARY` | applied at `event_store/store.py:210`, regression-tested (`test_event_store.py:540`) | closed |

**No new capital-safety defect was found.** The known residuals (AD-25 W1/W2,
multi-fill cosmetic `remaining_quantity`, partial-close full margin hold,
latent amend-TIF on an unreachable path, M2/M3/M7) remain accepted — nothing
observed makes any of them unsafe.

## 3. New findings

### SEC-1 — plaintext secrets file `env` was one character away from leaking (HIGH — remediated in part, action required)
The untracked root file `env` holds live secrets in plaintext: the Hyperliquid
wallet **private key**, the signing key, the control API key, and a Telegram
bot token + chat id (two of them as bare unlabeled lines — the file is not even
a loadable env file).

- `.gitignore` only had `env/` — a **directory** rule that does not match a
  file named `env`. The file showed as untracked-but-unignored: one
  `git add -A` from committing a wallet private key.
- `.dockerignore` covered `.env`/`venv` but not `env`, and the Dockerfile does
  `COPY . .` — any local `docker compose up --build` would bake the key into
  the image layers at `/app/env`.

**Remediated now:** `env` added to both `.gitignore` and `.dockerignore`
(verified with `git check-ignore`).
**Still recommended (operator action):**
1. Move the values into `.env` (already ignored, and what docker compose
   actually auto-loads) and delete `env`.
2. If a Docker image was ever built from this directory (daemon was down
   during the audit, so this could not be checked), treat the wallet key as
   exposed and rotate before mainnet.
3. Long-term: keys used from an unencrypted Downloads folder should be rotated
   before mainnet regardless — the mainnet wallet should be freshly generated.

### OBS-1 — `last_error` never clears (LOW, affects soak observability)
`AppState.last_error` is written on every failure *and* on benign accounting
notes ("partial close … awaiting remaining fills"), but no code path ever
resets it. One transient venue error on day 1 of a 72-hour soak stays on
`/health`, `/status`, and metrics for the remaining days, and a soak
pass/fail criterion of "last_error empty" would false-fail. Recommend clearing
on a clean cycle (or exposing `last_error_at_utc` alongside it) before the
soak. Not a capital-safety issue.

### DOC-1 — `update_marks` idempotency comment is inaccurate (LOW, doc-only)
`accounting.py` claims idle cycles with unmoved marks append nothing, but the
request key embeds `snapshot.updated_at_utc`, which the marks append itself
advances (portfolio_manager/manager.py:156) — so the key never repeats and
every cycle with an open position appends one UPDATE_MARKS event regardless.
Replay correctness and the values themselves are unaffected, and in live
trading marks move every cycle anyway (so the growth rate is what the design
already implies): fix the comment, and note event-store growth of ~1 event per
cycle per open-position period when planning long-lived mainnet operation.

### DOC-2 — H-A not recorded in AUDIT_HISTORY.md (INFO)
The H-A open-order suppression fix is implemented and regression-covered
(`tests/test_open_order_suppression.py`) but is missing from the ticked list
in `AUDIT_HISTORY.md` and from PROJECT_HANDOVER's completed-fixes list.

### ENV-1 / ENV-2 — reproducibility nits (INFO)
No `requirements-dev.txt` (pytest unpinned, was absent from the machine); no
pytest config scoping collection to `tests/` (bare `pytest` fails on
`scratchpad/`). Two small files would make the regression run turnkey.

### Housekeeping (INFO)
Empty `New Text Document.txt` at root — delete. Root `amend_probe*/
amend_regression*/testnet_validation.log` event-store logs are gitignored
(`*.log`) and harmless; archive or delete at will.

## 4. Testnet validation readiness (focus item 2)

Prior progress (2026-07-18, adapter-level, from scratchpad artifacts):
reads, place, query, and amend all succeeded against Hyperliquid testnet.
An initial cancel-after-amend failure was root-caused — the venue mints a
**new oid on modify** (cloid stable) — and the adapter's amend path was
verified to return the live oid: the final probe passed **9/9 runtime checks**
(modify→new oid, status on new oid, cancel on new oid, no stale/duplicate
orders, cloid invariant).

Current account state (checked live today via the public info endpoint,
read-only): **0 open orders, 0 positions, perp accountValue 0.0, 999 USDC on
spot**. The stale probe orders that had 4.80 USDC reserved are gone.

Prerequisites before the app-level testnet run:
1. **Transfer USDC from spot to perps** on the testnet account (signed action
   — operator). Perp equity is currently zero; nothing can trade.
2. **Create the live-mode testnet config** — copy `deploy/engine.paper.toml`
   per its own header: `mode = "live"`, `network = "testnet"`, and uncomment
   `wallet_key_ref` (required for live mutations).
3. Set `PORTFOLIO_INITIAL_DEPOSIT` to the transferred perp equity (applied
   exactly once per event store) and point `ENGINE_STORE_PATH` at a **fresh**
   store for the validation run.
4. Then execute the handover checklist: place → query → amend → cancel →
   cancel-all → emergency stop → restart → replay validation → accounting
   validation → 24–72h soak (fix OBS-1 first if the soak gates on last_error).

## 5. Verdict

| Area | Verdict |
|---|---|
| Engineering / capital safety | **GO** — 820/820 verified, every closed fix re-verified from source, no new capital-safety defect, residuals remain safely bounded |
| Secrets / deployment hygiene | **CONDITIONAL** — SEC-1 ignore rules fixed in this audit; move `env` → `.env` and decide on rotation before any image build or mainnet key use |
| Testnet validation | **READY** once spot→perp transfer + live-testnet config exist (§4) |
| Mainnet | **NO-GO until** testnet checklist + soak complete (as already planned) and SEC-1 operator actions are done |
