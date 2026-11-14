"""Validate recorded numerical arithmetic without evaluating a trajectory.

This module imports no numerical producer. Its result means only that the
recorded finite predictions, arithmetic, row coverage and ranking agree. A
coherent fabricated prediction is not detected here; exact scientific replay
requires the separate analytic certificate checker.
"""
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
import math
import re
import sys

from .errors import AdapterError
from .exact import rational_text
from .models import DesignInput, NUMERICAL_POLICY

_NUMBER = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z")
_TOP_FIELDS = {"schema_version", "evaluator_id", "policy", "execution", "partial", "rows",
               "ranked_times", "selected_time", "outcome", "evaluated_count"}
_ROW_FIELDS = {"time", "status", "reason_code", "feasibility_reason", "predictions",
               "gap_approximation", "score_approximation", "ranking_score", "rank", "tied"}


def _error(path: str, *, malformed: bool = False) -> AdapterError:
    return AdapterError("invalid_input" if malformed else "numerical_record_mismatch",
                        "Recorded numerical fields are malformed or inconsistent with the declared policy.", (path,))


def _object(value: object, keys: set[str], path: str) -> dict:
    if type(value) is not dict or set(value) != keys:
        raise _error(path, malformed=True)
    return value


def _number_text(value: object, path: str) -> str:
    if type(value) is not str or not 1 <= len(value) <= 64 or _NUMBER.fullmatch(value) is None:
        raise _error(path, malformed=True)
    return value


def _raw_float(value: object, path: str) -> float:
    text = _number_text(value, path)
    try:
        result = float(text)
    except (OverflowError, ValueError):
        raise _error(path, malformed=True) from None
    if not math.isfinite(result) or result < 0 or repr(result) != text:
        raise _error(path, malformed=True)
    return result


def _rank_score(score: float) -> str:
    if score == 0:
        return "0"
    # A process-wide Decimal setting must not change a stored policy's meaning.
    with localcontext(Context(prec=12, rounding=ROUND_HALF_EVEN)):
        return str(+Decimal.from_float(score))


def validate_numerical_record(record: dict, design: DesignInput) -> None:
    """Check recorded arithmetic/selection only, against a normalized design.

    The enclosing replay layer must validate the design against the independent
    expected problem and identity. This function does not approve scope, check
    compatibility, evaluate exponentials or establish a scientific conclusion.
    """
    if (type(design) is not DesignInput or type(design.grid) is not tuple or not 1 <= len(design.grid) <= 64
        or type(design.candidates) is not tuple or len(design.candidates) != 2
        or type(design.future_allowance) is not Fraction or design.future_allowance <= 0):
        raise _error("design", malformed=True)
    candidates = [candidate.id for candidate in design.candidates]
    if len(set(candidates)) != 2:
        raise _error("design/candidates", malformed=True)
    expected_times = [rational_text(option.time) for option in design.grid]
    if len(set(expected_times)) != len(expected_times) or list(design.grid) != sorted(design.grid, key=lambda option: option.time):
        raise _error("design/grid", malformed=True)
    r = _object(record, _TOP_FIELDS, "report/numerical")
    if (r["schema_version"] != "groundwork.numerical-grid.v1" or r["evaluator_id"] != "two-rate-expm1-binary64.v1"
        or r["policy"] != NUMERICAL_POLICY):
        raise _error("report/numerical", malformed=True)
    if type(r["partial"]) is not bool or type(r["evaluated_count"]) is not int:
        raise _error("report/numerical", malformed=True)
    if type(r["rows"]) is not list or len(r["rows"]) != len(design.grid):
        raise _error("report/numerical/rows", malformed=True)
    evaluated = []
    stopping_reason = None
    partial = False
    for index, (value, option) in enumerate(zip(r["rows"], design.grid)):
        path = f"report/numerical/rows/{index}"
        row = _object(value, _ROW_FIELDS, path)
        if row["time"] != expected_times[index] or row["feasibility_reason"] != option.reason:
            raise _error(path)
        predictions = _object(row["predictions"], set(candidates), path + "/predictions")
        if type(row["tied"]) is not bool:
            raise _error(path + "/tied", malformed=True)
        if row["status"] == "evaluated":
            if not option.feasible or row["reason_code"] is not None or stopping_reason is not None:
                raise _error(path)
            values = [_raw_float(predictions[cid], path + "/predictions/" + cid) for cid in candidates]
            gap = _raw_float(row["gap_approximation"], path + "/gap_approximation")
            score = _raw_float(row["score_approximation"], path + "/score_approximation")
            _number_text(row["ranking_score"], path + "/ranking_score")
            if any(0 < number < sys.float_info.min for number in values):
                raise _error(path + "/predictions")
            try:
                allowance = float(design.future_allowance)
                if not math.isfinite(allowance) or allowance <= 0:
                    raise ValueError
                computed_gap = abs(values[0] - values[1])
                computed_score = computed_gap / allowance
            except (ValueError, OverflowError, ZeroDivisionError):
                raise _error(path) from None
            if (not math.isfinite(computed_score) or gap != computed_gap or score != computed_score
                or (gap != 0 and (gap < sys.float_info.min or score < sys.float_info.min))
                or row["ranking_score"] != _rank_score(score)):
                raise _error(path)
            if type(row["rank"]) is not int or not 1 <= row["rank"] <= len(design.grid):
                raise _error(path + "/rank", malformed=True)
            evaluated.append(row)
        elif row["status"] in ("skipped", "failed"):
            if (any(value is not None for value in predictions.values())
                or any(row[key] is not None for key in ("gap_approximation", "score_approximation", "ranking_score", "rank"))
                or row["tied"]):
                raise _error(path)
            if not option.feasible:
                if row["status"] != "skipped" or row["reason_code"] != "infeasible_time":
                    raise _error(path)
            elif row["status"] == "failed":
                if row["reason_code"] != "numerical_range_limitation" or stopping_reason is not None:
                    raise _error(path)
                partial = True
            else:
                if row["reason_code"] not in ("cancelled", "resource_exhaustion"):
                    raise _error(path)
                if stopping_reason is not None and row["reason_code"] != stopping_reason:
                    raise _error(path)
                stopping_reason = row["reason_code"]
                partial = True
        else:
            raise _error(path + "/status", malformed=True)

    # Scores are already constrained to exactly the producer's finite decimal
    # representation. Decimal construction and copy_negate are context-free.
    try:
        ranked = sorted(evaluated, key=lambda row: (Decimal(row["ranking_score"]).copy_negate(), Fraction(row["time"])))
        scores = [Decimal(row["ranking_score"]) for row in ranked]
    except (InvalidOperation, ValueError, OverflowError):
        raise _error("report/numerical/ranked_times") from None
    rank = 0
    previous = None
    for row, score in zip(ranked, scores):
        if score != previous:
            rank += 1
        if row["rank"] != rank or row["tied"] != (scores.count(score) > 1):
            raise _error("report/numerical/rows")
        previous = score
    selected = ranked[0]["time"] if ranked and scores[0] > 0 else None
    outcome = "numerical_guidance" if selected else "no_useful_suggestion" if ranked else "unavailable"
    execution = "cancelled" if stopping_reason == "cancelled" else "interrupted" if stopping_reason else "completed"
    if (type(r["ranked_times"]) is not list or r["ranked_times"] != [row["time"] for row in ranked]
        or r["selected_time"] != selected or r["outcome"] != outcome or r["execution"] != execution
        or r["partial"] != partial or r["evaluated_count"] != len(evaluated)):
        raise _error("report/numerical")
