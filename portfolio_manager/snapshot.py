"""Immutable PortfolioSnapshot for the Portfolio Manager.

Assets, equity, and liabilities are DERIVED properties, computed from two
independently-accumulated ledgers -- never stored as separate fields that
could drift out of sync with each other:

  - The "physical" ledger: available_cash, reserved_margin, used_margin,
    unrealized_pnl.
  - The "roll-forward" ledger: cumulative deposits, withdrawals, realized
    PnL, funding, and fees.

Liabilities is always Decimal("0") in this model: the engine implements
no borrowing or leverage-as-debt, so there is no non-trivial liability to
represent. Assets == Equity is therefore the real, checkable invariant
(see manager.py's _assert_invariant), not a definitional tautology --
these two numbers are computed via completely different arithmetic paths
and must independently agree after every single mutation.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Tuple


@dataclass(frozen=True)
class PortfolioSnapshot:
    available_cash: Decimal
    reserved_margin: Decimal
    used_margin: Decimal
    unrealized_pnl: Decimal
    realized_pnl_cumulative: Decimal
    funding_cumulative: Decimal
    fees_cumulative: Decimal
    deposits_cumulative: Decimal
    withdrawals_cumulative: Decimal
    exposure: Decimal
    heat: Decimal
    open_position_ids: Tuple[str, ...]
    updated_at_utc: str

    @property
    def wallet_balance(self) -> Decimal:
        """Cash-basis balance: everything realized, excluding mark-to-market."""
        return (
            self.deposits_cumulative
            - self.withdrawals_cumulative
            + self.realized_pnl_cumulative
            + self.funding_cumulative
            - self.fees_cumulative
        )

    @property
    def equity(self) -> Decimal:
        return self.wallet_balance + self.unrealized_pnl

    @property
    def assets(self) -> Decimal:
        return self.available_cash + self.reserved_margin + self.used_margin + self.unrealized_pnl

    @property
    def liabilities(self) -> Decimal:
        return Decimal("0")

    @property
    def leverage(self) -> Decimal:
        if self.equity == 0:
            return Decimal("0")
        return self.exposure / self.equity

    @property
    def position_count(self) -> int:
        return len(self.open_position_ids)
