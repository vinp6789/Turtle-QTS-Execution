"""Typed bridge between an EvidencePackage and the Experiment Registry
(Alpha Engine R1).

The registry stores evidence OPAQUELY (attach_evidence takes a plain
JSON-native mapping -- registry/registry.py); this module is the typed
entry point that a research workflow actually calls. Its added value is
the INTEGRITY CROSS-CHECK the registry itself deliberately cannot
perform: the evidence package's embedded candidate_specification must be
byte-identical to the specification the experiment was registered (and
sealed) under. Without this check, evidence produced for one parameter
set could be silently attached to an experiment registered under
another -- exactly the researcher-degrees-of-freedom loophole
pre-registration exists to close.

Dependency direction: validation -> registry (downward to the base
layer; the registry imports nothing from validation, so no cycle).
"""

from ..registry import ExperimentRegistry
from .errors import ValidationError
from .evidence import EvidencePackage


def attach_evidence_package(
    registry: ExperimentRegistry,
    experiment_id: str,
    package: EvidencePackage,
):
    """Cross-checks and durably attaches `package` to `experiment_id`.

    Raises ValidationError if the package's candidate_specification does
    not exactly equal the experiment's registered specification (the
    integrity check described above); propagates the registry's own
    errors (unknown experiment, unsealed, already-attached) unchanged.
    Returns the updated ExperimentRecord."""
    if not isinstance(registry, ExperimentRegistry):
        raise ValidationError(f"registry must be an ExperimentRegistry, got {type(registry).__name__}")
    if not isinstance(package, EvidencePackage):
        raise ValidationError(f"package must be an EvidencePackage, got {type(package).__name__}")

    record = registry.get(experiment_id)
    if dict(record.specification) != dict(package.candidate_specification):
        raise ValidationError(
            f"evidence package specification does not match experiment {experiment_id!r}'s "
            "registered specification -- refusing to attach evidence produced for a different "
            "hypothesis (pre-registration integrity)"
        )
    return registry.attach_evidence(experiment_id, package.to_dict(), package.fingerprint)
