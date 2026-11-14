"""Elementary exact oracles for fixed-pair margins (work order section 6).

These are constructed arithmetic controls. They are not kinetic results and
not a newly admitted product model. Owner 01 reviews scientific expectations.
"""
from __future__ import annotations

from fractions import Fraction as F


def margin(delta: F, eta: F, e1: F = F(0), e2: F = F(0)) -> F:
    """M = Delta - e1 - e2 - 2*eta."""
    if eta <= 0:
        raise ValueError("future hard allowance eta must be positive")
    if e1 < 0 or e2 < 0 or delta < 0:
        raise ValueError("delta and checked errors must be nonnegative")
    return delta - e1 - e2 - 2 * eta


def establishes_separation(m: F) -> bool:
    """Strict: equality fails because closed observation bands touch."""
    return m > 0


def select_checked(options):
    """Recorded margin policy for checked feasible options.

    options: iterable of dicts with exact 'margin' (Fraction), 'time' (Fraction)
    and 'candidate_ids' (tuple of str). Positive margins only; then larger
    margin, then earlier time, then stable candidate ids. Raw score plays no
    part. Returns the selected option or None.
    """
    positive = [option for option in options if establishes_separation(option["margin"])]
    if not positive:
        return None
    return sorted(positive, key=lambda o: (-o["margin"], o["time"], tuple(o["candidate_ids"])))[0]


def raw_score(delta: F, eta: F) -> F:
    """The baseline helper's Delta/eta. A ranking heuristic, never proof."""
    return delta / eta


# Constructed oracle: u' = a, u(0) = 0, a in [0, 1]; u(t) = a*t exactly.
def constructed_center(a: F, t: F) -> F:
    return a * t


def constructed_margin(t: F, eta: F = F(1, 10)) -> F:
    """Candidates a=0 and a=1 with zero enclosure error."""
    return margin(abs(constructed_center(F(1), t) - constructed_center(F(0), t)), eta)


def compatible(center: F, datum: F, allowance: F) -> bool:
    """Closed band: |center - datum| <= allowance."""
    return abs(center - datum) <= allowance
