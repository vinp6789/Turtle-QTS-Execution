"""Errors for the Experiment Registry."""


class RegistryError(Exception):
    """Base for every Experiment Registry failure."""


class DuplicateExperimentError(RegistryError):
    """Raised by ExperimentRegistry.create() when experiment_id is already
    registered."""


class ExperimentNotFoundError(RegistryError):
    """Raised when an operation references an experiment_id that is not
    registered -- including a parent_id given at creation time that does
    not already exist."""


class AlreadySealedError(RegistryError):
    """Raised by ExperimentRegistry.seal() when the experiment is already
    sealed. Sealing is a one-time transition (Architecture v0.2 SS2.1,
    'Immutable once sealed'); a correction is a new experiment linked via
    parent_id, never a re-seal of an existing one."""


class InvalidSpecificationError(RegistryError):
    """Raised when a specification passed to create() is not a Mapping,
    or is not JSON-serializable using only JSON-native types (str, int,
    float, bool, None, list, dict). Non-native types (Decimal, datetime,
    custom objects) must be explicitly stringified by the caller before
    storing -- silently coercing them here would risk exactly the kind of
    byte-identical-reproducibility loss Architecture v0.2 SS4.3
    prohibits."""


class ExperimentNotSealedError(RegistryError):
    """Raised by ExperimentRegistry.attach_evidence() when the experiment's
    specification has not been sealed yet. Evidence may only attach to an
    immutable, pre-registered specification (Architecture v0.2 SS6.1) --
    attaching evidence to a still-mutable spec would let the hypothesis be
    quietly rewritten after its results were known."""


class EvidenceAlreadyAttachedError(RegistryError):
    """Raised by ExperimentRegistry.attach_evidence() when the experiment
    already has evidence. One evidence package per experiment, ever
    (Architecture v0.2 SS2.1: immutable once sealed) -- a re-run is a new
    experiment linked via parent_id, never a replacement of prior
    evidence."""


class IllegalLifecycleTransitionError(RegistryError):
    """Raised by ExperimentRegistry.transition() when the requested state
    change is not an edge in lifecycle.ALLOWED_TRANSITIONS."""


class LifecycleGuardError(RegistryError):
    """Raised when a transition is table-legal but a precondition guard
    fails (e.g. EVIDENCE_SEALED requires evidence attached)."""


class GovernanceRequiredError(RegistryError):
    """Raised when a caller attempts to enter APPROVED/REJECTED/DEFERRED
    through transition() directly -- those states are reachable only via
    a recorded governance decision (apply_governance_decision, R3)."""


class MalformedRegistryLogError(RegistryError):
    """Raised when the registry's durable log contains an entry that
    cannot be explained by normal operation: unparseable JSON, a missing
    required field, an unrecognized entry type, a duplicate 'created'
    entry for one experiment_id, a 'sealed' entry for an unknown or
    already-sealed experiment_id, or (B3) a per-entry checksum mismatch
    on a fully-formed (non-tail) line -- bit-level corruption a clean
    crash-during-append cannot explain. Distinct from the live API's
    DuplicateExperimentError/AlreadySealedError, which guard ordinary
    call-time misuse -- this indicates the durable log itself is
    inconsistent, a data-integrity issue rather than a caller error."""


class RegistryLockError(RegistryError):
    """Raised (B3) when the registry log file is already exclusively
    locked by another writer (another process, or another
    FileRegistryStorage instance in this one). Mirrors event_store's
    EventStoreLockError -- single-writer enforcement, not a data
    condition."""
