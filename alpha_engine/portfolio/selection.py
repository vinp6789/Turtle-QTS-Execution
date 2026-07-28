"""Approved-signal selection (Alpha Engine R6; Architecture v0.2 SS4
Portfolio Construction -- the minimal, single-allocation-free slice).

select_signals() reduces the raw signal set emitted by (potentially
several) approved candidates into the set the execution bridge may act
on. Policy, fully deterministic and deliberately conservative:

  1. Only available, directional signals participate: unavailable
     signals and FLAT opinions are dropped (they made no actionable
     claim).
  2. CONFLICT REFUSAL: if two approved candidates disagree on a symbol
     (one LONG, one SHORT), EVERY signal for that symbol is dropped --
     the fail-safe direction. Netting, weighting, or trusting the
     higher-ranked candidate are all real policies a future milestone
     may add under governance control; silently picking one today would
     encode an unreviewed judgment about which strategy family to trust.
     Refusing to trade a disputed symbol encodes only "in doubt, do
     nothing" -- this codebase's consistent default.
  3. Same-direction duplicates collapse to one signal per (symbol,
     direction), keeping the first by (candidate_name,
     candidate_version) sort order -- a deterministic representative,
     not a preference claim.
  4. Output is sorted by symbol value: reproducible iteration for the
     bridge and for tests.

Capital sizing does NOT happen here: the Execution Engine's own frozen
RiskManager/portfolio-construction stack sizes every TradeIntent it
accepts. This layer decides only WHICH opinions survive aggregation.
"""

from typing import Dict, List, Tuple

from ..candidates import CandidateSignal, SignalDirection
from .errors import PortfolioError


def select_signals(signals: Tuple[CandidateSignal, ...]) -> Tuple[CandidateSignal, ...]:
    """Applies the selection policy above. An empty result is a normal,
    valid outcome (nothing actionable this cycle), never an error."""
    if not isinstance(signals, tuple):
        raise PortfolioError(f"signals must be a tuple, got {type(signals).__name__}")
    if not all(isinstance(s, CandidateSignal) for s in signals):
        raise PortfolioError("signals must contain only CandidateSignal instances")

    directional = [
        s for s in signals
        if s.available and s.direction is not SignalDirection.FLAT
    ]

    by_symbol: Dict[str, List[CandidateSignal]] = {}
    for signal in directional:
        by_symbol.setdefault(signal.symbol.value, []).append(signal)

    selected: List[CandidateSignal] = []
    for symbol_value in sorted(by_symbol):
        group = by_symbol[symbol_value]
        directions = {s.direction for s in group}
        if len(directions) > 1:
            continue  # conflict refusal: drop the whole symbol (policy #2)
        group.sort(key=lambda s: (s.candidate_name, s.candidate_version))
        selected.append(group[0])
    return tuple(selected)
