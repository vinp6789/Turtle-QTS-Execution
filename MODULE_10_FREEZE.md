# Module 10 — Hyperliquid Adapter — Freeze Package

**Status:** Ready to freeze (no proven production blocker)
**Prepared:** 2026-07-18
**Scope:** `hyperliquid_adapter/` — concrete `ExchangeAdapter` for the Hyperliquid venue (read-only + authenticated mutations)

---

## 1. Release Notes

Module 10 implements the frozen Module 5 `ExchangeAdapter` contract for Hyperliquid. It owns venue transport, translation of native venue shapes into Module 5 typed models, venue error mapping into Module 5's closed error hierarchy, and venue request signing. It owns **no business logic** — it never decides whether, when, or how much to trade.

Delivered work packages:

| WP | Deliverable | Files |
|----|-------------|-------|
| WP-1 | Package skeleton + capability declaration | `__init__.py`, `capabilities.py` |
| WP-2/3 | Order attribution interface + venue error mapping | `errors.py` |
| WP-4 | REST transport seam (stdlib `urllib`) | `transport.py` |
| WP-5 | Read-only `HyperliquidAdapter` (11 read/lifecycle methods, `find_order` override) | `adapter.py`, `codec.py` |
| WP-6 | Mutation-transport foundation (nonce source, request envelope) | `exchange.py` |
| WP-6/7 | Venue signing (EIP-712 phantom-agent secp256k1) | `signing.py` |
| WP-8 | `/exchange` action construction + msgpack action hashing; four authenticated mutations | `action_codec.py`, `adapter.py` |
| M1 | Durable engine-id ↔ venue-token mapping | `mapping.py` |

Key behaviors:
- **Reads** (`get_positions/orders/balances/mark_price/funding_rate/order_status/fills`, `find_order`, `reconcile`) run against the public `/info` endpoint — no authentication, standard-library only.
- **Mutations** (`place_order`, `cancel_order`, `cancel_all`, `amend_order`) are authenticated against `/exchange`, gated by the SigningBoundary Emergency-Kill check *before* any signing or transmission, and are `UNSAFE_NEVER_AUTO_RETRY`.
- **Amend = cancel-and-replace:** a successful modify retires the pre-modify oid and allocates a new one under the same cloid. The adapter resolves the live replacement via `frontendOpenOrders` (never returns the obsolete oid) and **fails loud** if no replacement is found.
- **Attribution (M1):** every returned `Order`/`Fill` carries the engine `client_order_id`, resolved through the durable mapping; unresolvable venue entries are excluded, never mislabeled.

---

## 2. Architecture Summary

### Dependencies (frozen modules only)
- **Module 5** `exchange_adapter` — the abstract contract, typed models, closed error hierarchy, retry policy.
- **Module 2** `secrets_boundary` — `SigningBoundary` authorization gate (Emergency Kill via key revocation).
- **Module 3** `event_store` — shared canonical `EventStore` backing the durable order-id mapping.

### Components
```
__init__.py        Public API surface (see §5)
adapter.py         HyperliquidAdapter: reads, find_order override, 4 mutation hooks
codec.py           Pure venue-shape -> Module 5 model translation (Decimal, never float)
capabilities.py    DEFAULT_HYPERLIQUID_CAPABILITIES (adapter's effective contract)
errors.py          Venue error shapes -> closed exception hierarchy
transport.py       Injectable TransportFn seam; stdlib-urllib post_json default
exchange.py        NonceSource (monotonic ms) + /exchange request envelope
action_codec.py    Action dicts + msgpack serialization + keccak connectionId hash
signing.py         HyperliquidWalletSigner: EIP-712 phantom-agent signature
mapping.py         OrderIdMapping: durable engine-id <-> cloid, via EventStore
```

### Two-key signing model (ADR-20/24)
`SigningBoundary` wraps every message in Turtle's domain-separated preimage, so a signature it produces is **not** venue-acceptable. It therefore stays the **authorization gate** (revocation = Emergency Kill), while venue-format EIP-712 signatures are produced separately by `HyperliquidWalletSigner`, keyed on `wallet_key_ref`. Both are independently revocable; a revoked key on either lever stops all mutations.

### Attribution mechanism (M1)
Hyperliquid's 16-byte cloid cannot carry an arbitrary engine `client_order_id`, so the adapter mints a deterministic cloid = `"0x" + first 32 hex of SHA-256(engine_id)` and records the `engine_id → cloid` pair fsync-durably in the shared `EventStore` **before** transmission (persist-before-transmit). Mapping events are adapter-private, source-tagged, and replay-rebuilt; they are invisible to Modules 4/6/7/8.

### Mutation flow (all four hooks)
```
_require_connected -> _require_signer -> authorization_gate(SigningBoundary, Emergency Kill)
  -> [place only] mapping.record(engine_id) durably BEFORE transmit
  -> build action -> connectionId = keccak(msgpack(action)+nonce+vault)
  -> wallet_signer.sign_connection_id -> POST /exchange -> _check_ok -> typed Order
```

---

## 3. Known Limitations

All are **declared/bounded** — none is a proven production blocker.

