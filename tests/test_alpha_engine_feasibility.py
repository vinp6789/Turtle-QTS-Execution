"""Tests for alpha_engine.feasibility -- the pre-registration gate.

Four jobs:

  1. ARITHMETIC. Every formula is checked against a value derived by hand
     in the test, not against a value produced by the code. A regression
     here would silently pass or fail real campaigns.

  2. REGRESSION AGAINST THE CLOSED RECORD. The gate is applied to the
     actual measured configuration of Campaigns 01-08. Those inputs are
     historical fact and cannot change, so these tests pin what the gate
     WOULD have said. If a future edit makes the gate approve CAMP-08,
     the edit is wrong.

  3. THE FOUR AUDITED DEFECTS STAY FIXED. The 2026-08-06 audit found four
     errors in the first version of this module. Each has a test named
     for it, so a "simplification" that reintroduces one fails loudly.

  4. REFUSAL TO FLATTER. breakeven_hit_rate must be allowed to return
     values above 1.0, minimum_detectable_effect must return 1.0 at zero
     samples, and effective_sample_size must never credit more
     independent information than there are series. All three are the
     arithmetic saying "impossible"; clamping any of them would convert
     the gate into a formality.
"""

import math
import unittest

from alpha_engine.feasibility import (
    MAKER_FEE_BPS,
    MIN_GROSS_PROFIT_FACTOR,
    TAKER_FEE_BPS,
    VDA_TAX_RATE,
    assess,
    breakeven_hit_rate,
    effective_sample_size,
    hit_correlation,
    minimum_detectable_effect,
    participation_ratio,
    required_effective_samples,
    round_trip_cost_bps,
    survives_vda_tax,
    tax_viable_hit_rate,
)

# Measured 2026-08-06 from Hyperliquid 1h candles, BTC/ETH/SOL pooled,
# 200-day window.
MEAN_ABS_MOVE_BPS = {1: 39.8, 24: 218.8, 72: 371.3, 120: 444.1}

# Measured cross-symbol correlation of RETURNS (not hits) per horizon.
RETURN_RHO = {1: 0.8753, 24: 0.6893, 72: 0.296, 120: 0.296}

# Measured cross-sectional configuration: 30 liquid perps, 392 daily
# observations each, market-neutral residuals.
XS_RESIDUAL_MOVE_BPS = 203.6
XS_INDEPENDENT_SERIES = 21.58   # participation ratio of the sign-corr matrix
XS_PANEL_RAW = 11760            # 392 days x 30 symbols


class TestCostModel(unittest.TestCase):
    def test_taker_round_trip_is_two_taker_fees_plus_funding(self):
        self.assertAlmostEqual(round_trip_cost_bps(horizon_hours=24),
                               4.5 + 4.5 + 1.40, places=6)

    def test_maker_round_trip_is_cheaper_by_six_bps(self):
        taker = round_trip_cost_bps(horizon_hours=1)
        maker = round_trip_cost_bps(horizon_hours=1, entry_is_maker=True,
                                    exit_is_maker=True)
        self.assertAlmostEqual(taker - maker,
                               2 * (TAKER_FEE_BPS - MAKER_FEE_BPS), places=6)

    def test_funding_scales_linearly_with_horizon(self):
        self.assertAlmostEqual(round_trip_cost_bps(horizon_hours=48)
                               - round_trip_cost_bps(horizon_hours=24),
                               1.40, places=6)

    def test_market_neutral_books_may_zero_funding(self):
        """A long/short book's two legs largely cancel; the default is pessimistic."""
        self.assertAlmostEqual(
            round_trip_cost_bps(horizon_hours=24, funding_bps_per_day=0.0),
            2 * TAKER_FEE_BPS, places=6)

    def test_slippage_is_charged_on_both_sides_and_defaults_to_zero(self):
        base = round_trip_cost_bps(horizon_hours=1)
        self.assertAlmostEqual(
            round_trip_cost_bps(horizon_hours=1, slippage_bps_per_side=2.0) - base,
            4.0, places=6)
        self.assertAlmostEqual(base, TAKER_FEE_BPS * 2 + 1.40 / 24.0, places=6)


