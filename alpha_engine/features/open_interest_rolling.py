"""Rolling (windowed) Open-Interest extremeness transforms — the first
features in this package that are NOT single-reading pass-throughs.

WHY THIS IS A DIFFERENT SHAPE FROM FundingRateFeature/OpenInterestFeature
(and why that is correct, not a violation): those features are pure
functions of ONE reading (WARMUP_PERIODS = 0) because the platform had no
historical windowing. Research Campaign 01 established empirically (see
docs/RESEARCH_CAMPAIGN_01_open_interest.md) that raw Open Interest is
strongly non-stationary — it grows ~3.4× over the sample for purely
secular reasons — so a fixed absolute threshold cannot express "extreme
OI." "Extreme relative to recent history" is inherently a WINDOWED
computation. These functions therefore take a trailing window of prior
values plus the current value, and return an extremeness score. They are
deliberately plain functions (not a new Feature ABC / windowed-feature
framework): a framework extracted from one windowed use would risk the
wrong contract, exactly the restraint applied to every prior feature.

POINT-IN-TIME CORRECTNESS IS THE CALLER'S CONTRACT: each function scores
`current` against a `window` of PRIOR observations. The caller
(campaign sample-construction code) must pass only values with
observed_at_utc <= the current sample's time — these functions cannot
enforce that (they receive plain Decimals), so the discipline lives at
the call site and is asserted there. Given a correct trailing window,
the output is a pure, deterministic function of its inputs: no wall
clock, no hidden state, no look-ahead possible from within.

Two normalizations, matching Research Campaign 01's pre-registration:
  - percentile_rank_centered(): the PRIMARY normalization. Robust to the
    heavy-tailed, regime-dependent OI distribution (it assumes nothing
    about the shape). Centered at 0 so the sign encodes which tail.
  - zscore(): the ROBUSTNESS normalization. Assumes an approximately
    stable mean/σ over the window; more sensitive to outliers, which is
    exactly why it is the secondary check, not the primary decision.

Both return a SIGNED score centered at 0 (positive = current is high
relative to the window; negative = low), so a single two-sided threshold
candidate (open_interest_extremeness_rule) can consume either.
"""

from decimal import Decimal
from typing import Optional, Sequence

# Canonical feature identities — shared by the campaign sample-construction
# code (which stamps them onto FeatureValue.feature_name) and by the
# candidate spec factory (which validates against them), so the two can
# never silently drift, exactly as every other feature/candidate pairing
# in this codebase guarantees.
PCTRANK_NAME = "open_interest_pctrank_centered"
PCTRANK_VERSION = "v1"
ZSCORE_NAME = "open_interest_zscore"
ZSCORE_VERSION = "v1"


def percentile_rank_centered(window: Sequence[Decimal], current: Decimal) -> Optional[Decimal]:
    """The centered percentile rank of `current` within `window` (the
    trailing distribution): (fraction of window strictly below current +
    half the fraction equal to it) − 0.5. Range (−0.5, +0.5]. Positive =
    current sits in the upper tail; negative = lower tail; ~0 = typical.

    Returns None (an unavailable feature — never a fabricated 0) if the
    window is empty: with no history there is no distribution to rank
    against. The "+ half the ties" convention (standard mid-rank) keeps
    the score symmetric and unbiased when many window values equal
    current."""
    if not isinstance(current, Decimal):
        raise TypeError(f"current must be a Decimal, got {type(current).__name__}")
    n = len(window)
    if n == 0:
        return None
    below = 0
    equal = 0
    for v in window:
        if not isinstance(v, Decimal):
            raise TypeError(f"window values must be Decimal, got {type(v).__name__}")
        if v < current:
            below += 1
        elif v == current:
            equal += 1
    rank = (Decimal(below) + Decimal(equal) / Decimal(2)) / Decimal(n)
    return rank - Decimal("0.5")


def zscore(window: Sequence[Decimal], current: Decimal) -> Optional[Decimal]:
    """The z-score of `current` against `window`'s mean and (population)
    standard deviation: (current − mean) / σ. Returns None (unavailable,
    never fabricated) if the window has fewer than 2 points or σ == 0
    (a degenerate, constant window has no scale to normalize against —
    reporting 0 would falsely claim 'perfectly typical')."""
    if not isinstance(current, Decimal):
        raise TypeError(f"current must be a Decimal, got {type(current).__name__}")
    n = len(window)
    if n < 2:
        return None
    for v in window:
        if not isinstance(v, Decimal):
            raise TypeError(f"window values must be Decimal, got {type(v).__name__}")
    mean = sum(window, Decimal(0)) / Decimal(n)
    variance = sum(((v - mean) ** 2 for v in window), Decimal(0)) / Decimal(n)
    if variance == 0:
        return None
    std = variance.sqrt()
    return (current - mean) / std