1. **REST-only (no websocket).** `HealthStatus.websocket_connected` is always `False`; `supports_partial_fill_notifications=False`; no sequence-gap detection. Push notifications require a future WS build.
2. **Modify immediate-full-fill semantics — NOT PROVEN.** Whether a Hyperliquid `modify` can fully fill on submission (rather than always resting) is undocumented in scope and was not reproduced on testnet (the one live modify rested and the venue reported the replacement as `Alo`). If it ever occurred, `_transmit_amend_order` would **fail loud** (`ExchangeAdapterError`) rather than return a stale/wrong oid — the safety-critical invariant holds regardless. Flagged as a **soak-test observation item**, not an engineering defect.
3. **Resting-order tif modeled as GTC.** `codec.parse_order_status`/`parse_open_orders` set `time_in_force = GTC` by default (the venue tif field is not read back into the model). Amend reconstructs the modify wire with this default. Live evidence shows the venue itself returns the replacement's effective tif (`Alo`); the engine's model does not track per-order tif precisely. Bounded, documented.
4. **Fills may under-report.** Whether Hyperliquid echoes `cloid` on `userFills` is unconfirmed (the official SDK's Fill type has no cloid field), so `get_fills` may return fewer entries than exist — the deliberately safe direction (never mis-attributes). Fill attribution by oid remains available via `OrderSnapshot.exchange_order_id`.
5. **`orderStatus` nested-object shape is an assumption.** The nested order object is assumed to share `openOrders`/`frontendOpenOrders`' field shape (venue docs redacted it). Parsing is defensive: a wrong assumption raises a closed-hierarchy error, never fabricates a model.
6. **Unsupported order features (by capability declaration).** No market orders (ADR-22: aggressive-IOC emulation declined), no FOK (no venue equivalent), no trigger orders (unexpressible through the frozen `OrderType`). Risk Manager vetoes these upfront.
7. **Wiring obligations are unowned (INV-16).** The composition root must (a) inject the *same* `EventStore` instance used by OrderManager/state machine, and (b) enforce one engine deployment per venue account. Not enforceable within this module.
8. **Stale public docstring (documentation only).** `hyperliquid_adapter/__init__.py` still reads *"Build state: M1, read-only … The four mutation hooks remain fail-closed: no signing capability exists yet."* This predates WP-6/7/8. **Correct before freeze** (see checklist §7). Behavior is unaffected.

---

## 4. Operational Runbook

### 4.1 Deployment wiring (composition root)
- Construct `HyperliquidAdapter(signing_boundary, signing_key_ref, account_address, …)`.
- Pass the **same** `EventStore` instance used by OrderManager/ExecutionStateMachine (a second open on the same path fails loudly by design).
- For mutations, inject a `HyperliquidWalletSigner(wallet_key_ref, is_mainnet, …)` via `wallet_signer=`. Without it, every mutation fails closed with no network call.
- **One engine per venue account.** Two engines sharing an account would each treat the other's orders as foreign; identical engine ids across deployments would mint identical cloids.

### 4.2 Network / base URL
- `base_url` must match the signer's network. The adapter rejects a `mainnet`/`testnet` mismatch at construction (a mismatched network makes every signed action rejected). Signatures are network-bound (source `"a"` mainnet / `"b"` testnet) and cannot be replayed across networks.

### 4.3 Secrets
- Wallet key is read from env var `TURTLE_SECRET_<WALLET_KEY_REF>` (uppercased ref). A missing/blank/invalid key raises `ExchangeAuthenticationError` (never auto-retried).
- The raw key never leaves `HyperliquidWalletSigner`: no accessor, no `__repr__` exposure, no pickling, no deep-copy. Only the public wallet address is exposed.

### 4.4 Emergency Kill
- **Authorization lever:** revoke `signing_key_ref` at the `SigningBoundary` → every mutation raises before signing/transmit.
- **Wallet lever:** call `HyperliquidWalletSigner.revoke()` (one-way, idempotent) → signing raises, key reference dropped.
- Either lever alone halts all capital-moving actions.

### 4.5 Monitoring / alerting
- Alert on `ExchangeAdapterError` from `amend_order` (the fail-loud "replacement not found in open orders" path — investigate for an immediate-fill or venue anomaly; cross-check `get_fills`).
- Alert on `ExchangeAuthenticationError` (revoked/expired key, or network mismatch).
- Alert on `RateLimitExceededError` (HTTP 429; honors `Retry-After` when numeric).
- Track nonce monotonicity is internal; no action needed unless clock is grossly skewed backward.

### 4.6 New-asset handling
- Coin→asset-index map is cached from the `meta` endpoint and auto-refreshed once on a cache miss. Call `refresh_asset_index()` to force a re-fetch after a new listing (read-only, thread-safe).

---

## 5. Dependency List

**Runtime environment:** Python 3.13 (validated on CPython 3.13, Windows 11).

| Dependency | Constraint | Validated version | Scope |
|------------|-----------|-------------------|-------|
| Python stdlib | — | 3.13 | Frozen core + adapter read-only path (no third-party deps) |
| `eth-account` | `>=0.13.5` | **0.13.7** | Venue signing only (`signing.py`) — secp256k1/keccak the stdlib lacks |
| `msgpack` | `>=1.0.0` | **1.2.1** | Mutation action hashing only (`action_codec.py`) |

Both third-party deps are **imported lazily** — the frozen core and the read-only adapter import and run without them installed. Declared in `requirements.txt`.

---

## 6. Validation Evidence

### 6.1 Automated regression (runtime — this session)
- **Module 10 suite:** `Ran 206 tests … OK` across 14 test files
  (`action_codec, adapter, capabilities, codec, errors, exchange, mapping, mutations, network_and_cache, signing, signing_integration, transport, crash_recovery, signer_concurrency`).
- **Full engine suite:** `Ran 534 tests … OK` — Module 10 introduces no regression in the frozen core (Modules 1–9).

### 6.2 Amend-fix regression coverage (`tests/test_hyperliquid_adapter_mutations.py`)
- `test_amend_returns_live_replacement_oid_from_open_orders_not_stale_cloid_lookup` — asserts the **new** oid (556) is returned, not the stale pre-modify oid (555). **VERIFIED**
- `test_amend_raises_if_replacement_not_in_open_orders_rather_than_returning_stale_oid` — asserts **fail-loud** when no replacement is present. **VERIFIED**
- `test_amend_new_quantity_builds_modify_and_returns_updated_order` — transmits a `modify` carrying the resolved cloid. **VERIFIED**
- `test_amend_gates_on_signing_boundary` — revoked key blocks amend before transmit (Emergency Kill). **VERIFIED**
- `test_amend_venue_error_maps` — venue `{"status":"err"}` maps into the closed hierarchy. **VERIFIED**

### 6.3 Live testnet validation (`scratchpad/amend_regression_out.txt`)
End-to-end place → modify → status → cancel against Hyperliquid testnet. All nine runtime-observable checks **PASS**:
- modify returned a different oid; cloid never changes; no stale oid returned; `get_order_status(new_oid)` succeeds; returned oid equals the venue's live oid; `cancel(new_oid)` succeeds; old oid no longer exists; no open order carries the cloid after cancel; no duplicate orders created.
Observed: original oid `56654306792` → replacement oid `56654307857`, cloid preserved, replacement then cancelled.

### 6.4 Dependency check (runtime)
`eth-account 0.13.7` and `msgpack 1.2.1` importable; read-only path confirmed independent of both via lazy import.

### 6.5 Verdict classification
| Area | Class |
|------|-------|
| Reads / lifecycle / attribution | **VERIFIED** |
| Mutations (place/cancel/cancel_all/amend) incl. signing gate | **VERIFIED** |
| Amend live-replacement resolution + fail-loud | **VERIFIED** |
| Error mapping to closed hierarchy | **VERIFIED** |
| No regression in frozen core | **VERIFIED** |
| Modify immediate-full-fill reachability | **NOT PROVEN** (non-blocking; fail-loud mitigation VERIFIED) |

**No finding is NOT VERIFIED. No proven production blocker remains.**

---

## 7. Final Freeze Checklist

Engineering (code) — complete:
- [x] All 11 read/lifecycle methods implemented and tested
- [x] Four mutations implemented, gated (Emergency Kill), fail-closed without a signer
- [x] Persist-before-transmit + engine-id attribution invariants enforced structurally
- [x] Amend returns live replacement oid, never stale; fails loud otherwise
- [x] Venue/HTTP errors mapped to closed hierarchy; auth never auto-retried
- [x] Wallet key material never exposed (no repr/pickle/deepcopy; revocable)
- [x] Read-only path free of third-party deps (lazy imports)
- [x] 206 module tests + 534 full-suite tests pass
- [x] Live testnet validation passed (9/9 checks)

Pre-freeze actions (required before tagging):
- [ ] **Commit the mutation work.** WP-6/7/8 + M1 are currently uncommitted working-tree state (last commit `afe3114` is WP-5, read-only). The freeze commit must include: `action_codec.py`, `exchange.py`, `mapping.py`, `signing.py`, modified `adapter.py`/`codec.py`/`transport.py`/`__init__.py`, `requirements.txt`, and the new test files. Review `git status` / `git add` output for stray artifacts (e.g. `__pycache__`, `scratchpad/`) before committing.
- [ ] **Correct the stale `__init__.py` docstring** (Known Limitation §3.8) to reflect that mutations and venue signing are implemented (WP-8), not "read-only / fail-closed." Documentation-only edit.
- [ ] Confirm `requirements.txt` is included and dependency versions match the deployment target.

Operational (post-freeze, non-engineering):
- [ ] Composition-root wiring per §4.1 (shared EventStore, one-engine-per-account)
- [ ] Monitoring/alerting per §4.5
- [ ] Testnet soak run characterizing modify-fill behavior (Known Limitation §3.2)
- [ ] Operator runbook distributed

**Freeze recommendation:** Ready to freeze once the two required pre-freeze actions (commit the mutation work; correct the stale docstring) are completed. Both are packaging/documentation steps — no engineering work remains on the adapter itself.
