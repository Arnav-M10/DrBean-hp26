"""Oracle: elementary interval arithmetic, never an ODE certificate fixture."""

from dataclasses import FrozenInstanceError
from fractions import Fraction as Q
import unittest

from counterdex.arithmetic import (
    ArithmeticSeparation, MarginOption, pair_margin, possible_data_bands,
    rank_margins, select_positive,
)


class ArithmeticControls(unittest.TestCase):
    def test_constructed_bands_and_actual_readings(self):
        result = pair_margin(Q(5), Q(7), Q(0), Q(0), Q(1, 5))
        self.assertEqual(result.bands, ((Q(24, 5), Q(26, 5)), (Q(34, 5), Q(36, 5))))
        self.assertEqual(result.gap, Q(2))
        self.assertEqual(result.raw_score, Q(10))
        self.assertEqual(result.margin, Q(8, 5))
        self.assertTrue(result.separated)
        first, second = result.bands
        self.assertTrue(first[0] <= 5 <= first[1])
        self.assertFalse(second[0] <= 5 <= second[1])
        self.assertFalse(first[0] <= 7 <= first[1])
        self.assertTrue(second[0] <= 7 <= second[1])
        self.assertFalse(first[0] <= 6 <= first[1])
        self.assertFalse(second[0] <= 6 <= second[1])

    def test_touching_closed_bands_do_not_separate(self):
        result = pair_margin(Q(5), Q(7), Q(1, 2), Q(1, 2), Q(1, 2))
        self.assertEqual(result.bands, ((Q(4), Q(6)), (Q(6), Q(8))))
        self.assertEqual(result.margin, Q(0))
        self.assertFalse(result.separated)
        self.assertEqual(result.bands[0][1], result.bands[1][0])

    def test_strict_boundary_one_rational_step_away(self):
        step = Q(1, 10**30)
        at = pair_margin(Q(0), Q(2), Q(0), Q(0), Q(1))
        above = pair_margin(Q(0), Q(2) + step, Q(0), Q(0), Q(1))
        below = pair_margin(Q(0), Q(2) - step, Q(0), Q(0), Q(1))
        self.assertFalse(at.separated)
        self.assertTrue(above.separated)
        self.assertFalse(below.separated)
        self.assertEqual(above.margin, step)
        self.assertEqual(below.margin, -step)

    def test_smaller_raw_score_can_have_the_best_positive_margin(self):
        weak = pair_margin(Q(0), Q(1, 2), Q(1, 5), Q(1, 5), Q(1, 10))
        separating = pair_margin(Q(0), Q(1, 4), Q(0), Q(0), Q(1, 10))
        self.assertEqual((weak.raw_score, weak.margin), (Q(5), Q(-1, 10)))
        self.assertEqual((separating.raw_score, separating.margin), (Q(5, 2), Q(1, 20)))
        weak_option = MarginOption(Q(1), ("a", "b"), weak)
        strong_option = MarginOption(Q(2), ("a", "b"), separating)
        self.assertEqual(rank_margins([weak_option, strong_option]), (strong_option, weak_option))
        self.assertEqual(select_positive([weak_option, strong_option]), strong_option)
        self.assertIsNone(select_positive([weak_option]))
        self.assertIsNone(select_positive([]))

    def test_time_then_ids_break_exact_margin_ties(self):
        arithmetic = pair_margin(Q(1), Q(3), Q(0), Q(0), Q(1, 5))
        late = MarginOption(Q(2), ("a", "b"), arithmetic)
        early_b = MarginOption(Q(1), ("b", "c"), arithmetic)
        early_a = MarginOption(Q(1), ("a", "c"), arithmetic)
        self.assertEqual(rank_margins([late, early_b, early_a]), (early_a, early_b, late))

    def test_candidate_permutation_moves_its_error_and_band(self):
        forward = pair_margin(Q(2), Q(6), Q(1, 4), Q(1, 3), Q(1, 5))
        reverse = pair_margin(Q(6), Q(2), Q(1, 3), Q(1, 4), Q(1, 5))
        self.assertEqual(reverse.bands, forward.bands[::-1])
        self.assertEqual(reverse.margin, forward.margin)
        self.assertEqual(reverse.raw_score, forward.raw_score)
        self.assertEqual(reverse.separated, forward.separated)

    def test_larger_allowance_only_weakens_fixed_bounds(self):
        small = pair_margin(Q(1), Q(2), Q(1, 10), Q(1, 10), Q(1, 10))
        large = pair_margin(Q(1), Q(2), Q(1, 10), Q(1, 10), Q(2, 5))
        self.assertEqual(small.margin - large.margin, Q(3, 5))
        self.assertTrue(small.separated)
        self.assertFalse(large.separated)
        self.assertGreater(small.raw_score, large.raw_score)
        for narrow, wide in zip(small.bands, large.bands):
            self.assertLessEqual(wide[0], narrow[0])
            self.assertGreaterEqual(wide[1], narrow[1])

    def test_helpers_require_fraction_inputs(self):
        for helper in (pair_margin, possible_data_bands):
            for position in range(5):
                for value in (0, 0.0, True, "0/1", None):
                    args = [Q(0), Q(2), Q(0), Q(0), Q(1)]
                    args[position] = value
                    with self.subTest(helper=helper.__name__, position=position, value=value):
                        with self.assertRaises(TypeError):
                            helper(*args)

    def test_negative_errors_and_nonpositive_allowance_rejected(self):
        for args in (
            (Q(0), Q(2), Q(-1), Q(0), Q(1)),
            (Q(0), Q(2), Q(0), Q(-1), Q(1)),
            (Q(0), Q(2), Q(0), Q(0), Q(0)),
            (Q(0), Q(2), Q(0), Q(0), Q(-1)),
        ):
            for helper in (pair_margin, possible_data_bands):
                with self.assertRaises(ValueError):
                    helper(*args)

    def test_reports_are_immutable_arithmetic_only(self):
        result = pair_margin(Q(0), Q(3), Q(0), Q(0), Q(1))
        self.assertIsInstance(result, ArithmeticSeparation)
        self.assertEqual(result.evidence_scope, "elementary_arithmetic_only")
        with self.assertRaises(FrozenInstanceError):
            result.separated = False

    def test_invalid_ranking_options_rejected(self):
        arithmetic = pair_margin(Q(0), Q(3), Q(0), Q(0), Q(1))
        for time in (1, 1.0, "1/1", True):
            with self.assertRaises(TypeError):
                MarginOption(time, ("a", "b"), arithmetic)
        with self.assertRaises(ValueError):
            MarginOption(Q(-1), ("a", "b"), arithmetic)
        for ids in (("a", "a"), ("a", ""), ("a",), ["a", "b"], (1, "b")):
            with self.assertRaises(ValueError):
                MarginOption(Q(1), ids, arithmetic)
        with self.assertRaises(TypeError):
            rank_margins([arithmetic])


if __name__ == "__main__":
    unittest.main()
