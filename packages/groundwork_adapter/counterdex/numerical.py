"""Bounded diagnostic comparison of two fixed vectors over an approved grid.

Transcendental values are binary64 diagnostics, never compatibility evidence.
The stored decimal score defines ranking; exact time only breaks display ties.
"""
from __future__ import annotations

from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
import math
import sys

from .errors import AdapterError
from .resource import ExecutionContext
from .exact import rational_text
from .models import DesignInput, HistoricalProblem, NUMERICAL_POLICY, revalidate_inputs

EVALUATOR_ID = "two-rate-expm1-binary64.v1"
_MIN_NORMAL = sys.float_info.min


def _range_error() -> AdapterError:
    return AdapterError("numerical_range_limitation", "This row exceeds the admitted binary64 numerical range.", ("design/grid",))


def _finite_float(value: Fraction) -> float:
    try:
        result = float(value)
    except (OverflowError, ValueError):
        raise _range_error() from None
    if not math.isfinite(result) or (value != 0 and result == 0):
        raise _range_error()
    return result


def _prediction(parameters: tuple[Fraction, Fraction, Fraction], t: Fraction) -> float:
    if t == 0:
        return 0.0
    a, ke, ka = parameters
    amplitude = _finite_float(a)
    slow_argument = _finite_float(ke * t)
    difference_argument = _finite_float((ka - ke) * t)
    tail = math.exp(-slow_argument)
    growth = -math.expm1(-difference_argument)
    if tail < _MIN_NORMAL or growth < _MIN_NORMAL:
        raise _range_error()
    # Multiplication of positive factors <= 1 avoids cancellation in the model.
    product = amplitude * tail
    result = product * growth
    if not math.isfinite(product) or not math.isfinite(result) or result < _MIN_NORMAL:
        raise _range_error()
    return result


def _stored_score(score: float) -> str:
    if score == 0:
        return "0"
    with localcontext(Context(prec=12, rounding=ROUND_HALF_EVEN)):
        return str(+Decimal.from_float(score))


def compare_grid(problem: HistoricalProblem, design: DesignInput, context: ExecutionContext | None = None) -> dict:
    """Revalidate the frozen projections and evaluate each admitted feasible time.

    Returned numbers are explicitly approximate strings. A completed result
    confers no exact witness status, even if a source artifact was referenced.
    """
    problem, design = revalidate_inputs(problem, design)
    if context is None:
        context = ExecutionContext(wall_seconds=design.limits.wall_seconds)
    if not isinstance(context, ExecutionContext):
        raise AdapterError("invalid_input", "Expected a bounded execution context.", ("context",))
    rows = []
    stopped = None
    for option in design.grid:
        row = {"time": rational_text(option.time), "status": "skipped", "reason_code": None,
               "feasibility_reason": option.reason, "predictions": {c.id: None for c in design.candidates},
               "gap_approximation": None, "score_approximation": None, "ranking_score": None,
               "rank": None, "tied": False}
        if not option.feasible:
            row["reason_code"] = "infeasible_time"
        else:
            stopped = context.stop_reason(design.limits.wall_seconds)
            if stopped is not None:
                row["reason_code"] = stopped
            else:
                try:
                    predictions = [_prediction(candidate.parameters, option.time) for candidate in design.candidates]
                    allowance = _finite_float(design.future_allowance)
                    gap = abs(predictions[0] - predictions[1])
                    score = gap / allowance
                    if not math.isfinite(score) or not math.isfinite(gap) or (gap != 0 and (gap < _MIN_NORMAL or score < _MIN_NORMAL)):
                        raise _range_error()
                except (AdapterError, OverflowError, ZeroDivisionError):
                    row["status"] = "failed"
                    row["reason_code"] = "numerical_range_limitation"
                else:
                    row.update(status="evaluated", predictions={c.id: repr(value) for c, value in zip(design.candidates, predictions)},
                               gap_approximation=repr(gap), score_approximation=repr(score), ranking_score=_stored_score(score))
        rows.append(row)
    evaluated = [row for row in rows if row["status"] == "evaluated"]
    ranked = sorted(evaluated, key=lambda row: (Decimal(row["ranking_score"]).copy_negate(), Fraction(row["time"])))
    scores = [Decimal(row["ranking_score"]) for row in ranked]
    rank = 0
    previous = None
    for row, score in zip(ranked, scores):
        if score != previous:
            rank += 1
        row["rank"] = rank
        row["tied"] = scores.count(score) > 1
        previous = score
    selected = ranked[0]["time"] if ranked and scores[0] > 0 else None
    partial = any(option.feasible and row["status"] != "evaluated" for option, row in zip(design.grid, rows))
    return {"schema_version": "groundwork.numerical-grid.v1", "evaluator_id": EVALUATOR_ID,
            "policy": NUMERICAL_POLICY, "execution": "cancelled" if stopped == "cancelled" else "interrupted" if stopped else "completed",
            "partial": partial, "rows": rows, "ranked_times": [row["time"] for row in ranked],
            "selected_time": selected, "outcome": "numerical_guidance" if selected else "no_useful_suggestion" if ranked else "unavailable",
            "evaluated_count": len(evaluated)}
