"""Trading System layer for the Turtle Execution Engine.

Sits ABOVE orchestration and composition_root, which remain frozen
infrastructure this layer only ever calls into, never reimplements:
composition_root builds the wired Engine; orchestration coordinates
lifecycle/synchronization/reconciliation/dispatch. Nothing here
constructs a frozen module directly, and nothing here duplicates
execution, risk, reconciliation, or synchronization logic.

This package is a namespace for independent sub-packages, each with its
own public API (import from the sub-package directly, e.g.
`from trading_system.strategy import Strategy`, not from this top-level
module, which stays a thin docstring-only anchor):

    trading_system.strategy      -- pluggable Strategy interface (Milestone 5)
    trading_system.market_data   -- read-only market-data facade (Milestone 5)
    trading_system.sizing            (future milestone)
    trading_system.portfolio_construction (future milestone)
    trading_system.execution         (future milestone)
    trading_system.monitoring         (future milestone)
    trading_system.reporting          (future milestone)

Scheduling/runtime loops are explicitly deferred -- no sub-package here
contains a timer, thread, or loop until a future milestone authorizes it.
"""
