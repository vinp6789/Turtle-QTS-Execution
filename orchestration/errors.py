"""Closed error hierarchy for the orchestration layer.

An orchestration failure means a coordination step could not complete --
never a venue error (exchange_adapter.errors), never a lifecycle-state
violation (order_manager/position_manager/execution_state_machine's own
hierarchies). Those propagate unchanged; orchestration adds its own
exception only where IT is the one making a decision (e.g. an unrecognized
event type it does not know how to route).
"""


class OrchestrationError(Exception):
    """Base for every orchestration-layer failure."""


class UnknownVenueEventError(OrchestrationError):
    """dispatch() was given an event type this layer has no route for."""
