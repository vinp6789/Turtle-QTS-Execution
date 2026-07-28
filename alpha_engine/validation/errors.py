"""Errors for the validation harness."""


class ValidationError(Exception):
    """Base for every validation-harness failure. Raised for structural
    caller errors (bad argument types, empty sample sets, a malformed
    acceptance-criteria value under a recognized key) -- never for an
    individual sample's signal being unavailable or flat, which is a
    normal, counted outcome (see models.ValidationResult)."""
