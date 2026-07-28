"""Errors for lifecycle policies."""


class DegradationError(Exception):
    """Raised for degradation-policy caller errors (assessing a non-live
    experiment, a result/record mismatch, or acting on a non-degraded
    assessment). State-machine violations raise the registry's own
    errors unchanged."""