class TestBreakeven(unittest.TestCase):
    def test_symmetric_matches_the_closed_form(self):
        # (l + c)/(w + l) with w = l = 100, c = 9 -> 109/200 = 0.545
        self.assertAlmostEqual(breakeven_hit_rate(100.0, 9.0), 0.545, places=9)
        self.assertAlmostEqual(breakeven_hit_rate(100.0, 9.0),
                               0.5 + 9.0 / 200.0, places=12)

    def test_zero_cost_breaks_even_at_a_coin_flip(self):
        self.assertAlmostEqual(breakeven_hit_rate(50.0, 0.0), 0.5, places=9)

    def test_asymmetric_payoffs_lower_the_breakeven(self):
        # w = 2l = 200, l = 100, c = 9 -> 109/300 = 0.36333
        self.assertAlmostEqual(
            breakeven_hit_rate(100.0, 9.0, win_loss_ratio=2.0), 109.0 / 300.0,
            places=9)

    def test_may_exceed_one_and_is_never_clamped(self):
        self.assertGreater(breakeven_hit_rate(1.0, 9.0), 1.0)

    def test_rejects_invalid_inputs(self):
        with self.assertRaises(ValueError):
            breakeven_hit_rate(0.0, 9.0)
        with self.assertRaises(ValueError):
            breakeven_hit_rate(100.0, 9.0, win_loss_ratio=0.0)


class TestDefectA_HitCorrelation(unittest.TestCase):
    """The N_eff input must be hit correlation, not return correlation."""

    def test_arcsine_law(self):
        # 2*arcsin(0.6893)/pi
        self.assertAlmostEqual(hit_correlation(0.6893),
                               2 * math.asin(0.6893) / math.pi, places=12)
        self.assertAlmostEqual(hit_correlation(0.6893), 0.4841636, places=7)

    def test_hit_correlation_is_strictly_below_return_correlation(self):
        for r in (0.296, 0.5997, 0.6893, 0.731, 0.8753):
            self.assertLess(hit_correlation(r), r)

    def test_endpoints_and_sign_are_preserved(self):
        self.assertAlmostEqual(hit_correlation(0.0), 0.0, places=12)
        self.assertAlmostEqual(hit_correlation(1.0), 1.0, places=12)
        self.assertAlmostEqual(hit_correlation(-1.0), -1.0, places=12)
        self.assertLess(hit_correlation(-0.5), 0.0)

    def test_using_return_rho_would_understate_n_eff_by_about_a_fifth(self):
        wrong = effective_sample_size(1000, n_instruments=3, hit_rho_bar=0.6893)
        right = effective_sample_size(1000, n_instruments=3,
                                      hit_rho_bar=hit_correlation(0.6893))
        self.assertGreater(right / wrong, 1.19)
        self.assertLess(right / wrong, 1.22)


class TestDefectB_ParticipationRatio(unittest.TestCase):
    """Equicorrelation breaks down where the eigenstructure does not."""

    def test_equal_eigenvalues_mean_full_independence(self):
        self.assertAlmostEqual(participation_ratio([1.0] * 30), 30.0, places=9)

    def test_one_dominant_factor_collapses_to_about_one(self):
        self.assertLess(participation_ratio([29.0, 0.05, 0.05]), 1.1)

    def test_measured_directional_and_residual_structures(self):
        # Directional: lambda1 = 18.97 of 30 -> N_eff well under 5.
        self.assertLess(participation_ratio([18.97, 1.15, 0.99, 0.78, 0.72]
                                            + [0.2] * 25), 5.0)

    def test_equicorrelation_refuses_negative_rho_instead_of_returning_nonsense(self):
        """k/(1+(k-1)rho) exceeds k for negative rho -- meaningless as a count."""
        with self.assertRaises(ValueError):
            effective_sample_size(100, n_instruments=30, hit_rho_bar=-0.05)

    def test_independent_series_is_never_credited_above_k(self):
        got = effective_sample_size(1000, n_instruments=30, independent_series=73.0)
        self.assertAlmostEqual(got, 1000.0, places=9)

    def test_rejects_empty_or_non_positive_eigenvalues(self):
        with self.assertRaises(ValueError):
            participation_ratio([])
        with self.assertRaises(ValueError):
            participation_ratio([0.0, -1.0])


class TestEffectiveSampleSize(unittest.TestCase):
    def test_independent_instruments_lose_nothing(self):
        self.assertAlmostEqual(
            effective_sample_size(300, n_instruments=3, hit_rho_bar=0.0),
            300.0, places=6)

    def test_perfect_correlation_collapses_three_symbols_to_one(self):
        self.assertAlmostEqual(
            effective_sample_size(300, n_instruments=3, hit_rho_bar=1.0),
            100.0, places=6)

    def test_serial_retention_is_a_separate_multiplier(self):
        a = effective_sample_size(1000, n_instruments=3, hit_rho_bar=0.5)
        b = effective_sample_size(1000, n_instruments=3, hit_rho_bar=0.5,
                                  serial_retention=0.5)
        self.assertAlmostEqual(b, a * 0.5, places=6)

    def test_rejects_impossible_inputs(self):
        with self.assertRaises(ValueError):
            effective_sample_size(-1)
        with self.assertRaises(ValueError):
            effective_sample_size(10, n_instruments=3, hit_rho_bar=1.5)
        with self.assertRaises(ValueError):
            effective_sample_size(10, serial_retention=0.0)


