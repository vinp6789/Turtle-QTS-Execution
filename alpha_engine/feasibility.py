"""Pre-registration feasibility arithmetic: can this campaign answer its own question?

Three questions every campaign must answer BEFORE its specification is
locked, and which no campaign in this project's history has answered:

  1. **Economic** -- is the pre-registered hit-rate bar above the rate at
     which the strategy merely breaks even against costs? A bar below
     breakeven means the campaign can PASS and still lose money.
  2. **Statistical** -- is the effective sample large enough to detect an
     effect as small as that bar? An MDE above the bar means the campaign
     cannot distinguish its own hypothesis from noise, so a null result
     is UNRESOLVED, not REJECTED.
  3. **Fiscal** -- does the payoff structure survive taxation of gross
     gains with no loss set-off? A strategy can clear (1) and (2) on every
     trade and still be untradeable by an Indian taxpayer.

All three are arithmetic. None needs data, a backtest, or a model. All
three were available before any of the nine campaigns ran.

WHY THIS IS NOT A NEW ABSTRACTION (Constitution Section 5). Pure functions
over floats with no state, no I/O, no clock and no dependency on any other
alpha_engine module. It builds no framework -- it writes down arithmetic
the pre-registration feasibility review (Constitution Section 6) was
already required to perform and had no shared implementation for.

FLOATS, DELIBERATELY. Every other numeric path in this project uses
Decimal because it touches prices or capital. This module touches
neither: it is a planning calculator whose inputs are estimates (mean
move, slippage, correlation) with two significant figures at best.
Decimal would imply a precision the inputs do not have.

DEFAULTS ARE MEASURED, NOT ASSUMED -- see each constant.

CORRECTIONS APPLIED after the independent audit of 2026-08-06. Four
defects were found in the first version of this module and are fixed
here; each is recorded because the wrong answers were briefly used:

  A. **Dependence input was the wrong quantity.** N_eff was computed from
     the correlation of RETURNS, but the statistic being pooled is a
     binary HIT INDICATOR. For jointly normal returns with correlation r,
     the sign indicators correlate at 2*arcsin(r)/pi, which is materially
     lower. Using r directly understated N_eff by ~21% at r = 0.69. See
     hit_correlation().
  B. **Equicorrelation ignored the real eigenstructure.** k/(1+(k-1)*rho)
     assumes one uniform pairwise correlation, and returns N_eff > k --
     which is meaningless as an information count -- whenever rho is
     negative, as it is for cross-sectionally demeaned residuals. See
     participation_ratio().
  C. **The tax gate omitted fees.** The profit factor was computed on
     gross moves, but a winner nets (win - cost) and a loser costs
     (loss + cost). This understated the required hit rate by 2.44
     percentage points (0.5924 vs 0.6169 on the measured cross-sectional
     configuration).
  D. **The MDE approximation's direction was documented backwards.** It
     overstates MDE slightly (conservative), it does not understate it.

Defect C also removed this module's original scope limit: because the
tax gate makes symmetric-payoff designs effectively untradeable, every
campaign worth running is asymmetric, so asymmetric payoffs are now a
present concrete need rather than a hypothetical one.
"""

import math

# Hyperliquid perp fees, base tier (no volume, staking or referral
# discount). MEASURED live from /info userFees on 2026-08-06:
# userCrossRate 0.00045, userAddRate 0.00015.
TAKER_FEE_BPS = 4.5
MAKER_FEE_BPS = 1.5

# Funding cost of holding a perp position, one side, per day.
# MEASURED: 5.10%/yr verified across 14/14 instruments with 0.0% gaps
# -> 5.10 / 365 * 100 = 1.397 bp/day.
#
# CHARGED AS A COST, WHICH IS CONSERVATIVE AND OFTEN WRONG. A position
# pays this on one side and receives it on the other. For a signal
# uncorrelated with funding the expectation is ~0, and for a
# market-neutral long/short book the two legs largely cancel. Pass
# funding_bps_per_day=0.0 for a market-neutral design and say so in the
# pre-registration; the default is deliberately pessimistic.
FUNDING_BPS_PER_DAY = 1.40

# Indian VDA taxation: 30% + 4% cess on the tax = 31.2% effective, levied
# on GROSS gains, with no loss set-off and no carry-forward. After-tax
# profit is 0.688 * gross_wins - gross_losses, so viability requires
# gross_wins / gross_losses > 1 / 0.688.
VDA_TAX_RATE = 0.30 * 1.04
MIN_GROSS_PROFIT_FACTOR = 1.0 / (1.0 - VDA_TAX_RATE)  # 1.45349

