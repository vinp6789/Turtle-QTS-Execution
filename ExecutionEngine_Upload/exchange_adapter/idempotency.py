"""Generic idempotency cache for outbound exchange mutations.

Keyed by request_id/client_order_id. First writer wins: a second store()
for a key that already has a value returns the ORIGINAL value, never
overwrites it -- matching the idempotency semantics already established
in Module 3 (EventStore) and Module 4 (ExecutionStateMachine).
"""

import threading
from typing import Dict, Generic, Optional, TypeVar

T = TypeVar("T")


class IdempotencyCache(Generic[T]):
    def __init__(self):
        self._lock = threading.Lock()
        self._results: Dict[str, T] = {}

    def get(self, key: str) -> Optional[T]:
        with self._lock:
            return self._results.get(key)

    def store(self, key: str, value: T) -> T:
        with self._lock:
            if key not in self._results:
                self._results[key] = value
            return self._results[key]
