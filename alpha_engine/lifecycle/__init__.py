"""Lifecycle policies (Architecture v0.2 SS3.3-3.4; Alpha Engine R7).

The lifecycle STATE MACHINE itself lives in alpha_engine.registry
(registry/lifecycle.py -- the registry is the experiment's durable
outcome timeline); this package hosts the POLICIES that decide when to
request a transition.

Public API:
    assess_degradation    -- pure judgment: does a recent
                             ValidationResult clear the experiment's own
                             pre-registered acceptance criteria?
    DegradationAssessment -- one assessment's outcome
    freeze_degraded       -- applies a degraded assessment (-> FROZEN,
                             through the registry's guarded transition)
    DegradationError      -- this sub-package's error base

Deliberately NOT built: automated retirement (RETIRING/RETIRED remain
deliberate operator/governance acts via registry.transition()),
shakedown ramp criteria (needs live capital history that does not exist
yet), and statistical drift detection beyond the pre-registered bar
(needs accumulated live evidence to compare against).
"""

from .degradation import DegradationAssessment, assess_degradation, freeze_degraded
from .errors import DegradationError

__all__ = [
    "assess_degradation",
    "DegradationAssessment",
    "freeze_degraded",
    "DegradationError",
]
