"""Orchestrator: the single ergonomic entry point over an already-built
Engine.

Holds no state of its own beyond the Engine reference and delegates every
method to this package's free functions (lifecycle.py, synchronization.py,
reconciliation.py, dispatch.py) -- those functions are the actual
implementation and are independently usable without this class. Orchestrator
exists only so a caller does not have to thread `engine` through every call.

Orchestrator never constructs an Engine itself: build one with
composition_root.build_engine() first. This is the enforced separation
between dependency injection (composition_root) and orchestration (this
package).
"""

from exchange_adapter import ReconciliationReport
from order_manager import OrderSnapshot

from composition_root import Engine

from .dispatch import dispatch
from .events import VenueEvent
from .lifecycle import StartupReport, shutdown, startup
from .reconciliation import reconcile
from .synchronization import synchronize


class Orchestrator:
    def __init__(self, engine: Engine):
        if not isinstance(engine, Engine):
            raise TypeError(f"engine must be a composition_root.Engine, got {type(engine).__name__}")
        self._engine = engine

    @property
    def engine(self) -> Engine:
        return self._engine

    def startup(self) -> StartupReport:
        return startup(self._engine)

    def shutdown(self) -> None:
        shutdown(self._engine)

    def synchronize(self) -> "tuple[OrderSnapshot, ...]":
        return synchronize(self._engine)

    def reconcile(self) -> ReconciliationReport:
        return reconcile(self._engine)

    def dispatch(self, event: VenueEvent) -> OrderSnapshot:
        return dispatch(self._engine, event)

    def __repr__(self) -> str:
        return f"Orchestrator(engine={self._engine!r})"

    __str__ = __repr__
