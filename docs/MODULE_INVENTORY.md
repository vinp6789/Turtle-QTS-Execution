# MODULE_INVENTORY.md

Inventory of Execution Engine Modules 1–9. Every field is taken from actual
repository contents: `__all__` for Public API, real imports for Depends On,
and `pytest --collect-only` for test counts.

**Totals:** 9 packages, 9 test files, **306 tests collected** (plus 5
runtime subtests from a `self.subTest` loop in `test_secrets_boundary.py`).
Verified 306 passing on Windows (CPython 3.13) after the Module 3.1
correction; the pre-correction 305 on Linux (CPython 3.12.3) is unchanged by
the fix. Freeze status for all nine is **FROZEN** per the project statement
("completed and frozen Execution Engine Modules 1–9"); Module 3 is frozen as
**Module 3.1** following a critical Windows defect correction (v1.0.1).

| # | Package | Responsibility (from `__init__` docstring) | Public API (`__all__`) | Depends On | Test File | # Tests | Freeze |
|---|---------|--------------------------------------------|------------------------|-----------|-----------|--------|--------|
| 1 | `config` | Load, validate, provide immutable typed config; holds no secrets, no business logic | `load_config`, `EngineConfig`, `ExchangeConfig`, `UniverseConfig`, `RiskConfig`, `RiskProfileParams`, `OperationalConfig`, `SecretsConfig`, `TelegramConfig`, `LoggingConfig`, `ConfigError`, `ConfigFileError`, `ConfigValidationError` | (none) | `tests/test_config.py` | 22 | FROZEN |
| 2 | `secrets_boundary` | Resolve secret references to signing capability without exposing raw key material | `SigningBoundary`, `SigningPurpose`, `SigningBackend`, `EnvironmentHmacBackend`, `build_preimage`, `ENGINE_ID`, `MAX_SIGNING_PAYLOAD_BYTES`, `SecretsError`, `SecretsConfigurationError`, `SecretsStartupError`, `UnknownSecretReferenceError`, `SecretRevokedError`, `PayloadTooLargeError` | (none) | `tests/test_secrets_boundary.py` | 41 | FROZEN |
| 3 | `event_store` | Durable, append-only, crash-safe event sourcing + idempotency ledger; records/replays only | `EventStore`, `read_events`, `EventType`, `Event`, `RecoveryReport`, `MAX_PAYLOAD_BYTES`, `MAX_IDEMPOTENCY_KEY_LENGTH`, `EventStoreError`, `MalformedEventError`, `CorruptEventStoreError`, `EventStoreLockError`, `EventStoreClosedError` | (none) | `tests/test_event_store.py` | 38 | FROZEN (3.1) |
| 4 | `execution_state_machine` | Single source of truth for execution lifecycle state; deterministic, event-driven | `ExecutionStateMachine`, `State`, `Trigger`, `TransitionResult`, `TRANSITION_TABLE`, `LEGAL_TRIGGERS_BY_STATE`, `TRIGGER_EVENT_TYPE`, `ExecutionStateMachineError`, `IllegalTransitionError`, `UnknownTriggerError`, `ReplayIntegrityError` | `event_store` (3) | `tests/test_execution_state_machine.py` | 42 | FROZEN |
| 5 | `exchange_adapter` | Abstract exchange contract + mock; no exchange-specific logic, no real network, no decisions | `ExchangeAdapter`, `MockExchangeAdapter`, `DEFAULT_MOCK_CAPABILITIES`, `Symbol`, `OrderSide`, `OrderType`, `TimeInForce`, `OrderStatus`, `ConnectionState`, `ExchangeCapabilities`, `OrderRequest`, `AmendRequest`, `CancelRequest`, `CancelAllRequest`, `Order`, `Fill`, `Position`, `Balance`, `MarkPrice`, `FundingRate`, `HealthStatus`, `ReconciliationReport`, `AuditRecord`, `ExchangeAdapterError`, `ExchangeConnectionError`, `ExchangeTimeoutError`, `ExchangeAuthenticationError`, `RateLimitExceededError`, `OrderUnknownError`, `ExchangeRejectedOrderError`, `StaleSnapshotError`, `SequenceGapError`, `ReconciliationMismatchError`, `IdempotencyCache`, `Operation`, `OperationSafety`, `DEFAULT_OPERATION_SAFETY`, `RetryPolicy`, `execute_with_retry` | `secrets_boundary` (2) | `tests/test_exchange_adapter.py` | 41 | FROZEN |
| 6 | `order_manager` | Order lifecycle after a trade decision: id generation, sequencing, replayable order state | `OrderManager`, `OrderSnapshot`, `OrderLifecycleState`, `OrderLifecycleTrigger`, `TRANSITION_TABLE`, `LEGAL_TRIGGERS_BY_STATE`, `OrderManagerError`, `OrderNotFoundError`, `IllegalOrderTransitionError`, `OrderStateInconsistencyError`, `ReplayIntegrityError` | `event_store` (3), `execution_state_machine` (4), `exchange_adapter` (5) | `tests/test_order_manager.py` | 23 | FROZEN |
| 7 | `position_manager` | Live-position lifecycle: fill accumulation, avg price, PnL, T1/T2/stop status, close, archival | `PositionManager`, `PositionSnapshot`, `ClosedLeg`, `PositionLifecycleState`, `PositionLifecycleTrigger`, `TRANSITION_TABLE`, `LEGAL_TRIGGERS_BY_STATE`, `PositionManagerError`, `PositionNotFoundError`, `IllegalPositionTransitionError`, `PositionStateInconsistencyError`, `ReplayIntegrityError` | `event_store` (3), `exchange_adapter` (5) | `tests/test_position_manager.py` | 22 | FROZEN |
| 8 | `portfolio_manager` | Portfolio-level ledger only: cash, margin, PnL, exposure, heat, open-position set | `PortfolioManager`, `PortfolioSnapshot`, `PortfolioManagerError`, `InsufficientFundsError`, `InsufficientMarginError`, `AccountingInvariantError`, `ReplayIntegrityError` | `event_store` (3) | `tests/test_portfolio_manager.py` | 21 | FROZEN |
| 9 | `risk_manager` | Pure approval/veto over a fully-specified proposed trade; never sizes or submits | `RiskManager`, `RiskManagerLimits`, `TradeRequest`, `FundingInfo`, `CorrelationInfo`, `CorrelationEntry`, `Decision`, `ReasonCode`, `RiskDecision`, `CORRELATION_THRESHOLD`, `RiskManagerError`, `RiskManagerConfigurationError` | `config` (1), `execution_state_machine` (4), `exchange_adapter` (5), `position_manager` (7), `portfolio_manager` (8) | `tests/test_risk_manager.py` | 56 | FROZEN |

## Notes

- **Public API** columns list exactly the names in each package's
  `__all__`. All nine packages declare `__all__`.
- **# Tests** counts test methods collected per file; the
  per-file sum (22+41+38+42+41+23+22+21+56) equals the collected total
  **306** (the event_store count rose 37→38 with the Module 3.1 Windows
  binary-framing regression test).
- **Module 9 numbering** is inferred by elimination (no literal `Module 9`
  string exists in the repo) — see `DEPENDENCY_GRAPH.md`.
