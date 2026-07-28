"""ExperimentRegistry: the Experiment Registry's write path (Milestone
0.2) and query path (Milestone 0.3) (Architecture v0.2 SS1).

Records every hypothesis's identity, lineage, and specification,
append-only and durable via an injected RegistryStorage (storage.py).
This class depends only on that two-method abstraction -- append() and
read_all() -- and has zero knowledge of how or where entries are
physically kept, so a future storage backend never requires a change
here. Per project direction, the storage interface stays stable: every
query added in Milestone 0.3 operates purely in-memory over
self._records (already fully reconstructed by replay at construction
time) -- none of them needed, or were given, a new RegistryStorage
method.

Scope boundaries, deliberate:
  - A specification is stored and fingerprinted as an opaque,
    JSON-serializable mapping. This module does not interpret its
    internal shape (universe, feature versions, acceptance criteria,
    candidate type, etc.) -- that schema belongs to alpha_engine.
    candidates (Milestone 3.1), not to the registry. Consequently,
    find_by_specification_field() is schema-agnostic: it matches a
    caller-supplied key/value pair without the registry ever assuming
    what keys exist. This is how "queryable by data source, by feature"
    (Architecture v0.2 SS1) is honestly fulfilled today -- the registry
    provides the primitive; alpha_engine.candidates (M3.1) will define
    the actual field names (e.g. "data_source_version",
    "feature_version") callers use with it. No registry change will be
    needed when that lands.
  - "Queryable ... by decision" (governance approve/reject/defer) is
    similarly partial today: only seal state (sealed/unsealed) exists as
    a tracked state at this milestone. Full governance decision state
    arrives with alpha_engine.governance (M5.x) and alpha_engine.
    lifecycle (M6.x); list_experiments(sealed=...) is the seal-state
    slice of that requirement available now.
"""

import hashlib
import json
import threading
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Tuple

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
)
from .lifecycle import (
    GOVERNANCE_DECISION_STATES,
    INITIAL_STATE,
    LifecycleState,
    is_legal_transition,
)
from .models import ExperimentRecord
from .storage import RegistryStorage

