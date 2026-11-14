"""Finite numerical candidate production for the fixed two-rate model.

This module never certifies compatibility or an interval claim. Every proposed
vector is frozen as exact rationals for a separate historical checker. The
finite grid, rounding, ordering and stop conditions are visible in the report;
there is no retry, refinement, random seed or demonstration-vector lookup.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
import math
import sys
import time

from .errors import AdapterError
from .exact import artifact_digest, canonical_bytes, rational_text
from .models import (
    FixedCandidate, HistoricalProblem, _check_problem_object, counter, fields,
    normalize_problem,
)
from .resource import ExecutionContext

SEARCH_POLICY = "rate-grid-amplitude-midpoint-12sig.v1"
SEARCH_PROFILE = "groundwork.baseline-search.v1"
SEARCH_EVALUATOR = "two-rate-expm1-binary64.v1"
_MIN_NORMAL = sys.float_info.min


@dataclass(frozen=True)
class SearchSettings:
    """Explicit reviewed caps, never increased by the producer."""

    ke_points: int = 128
    ka_points: int = 128
    max_rate_pairs: int = 16384
    max_candidates: int = 32
    wall_seconds: int = 120

    def to_payload(self) -> dict:
        return {"policy": SEARCH_POLICY, "ke_points": self.ke_points,
                "ka_points": self.ka_points, "max_rate_pairs": self.max_rate_pairs,
                "max_candidates": self.max_candidates, "wall_seconds": self.wall_seconds}


def normalize_search_settings(payload: dict) -> SearchSettings:
    if type(payload) is dict and not payload:
        return SearchSettings()
    p = fields(payload, {"policy", "ke_points", "ka_points", "max_rate_pairs",
                         "max_candidates", "wall_seconds"}, "search")
    if p["policy"] != SEARCH_POLICY:
        raise AdapterError("invalid_input", "Unsupported finite search policy.", ("search/policy",))
    limits = {"ke_points": (2, 128), "ka_points": (2, 128), "max_rate_pairs": (1, 16384),
              "max_candidates": (1, 32), "wall_seconds": (1, 120)}
    return SearchSettings(**{name: counter(p[name], "search/" + name, *bounds)
                             for name, bounds in limits.items()})


@dataclass(frozen=True)
class SearchResult:
    candidates: tuple[FixedCandidate, ...]
    report: dict


@dataclass(frozen=True)
class _Proposal:
    candidate: FixedCandidate
    outside: bool
    ke_index: int
    ka_index: int
    amplitude_interval: tuple[float, float]
    maximum_residual: float
    ranking_score: str
    residuals: tuple[float | None, ...]

    @property
    def rank_key(self) -> tuple:
        # The displayed 12-significant-digit value is the ranking value.
        return Decimal(self.ranking_score), self.ke_index, self.ka_index

    def to_payload(self) -> dict:
        return {"candidate": self.candidate.to_payload(),
                "claim_position": "outside" if self.outside else "inside",
                "grid_index": {"ke": self.ke_index, "ka": self.ka_index},
                "amplitude_interval_approximation": [repr(x) for x in self.amplitude_interval],
                "maximum_normalized_residual_approximation": repr(self.maximum_residual),
                "ranking_score": self.ranking_score,
                "residual_approximations": [None if x is None else repr(x) for x in self.residuals]}


def _range_error() -> AdapterError:
    return AdapterError("numerical_range_limitation",
                        "This search evaluation exceeds the admitted binary64 range.", ("search",))


def _finite(value: Fraction) -> float:
    try:
        result = float(value)
    except (OverflowError, ValueError):
        raise _range_error() from None
    if not math.isfinite(result) or (value != 0 and result == 0):
        raise _range_error()
    return result


def _basis(ke: Fraction, ka: Fraction, t: Fraction) -> float:
    if t == 0:
        return 0.0
    # Form the small rate difference exactly before converting to binary64.
    tail = math.exp(-_finite(ke * t))
    rise = -math.expm1(-_finite((ka - ke) * t))
    result = tail * rise
    if tail < _MIN_NORMAL or rise < _MIN_NORMAL or result < _MIN_NORMAL:
        raise _range_error()
    return result


def _rounded(value: float) -> str:
    with localcontext(Context(prec=12, rounding=ROUND_HALF_EVEN)):
        return str(+Decimal.from_float(value))


def _grid(bounds: tuple[Fraction, Fraction], points: int) -> tuple[Fraction, ...]:
    lo, hi = bounds
    return tuple(lo + (hi - lo) * i / (points - 1) for i in range(points))


def _screen(problem: HistoricalProblem, digest: str, ke: Fraction, ka: Fraction,
            ke_index: int, ka_index: int) -> _Proposal | None:
    lo, hi = (_finite(x) for x in problem.domain[0])
    bases: list[float | None] = []
    for row in problem.observations:
        if not row.included:
            bases.append(None)
            continue
        basis = _basis(ke, ka, row.time)
        bases.append(basis)
        if row.time == 0:
            # c(0)=0 exactly; no division by an artificial near-zero value.
            if abs(row.value) > row.allowance:
                return None
            continue
        lower = _finite(row.value - row.allowance) / basis
        upper = _finite(row.value + row.allowance) / basis
        if not math.isfinite(lower) or not math.isfinite(upper):
            raise _range_error()
        lo, hi = max(lo, lower), min(hi, upper)
        if lo > hi:
            return None
    # Avoid overflowing lo+hi. Clamping is to the exact reviewed amplitude
    # domain, not a claim that numerical feasibility endpoints are exact.
    amplitude = Fraction(_rounded(lo / 2 + hi / 2))
    amplitude = max(problem.domain[0][0], min(problem.domain[0][1], amplitude))
    frozen_amplitude = _finite(amplitude)
    residuals = []
    maximum_residual = 0.0
    for row, basis in zip(problem.observations, bases):
        if basis is None:
            residuals.append(None)
            continue
        prediction = frozen_amplitude * basis
        residual = prediction - _finite(row.value)
        normalized = abs(residual) / _finite(row.allowance)
        if (not math.isfinite(prediction) or not math.isfinite(residual) or not math.isfinite(normalized)
                or (row.time != 0 and prediction < _MIN_NORMAL)):
            raise _range_error()
        residuals.append(residual)
        maximum_residual = max(maximum_residual, normalized)
    parameters = (amplitude, ke, ka)
    vector_digest = artifact_digest(canonical_bytes(
        {"problem_digest": digest, "parameters": [rational_text(x) for x in parameters]}))
    candidate = FixedCandidate("search-" + vector_digest[:24], digest, parameters, None)
    return _Proposal(candidate, candidate.is_outside(problem), ke_index, ka_index, (lo, hi),
                     maximum_residual, _rounded(maximum_residual), tuple(residuals))


def _retain(pool: list[_Proposal], proposal: _Proposal, cap: int) -> None:
    pool.append(proposal)
    pool.sort(key=lambda item: item.rank_key)
    if len(pool) > cap:
        pool.pop()


def _interleave(inside: list[_Proposal], outside: list[_Proposal], cap: int) -> list[_Proposal]:
    # One available slot prioritizes an outside proposal for exact checking.
    if cap == 1:
        return (outside or inside)[:1]
    selected = []
    for index in range(max(len(inside), len(outside))):
        for pool in (inside, outside):
            if index < len(pool):
                selected.append(pool[index])
                if len(selected) == cap:
                    return selected
    return selected


def search_candidates(problem: HistoricalProblem, *, settings: SearchSettings | None = None,
                      context: ExecutionContext | None = None) -> SearchResult:
    """Screen a disclosed finite rate grid and return unverified exact vectors.

    Grid pairs are visited in ascending ke, then ascending ka order, including
    each reviewed domain endpoint. Feasible amplitudes use a rounded midpoint.
    Each class is ranked by maximum absolute residual / row-specific allowance,
    rounded to 12 significant decimal digits (half even); grid indices break ties.
    Retained vectors alternate inside then outside the closed claim. A smaller
    pair cap truncates that same grid; it never changes its spacing or retries.

    The caller must freshly check these frozen vectors before asserting any
    compatibility, counterexample or useful pair. An empty list is only a
    bounded numerical search result. Hard process supervision belongs to the
    bridge; this producer cooperatively checks before every rate-pair attempt.
    """
    started = time.monotonic()
    _check_problem_object(problem)
    problem = normalize_problem(problem.to_payload())
    if settings is None:
        settings = SearchSettings()
    if type(settings) is not SearchSettings:
        raise AdapterError("invalid_input", "Expected explicit finite search settings.", ("search",))
    settings = normalize_search_settings(settings.to_payload())
    if context is None:
        context = ExecutionContext(wall_seconds=settings.wall_seconds)
    if not isinstance(context, ExecutionContext):
        raise AdapterError("invalid_input", "Expected a bounded execution context.", ("context",))

    digest = problem.digest
    inside: list[_Proposal] = []
    outside: list[_Proposal] = []
    attempted = evaluated = feasible = 0
    failures = {"amplitude_infeasible": 0, "numerical_range_limitation": 0}
    stopped = None
    ke_grid = _grid(problem.domain[1], settings.ke_points)
    ka_grid = _grid(problem.domain[2], settings.ka_points)
    possible = len(ke_grid) * len(ka_grid)
    for ke_index, ke in enumerate(ke_grid):
        for ka_index, ka in enumerate(ka_grid):
            stopped = context.stop_reason(settings.wall_seconds)
            if stopped is not None:
                break
            if attempted >= settings.max_rate_pairs:
                stopped = "rate_pair_cap"
                break
            attempted += 1
            try:
                proposal = _screen(problem, digest, ke, ka, ke_index, ka_index)
            except (AdapterError, OverflowError, ZeroDivisionError):
                failures["numerical_range_limitation"] += 1
                continue
            evaluated += 1
            if proposal is None:
                failures["amplitude_infeasible"] += 1
            else:
                feasible += 1
                _retain(outside if proposal.outside else inside, proposal, settings.max_candidates)
        if stopped is not None:
            break
    selected = _interleave(inside, outside, settings.max_candidates)
    report = {"schema_version": SEARCH_PROFILE, "policy": SEARCH_POLICY,
              "evaluator_id": SEARCH_EVALUATOR, "problem_digest": digest,
              "settings": settings.to_payload(),
              "grid_order": "ascending-ke-then-ascending-ka-inclusive-endpoints",
              "amplitude_rule": "feasible-interval-midpoint-12sig-half-even-clamped-to-reviewed-domain",
              "retention_rule": "12sig-maximum-normalized-residual-then-grid-index-inside-outside-alternation",
              "execution": "cancelled" if stopped == "cancelled" else "interrupted" if stopped else "completed",
              "reason_code": stopped,
              "partial": attempted < possible or failures["numerical_range_limitation"] > 0,
              "outcome": "numerical_candidates" if selected else "no_numerical_candidate_found",
              "attempted_count": attempted, "evaluated_count": evaluated,
              "feasible_count": feasible, "retained_count": len(selected), "possible_count": possible,
              "failure_counts": failures, "elapsed_seconds": repr(max(0.0, time.monotonic() - started)),
              "observation_ids": [row.id for row in problem.observations],
              "included": [row.included for row in problem.observations],
              "candidates": [proposal.to_payload() for proposal in selected]}
    return SearchResult(tuple(proposal.candidate for proposal in selected), report)
