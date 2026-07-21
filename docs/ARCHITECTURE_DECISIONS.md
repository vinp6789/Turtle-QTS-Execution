# ARCHITECTURE_DECISIONS.md

Architecture decisions that are **evidenced in the source** of the Turtle
Execution Engine. Each records the decision and the repository artifact that
demonstrates it. This is a description of decisions already made and frozen,
not a proposal; nothing here is invented.

## AD-1: Package-per-module, no single-file design
Each module is its own package with an `__init__.py` exposing a minimal
`__all__`. There is no top-level entrypoint. *Evidence:* nine package
directories; no root-level `.py`.

## AD-2: Strict acyclic, lower-numbered-only dependencies
Modules depend only on lower-numbered modules; the import graph is acyclic,
with `config`, `secrets_boundary`, and `event_store` foundational.
*Evidence:* actual cross-package imports (see `DEPENDENCY_GRAPH.md`).

## AD-3: Event sourcing as the system of record
State transitions are recorded through an append-only, crash-safe event log
with replay. Business modules persist via the event store rather than
ad-hoc storage. *Evidence:* `event_store` module docstring ("records and
replays"); managers reference "persist through Module 3's Event Store".

## AD-4: Binary, checksummed record framing with explicit recovery classes
Records use a magic + version + id + length + SHA-256 checksum frame.
Torn-tail writes are recovered; bad magic, unsupported version, mid-file
corruption, and non-monotonic ids are hard errors. *Evidence:*
`event_store/codec.py`, `event_store/store.py` (`_scan_file`).

## AD-5: Single-writer exclusive lock
Exactly one `EventStore` may hold the write lock; recovery truncation is
safe only because the lock is held. *Evidence:* `EventStore` docstring and
lock acquisition in `store.py`.

## AD-6: Cross-platform locking via an import-guarded shim
File locking is abstracted in `event_store/_locking.py`, selecting `fcntl`
(POSIX) or `msvcrt` (Windows), both import-guarded. The POSIX path is
byte-for-byte the original behavior. *Evidence:* `event_store/_locking.py`;
`store.py` imports `acquire_exclusive_nonblocking`/`release_lock`.

## AD-7: Idempotency ledger for safe retries
An `idempotency_key` deduplicates actions so a crashed caller can retry
without duplicating an exchange action. *Evidence:* `append()` idempotency
logic and index in `store.py`; `IdempotencyCache` in `exchange_adapter`.

## AD-8: Secrets never leave the boundary
The only signing surface is `SigningBoundary.sign(...)`; raw key material is
never exposed. Signing uses HMAC-SHA256; revocation is one-way. *Evidence:*
`secrets_boundary/boundary.py`, `backend.py` (`EnvironmentHmacBackend`).

## AD-9: Events must not carry secrets
Payload field names are scanned for secret-suggestive names and rejected.
*Evidence:* `_FORBIDDEN_KEY_SUBSTRINGS` and `_scan_forbidden_keys` in
`store.py`.

## AD-10: Abstract exchange contract, concrete adapters external
`ExchangeAdapter` defines the contract with no exchange-specific logic and
no real network; a concrete adapter implements it unchanged. *Evidence:*
`exchange_adapter/adapter.py`, `__init__.py`; only `MockExchangeAdapter`
exists.

## AD-11: Typed, normalized exchange models
Adapter models carry no exchange-specific fields; a concrete adapter
translates its own venue shape into them. *Evidence:*
`exchange_adapter/models.py`.

## AD-12: Operation-safety classification with a retry policy
Operations are tagged with an `OperationSafety` and retried through a
`RetryPolicy`, with reconciliation via `reconcile()` →
`ReconciliationReport`. *Evidence:* `exchange_adapter/retry.py`,
`adapter.py`.

## AD-13: Deterministic finite state machines with replay integrity
Execution, order, and position lifecycles are explicit transition tables
that reject illegal transitions and verify replay integrity. *Evidence:*
`execution_state_machine/transitions.py`, `order_manager/states.py`,
`position_manager/states.py`; `ReplayIntegrityError` in several packages.

## AD-14: Risk as a pure approval/veto with fail-safe
`RiskManager` only approves or vetoes a fully-specified trade, returning a
`Decision` and `ReasonCode`, and can `FAIL_SAFE` on missing/stale data.
*Evidence:* `risk_manager/models.py` (`Decision`, `ReasonCode`),
`manager.py`.

## AD-15: Portfolio as a single-lock ledger with accounting invariants
`PortfolioManager` owns cash/margin/PnL/exposure/heat and raises
`InsufficientFundsError`/`InsufficientMarginError`/`AccountingInvariantError`
on invalid states. *Evidence:* `portfolio_manager/manager.py`, `errors.py`.

## AD-16: Decimal money arithmetic
Capital-sensitive values use `Decimal`, not float. *Evidence:* `Decimal`
usage in `risk_manager/models.py` (e.g. `CORRELATION_THRESHOLD =
Decimal("0.5")`).

## AD-17: Standard-library-only footprint
No third-party runtime dependency; configuration uses stdlib `tomllib`.
*Evidence:* import scan across all packages; `config/loader.py`.

## AD-18: Additive-only freeze discipline
Frozen modules change only via authorized critical-defect correction; new
capability is added, not retrofitted by rewrite. *Evidence:* the Module 3
reconciliation was a minimal additive shim with no public-API change; see
`DEVELOPMENT_WORKFLOW.md`.

## AD-19: Internal authorization and exchange-native authentication are separate secret domains
`SecretsConfig.wallet_key_ref` is a dedicated, optional reference for a
venue wallet-signing key (e.g. EIP-712/secp256k1), kept distinct from
`signing_key_ref` rather than reused or left outside the validated config
schema. *Evidence:* `config/schema.py` (`SecretsConfig` docstring and
field), `config/loader.py` (`_validate_secrets`,
`TURTLE_EXEC_WALLET_KEY_REF` override). *Rationale (ADR-20/ADR-21,
this session):* a signature's contract is defined by its verifier; Turtle's
`SigningBoundary.sign()` unconditionally binds every signature to a
Turtle-internal, domain-separated preimage (`secrets_boundary/domain.py`),
which is a different and incompatible contract from an exchange verifying
its own native signature format. Reusing one key reference for both would
be cross-primitive key reuse with coupled rotation of a capital-moving
secret; this AD keeps the two domains structurally separate at the
configuration layer. This is an authorized additive evolution of a frozen
module (Module 1, re-frozen as Module 1.1) under a distinct authorization
category from AD-18's critical-defect exception -- see
`DEVELOPMENT_WORKFLOW.md`.

## AD-25: Accepted accounting crash windows (venue-ACK <-> EventStore)
The app-layer accounting synchronization retains exactly two crash
windows, each one local fsync wide: venue-order-acceptance -> levels
append (W1), and Module 7's self-minted position CREATE -> the
order->position mapping append (W2). Both are accepted, not fixable in
place: W1 is a distributed-atomic-commit impossibility (the venue's
matching engine and the local EventStore are independent durability
domains with no shared coordinator), and every reachable reordering or
compensation either recreates an equivalent window, requires modifying
frozen Module 6 (carrying the stop level in the SUBMIT event -- the
correct long-term fix if the module is ever reopened under AD-18), or
fabricates capital data. The failure mode is bookkeeping-conservative
(nothing is invented; no fabricated position ever enters a risk
decision), loud (per-sync notes plus a reconciliation mismatch every
cycle until resolved), and replay-safe (every accounting fact is a
single idempotent append; re-syncing the venue's fill history is a
proven zero-append no-op). *Evidence:* `app/runtime/accounting.py`
(module docstring), `trading_system/scheduling/cycle.py` (`on_execution`
hook), crash-injection regression tests in `tests/test_app_accounting.py`
(`TestLevelsCrashWindow`, `TestF1CrashWindowHealing`). *Full analysis
with crash timeline:* `ADR_ACCOUNTING_CRASH_WINDOWS.md`.