# Two-sided z at alpha=0.05, and one-sided z at power=0.80.
# Two-sided is the default because this project registers contrarian AND
# momentum as separate experiments (Constitution Section 6), which is
# structurally a two-sided test of one mechanism.
_Z_ALPHA_TWO_SIDED = 1.959964
_Z_ALPHA_ONE_SIDED = 1.644854
_Z_POWER = 0.841621


# --------------------------------------------------------------- costs

def round_trip_cost_bps(
    *,
    horizon_hours,
    entry_is_maker=False,
    exit_is_maker=False,
    slippage_bps_per_side=0.0,
    funding_bps_per_day=FUNDING_BPS_PER_DAY,
):
    """Total cost of one round trip, in basis points of notional.

    Slippage defaults to ZERO and that is deliberate: this project has
    never measured its own slippage, and a plausible-looking guess would
    silently become the number every downstream verdict rests on. Until a
    measured value exists the returned cost is a LOWER BOUND and every
    breakeven derived from it is optimistic.
    """
    entry = MAKER_FEE_BPS if entry_is_maker else TAKER_FEE_BPS
    exit_ = MAKER_FEE_BPS if exit_is_maker else TAKER_FEE_BPS
    funding = funding_bps_per_day * (horizon_hours / 24.0)
    return entry + exit_ + 2.0 * slippage_bps_per_side + funding


def breakeven_hit_rate(mean_abs_move_bps, cost_bps, *, win_loss_ratio=1.0):
    """Hit rate at which a directional bet nets exactly zero.

    A winner gains (w - c); a loser gives up (l + c). Setting expectancy
    to zero gives p = (l + c) / (w + l), where l is the typical adverse
    move and w = win_loss_ratio * l the typical favourable one. For a
    symmetric bet this reduces to the familiar 0.5 + c/(2m).

    Returns a value > 1.0 when costs exceed the available move -- not an
    error, but the arithmetic proof that no hit rate makes the horizon
    tradeable. Callers must not clamp it.
    """
    if mean_abs_move_bps <= 0:
        raise ValueError("mean_abs_move_bps must be positive")
    if win_loss_ratio <= 0:
        raise ValueError("win_loss_ratio must be positive")
    loss = mean_abs_move_bps
    win = win_loss_ratio * loss
    return (loss + cost_bps) / (win + loss)


# ---------------------------------------------------------- dependence

def hit_correlation(return_correlation):
    """Correlation of SIGN agreement implied by a correlation of returns.

    For jointly normal (X, Y) with correlation r, P(sign X = sign Y) =
    1/2 + arcsin(r)/pi, and the two sign indicators -- each Bernoulli(1/2)
    -- therefore correlate at 2*arcsin(r)/pi.

    This is the quantity effective_sample_size() needs. A hit indicator is
    a sign agreement, not a return, and feeding a return correlation
    straight in overstates the dependence between pooled instruments
    (defect A). At r = +0.69 the hit correlation is +0.48.
    """
    r = max(-1.0, min(1.0, return_correlation))
    return 2.0 * math.asin(r) / math.pi


def participation_ratio(eigenvalues):
    """Effective number of independent series from a correlation matrix.

    (sum lambda)^2 / sum(lambda^2) -- the standard participation ratio.
    Equals k when every eigenvalue is equal (fully independent) and 1 when
    one factor explains everything.

    Preferred over the equicorrelation formula whenever the eigenvalues
    are available: equicorrelation assumes a single uniform pairwise rho
    and breaks down entirely for negative rho, where it reports N_eff > k
    (defect B). Eigenvalues are supplied by the caller so this module
    keeps no numeric dependency.
    """
    ev = [e for e in eigenvalues if e > 0]
    if not ev:
        raise ValueError("eigenvalues must contain at least one positive value")
    total = sum(ev)
    return (total * total) / sum(e * e for e in ev)


def effective_sample_size(
    n_raw, *, n_instruments=1, hit_rho_bar=0.0, serial_retention=1.0,
    independent_series=None,
):
    """Raw pooled samples discounted for cross-instrument and serial dependence.

    `hit_rho_bar` must be the correlation of the HIT INDICATORS -- pass a
    return correlation through hit_correlation() first. Named explicitly
    so the defect-A substitution cannot happen silently again.

    `independent_series` overrides the equicorrelation estimate with a
    directly measured value, normally from participation_ratio(). Use it
    whenever the eigenvalues are available; it is strictly more accurate.

    Serial retention is a separate multiplier the caller measures; it is
    NOT folded into hit_rho_bar.
    """
    if n_raw < 0:
        raise ValueError("n_raw must be non-negative")
    if n_instruments < 1:
        raise ValueError("n_instruments must be at least 1")
    if not -1.0 <= hit_rho_bar <= 1.0:
        raise ValueError("hit_rho_bar must be in [-1, 1]")
    if not 0.0 < serial_retention <= 1.0:
        raise ValueError("serial_retention must be in (0, 1]")
    k = float(n_instruments)
    if independent_series is None:
        denominator = 1.0 + (k - 1.0) * hit_rho_bar
        if denominator <= 0:
            raise ValueError(
                "equicorrelation is undefined for this hit_rho_bar; supply "
                "independent_series from participation_ratio() instead"
            )
        independent_series = k / denominator
    if independent_series <= 0:
        raise ValueError("independent_series must be positive")
    # Never credit more independent information than there are series.
    independent_series = min(independent_series, k)
    return n_raw * (independent_series / k) * serial_retention