class TestDefectD_MinimumDetectableEffect(unittest.TestCase):
    """The exact solve, and the documented direction of the approximation."""

    def test_solves_its_own_defining_equation(self):
        n = 400.0
        p = minimum_detectable_effect(n)
        rhs = 0.5 + (1.959964 * 0.5 + 0.841621 * math.sqrt(p * (1 - p))) / math.sqrt(n)
        self.assertAlmostEqual(p, rhs, places=12)

    def test_exact_is_below_the_variance_at_half_shortcut(self):
        """The shortcut OVERSTATES MDE -- conservative, not optimistic."""
        for n in (45, 100, 785):
            shortcut = 0.5 + 0.5 * (1.959964 + 0.841621) / math.sqrt(n)
            self.assertLess(minimum_detectable_effect(n), shortcut)

    def test_one_sided_is_less_demanding_than_two_sided(self):
        self.assertLess(minimum_detectable_effect(400, two_sided=False),
                        minimum_detectable_effect(400, two_sided=True))

    def test_zero_samples_detect_nothing(self):
        self.assertEqual(minimum_detectable_effect(0), 1.0)

    def test_round_trips_with_required_effective_samples(self):
        for bar in (0.52, 0.55, 0.6169):
            n = required_effective_samples(bar)
            self.assertAlmostEqual(minimum_detectable_effect(n), bar, places=9)

    def test_a_055_bar_needs_about_783_effective_samples(self):
        self.assertAlmostEqual(required_effective_samples(0.55), 782.5, places=1)

    def test_the_project_floor_of_100_corresponds_to_an_mde_of_064(self):
        """min_signaled_samples=100 was never a power criterion."""
        self.assertAlmostEqual(minimum_detectable_effect(100), 0.6384, places=4)
        self.assertGreater(required_effective_samples(0.55) / 100.0, 7.0)

    def test_rejects_a_bar_at_or_below_chance(self):
        with self.assertRaises(ValueError):
            required_effective_samples(0.5)


class TestDefectC_TaxGate(unittest.TestCase):
    """Fees belong inside the profit factor."""

    def test_effective_rate_and_threshold(self):
        self.assertAlmostEqual(VDA_TAX_RATE, 0.312, places=9)
        self.assertAlmostEqual(MIN_GROSS_PROFIT_FACTOR, 1.45349, places=5)

    def test_profit_factor_boundary(self):
        self.assertFalse(survives_vda_tax(1.4))
        self.assertTrue(survives_vda_tax(1.5))

    def test_zero_cost_form_reproduces_the_gross_derivation(self):
        self.assertAlmostEqual(tax_viable_hit_rate(), 0.5924171, places=7)

    def test_including_fees_raises_the_bar_by_244_basis_points(self):
        """0.5924 was the uncorrected figure; 0.6169 is correct."""
        gross = tax_viable_hit_rate()
        net = tax_viable_hit_rate(mean_abs_move_bps=XS_RESIDUAL_MOVE_BPS,
                                  cost_bps=10.4)
        self.assertAlmostEqual(net, 0.61685, places=5)
        self.assertAlmostEqual(net - gross, 0.0244370, places=7)

    def test_asymmetric_payoffs_lower_the_required_hit_rate(self):
        sym = tax_viable_hit_rate(mean_abs_move_bps=XS_RESIDUAL_MOVE_BPS,
                                  cost_bps=10.4)
        asym = tax_viable_hit_rate(win_loss_ratio=2.0,
                                   mean_abs_move_bps=XS_RESIDUAL_MOVE_BPS,
                                   cost_bps=10.4)
        self.assertLess(asym, sym)
        self.assertAlmostEqual(asym, 0.4394265, places=7)

    def test_a_winner_that_cannot_cover_its_cost_is_impossible_at_any_hit_rate(self):
        self.assertEqual(tax_viable_hit_rate(mean_abs_move_bps=5.0, cost_bps=9.4), 1.0)

    def test_rejects_costs_without_a_move_to_compare_them_to(self):
        with self.assertRaises(ValueError):
            tax_viable_hit_rate(cost_bps=10.0)
        with self.assertRaises(ValueError):
            tax_viable_hit_rate(win_loss_ratio=0.0)


