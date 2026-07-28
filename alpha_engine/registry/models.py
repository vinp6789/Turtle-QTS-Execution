"""ExperimentRecord: the immutable snapshot type ExperimentRegistry
returns to callers.

Mirrors the frozen Execution Engine's own snapshot pattern (e.g.
portfolio_manager.PortfolioSnapshot): the registry keeps mutable internal
state privately (registry.py) and returns a frozen, point-in-time
snapshot from it. A snapshot is read-only; every mutation goes through
ExperimentRegistry's own methods, never through this type.
"""

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .errors import RegistryError
from .lifecycle import INITIAL_STATE, LifecycleState


@dataclass(frozen=True)
class ExperimentRecord:
    """One hypothesis's identity, lineage, specification, and seal state
    at the moment this snapshot was taken.

    specification is stored opaquely -- this type (and the registry as a
    whole) does not interpret its internal shape. The schema for what a
    specification actually contains (universe, feature versions,
    acceptance criteria, candidate type, etc.) belongs to
    alpha_engine.candidates (Milestone 3.1), not to the registry.
    """

    experiment_id: str
    fingerprint: str
    parent_id: Optional[str]
    specification: Mapping[str, Any]
    created_at_utc: str
    sealed: bool
    sealed_at_utc: Optional[str]
    # R1 (additive): content fingerprint of the attached EvidencePackage,
    # None until evidence is attached. The full evidence dict is NOT
    # carried on every snapshot (it can be large) -- retrieve it via
    # ExperimentRegistry.get_evidence().
    evidence_fingerprint: Optional[str] = None
    # R2 (additive): current lifecycle state (registry/lifecycle.py).
    lifecycle_state: LifecycleState = INITIAL_STATE

    def __post_init__(self):
        if not isinstance(self.experiment_id, str) or not self.experiment_id.strip():
            raise RegistryError("ExperimentRecord.experiment_id must be a non-empty string")
        if not isinstance(self.fingerprint, str) or not self.fingerprint.strip():
            raise RegistryError("ExperimentRecord.fingerprint must be a non-empty string")
        if self.parent_id is not None and (not isinstance(self.parent_id, str) or not self.parent_id.strip()):
            raise RegistryError("ExperimentRecord.parent_id must be a non-empty string or None")
        if not isinstance(self.specification, Mapping):
            raise RegistryError("ExperimentRecord.specification must be a Mapping")
        if not isinstance(self.created_at_utc, str) or not self.created_at_utc.strip():
            raise RegistryError("ExperimentRecord.created_at_utc must be a non-empty string")
        if not isinstance(self.sealed, bool):
            raise RegistryError("ExperimentRecord.sealed must be a bool")
        if self.sealed_at_utc is not None and not isinstance(self.sealed_at_utc, str):
            raise RegistryError("ExperimentRecord.sealed_at_utc must be a string or None")
        if self.sealed and self.sealed_at_utc is None:
            raise RegistryError("ExperimentRecord.sealed_at_utc must be set when sealed is True")
        if not self.sealed and self.sealed_at_utc is not None:
            raise RegistryError("ExperimentRecord.sealed_at_utc must be None when sealed is False")
        if self.evidence_fingerprint is not None and (
            not isinstance(self.evidence_fingerprint, str) or not self.evidence_fingerprint.strip()
        ):
            raise RegistryError("ExperimentRecord.evidence_fingerprint must be a non-empty string or None")
        if not isinstance(self.lifecycle_state, LifecycleState):
            raise RegistryError("ExperimentRecord.lifecycle_state must be a LifecycleState")

    @property
    def has_evidence(self) -> bool:
        return self.evidence_fingerprint is not None
