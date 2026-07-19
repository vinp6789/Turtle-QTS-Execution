"""Background cycle worker: repeatedly calls AppState.run_one_cycle() on a
fixed interval.

This is the ONLY loop in the whole system. It is deliberately in the app
layer, never in trading_system: scheduling.run_cycle remains a single
deterministic cycle (Milestone 8's contract), and this worker is just one
caller of it that happens to call it on a timer. Uses a threading.Event
for an interruptible sleep so shutdown is immediate, not "up to one
interval late".

Resilient by design: a cycle that raises (e.g. a transient venue error)
is logged to AppState.last_error and the worker keeps running -- one bad
cycle must not kill the process. Mutations remain UNSAFE_NEVER_AUTO_RETRY
inside the engine, so the worker never re-submits anything; it simply
waits for the next scheduled cycle.
"""

import threading
from typing import Callable, Optional

from .state import AppState


class CycleWorker:
    def __init__(self, state: AppState, on_cycle: Optional[Callable[[object], None]] = None,
                 on_error: Optional[Callable[[BaseException], None]] = None):
        self._state = state
        self._interval = max(1, int(state.settings.cycle_interval_seconds))
        self._on_cycle = on_cycle
        self._on_error = on_error
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="cycle-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        self._thread = None

    def run_once(self):
        """Run a single cycle synchronously (used by the manual-trigger
        endpoint). Errors propagate to the caller."""
        return self._state.run_one_cycle()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                result = self._state.run_one_cycle()
                if self._on_cycle is not None:
                    self._on_cycle(result)
            except BaseException as exc:  # noqa: BLE001 -- resilience: never let the loop die
                if self._on_error is not None:
                    try:
                        self._on_error(exc)
                    except Exception:  # noqa: BLE001
                        pass
            # Interruptible wait: returns immediately when stop() is called.
            self._stop.wait(self._interval)