# ----------------------------------------------------------- power

def minimum_detectable_effect(n_eff, *, two_sided=True):
    """Smallest hit rate distinguishable from 0.5 at 80% power, alpha=0.05.

    Solves p = 0.5 + (z_alpha*0.5 + z_beta*sqrt(p(1-p))) / sqrt(n)
    exactly by fixed-point iteration rather than holding the alternative's
    variance at its p=0.5 value. The shortcut OVERSTATES MDE (by 0.005 at
    n=45, 0.0001 at n=785) -- conservative, but the original docstring
    described the direction backwards (defect D).
    """
    if n_eff <= 0:
        return 1.0
    za = _Z_ALPHA_TWO_SIDED if two_sided else _Z_ALPHA_ONE_SIDED
    p = 0.55
    for _ in range(100):
        p_next = 0.5 + (za * 0.5 + _Z_POWER * math.sqrt(p * (1.0 - p))) / math.sqrt(n_eff)
        if abs(p_next - p) < 1e-15:
            p = p_next
            break
        p = min(p_next, 0.999999)
    return min(p, 1.0)


def required_effective_samples(target_hit_rate, *, two_sided=True):
    """Exact inverse of minimum_detectable_effect()."""
    edge = target_hit_rate - 0.5
    if edge <= 0:
        raise ValueError("target_hit_rate must exceed 0.5")
    za = _Z_ALPHA_TWO_SIDED if two_sided else _Z_ALPHA_ONE_SIDED
    numerator = za * 0.5 + _Z_POWER * math.sqrt(target_hit_rate * (1.0 - target_hit_rate))
    return (numerator / edge) ** 2


# ------------------------------------------------------------- tax

def survives_vda_tax(gross_profit_factor):
    """Indian VDA tax leaves a net profit only above a gross PF of ~1.4535."""
    return gross_profit_factor > MIN_GROSS_PROFIT_FACTOR


def tax_viable_hit_rate(*, win_loss_ratio=1.0, mean_abs_move_bps=None, cost_bps=0.0):
    """Hit rate at which the profit factor clears the VDA threshold.

    PF = p(w - c) / [(1 - p)(l + c)] > R, so
    p > R(l + c) / [R(l + c) + (w - c)].

    Fees belong inside this calculation: a winner realises (w - c) and a
    loser realises (l + c), so omitting them understates the required hit
    rate (defect C). Pass mean_abs_move_bps and cost_bps to include them;
    omitting mean_abs_move_bps falls back to the gross-move form, which is
    correct only at zero cost.

    On the measured cross-sectional configuration (m = 203.6 bp,
    c = 10.4 bp, symmetric) this returns 0.6169, not the 0.5924 the
    uncorrected form produced.
    """
    if win_loss_ratio <= 0:
        raise ValueError("win_loss_ratio must be positive")
    R = MIN_GROSS_PROFIT_FACTOR
    if mean_abs_move_bps is None:
        if cost_bps:
            raise ValueError("cost_bps requires mean_abs_move_bps to be meaningful")
        return R / (R + win_loss_ratio)
    if mean_abs_move_bps <= 0:
        raise ValueError("mean_abs_move_bps must be positive")
    loss = mean_abs_move_bps
    win = win_loss_ratio * loss
    if win <= cost_bps:
        return 1.0  # a winner does not even cover its own cost
    return R * (loss + cost_bps) / (R * (loss + cost_bps) + (win - cost_bps))


# ------------------------------------------------------------ gate