_ENTRY_CREATED = "experiment_created"
_ENTRY_SEALED = "experiment_sealed"
_ENTRY_EVIDENCE = "evidence_attached"
_ENTRY_STATE = "state_changed"
_ENTRY_DECISION = "governance_decision"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fingerprint(specification: Mapping[str, Any]) -> str:
    """Content-derived: two experiments with an identical specification
    resolve to the same fingerprint (Architecture v0.2 SS1), regardless
    of experiment_id. No `default=` fallback -- specification is already
    guaranteed JSON-native by _validate_specification, and using the same
    serialization here as storage.append() keeps the fingerprint and the
    durable record byte-consistent."""
    canonical = json.dumps(specification, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _deep_copy_json(value: Mapping[str, Any]) -> Dict[str, Any]:
    """B6: a shallow dict(value) only copies the OUTER mapping -- any
    nested list/dict inside it is still the SAME object the caller (or a
    previously returned snapshot) holds a reference to. A caller mutating
    a nested value after passing it in (or after reading it back from
    get_evidence()/a snapshot) would silently corrupt this registry's
    durable in-memory state, undetected, since nothing re-validates it
    until the next replay. A JSON round-trip is a genuine deep copy and is
    always safe here: every value stored via this module has already been
    proven JSON-native (json.dumps succeeded) before this function is
    called."""
    return json.loads(json.dumps(value))


def _validate_specification(specification: Any) -> Dict[str, Any]:
    if not isinstance(specification, Mapping):
        raise InvalidSpecificationError(
            f"specification must be a Mapping, got {type(specification).__name__}"
        )
    try:
        json.dumps(specification)
    except TypeError as exc:
        raise InvalidSpecificationError(
            "specification must be JSON-serializable using only JSON-native types "
            f"(str, int, float, bool, None, list, dict) -- stringify anything else "
            f"before storing: {exc}"
        ) from exc
    return _deep_copy_json(specification)


class ExperimentRegistry:
    """One instance per Alpha Engine deployment. Rebuilds its in-memory
    index from storage.read_all() on construction (replay), so a fresh
    process sees every experiment ever recorded -- the same durability
    posture the frozen Execution Engine's own managers hold (e.g.
    portfolio_manager.PortfolioManager replaying from its EventStore)."""

    def __init__(self, storage: RegistryStorage):
        if not isinstance(storage, RegistryStorage):
            raise TypeError(f"storage must be a RegistryStorage, got {type(storage).__name__}")
        self._storage = storage
        self._lock = threading.Lock()
        self._records: Dict[str, Dict[str, Any]] = {}
        self._replay()

    # -- replay --

    def _replay(self) -> None:
        for entry in self._storage.read_all():
            try:
                self._apply_entry(entry)
            except KeyError as exc:
                raise MalformedRegistryLogError(
                    f"registry log entry missing required field {exc}: {entry!r}"
                ) from exc

    def _apply_entry(self, entry: Mapping[str, Any]) -> None:
        entry_type = entry.get("type")
        if entry_type == _ENTRY_CREATED:
            experiment_id = entry["experiment_id"]
            if experiment_id in self._records:
                raise MalformedRegistryLogError(
                    f"duplicate {_ENTRY_CREATED!r} entry for experiment_id {experiment_id!r}"
                )
            parent_id = entry.get("parent_id")
            if parent_id is not None and parent_id not in self._records:
                raise MalformedRegistryLogError(
                    f"experiment {experiment_id!r} created with unknown parent_id {parent_id!r}"
                )
            self._records[experiment_id] = {
                "experiment_id": experiment_id,
                "fingerprint": entry["fingerprint"],
                "parent_id": parent_id,
                "specification": _deep_copy_json(entry["specification"]),
                "created_at_utc": entry["created_at_utc"],
                "sealed": False,
                "sealed_at_utc": None,
                "evidence": None,
                "evidence_fingerprint": None,
                "lifecycle_state": INITIAL_STATE,
                "governance_decision": None,
            }
        elif entry_type == _ENTRY_SEALED:
            experiment_id = entry["experiment_id"]
            record = self._records.get(experiment_id)
            if record is None:
                raise MalformedRegistryLogError(
                    f"{_ENTRY_SEALED!r} entry for unknown experiment_id {experiment_id!r}"
                )
            if record["sealed"]:
                raise MalformedRegistryLogError(
                    f"duplicate {_ENTRY_SEALED!r} entry for experiment_id {experiment_id!r}"
                )
            record["sealed"] = True
            record["sealed_at_utc"] = entry["sealed_at_utc"]
        elif entry_type == _ENTRY_EVIDENCE:
            experiment_id = entry["experiment_id"]
            record = self._records.get(experiment_id)
            if record is None:
                raise MalformedRegistryLogError(
                    f"{_ENTRY_EVIDENCE!r} entry for unknown experiment_id {experiment_id!r}"
                )
            if not record["sealed"]:
                raise MalformedRegistryLogError(
                    f"{_ENTRY_EVIDENCE!r} entry for unsealed experiment_id {experiment_id!r}"
                )
            if record["evidence"] is not None:
                raise MalformedRegistryLogError(
                    f"duplicate {_ENTRY_EVIDENCE!r} entry for experiment_id {experiment_id!r}"
                )
            record["evidence"] = _deep_copy_json(entry["evidence"])
            record["evidence_fingerprint"] = entry["evidence_fingerprint"]
        elif entry_type == _ENTRY_STATE:
            experiment_id = entry["experiment_id"]
            record = self._records.get(experiment_id)
            if record is None:
                raise MalformedRegistryLogError(
                    f"{_ENTRY_STATE!r} entry for unknown experiment_id {experiment_id!r}"
                )
            try:
                from_state = LifecycleState(entry["from_state"])
                to_state = LifecycleState(entry["to_state"])
            except ValueError as exc:
                raise MalformedRegistryLogError(
                    f"{_ENTRY_STATE!r} entry with unrecognized state: {entry!r}"
                ) from exc
            if record["lifecycle_state"] is not from_state:
                raise MalformedRegistryLogError(
                    f"{_ENTRY_STATE!r} entry for {experiment_id!r} declares from_state "
                    f"{from_state.value!r} but the replayed state is "
                    f"{record['lifecycle_state'].value!r}"
                )
            if not is_legal_transition(from_state, to_state):
                raise MalformedRegistryLogError(
                    f"{_ENTRY_STATE!r} entry for {experiment_id!r} records an illegal "
                    f"transition {from_state.value!r} -> {to_state.value!r}"
                )
            if to_state in GOVERNANCE_DECISION_STATES and record["governance_decision"] is None:
                raise MalformedRegistryLogError(
                    f"{_ENTRY_STATE!r} entry for {experiment_id!r} enters governance-gated state "
                    f"{to_state.value!r} without a recorded governance decision"
                )
            record["lifecycle_state"] = to_state
        elif entry_type == _ENTRY_DECISION:
            experiment_id = entry["experiment_id"]
            record = self._records.get(experiment_id)
            if record is None:
                raise MalformedRegistryLogError(
                    f"{_ENTRY_DECISION!r} entry for unknown experiment_id {experiment_id!r}"
                )
            if record["lifecycle_state"] is not LifecycleState.IN_REVIEW:
                raise MalformedRegistryLogError(
                    f"{_ENTRY_DECISION!r} entry for {experiment_id!r} while in state "
                    f"{record['lifecycle_state'].value!r} -- decisions are only valid in "
                    f"{LifecycleState.IN_REVIEW.value!r}"
                )
            if record["governance_decision"] is not None:
                raise MalformedRegistryLogError(
                    f"duplicate {_ENTRY_DECISION!r} entry for experiment_id {experiment_id!r}"
                )
            record["governance_decision"] = _deep_copy_json(entry["decision"])
        else:
            raise MalformedRegistryLogError(
                f"unrecognized registry log entry type {entry_type!r}: {entry!r}"
            )

    # -- write path --

    def create(
        self,
        experiment_id: str,
        specification: Mapping[str, Any],
        parent_id: Optional[str] = None,
    ) -> ExperimentRecord:
        """Registers a new experiment, unsealed. Raises
        DuplicateExperimentError if experiment_id is already registered,
        ExperimentNotFoundError if parent_id is given but not registered,
        InvalidSpecificationError if specification is not a
        JSON-serializable Mapping."""
        if not isinstance(experiment_id, str) or not experiment_id.strip():
            raise ValueError("experiment_id must be a non-empty string")
        spec = _validate_specification(specification)
        if parent_id is not None and (not isinstance(parent_id, str) or not parent_id.strip()):
            raise ValueError("parent_id must be a non-empty string or None")

        with self._lock:
            if experiment_id in self._records:
                raise DuplicateExperimentError(f"experiment_id {experiment_id!r} already exists")
            if parent_id is not None and parent_id not in self._records:
                raise ExperimentNotFoundError(f"parent_id {parent_id!r} is not a registered experiment")

            fingerprint = _fingerprint(spec)
            created_at_utc = _now()
            self._storage.append({
                "type": _ENTRY_CREATED,
                "experiment_id": experiment_id,
                "fingerprint": fingerprint,
                "parent_id": parent_id,
                "specification": spec,
                "created_at_utc": created_at_utc,
            })
            self._records[experiment_id] = {
                "experiment_id": experiment_id,
                "fingerprint": fingerprint,
                "parent_id": parent_id,
                "specification": spec,
                "created_at_utc": created_at_utc,
                "sealed": False,
                "sealed_at_utc": None,
                "evidence": None,
                "evidence_fingerprint": None,
                "lifecycle_state": INITIAL_STATE,
                "governance_decision": None,
            }
            return self._snapshot(experiment_id)

    def seal(self, experiment_id: str) -> ExperimentRecord:
        """Seals an experiment's specification as immutable (Architecture
        v0.2 SS2.1: 'Immutable once sealed'). Raises
        ExperimentNotFoundError if unknown, AlreadySealedError if already
        sealed -- sealing is a one-time transition; a correction is a
        new, linked experiment (parent_id), never a re-seal."""
        if not isinstance(experiment_id, str) or not experiment_id.strip():
            raise ValueError("experiment_id must be a non-empty string")
        with self._lock:
            record = self._records.get(experiment_id)
            if record is None:
                raise ExperimentNotFoundError(f"experiment_id {experiment_id!r} is not registered")
            if record["sealed"]:
                raise AlreadySealedError(f"experiment_id {experiment_id!r} is already sealed")

            sealed_at_utc = _now()
            self._storage.append({
                "type": _ENTRY_SEALED,
                "experiment_id": experiment_id,
                "sealed_at_utc": sealed_at_utc,
            })
            record["sealed"] = True
            record["sealed_at_utc"] = sealed_at_utc
            return self._snapshot(experiment_id)

    def attach_evidence(
        self,
        experiment_id: str,
        evidence: Mapping[str, Any],
        evidence_fingerprint: str,
    ) -> ExperimentRecord:
        """Durably links one evidence bundle to one experiment (R1). The
        evidence is an OPAQUE, JSON-native mapping -- the registry does not
        interpret its internal shape (the same discipline as
        specifications); alpha_engine.validation.attach_evidence_package()
        is the typed entry point that additionally cross-checks the
        evidence's specification against this record's before calling
        here. Guards: the experiment must exist and be SEALED (an
        immutable, pre-registered spec -- evidence must never attach to a
        hypothesis that can still be rewritten), and must not already have
        evidence (one package per experiment, ever; a re-run is a new,
        parent-linked experiment)."""
        if not isinstance(experiment_id, str) or not experiment_id.strip():
            raise ValueError("experiment_id must be a non-empty string")
        if not isinstance(evidence_fingerprint, str) or not evidence_fingerprint.strip():
            raise ValueError("evidence_fingerprint must be a non-empty string")
        if not isinstance(evidence, Mapping) or len(evidence) == 0:
            raise InvalidSpecificationError("evidence must be a non-empty Mapping")
        try:
            json.dumps(dict(evidence))
        except TypeError as exc:
            raise InvalidSpecificationError(
                f"evidence must be JSON-serializable using only JSON-native types: {exc}"
            ) from exc

        with self._lock:
            record = self._records.get(experiment_id)
            if record is None:
                raise ExperimentNotFoundError(f"experiment_id {experiment_id!r} is not registered")
            if not record["sealed"]:
                raise ExperimentNotSealedError(
                    f"experiment_id {experiment_id!r} is not sealed -- seal the specification "
                    "before attaching evidence"
                )
            if record["evidence"] is not None:
                raise EvidenceAlreadyAttachedError(
                    f"experiment_id {experiment_id!r} already has evidence "
                    f"(fingerprint {record['evidence_fingerprint']!r})"
                )
            evidence_dict = _deep_copy_json(evidence)
            self._storage.append({
                "type": _ENTRY_EVIDENCE,
                "experiment_id": experiment_id,
                "evidence": evidence_dict,
                "evidence_fingerprint": evidence_fingerprint,
            })
            record["evidence"] = _deep_copy_json(evidence_dict)
            record["evidence_fingerprint"] = evidence_fingerprint
            return self._snapshot(experiment_id)

    def transition(self, experiment_id: str, to_state: LifecycleState) -> ExperimentRecord:
        """Advances an experiment's lifecycle state (R2), durably. Guards,
        in order:
          - the experiment must exist and to_state must be a LifecycleState;
          - APPROVED/REJECTED/DEFERRED are refused outright
            (GovernanceRequiredError) -- only a recorded governance
            decision (R3) may enter them;
          - the edge must exist in lifecycle.ALLOWED_TRANSITIONS
            (IllegalLifecycleTransitionError);
          - entering EVIDENCE_SEALED requires evidence attached
            (LifecycleGuardError) -- an experiment with no evidence has
            nothing to seal."""
        if not isinstance(to_state, LifecycleState):
            raise ValueError(f"to_state must be a LifecycleState, got {type(to_state).__name__}")
        with self._lock:
            record = self._records.get(experiment_id)
            if record is None:
                raise ExperimentNotFoundError(f"experiment_id {experiment_id!r} is not registered")
            if to_state in GOVERNANCE_DECISION_STATES:
                raise GovernanceRequiredError(
                    f"state {to_state.value!r} is reachable only via a recorded governance "
                    "decision -- use alpha_engine.governance, never transition() directly"
                )
            return self._transition_locked(record, to_state)

    def _transition_locked(self, record: Dict[str, Any], to_state: LifecycleState) -> ExperimentRecord:
        """Table/guard checks + durable append. Assumes self._lock held
        and governance gating already handled by the caller."""
        from_state: LifecycleState = record["lifecycle_state"]
        if not is_legal_transition(from_state, to_state):
            raise IllegalLifecycleTransitionError(
                f"illegal lifecycle transition {from_state.value!r} -> {to_state.value!r} "
                f"for experiment {record['experiment_id']!r}"
            )
        if to_state is LifecycleState.EVIDENCE_SEALED and record["evidence"] is None:
            raise LifecycleGuardError(
                f"experiment {record['experiment_id']!r} cannot enter "
                f"{LifecycleState.EVIDENCE_SEALED.value!r}: no evidence attached"
            )
        self._storage.append({
            "type": _ENTRY_STATE,
            "experiment_id": record["experiment_id"],
            "from_state": from_state.value,
            "to_state": to_state.value,
            "changed_at_utc": _now(),
        })
        record["lifecycle_state"] = to_state
        return self._snapshot(record["experiment_id"])

    def apply_governance_decision(
        self,
        experiment_id: str,
        decision: Mapping[str, Any],
        to_state: LifecycleState,
    ) -> ExperimentRecord:
        """The ONLY path into APPROVED/REJECTED/DEFERRED (R3): durably
        records a governance decision (opaque JSON-native mapping -- the
        typed shape lives in alpha_engine.governance, which is the
        intended caller) and applies the resulting lifecycle transition.
        Guards: experiment must exist and be IN_REVIEW, must have no prior
        decision (one decision per experiment, ever -- a deferral or
        re-review is a NEW experiment), and to_state must be one of the
        three governance-gated states."""
        if not isinstance(to_state, LifecycleState) or to_state not in GOVERNANCE_DECISION_STATES:
            raise ValueError(
                f"to_state must be one of {sorted(s.value for s in GOVERNANCE_DECISION_STATES)}, "
                f"got {to_state!r}"
            )
        if not isinstance(decision, Mapping) or len(decision) == 0:
            raise InvalidSpecificationError("decision must be a non-empty Mapping")
        try:
            json.dumps(dict(decision))
        except TypeError as exc:
            raise InvalidSpecificationError(
                f"decision must be JSON-serializable using only JSON-native types: {exc}"
            ) from exc

        with self._lock:
            record = self._records.get(experiment_id)
            if record is None:
                raise ExperimentNotFoundError(f"experiment_id {experiment_id!r} is not registered")
            if record["lifecycle_state"] is not LifecycleState.IN_REVIEW:
                raise LifecycleGuardError(
                    f"experiment {experiment_id!r} is in state "
                    f"{record['lifecycle_state'].value!r}; governance decisions are only valid "
                    f"in {LifecycleState.IN_REVIEW.value!r}"
                )
            if record["governance_decision"] is not None:
                raise LifecycleGuardError(
                    f"experiment {experiment_id!r} already has a governance decision -- "
                    "one decision per experiment, ever"
                )
            decision_dict = _deep_copy_json(decision)
            self._storage.append({
                "type": _ENTRY_DECISION,
                "experiment_id": experiment_id,
                "decision": decision_dict,
            })
            record["governance_decision"] = _deep_copy_json(decision_dict)
            return self._transition_locked(record, to_state)

    def get_governance_decision(self, experiment_id: str) -> Optional[Mapping[str, Any]]:
        """The recorded governance decision as a read-only mapping, or
        None if no decision has been recorded yet."""
        with self._lock:
            if experiment_id not in self._records:
                raise ExperimentNotFoundError(f"experiment_id {experiment_id!r} is not registered")
            decision = self._records[experiment_id]["governance_decision"]
            return MappingProxyType(_deep_copy_json(decision)) if decision is not None else None

    def get_evidence(self, experiment_id: str) -> Optional[Mapping[str, Any]]:
        """The attached evidence bundle as a read-only mapping, or None if
        no evidence has been attached yet. Raises ExperimentNotFoundError
        for an unknown experiment_id."""
        with self._lock:
            if experiment_id not in self._records:
                raise ExperimentNotFoundError(f"experiment_id {experiment_id!r} is not registered")
            evidence = self._records[experiment_id]["evidence"]
            return MappingProxyType(_deep_copy_json(evidence)) if evidence is not None else None

    # -- minimal read path (Milestone 0.2) --

    def exists(self, experiment_id: str) -> bool:
        with self._lock:
            return experiment_id in self._records

    def get(self, experiment_id: str) -> ExperimentRecord:
        """Raises ExperimentNotFoundError if experiment_id is not
        registered."""
        with self._lock:
            if experiment_id not in self._records:
                raise ExperimentNotFoundError(f"experiment_id {experiment_id!r} is not registered")
            return self._snapshot(experiment_id)

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)

    # -- query path (Milestone 0.3) --
    #
    # Every method below is read-only over self._records, already fully
    # populated by _replay() at construction time -- none of them touch
    # self._storage. Results are always ordered deterministically
    # (created_at_utc, then experiment_id as a tiebreak) so a query's
    # output is reproducible, matching this codebase's determinism ethos.

    def list_experiments(
        self,
        *,
        sealed: Optional[bool] = None,
        state: Optional[LifecycleState] = None,
    ) -> Tuple[ExperimentRecord, ...]:
        """All registered experiments, optionally filtered by seal state
        and/or lifecycle state (filters compose with AND). Defaults return
        everything."""
        if sealed is not None and not isinstance(sealed, bool):
            raise ValueError(f"sealed must be a bool or None, got {type(sealed).__name__}")
        if state is not None and not isinstance(state, LifecycleState):
            raise ValueError(f"state must be a LifecycleState or None, got {type(state).__name__}")
        with self._lock:
            ids = self._sorted_ids(
                eid for eid, rec in self._records.items()
                if (sealed is None or rec["sealed"] == sealed)
                and (state is None or rec["lifecycle_state"] is state)
            )
            return tuple(self._snapshot(eid) for eid in ids)

    def get_roots(self) -> Tuple[ExperimentRecord, ...]:
        """Every experiment with no parent (parent_id is None) -- the
        starting points of every lineage tree."""
        with self._lock:
            ids = self._sorted_ids(
                eid for eid, rec in self._records.items() if rec["parent_id"] is None
            )
            return tuple(self._snapshot(eid) for eid in ids)

    def get_children(self, experiment_id: str) -> Tuple[ExperimentRecord, ...]:
        """Direct children of experiment_id (one level down only -- see
        get_descendants() for the full subtree). Raises
        ExperimentNotFoundError if experiment_id is not registered; an
        empty tuple is a valid, non-error result for a leaf."""
        with self._lock:
            self._require_known(experiment_id)
            ids = self._sorted_ids(
                eid for eid, rec in self._records.items() if rec["parent_id"] == experiment_id
            )
            return tuple(self._snapshot(eid) for eid in ids)

    def get_ancestors(self, experiment_id: str) -> Tuple[ExperimentRecord, ...]:
        """The full ancestor chain of experiment_id, root-first (i.e.
        index 0 is the root, the last element is the immediate parent).
        Empty tuple if experiment_id is itself a root. Raises
        ExperimentNotFoundError if experiment_id is not registered, or
        MalformedRegistryLogError if the parent chain is broken or cyclic
        (a data-integrity issue -- structurally impossible to reach
        through create()'s own parent-must-already-exist validation, but
        guarded against defensively rather than looping forever)."""
        with self._lock:
            self._require_known(experiment_id)
            chain: List[str] = []
            visited = {experiment_id}
            current = self._records[experiment_id]["parent_id"]
            while current is not None:
                if current in visited:
                    raise MalformedRegistryLogError(
                        f"cycle detected in experiment lineage while walking ancestors of "
                        f"{experiment_id!r} (revisited {current!r})"
                    )
                if current not in self._records:
                    raise MalformedRegistryLogError(
                        f"experiment {experiment_id!r} has ancestor {current!r} which is not registered"
                    )
                visited.add(current)
                chain.append(current)
                current = self._records[current]["parent_id"]
            chain.reverse()
            return tuple(self._snapshot(eid) for eid in chain)

    def get_descendants(self, experiment_id: str) -> Tuple[ExperimentRecord, ...]:
        """The full descendant subtree of experiment_id (children,
        grandchildren, ...), breadth-first, each level ordered
        deterministically. Empty tuple for a leaf. Raises
        ExperimentNotFoundError if experiment_id is not registered, or
        MalformedRegistryLogError on a cyclic parent chain (see
        get_ancestors() -- same defensive guarantee)."""
        with self._lock:
            self._require_known(experiment_id)
            result: List[str] = []
            visited = {experiment_id}
            frontier = [experiment_id]
            while frontier:
                current = frontier.pop(0)
                children_ids = self._sorted_ids(
                    eid for eid, rec in self._records.items() if rec["parent_id"] == current
                )
                for child_id in children_ids:
                    if child_id in visited:
                        raise MalformedRegistryLogError(
                            f"cycle detected in experiment lineage while walking descendants of "
                            f"{experiment_id!r} (revisited {child_id!r})"
                        )
                    visited.add(child_id)
                    result.append(child_id)
                    frontier.append(child_id)
            return tuple(self._snapshot(eid) for eid in result)

    def find_by_fingerprint(self, fingerprint: str) -> Tuple[ExperimentRecord, ...]:
        """Every experiment whose specification content hash equals
        fingerprint -- i.e. every literal re-test of the same idea,
        regardless of experiment_id or parent_id. Empty tuple if none
        match (not an error: a fingerprint is a search key, not a
        reference to a specific required experiment)."""
        if not isinstance(fingerprint, str) or not fingerprint.strip():
            raise ValueError("fingerprint must be a non-empty string")
        with self._lock:
            ids = self._sorted_ids(
                eid for eid, rec in self._records.items() if rec["fingerprint"] == fingerprint
            )
            return tuple(self._snapshot(eid) for eid in ids)

    def find_by_specification_field(self, key: str, value: Any) -> Tuple[ExperimentRecord, ...]:
        """Every experiment whose specification[key] == value. Schema-
        agnostic (see module docstring): the registry does not know or
        care what keys a specification contains. Empty tuple if none
        match, or if no experiment's specification even has this key."""
        if not isinstance(key, str) or not key.strip():
            raise ValueError("key must be a non-empty string")
        with self._lock:
            ids = self._sorted_ids(
                eid for eid, rec in self._records.items()
                if key in rec["specification"] and rec["specification"][key] == value
            )
            return tuple(self._snapshot(eid) for eid in ids)

    # -- internal --

    def _require_known(self, experiment_id: str) -> None:
        """Assumes the caller already holds self._lock."""
        if experiment_id not in self._records:
            raise ExperimentNotFoundError(f"experiment_id {experiment_id!r} is not registered")

    def _sorted_ids(self, ids) -> List[str]:
        """Deterministic ordering shared by every query method: creation
        time, then experiment_id as a tiebreak for two experiments
        created in the same instant. Assumes the caller already holds
        self._lock."""
        return sorted(ids, key=lambda eid: (self._records[eid]["created_at_utc"], eid))

    def _snapshot(self, experiment_id: str) -> ExperimentRecord:
        """Assumes the caller already holds self._lock."""
        record = self._records[experiment_id]
        return ExperimentRecord(
            experiment_id=record["experiment_id"],
            fingerprint=record["fingerprint"],
            parent_id=record["parent_id"],
            specification=MappingProxyType(_deep_copy_json(record["specification"])),
            created_at_utc=record["created_at_utc"],
            sealed=record["sealed"],
            sealed_at_utc=record["sealed_at_utc"],
            evidence_fingerprint=record["evidence_fingerprint"],
            lifecycle_state=record["lifecycle_state"],
        )

    def __repr__(self) -> str:
        return f"ExperimentRegistry(experiments={len(self._records)})"

    __str__ = __repr__
