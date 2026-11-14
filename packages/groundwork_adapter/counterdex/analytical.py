"""Bounded exact enclosures for the declared two-rate analytic template.

For rational 0 <= u <= 1, the alternating Taylor series for exp(-u) has
nonincreasing term magnitudes and remainder of the next term's sign. Thus
S33 <= exp(-u) <= S32, where Sn = sum((-u)**j / j!, j=0..n).
Rational floor/ceiling to a 2**-128 lattice preserve these inequalities.
For z = 2**k * u, repeated squaring preserves enclosure on nonnegative
intervals; each step rounds outward again. Replacing a negative lower bound
by zero is valid because exp is positive. No floating-point value enters.

These are a new, fixed analytic-template calculation. They neither parse nor
check general ODE/polynomial evidence. The policy fixes degree, lattice and
resource limits; a difficult input cannot trigger hidden adaptive refinement.
"""

from fractions import Fraction

from .errors import AdapterError


EXP_POLICY = "alternating32-dyadic128.v1"
MAX_ARGUMENT_BITS = 256
MAX_ARGUMENT = Fraction(1024)
MAX_REDUCTIONS = 10
TAYLOR_EVEN_DEGREE = 32
DYADIC_BITS = 128
_LATTICE = 1 << DYADIC_BITS


def _bounded_fraction(value: object, field: str) -> Fraction:
    if type(value) is not Fraction:
        raise AdapterError("invalid_input", "An exact Fraction is required.", (field,))
    if max(value.numerator.bit_length(), value.denominator.bit_length()) > MAX_ARGUMENT_BITS:
        raise AdapterError(
            "construction_range", "Exact analytic input exceeds the fixed arithmetic limit.", (field,)
        )
    return value


def _round_down(value: Fraction) -> Fraction:
    return Fraction((value.numerator * _LATTICE) // value.denominator, _LATTICE)


def _round_up(value: Fraction) -> Fraction:
    scaled = value.numerator * _LATTICE
    return Fraction(-((-scaled) // value.denominator), _LATTICE)


def exp_neg_interval(z: Fraction) -> tuple[Fraction, Fraction]:
    """Enclose exp(-z), with 0 <= z <= 1024, using the fixed named policy.

    Each argument numerator and denominator may have at most 256 bits.
    Returned endpoints are rational dyadics whose denominators divide 2**128.
    At large z the interval may have a zero lower endpoint; no relative-error
    guarantee or zero-error trajectory claim follows from a narrow interval.
    """
    z = _bounded_fraction(z, "argument")
    if z < 0:
        raise AdapterError("invalid_input", "The exponential argument must be nonnegative.", ("argument",))
    if z > MAX_ARGUMENT:
        raise AdapterError(
            "construction_range", "The exponential argument exceeds the fixed analytic range.", ("argument",)
        )
    if z == 0:
        return Fraction(1), Fraction(1)

    reduced = z
    reductions = 0
    for _ in range(MAX_REDUCTIONS):
        if reduced <= 1:
            break
        reduced /= 2
        reductions += 1
    if reduced > 1:
        raise AdapterError(
            "construction_range", "The fixed range-reduction budget is insufficient.", ("argument",)
        )

    term = Fraction(1)
    total = Fraction(1)
    for degree in range(1, TAYLOR_EVEN_DEGREE + 1):
        term *= -reduced / degree
        total += term
    upper = _round_up(total)
    next_term = term * -reduced / (TAYLOR_EVEN_DEGREE + 1)
    lower = max(Fraction(0), _round_down(total + next_term))

    for _ in range(reductions):
        lower = max(Fraction(0), _round_down(lower * lower))
        upper = _round_up(upper * upper)
    return lower, upper


def concentration_interval(
    A: Fraction, ke: Fraction, ka: Fraction, t: Fraction
) -> tuple[Fraction, Fraction]:
    """Enclose A*(exp(-ke*t)-exp(-ka*t)) for the fixed analytic template.

    Requires A > 0, 0 < ke < ka, t >= 0 and bounded rational inputs. Each
    rate*time product must also satisfy exp_neg_interval's admission policy.
    Subtracting intervals and positive exact scaling are sound even if the
    conservative lower concentration bound is negative.
    """
    A = _bounded_fraction(A, "parameters/A")
    ke = _bounded_fraction(ke, "parameters/ke")
    ka = _bounded_fraction(ka, "parameters/ka")
    t = _bounded_fraction(t, "time")
    if A <= 0 or not 0 < ke < ka:
        raise AdapterError(
            "invalid_input", "The analytic template requires A > 0 and 0 < ke < ka.", ("parameters",)
        )
    if t < 0:
        raise AdapterError("invalid_input", "Time must be nonnegative.", ("time",))
    slow_lower, slow_upper = exp_neg_interval(ke * t)
    fast_lower, fast_upper = exp_neg_interval(ka * t)
    return A * (slow_lower - fast_upper), A * (slow_upper - fast_lower)