class Verdict:
    """The result of assess(). Truthy only when the campaign can answer its question."""

    __slots__ = ("breakeven", "mde", "bar", "n_eff", "cost_bps",
                 "mean_abs_move_bps", "tax_bar", "reasons")

    def __init__(self, breakeven, mde, bar, n_eff, cost_bps,
                 mean_abs_move_bps, tax_bar, reasons):
        self.breakeven = breakeven
        self.mde = mde
        self.bar = bar
        self.n_eff = n_eff
        self.cost_bps = cost_bps
        self.mean_abs_move_bps = mean_abs_move_bps
        self.tax_bar = tax_bar
        self.reasons = tuple(reasons)

    @property
    def viable(self):
        return not self.reasons

    @property
    def label(self):
        if self.viable:
            return "VIABLE"
        tags = []
        for prefix in ("UNECONOMIC", "UNDERPOWERED", "TAX-DESTROYED"):
            if any(r.startswith(prefix) for r in self.reasons):
                tags.append(prefix)
        return "+".join(tags)

    def __bool__(self):
        return self.viable

    def __repr__(self):
        return (f"Verdict({self.label}: bar={self.bar:.4f} "
                f"breakeven={self.breakeven:.4f} mde={self.mde:.4f} "
                f"tax_bar={self.tax_bar:.4f} n_eff={self.n_eff:.0f})")


def assess(
    *,
    mean_abs_move_bps,
    pre_registered_bar,
    n_raw_signalled,
    horizon_hours,
    n_instruments=1,
    hit_rho_bar=0.0,
    independent_series=None,
    serial_retention=1.0,
    win_loss_ratio=1.0,
    entry_is_maker=False,
    exit_is_maker=False,
    slippage_bps_per_side=0.0,
    funding_bps_per_day=FUNDING_BPS_PER_DAY,
    two_sided=True,
):
    """The gate. A campaign may be pre-registered only if this is truthy.

    Fails for three independent reasons and reports every one that
    applies, because the remedies differ. UNECONOMIC is fixed by raising
    the bar, lengthening the horizon or paying maker fees; UNDERPOWERED
    only by more independent data; TAX-DESTROYED only by changing the
    payoff shape.
    """
    cost = round_trip_cost_bps(
        horizon_hours=horizon_hours,
        entry_is_maker=entry_is_maker,
        exit_is_maker=exit_is_maker,
        slippage_bps_per_side=slippage_bps_per_side,
        funding_bps_per_day=funding_bps_per_day,
    )
    breakeven = breakeven_hit_rate(mean_abs_move_bps, cost, win_loss_ratio=win_loss_ratio)
    n_eff = effective_sample_size(
        n_raw_signalled, n_instruments=n_instruments, hit_rho_bar=hit_rho_bar,
        independent_series=independent_series, serial_retention=serial_retention,
    )
    mde = minimum_detectable_effect(n_eff, two_sided=two_sided)
    tax_bar = tax_viable_hit_rate(
        win_loss_ratio=win_loss_ratio,
        mean_abs_move_bps=mean_abs_move_bps,
        cost_bps=cost,
    )

    reasons = []
    if pre_registered_bar < breakeven:
        reasons.append(
            f"UNECONOMIC: bar {pre_registered_bar:.4f} is below breakeven "
            f"{breakeven:.4f} at {cost:.1f}bp cost / {mean_abs_move_bps:.1f}bp move "
            f"-- this campaign can PASS and still lose money"
        )
    if mde > pre_registered_bar:
        needed = required_effective_samples(pre_registered_bar, two_sided=two_sided)
        reasons.append(
            f"UNDERPOWERED: MDE {mde:.4f} exceeds bar {pre_registered_bar:.4f} at "
            f"n_eff {n_eff:.0f} -- needs {needed:.0f} effective samples; a null "
            f"here is UNRESOLVED, not REJECTED"
        )
    if pre_registered_bar < tax_bar:
        reasons.append(
            f"TAX-DESTROYED: bar {pre_registered_bar:.4f} is below the after-tax "
            f"threshold {tax_bar:.4f} at win/loss {win_loss_ratio:.2f} -- gross "
            f"gains are taxed at {VDA_TAX_RATE:.1%} with no loss set-off"
        )
    return Verdict(breakeven, mde, pre_registered_bar, n_eff, cost,
                   mean_abs_move_bps, tax_bar, reasons)


# ------------------------------------------- A1: asymmetric-design gating

def profit_factor(payoffs):
    """Gross profit factor of a realised payoff series.

    Payoffs are signed per-trade results in any consistent unit. Zeros
    belong to neither leg, exactly as in the validation runner.

    Returns None when there is no losing trade: a ratio with no
    denominator is undefined, not infinite. Returns 0.0 for losses with
    no wins, which is well defined.
    """
    wins = sum(p for p in payoffs if p > 0)
    losses = -sum(p for p in payoffs if p < 0)
    if losses <= 0:
        return None
    return wins / losses