class TestAssessGateAgainstTheClosedRecord(unittest.TestCase):
    """Applied to the real, closed record. These inputs are historical fact."""

    def _camp(self, horizon, signalled, return_rho=None, serial=1.0, bar=0.55):
        rho = RETURN_RHO[horizon] if return_rho is None else return_rho
        return assess(
            mean_abs_move_bps=MEAN_ABS_MOVE_BPS[horizon],
            pre_registered_bar=bar,
            n_raw_signalled=signalled,
            horizon_hours=horizon,
            n_instruments=3,
            hit_rho_bar=hit_correlation(rho),
            serial_retention=serial,
        )

    def test_camp01_was_underpowered(self):
        v = self._camp(24, 126)
        self.assertIn("UNDERPOWERED", v.label)
        self.assertGreater(v.mde, 0.55)

    def test_camp08_was_powered_but_uneconomic(self):
        v = self._camp(1, 3678, return_rho=0.731, serial=0.654)
        self.assertLessEqual(v.mde, 0.55)          # the only powered campaign
        self.assertGreater(v.breakeven, 0.55)      # and its bar was below breakeven
        self.assertIn("UNECONOMIC", v.label)

    def test_camp07_t025_is_the_marginal_case_and_flips_one_sided(self):
        two = self._camp(72, 1035)
        one = assess(mean_abs_move_bps=MEAN_ABS_MOVE_BPS[72],
                     pre_registered_bar=0.55, n_raw_signalled=1035,
                     horizon_hours=72, n_instruments=3,
                     hit_rho_bar=hit_correlation(0.296), two_sided=False)
        self.assertGreater(two.mde, 0.55)
        self.assertLess(one.mde, 0.55)

    def test_no_closed_campaign_was_both_economic_and_powered(self):
        configs = [
            (24, 126, None, 1.0), (24, 167, None, 1.0), (24, 141, None, 1.0),
            (24, 280, None, 1.0), (24, 461, None, 1.0), (24, 354, None, 1.0),
            (24, 450, None, 1.0), (24, 390, None, 1.0), (24, 106, 0.818, 1.0),
            (72, 572, None, 1.0), (72, 1035, None, 1.0), (120, 333, None, 1.0),
            (1, 3678, 0.731, 0.654),
        ]
        for horizon, signalled, rho, serial in configs:
            with self.subTest(horizon=horizon, signalled=signalled):
                self.assertFalse(self._camp(horizon, signalled, rho, serial).viable)

    def test_every_closed_campaign_also_failed_the_tax_gate(self):
        """The 0.55 bar sat below the after-tax threshold everywhere."""
        for horizon in (1, 24, 72, 120):
            with self.subTest(horizon=horizon):
                v = self._camp(horizon, 5000)
                self.assertIn("TAX-DESTROYED", v.label)

    def test_a_one_hour_horizon_needs_maker_fills_to_be_tradeable_at_all(self):
        taker = assess(mean_abs_move_bps=MEAN_ABS_MOVE_BPS[1],
                       pre_registered_bar=0.55, n_raw_signalled=10_000,
                       horizon_hours=1)
        maker = assess(mean_abs_move_bps=MEAN_ABS_MOVE_BPS[1],
                       pre_registered_bar=0.55, n_raw_signalled=10_000,
                       horizon_hours=1, entry_is_maker=True, exit_is_maker=True)
        self.assertGreater(taker.breakeven, 0.55)
        self.assertLess(maker.breakeven, 0.55)

    def test_all_three_failures_are_reported_together(self):
        v = assess(mean_abs_move_bps=MEAN_ABS_MOVE_BPS[1],
                   pre_registered_bar=0.55, n_raw_signalled=50,
                   horizon_hours=1, n_instruments=3,
                   hit_rho_bar=hit_correlation(0.8753))
        self.assertEqual(v.label, "UNECONOMIC+UNDERPOWERED+TAX-DESTROYED")
        self.assertEqual(len(v.reasons), 3)


class TestCrossSectionalConfiguration(unittest.TestCase):
    """The measured 30-symbol market-neutral panel, with corrected N_eff."""

    def _xs(self, bar, win_loss_ratio=1.0):
        return assess(
            mean_abs_move_bps=XS_RESIDUAL_MOVE_BPS,
            pre_registered_bar=bar,
            n_raw_signalled=XS_PANEL_RAW,
            horizon_hours=24,
            n_instruments=30,
            independent_series=XS_INDEPENDENT_SERIES,
            win_loss_ratio=win_loss_ratio,
            funding_bps_per_day=0.0,      # market-neutral: legs cancel
        )

    def test_panel_n_eff_is_about_8460_not_11790(self):
        v = self._xs(0.62)
        self.assertAlmostEqual(v.n_eff, 8459.8, places=0)

    def test_symmetric_design_fails_the_tax_gate_even_at_the_055_bar(self):
        v = self._xs(0.55)
        self.assertIn("TAX-DESTROYED", v.label)

    def test_symmetric_design_needs_an_implausible_hit_rate(self):
        v = self._xs(0.62)
        self.assertGreater(v.tax_bar, 0.61)
        self.assertLess(v.mde, 0.52)      # power is not the constraint

    def test_asymmetric_design_is_the_only_viable_shape(self):
        v = self._xs(0.55, win_loss_ratio=2.0)
        self.assertTrue(v.viable, msg=str(v))


if __name__ == "__main__":
    unittest.main()
