"""Experiment Registry (Architecture v0.2 SS1; Alpha Engine Milestone 0.2
write path + Milestone 0.3 query path).

Public API:
    ExperimentRegistry   -- create()/seal() a hypothesis record;
                            get()/exists() plus the query surface
                            (list_experiments, get_roots, get_children,
                            get_ancestors, get_descendants,
                            find_by_fingerprint,
                            find_by_specification_field) -- all queries
                            are read-only and operate purely in-memory,
                            with zero RegistryStorage changes
    ExperimentRecord     -- immutable snapshot of one experiment
    RegistryStorage      -- the storage abstraction ExperimentRegistry
                            depends on (append/read_all only). Swap
                            backends by implementing this -- zero change
                            to ExperimentRegistry or any higher Alpha
                            Engine layer.
    FileRegistryStorage  -- Milestone 0.2's one concrete backend: a
                            plain, fsync'd, append-only JSON-Lines log
    RegistryError and subclasses -- this sub-package's error hierarchy

Substrate decision log: see alpha_engine/DECISIONS.md (D1). Treat the
choice of FileRegistryStorage as an implementation detail, not a closed
architectural decision -- that is precisely what RegistryStorage exists
to make swappable.
"""

from .errors import (
    AlreadySealedError,
    DuplicateExperimentError,
    EvidenceAlreadyAttachedError,
    ExperimentNotFoundError,
    ExperimentNotSealedError,
    GovernanceRequiredError,
    IllegalLifecycleTransitionError,
    InvalidSpecificationError,
    LifecycleGuardError,
    MalformedRegistryLogError,
    RegistryError,
    RegistryLockError,
)
from .lifecycle import (
    ALLOWED_TRANSITIONS,
    GOVERNANCE_DECISION_STATES,
    INITIAL_STATE,
    LIVE_STATES,
    TERMINAL_STATES,
    LifecycleState,
    is_legal_transition,
)
from .models import ExperimentRecord
from .registry import ExperimentRegistry
from .storage import FileRegistryStorage, RegistryStorage

__all__ = [
    "ExperimentRegistry",
    "ExperimentRecord",
    "RegistryStorage",
    "FileRegistryStorage",
    "LifecycleState",
    "ALLOWED_TRANSITIONS",
    "GOVERNANCE_DECISION_STATES",
    "LIVE_STATES",
    "TERMINAL_STATES",
    "INITIAL_STATE",
    "is_legal_transition",
    "RegistryError",
    "DuplicateExperimentError",
    "ExperimentNotFoundError",
    "AlreadySealedError",
    "ExperimentNotSealedError",
    "EvidenceAlreadyAttachedError",
    "IllegalLifecycleTransitionError",
    "LifecycleGuardError",
    "GovernanceRequiredError",
    "InvalidSpecificationError",
    "MalformedRegistryLogError",
    "RegistryLockError",
]