def bootstrap_profit_factor_power(
    payoffs, *, n_trades, threshold=MIN_GROSS_PROFIT_FACTOR,
    n_resamples=1000, seed=7,
):
    """Probability that `n_trades` drawn from this payoff distribution
    produce a gross profit factor above `threshold`.

    WHY THIS EXISTS. minimum_detectable_effect() answers "how many
    samples to detect a hit rate", which is the wrong question for an
    asymmetric design: the tax gate forces win/loss ratios away from 1,
    and there the binomial has no closed form worth trusting. Resampling
    the actual payoff distribution answers the question directly and
    makes no distributional assumption at all.

    DETERMINISTIC by construction -- an explicit seed, never a global RNG
    (Constitution Section 5). Two runs over identical inputs are
    byte-identical.

    NOT a backtest and NOT out-of-sample. It answers only "is this
    payoff shape statistically distinguishable from the tax threshold at
    this sample size?" -- a power question, asked before any campaign is
    locked, from a pilot or prior payoff distribution.
    """
    import random
    if not payoffs:
        raise ValueError("payoffs must be non-empty")
    if n_trades < 1:
        raise ValueError("n_trades must be at least 1")
    if n_resamples < 1:
        raise ValueError("n_resamples must be at least 1")
    rng = random.Random(seed)
    pool = list(payoffs)
    cleared = 0
    for _ in range(n_resamples):
        draw = [pool[rng.randrange(len(pool))] for _ in range(n_trades)]
        pf = profit_factor(draw)
        # An undefined PF (no losing trade in the draw) clears any finite
        # threshold -- it is an unbroken winning run, not a missing value.
        if pf is None or pf > threshold:
            cleared += 1
    return cleared / n_resamples


def required_trades_for_profit_factor(
    payoffs, *, threshold=MIN_GROSS_PROFIT_FACTOR, target_power=0.80,
    n_resamples=1000, seed=7, max_trades=20_000,
):
    """Smallest n_trades whose bootstrap power reaches `target_power`.

    Doubling search then bisection -- power is monotone in n_trades for a
    fixed distribution, so this is well defined. Returns None when
    `max_trades` cannot reach the target, which is the honest answer for
    a payoff shape that is simply not viable: no sample size rescues a
    distribution whose expectancy is below the threshold.
    """
    lo, hi = 1, 1
    while hi <= max_trades:
        if bootstrap_profit_factor_power(payoffs, n_trades=hi, threshold=threshold,
                                         n_resamples=n_resamples, seed=seed) >= target_power:
            break
        lo, hi = hi, hi * 2
    else:
        return None
    while lo < hi:
        mid = (lo + hi) // 2
        if bootstrap_profit_factor_power(payoffs, n_trades=mid, threshold=threshold,
                                         n_resamples=n_resamples, seed=seed) >= target_power:
            hi = mid
        else:
            lo = mid + 1
    return lo


def derive_acceptance_bar(
    *, mean_abs_move_bps, horizon_hours, win_loss_ratio=1.0,
    entry_is_maker=False, exit_is_maker=False, slippage_bps_per_side=0.0,
    funding_bps_per_day=FUNDING_BPS_PER_DAY,
):
    """The per-campaign acceptance bar, DERIVED rather than inherited.

    Returns (bar, components). The bar is the binding constraint of two:

      cost breakeven  -- below it the campaign can pass and lose money
      tax threshold   -- below it the campaign can profit and still be
                         untradeable by an Indian taxpayer

    `[R]` Replaces `min_hit_rate = 0.55`, which was copied unexamined
    into all eight pre-registrations and appears in no derivation
    anywhere in the repository. It was simultaneously too low to be
    tradeable and too high to be detectable at the samples available.

    The bar is a floor, not a target. A campaign may pre-register a
    HIGHER bar; it may never register a lower one.
    """
    cost = round_trip_cost_bps(
        horizon_hours=horizon_hours, entry_is_maker=entry_is_maker,
        exit_is_maker=exit_is_maker, slippage_bps_per_side=slippage_bps_per_side,
        funding_bps_per_day=funding_bps_per_day,
    )
    breakeven = breakeven_hit_rate(mean_abs_move_bps, cost, win_loss_ratio=win_loss_ratio)
    tax_bar = tax_viable_hit_rate(
        win_loss_ratio=win_loss_ratio, mean_abs_move_bps=mean_abs_move_bps, cost_bps=cost)
    bar = max(breakeven, tax_bar)
    return bar, {
        "cost_bps": cost,
        "breakeven_hit_rate": breakeven,
        "tax_viable_hit_rate": tax_bar,
        "binding": "tax" if tax_bar >= breakeven else "cost",
    }
