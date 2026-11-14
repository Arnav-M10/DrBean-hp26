"""Exact arithmetic controls plus independent high-precision Decimal diagnostics.

Decimal agreement checks implementation behavior; the interval argument in the
module/docs supplies soundness. Decimal agreement is not a proof certificate.
"""

from decimal import Decimal, localcontext
from fractions import Fraction as Q
import unittest

from counterdex.analytical import (
    DYADIC_BITS, EXP_POLICY, concentration_interval, exp_neg_interval,
)
from counterdex.errors import AdapterError


def decimal_fraction(value: Q) -> Decimal:
    return Decimal(value.numerator) / Decimal(value.denominator)


class AnalyticalControls(unittest.TestCase):
    def test_exact_zero_argument(self):
        self.assertEqual(exp_neg_interval(Q(0)), (Q(1), Q(1)))

    def test_independent_decimal_diagnostics_across_range(self):
        values = (Q(1, 2**255), Q(1, 10), Q(1, 2), Q(1), Q(2), Q(3), Q(7),
                  Q(32), Q(128), Q(1024))
        with localcontext() as context:
            context.prec = 180
            for argument in values:
                with self.subTest(argument=argument):
                    lower, upper = exp_neg_interval(argument)
                    diagnostic = (-decimal_fraction(argument)).exp()
                    self.assertLessEqual(decimal_fraction(lower), diagnostic)
                    self.assertGreaterEqual(decimal_fraction(upper), diagnostic)
                    self.assertLessEqual(lower, upper)
                    self.assertGreaterEqual(lower, 0)
                    self.assertLessEqual(upper, 1)
                    self.assertLess(decimal_fraction(upper - lower), Decimal("1e-34"))

    def test_no_underflow_masquerades_as_zero_error(self):
        lower, upper = exp_neg_interval(Q(1024))
        self.assertEqual(lower, Q(0))
        self.assertGreater(upper, Q(0))
        self.assertLessEqual(upper, Q(1, 2**DYADIC_BITS))

    def test_deterministic_exact_dyadic_bounds(self):
        self.assertEqual(EXP_POLICY, "alternating32-dyadic128.v1")
        for argument in (Q(1, 3), Q(1), Q(33, 4), Q(1024)):
            first = exp_neg_interval(argument)
            self.assertEqual(first, exp_neg_interval(argument))
            for endpoint in first:
                self.assertIs(type(endpoint), Q)
                self.assertEqual((1 << DYADIC_BITS) % endpoint.denominator, 0)
                self.assertLessEqual(endpoint.denominator.bit_length(), DYADIC_BITS + 1)

    def test_range_and_arithmetic_limits_are_typed(self):
        for argument in (Q(1024) + Q(1, 2**200), Q(1025), Q(2**256), Q(1, 2**256)):
            with self.subTest(argument=argument):
                with self.assertRaises(AdapterError) as caught:
                    exp_neg_interval(argument)
                self.assertEqual(caught.exception.code, "construction_range")
        self.assertEqual(len(exp_neg_interval(Q(1, 2**255))), 2)

    def test_exp_rejects_wrong_types_and_negative_arguments(self):
        for argument in (0, 0.0, True, "0/1", None, Q(-1)):
            with self.subTest(argument=argument):
                with self.assertRaises(AdapterError) as caught:
                    exp_neg_interval(argument)
                self.assertEqual(caught.exception.code, "invalid_input")

    def test_concentration_independent_decimal_diagnostics(self):
        A, ke, ka = Q(13, 2), Q(1, 5), Q(3, 2)
        with localcontext() as context:
            context.prec = 180
            for time in (Q(0), Q(1, 10), Q(1), Q(8), Q(100)):
                with self.subTest(time=time):
                    lower, upper = concentration_interval(A, ke, ka, time)
                    diagnostic = decimal_fraction(A) * (
                        (-decimal_fraction(ke * time)).exp() - (-decimal_fraction(ka * time)).exp()
                    )
                    self.assertLessEqual(decimal_fraction(lower), diagnostic)
                    self.assertGreaterEqual(decimal_fraction(upper), diagnostic)
                    self.assertLessEqual(lower, upper)
                    self.assertLess(decimal_fraction(upper - lower), Decimal("1e-32"))

    def test_close_rates_preserve_conservative_negative_lower_bound(self):
        A, ke, ka, time = Q(5), Q(1, 5), Q(1, 5) + Q(1, 10**40), Q(7)
        lower, upper = concentration_interval(A, ke, ka, time)
        self.assertLess(lower, 0)
        self.assertGreater(upper, 0)
        with localcontext() as context:
            context.prec = 180
            diagnostic = decimal_fraction(A) * (
                (-decimal_fraction(ke * time)).exp() - (-decimal_fraction(ka * time)).exp()
            )
            self.assertGreater(diagnostic, 0)
            self.assertLessEqual(decimal_fraction(lower), diagnostic)
            self.assertGreaterEqual(decimal_fraction(upper), diagnostic)

    def test_analytic_initial_conditions(self):
        self.assertEqual(exp_neg_interval(Q(0)), (Q(1), Q(1)))
        self.assertEqual(concentration_interval(Q(7), Q(1, 5), Q(3), Q(0)), (Q(0), Q(0)))

    def test_concentration_domain_and_exact_types(self):
        base = [Q(7), Q(1, 5), Q(3), Q(1)]
        for position in range(4):
            invalid = list(base)
            invalid[position] = 1
            with self.assertRaises(AdapterError) as caught:
                concentration_interval(*invalid)
            self.assertEqual(caught.exception.code, "invalid_input")
        for args in ((Q(0), Q(1), Q(2), Q(1)), (Q(1), Q(0), Q(2), Q(1)),
                     (Q(1), Q(2), Q(2), Q(1)), (Q(1), Q(3), Q(2), Q(1)),
                     (Q(1), Q(1), Q(2), Q(-1))):
            with self.assertRaises(AdapterError) as caught:
                concentration_interval(*args)
            self.assertEqual(caught.exception.code, "invalid_input")

    def test_concentration_rejects_oversized_inputs_and_products(self):
        for args in ((Q(2**256), Q(1), Q(2), Q(1)),
                     (Q(1), Q(1), Q(2), Q(513)),
                     (Q(1), Q(1, 2**200), Q(1, 2**199), Q(1, 2**100))):
            with self.assertRaises(AdapterError) as caught:
                concentration_interval(*args)
            self.assertEqual(caught.exception.code, "construction_range")

    def test_concentration_result_denominators_remain_bounded(self):
        amplitude = Q(1, 2**255 - 19)
        bounds = concentration_interval(amplitude, Q(1, 3), Q(5, 3), Q(2))
        for endpoint in bounds:
            self.assertLessEqual(endpoint.denominator.bit_length(), 256 + DYADIC_BITS)


if __name__ == "__main__":
    unittest.main()
