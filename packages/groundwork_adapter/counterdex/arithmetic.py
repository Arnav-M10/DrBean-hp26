"""Elementary exact fixed-pair arithmetic, without a scientific proof claim.

These helpers do not check candidates, historical compatibility, continuation,
observable bounds, or artifact identities. ``separated`` describes only the
supplied intervals. It must never be used alone to publish checked separation.
"""

from dataclasses import dataclass
from fractions import Fraction
from typing import ClassVar, Iterable


Band = tuple[Fraction, Fraction]


def _fraction(value: object, name: str) -> Fraction:
    if not isinstance(value, Fraction):
        raise TypeError(f"{name} must be a Fraction")
    return value


def _inputs(
    p1: Fraction, p2: Fraction, e1: Fraction, e2: Fraction, eta: Fraction
) -> None:
    for name, value in (("p1", p1), ("p2", p2), ("e1", e1), ("e2", e2), ("eta", eta)):
        _fraction(value, name)
    if e1 < 0 or e2 < 0:
        raise ValueError("enclosure errors must be nonnegative")
    if eta <= 0:
        raise ValueError("future allowance must be positive")


@dataclass(frozen=True)
class ArithmeticSeparation:
    """Computed interval arithmetic only; not a compatibility certificate."""

    bands: tuple[Band, Band]
    gap: Fraction
    raw_score: Fraction
    margin: Fraction
    separated: bool
    evidence_scope: ClassVar[str] = "elementary_arithmetic_only"


def possible_data_bands(
    p1: Fraction, p2: Fraction, e1: Fraction, e2: Fraction, eta: Fraction
) -> tuple[Band, Band]:
    """Return closed intervals around supplied centers with errors plus allowance.

    This computation makes no claim that the supplied centers or errors bound
    any actual model trajectory.
    """
    _inputs(p1, p2, e1, e2, eta)
    return ((p1 - e1 - eta, p1 + e1 + eta), (p2 - e2 - eta, p2 + e2 + eta))


def pair_margin(
    p1: Fraction, p2: Fraction, e1: Fraction, e2: Fraction, eta: Fraction
) -> ArithmeticSeparation:
    """Calculate strict disjointness of supplied possible-data intervals.

    A zero margin means touching closed bands and does not separate. Positive
    margin is an elementary arithmetic fact about the supplied bounds, not an
    exact checker verdict about either candidate or the historical problem.
    """
    bands = possible_data_bands(p1, p2, e1, e2, eta)
    gap = abs(p1 - p2)
    margin = gap - e1 - e2 - 2 * eta
    return ArithmeticSeparation(bands, gap, gap / eta, margin, margin > 0)


@dataclass(frozen=True)
class MarginOption:
    """A named arithmetic control at an exact time; no verified model binding."""

    time: Fraction
    candidate_ids: tuple[str, str]
    arithmetic: ArithmeticSeparation

    def __post_init__(self) -> None:
        _fraction(self.time, "time")
        if self.time < 0:
            raise ValueError("time must be nonnegative")
        if (
            not isinstance(self.candidate_ids, tuple)
            or len(self.candidate_ids) != 2
            or any(not isinstance(item, str) or not item for item in self.candidate_ids)
            or self.candidate_ids[0] == self.candidate_ids[1]
        ):
            raise ValueError("candidate_ids must be two distinct nonempty strings in a tuple")
        if not isinstance(self.arithmetic, ArithmeticSeparation):
            raise TypeError("arithmetic must be an ArithmeticSeparation")


def rank_margins(options: Iterable[MarginOption]) -> tuple[MarginOption, ...]:
    """Positive margins first, then larger margin, earlier time, stable IDs.

    This ordering is a control for the proposed selection rule. It confers no
    scientific evidence class on the options. Raw score does not control it.
    """
    rows = tuple(options)
    if any(not isinstance(row, MarginOption) for row in rows):
        raise TypeError("options must contain only MarginOption values")
    return tuple(sorted(rows, key=lambda row: (
        row.arithmetic.margin <= 0,
        -row.arithmetic.margin,
        row.time,
        row.candidate_ids,
    )))


def select_positive(options: Iterable[MarginOption]) -> MarginOption | None:
    """Select the first positive arithmetic margin, or no option."""
    ranked = rank_margins(options)
    return ranked[0] if ranked and ranked[0].arithmetic.margin > 0 else None
