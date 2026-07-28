"""Candidate Data Sources (Architecture v0.2 SS4; Alpha Engine Milestone
1.1: funding rate -- the first, chosen deliberately because it requires
no new venue integration; Milestone 1.2: Open Interest -- the second, and
the first genuinely independent of the Execution Engine).

Public API:
    FundingRateProvider   -- wraps trading_system.market_data.
                            MarketDataView.get_funding_rate; one fetch()
                            method, fail-safe on any problem
    FundingRateReading    -- one fetch() attempt's outcome
    OpenInterestProvider  -- talks to Hyperliquid's public /info endpoint
                            directly via its own minimal stdlib HTTP
                            client; imports nothing from the Execution
                            Engine (see open_interest.py's docstring)
    OpenInterestReading   -- one fetch() attempt's outcome; mirrors
                            FundingRateReading's availability discipline
    DataSourceError       -- this sub-package's error base (caller-error
                            validation only; fetch() itself never raises
                            for a data problem)

Every provider here fails safe (no data -> no signal, never a fabricated
value) per the Failure Philosophy (Architecture v0.2 SS8), and is never
assumed to carry predictive edge (constraint #1) -- that is a question
for the validation gate (Milestone 4.x), not this layer.
"""

from .errors import DataSourceError
from .funding_rate import FundingRateProvider, FundingRateReading
from .open_interest import OpenInterestProvider, OpenInterestReading

__all__ = [
    "FundingRateProvider",
    "FundingRateReading",
    "OpenInterestProvider",
    "OpenInterestReading",
    "DataSourceError",
]
