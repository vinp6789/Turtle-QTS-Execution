"""Exceptions raised by the Portfolio Manager."""


class PortfolioManagerError(Exception):
    """Base exception for all Portfolio Manager failures."""


class InsufficientFundsError(PortfolioManagerError):
    """Raised when a withdrawal or margin reservation would exceed
    available cash. Never automatically overridden -- capital protection
    takes priority over convenience."""


class InsufficientMarginError(PortfolioManagerError):
    """Raised when an allocation would exceed the margin actually
    reserved for a position."""


class AccountingInvariantError(PortfolioManagerError):
    """Raised if Assets != Equity after any mutation. This should be
    structurally impossible given the module's arithmetic (see
    manager.py's _apply_event); if it is ever raised, it indicates a
    genuine bug or data corruption, never raised during ordinary
    operation."""


class ReplayIntegrityError(PortfolioManagerError):
    """Raised during recovery if persisted event history contains an
    unrecognized action. Indicates corruption or tampering, never raised
    during ordinary operation."""
