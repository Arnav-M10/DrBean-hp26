"""Independent high-precision oracle for the two-rate template. Standard library only.

    C(t) = A * (exp(-ke*t) - exp(-ka*t)),   A > 0, 0 < ke < ka, t >= 0

This is the harness's own arithmetic, written separately from Counterdex. It uses
``decimal`` at 80 significant digits, which is far tighter than any band edge the
shared scenarios approach. Anything within ``EDGE`` of a closed band boundary is
reported ``indeterminate`` rather than guessed. It is a test oracle for
expectations (which candidate a reading keeps or excludes); it is NOT a proof
system and never stands in for the project's exact checker or native replay.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
from fractions import Fraction

PRECISION = 80
EDGE = Decimal("1e-30")


def _dec(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, Fraction):
        return Decimal(value.numerator) / Decimal(value.denominator)
    if isinstance(value, str) and "/" in value:
        numerator, denominator = value.split("/")
        return Decimal(int(numerator)) / Decimal(int(denominator))
    if isinstance(value, (int, str)):
        return Decimal(value)
    raise TypeError(f"exact input required, got {type(value).__name__}")


def concentration(vector: dict, t) -> Decimal:
    with localcontext() as context:
        context.prec = PRECISION
        a, ke, ka, time = _dec(vector["A"]), _dec(vector["ke"]), _dec(vector["ka"]), _dec(t)
        if not (a > 0 and 0 < ke < ka and time >= 0):
            raise ValueError("vector outside the admitted template (A > 0, 0 < ke < ka, t >= 0)")
        return a * ((-ke * time).exp() - (-ka * time).exp())


def band_verdict(vector: dict, t, reading, allowance) -> str:
    """'compatible' if |C(t) - reading| <= allowance (closed), 'excluded' if clearly outside."""
    with localcontext() as context:
        context.prec = PRECISION
        gap = abs(concentration(vector, t) - _dec(reading)) - _dec(allowance)
        if abs(gap) <= EDGE:
            return "indeterminate"
        return "compatible" if gap < 0 else "excluded"


def history_verdict(vector: dict, rows: list[dict]) -> str:
    """Every included row within its hard allowance -> 'compatible'; any clear violation -> 'excluded'."""
    verdicts = [band_verdict(vector, row["time"], row["concentration"], row["hard_allowance"])
                for row in rows if row.get("included", True)]
    if "excluded" in verdicts:
        return "excluded"
    return "indeterminate" if "indeterminate" in verdicts else "compatible"


def outside_closed_claim(value, lower, upper) -> bool:
    """Endpoint equality is inside the closed claim."""
    v, lo, hi = Fraction(_frac(value)), Fraction(_frac(lower)), Fraction(_frac(upper))
    return v < lo or v > hi


def separation_margin(pair: list[dict], t, allowance) -> Decimal:
    """Approximate |C1 - C2| - 2*eta (positive means the closed future bands are disjoint)."""
    with localcontext() as context:
        context.prec = PRECISION
        return abs(concentration(pair[0], t) - concentration(pair[1], t)) - 2 * _dec(allowance)


def _frac(value) -> Fraction:
    if isinstance(value, Fraction):
        return value
    text = str(value)
    if "/" in text:
        numerator, denominator = text.split("/")
        return Fraction(int(numerator), int(denominator))
    return Fraction(text)
