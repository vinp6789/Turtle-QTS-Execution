"""Closed error hierarchy for the composition root.

A composition-root failure is a configuration or wiring problem discovered
at construction time -- never a venue or business-logic error (those
remain the wired modules' own hierarchies, e.g. exchange_adapter.errors,
risk_manager.errors). Raised only by composition_root.wiring.build_engine,
before any component is constructed.
"""


class CompositionRootError(Exception):
    """Base for every composition-root wiring failure."""


class CompositionRootTypeError(CompositionRootError, TypeError):
    """build_engine's own argument was the wrong type (e.g. config is not
    an EngineConfig). Distinct from the configuration-VALUE errors below;
    inherits both CompositionRootError (so callers can catch this whole
    hierarchy in one except) and TypeError (the conventional Python
    signal for a wrong-type argument)."""


class UnsupportedExchangeError(CompositionRootError):
    """config.exchange.name has no concrete adapter wired by this
    composition root (currently: 'hyperliquid' only)."""


class UnsupportedEnvironmentError(CompositionRootError):
    """config.environment is not one of the values this composition root
    knows how to wire ('paper' -> MockExchangeAdapter, 'live' ->
    HyperliquidAdapter)."""


class MissingDeploymentSettingError(CompositionRootError):
    """A deployment-specific value required for the selected environment
    (e.g. account_address for environment='live') was not supplied."""
