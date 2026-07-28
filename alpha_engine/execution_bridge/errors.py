"""Errors for the execution bridge."""


class ExecutionBridgeError(Exception):
    """Base for execution-bridge failures: invalid construction (wrong
    candidate family, missing/invalid risk-level parameters) or invalid
    arguments to the approved-specification loader. Runtime market-data
    problems never raise through the bridge -- they degrade to
    no-intent-for-that-symbol (fail-safe), consistent with every
    provider in this package."""
