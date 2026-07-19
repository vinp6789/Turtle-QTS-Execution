"""The wired Engine: a plain container for exactly one instance of every
constructed component, plus start()/stop() lifecycle.

Owns no business logic and runs no loop. It never decides whether, when,
or how much to trade -- callers drive order_manager/position_manager/
portfolio_manager/risk_manager themselves. See composition_root/wiring.py
for how an Engine is built.
"""

from typing import Optional

from event_store import EventStore
from exchange_adapter import ExchangeAdapter, HealthStatus
from execution_state_machine import ExecutionStateMachine
from order_manager import OrderManager
from portfolio_manager import PortfolioManager
from position_manager import PositionManager
from risk_manager import RiskManager
from secrets_boundary import SigningBoundary


class Engine:
    """Holds the fully-wired component graph for one deployment.

    Constructed only by composition_root.wiring.build_engine -- never
    construct this directly, since build_engine is what enforces the
    wiring invariants (shared EventStore, network-consistent adapter
    selection, etc.) that make the components below safe to use together.
    """

    def __init__(
        self,
        *,
        event_store: EventStore,
        signing_boundary: SigningBoundary,
        execution_state_machine: ExecutionStateMachine,
        adapter: ExchangeAdapter,
        order_manager: OrderManager,
        position_manager: PositionManager,
        portfolio_manager: PortfolioManager,
        risk_manager: RiskManager,
        wallet_signer: Optional[object] = None,
    ):
        self._event_store = event_store
        self._signing_boundary = signing_boundary
        self._execution_state_machine = execution_state_machine
        self._adapter = adapter
        self._order_manager = order_manager
        self._position_manager = position_manager
        self._portfolio_manager = portfolio_manager
        self._risk_manager = risk_manager
        self._wallet_signer = wallet_signer
        self._started = False

    # -- component access (read-only; callers drive these themselves) --

    @property
    def event_store(self) -> EventStore:
        return self._event_store

    @property
    def signing_boundary(self) -> SigningBoundary:
        return self._signing_boundary

    @property
    def execution_state_machine(self) -> ExecutionStateMachine:
        return self._execution_state_machine

    @property
    def adapter(self) -> ExchangeAdapter:
        return self._adapter

    @property
    def order_manager(self) -> OrderManager:
        return self._order_manager

    @property
    def position_manager(self) -> PositionManager:
        return self._position_manager

    @property
    def portfolio_manager(self) -> PortfolioManager:
        return self._portfolio_manager

    @property
    def risk_manager(self) -> RiskManager:
        return self._risk_manager

    @property
    def wallet_signer(self) -> Optional[object]:
        return self._wallet_signer

    @property
    def is_started(self) -> bool:
        return self._started

    # -- lifecycle: a one-time startup handshake and shutdown, never a
    #    loop, poll, schedule, or retry --

    def start(self) -> HealthStatus:
        """One-time startup handshake: calls the adapter's connect(),
        which exercises the SigningBoundary authorization gate and (for a
        live adapter) a lightweight connectivity probe. Returns the
        resulting HealthStatus. Does not poll, schedule, or loop -- call
        once at process start."""
        health = self._adapter.connect()
        self._started = True
        return health

    def stop(self) -> None:
        """Disconnects the adapter and releases the EventStore's file
        lock. Safe to call even if start() was never called."""
        self._adapter.disconnect()
        self._event_store.close()
        self._started = False

    def __repr__(self) -> str:
        return f"Engine(adapter={self._adapter!r}, started={self._started})"

    __str__ = __repr__
