"""Stable interface for trusted, registered numerical models.

A model is Python code registered by a trusted caller. Requests and artifacts
name a registered model by id; they can never supply or select code.

Three researcher inputs are deliberately separate types and never interchange:

* ``NoiseModel``: the assumed standard deviation of measurement noise. It
  weights fits, generates Monte Carlo readings and scales predicted differences.
* ``DetectionThreshold``: readings below it are reported only as "below the
  threshold" (left-censored). It is not a noise level.
* A hard allowance (a guaranteed bound on each reading's error) belongs to the
  exact Counterdex checker. This module does not accept one.

Everything here is binary64 numerical analysis. A better fit, a higher rank or
a larger predicted difference is never proof that a model is true, and never a
certified or globally optimal design.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
import math
import re
import time
from typing import Callable, Mapping, Sequence

INTERFACE_VERSION = "counterdex-models.interface.v1"

# Hard caps. Requests may ask for less, never more.
CAPS = {
    "models_per_request": 8,
    "parameters_per_model": 12,
    "observations": 512,
    "fit_starts": 64,
    "fit_iterations": 500,
    "sweep_points": 101,
    "scenarios": 16,
    "monte_carlo_replicates": 1000,
    "grid_times": 256,
    "hypotheses": 6,
    "model_evaluations": 5_000_000,
    "wall_seconds": 120,
}

_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,79}$")
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")


class ModelError(Exception):
    """A refused request or model definition, with a stable machine code."""

    def __init__(self, code: str, message: str, path: str = ""):
        super().__init__(message)
        self.code, self.message, self.path = code, message, path

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "path": self.path}


def to_float(value, path: str) -> float:
    """Accept a JSON number, a decimal string or an exact ``n/d`` string.

    Exact rationals from reviewed records are rounded to binary64 here; the
    numerical module never claims exactness.
    """
    if isinstance(value, bool) or value is None:
        raise ModelError("invalid_input", "Expected a finite number.", path)
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str) and len(value) <= 200:
        try:
            result = float(Fraction(value.strip()))
        except (ValueError, ZeroDivisionError, OverflowError):
            raise ModelError("invalid_input", "Expected a decimal or n/d number.", path) from None
    else:
        raise ModelError("invalid_input", "Expected a finite number.", path)
    if not math.isfinite(result):
        raise ModelError("invalid_input", "Expected a finite number.", path)
    return result


@dataclass(frozen=True)
class Parameter:
    """One fitted parameter with hard search bounds and a unit.

    ``scale="log"`` searches the bounds geometrically (rates, amplitudes
    spanning decades) and requires a positive lower bound.
    """

    name: str
    unit: str
    lower: float
    upper: float
    scale: str = "linear"
    description: str = ""

    def __post_init__(self):
        if not _NAME.match(self.name):
            raise ModelError("invalid_model", f"Parameter name {self.name!r} must be an identifier of at most 32 characters.")
        if not (math.isfinite(self.lower) and math.isfinite(self.upper) and self.lower < self.upper):
            raise ModelError("invalid_model", f"Parameter {self.name} needs finite bounds with lower < upper.")
        if self.scale not in ("linear", "log"):
            raise ModelError("invalid_model", f"Parameter {self.name} scale must be 'linear' or 'log'.")
        if self.scale == "log" and self.lower <= 0:
            raise ModelError("invalid_model", f"Log-scale parameter {self.name} needs a positive lower bound.")

    def to_dict(self) -> dict:
        return {"name": self.name, "unit": self.unit, "lower": self.lower, "upper": self.upper,
                "scale": self.scale, "description": self.description}


Predict = Callable[[Mapping[str, float], Sequence[float]], Sequence[float]]


@dataclass(frozen=True)
class Model:
    """A trusted model: parameters, units and a deterministic prediction function.

    ``predict(params, times)`` receives a mapping of every parameter name to a
    float inside its bounds and a sequence of times, and returns one prediction
    per time. It must be deterministic, side-effect free and provider-free.
    Non-finite output is recorded as a numerical failure, never as data.

    ``canonicalize`` optionally maps a parameter vector to a canonical
    equivalent (for example ordering exponential components) so that
    label-switched solutions are reported once.
    """

    id: str
    revision: int
    title: str
    time_unit: str
    response_unit: str
    parameters: tuple[Parameter, ...]
    predict: Predict
    description: str = ""
    synthetic_example: bool = False
    canonicalize: Callable[[dict], dict] | None = None

    def __post_init__(self):
        if not _ID.match(self.id):
            raise ModelError("invalid_model", "Model id must be 3-80 lowercase letters, digits, '.', '_' or '-'.")
        if type(self.revision) is not int or self.revision < 1:
            raise ModelError("invalid_model", "Model revision must be a positive integer.")
        if not self.parameters or len(self.parameters) > CAPS["parameters_per_model"]:
            raise ModelError("invalid_model", f"A model needs 1-{CAPS['parameters_per_model']} parameters.")
        names = [p.name for p in self.parameters]
        if len(set(names)) != len(names):
            raise ModelError("invalid_model", "Parameter names must be unique.")
        if not callable(self.predict) or (self.canonicalize is not None and not callable(self.canonicalize)):
            raise ModelError("invalid_model", "predict and canonicalize must be callable.")

    @property
    def parameter_names(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.parameters)

    def describe(self) -> dict:
        return {"id": self.id, "revision": self.revision, "title": self.title, "description": self.description,
                "time_unit": self.time_unit, "response_unit": self.response_unit,
                "parameter_count": len(self.parameters), "parameters": [p.to_dict() for p in self.parameters],
                "synthetic_example": self.synthetic_example}

    def evaluate(self, params: Mapping[str, float], times: Sequence[float], budget: "Budget | None" = None) -> list[float] | None:
        """Call ``predict`` once; return finite floats or ``None`` on numerical failure."""
        if budget is not None:
            budget.spend(len(times))
        try:
            values = list(self.predict(dict(params), list(times)))
        except (ArithmeticError, ValueError):
            return None
        if len(values) != len(times):
            raise ModelError("invalid_model", f"Model {self.id} returned {len(values)} predictions for {len(times)} times.")
        try:
            values = [float(v) for v in values]
        except (TypeError, ValueError):
            return None
        return values if all(math.isfinite(v) for v in values) else None


class ModelRegistry:
    """Trusted models, registered in code. Request data can only name them."""

    def __init__(self, models: Sequence[Model] = ()):
        self._models: dict[str, Model] = {}
        for model in models:
            self.register(model)

    def register(self, model: Model) -> Model:
        if not isinstance(model, Model):
            raise ModelError("invalid_model", "Only Model instances can be registered.")
        if model.id in self._models:
            raise ModelError("duplicate_model", f"Model {model.id} is already registered; publish a new id or revision.")
        self._models[model.id] = model
        return model

    def get(self, model_id: str) -> Model:
        if model_id not in self._models:
            raise ModelError("unknown_model", f"Model {model_id!r} is not registered.", "models")
        return self._models[model_id]

    def ids(self) -> list[str]:
        return sorted(self._models)

    def describe(self) -> list[dict]:
        return [self._models[i].describe() for i in self.ids()]


@dataclass(frozen=True)
class NoiseModel:
    """Assumed measurement-noise standard deviation: sqrt(absolute² + (relative·y)²).

    This is a statistical assumption, not a hard allowance and not a
    detection threshold.
    """

    absolute_sd: float = 0.0
    relative_sd: float = 0.0
    label: str = ""

    def __post_init__(self):
        for name in ("absolute_sd", "relative_sd"):
            value = getattr(self, name)
            if not (math.isfinite(value) and value >= 0):
                raise ModelError("invalid_input", f"{name} must be finite and non-negative.", f"noise/{name}")
        if self.absolute_sd == 0 and self.relative_sd == 0:
            raise ModelError("invalid_input", "A noise assumption needs a positive absolute or relative standard deviation.", "noise")

    def sd(self, level: float) -> float:
        return math.hypot(self.absolute_sd, self.relative_sd * abs(level)) or self.absolute_sd or 1e-300

    def to_dict(self) -> dict:
        return {"kind": "standard_deviation", "absolute_sd": self.absolute_sd, "relative_sd": self.relative_sd, "label": self.label}


@dataclass(frozen=True)
class DetectionThreshold:
    """Readings below ``value`` are known only to be below it (left-censored)."""

    value: float
    label: str = ""

    def __post_init__(self):
        if not (math.isfinite(self.value) and self.value > 0):
            raise ModelError("invalid_input", "A detection threshold must be positive and finite.", "detection_threshold/value")

    def to_dict(self) -> dict:
        return {"kind": "left_censoring_threshold", "value": self.value, "label": self.label}


@dataclass(frozen=True)
class Observation:
    """One reviewed reading. ``censored=True`` means "below the detection threshold"."""

    time: float
    value: float | None
    censored: bool = False


@dataclass(frozen=True)
class Observations:
    time_unit: str
    response_unit: str
    rows: tuple[Observation, ...]
    provenance: str = ""

    def __post_init__(self):
        if not 1 <= len(self.rows) <= CAPS["observations"]:
            raise ModelError("invalid_input", f"Supply 1-{CAPS['observations']} observations.", "observations/rows")
        for i, row in enumerate(self.rows):
            if not math.isfinite(row.time):
                raise ModelError("invalid_input", "Observation times must be finite.", f"observations/rows/{i}/time")
            if not row.censored and (row.value is None or not math.isfinite(row.value)):
                raise ModelError("invalid_input", "An uncensored observation needs a finite value.", f"observations/rows/{i}/value")

    def apply_threshold(self, threshold: DetectionThreshold | None) -> "Observations":
        """Mark readings below the threshold as censored; never invent values."""
        if threshold is None:
            if any(r.censored for r in self.rows):
                raise ModelError("invalid_input", "Censored observations need a detection threshold.", "detection_threshold")
            return self
        rows = tuple(Observation(r.time, None, True) if r.censored or r.value < threshold.value else r for r in self.rows)
        return Observations(self.time_unit, self.response_unit, rows, self.provenance)

    def check_units(self, model: Model) -> None:
        if (self.time_unit, self.response_unit) != (model.time_unit, model.response_unit):
            raise ModelError("unit_mismatch", f"Model {model.id} uses {model.time_unit} and {model.response_unit}; "
                             f"observations use {self.time_unit} and {self.response_unit}.", "observations")

    def to_dict(self) -> dict:
        return {"time_unit": self.time_unit, "response_unit": self.response_unit, "provenance": self.provenance,
                "rows": [{"time": r.time, "value": r.value, "censored": r.censored} for r in self.rows]}


class BudgetExhausted(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class Budget:
    """Deterministic evaluation cap plus a wall-clock safety stop.

    ``max_evaluations`` counts predicted points and makes stopping
    reproducible. The wall clock is only a safety net; a result stopped by
    it is marked as such and is not guaranteed to be reproducible.
    """

    max_evaluations: int = 2_000_000
    wall_seconds: float = 60.0
    clock: Callable[[], float] = time.monotonic
    cancelled: Callable[[], bool] = lambda: False
    used: int = field(init=False, default=0)
    stopped: str | None = field(init=False, default=None)
    _start: float = field(init=False, default=0.0)

    def __post_init__(self):
        if type(self.max_evaluations) is not int or not 0 < self.max_evaluations <= CAPS["model_evaluations"]:
            raise ModelError("invalid_input", f"max_evaluations must be 1-{CAPS['model_evaluations']}.", "limits/max_evaluations")
        if not (isinstance(self.wall_seconds, (int, float)) and 0 < self.wall_seconds <= CAPS["wall_seconds"]):
            raise ModelError("invalid_input", f"wall_seconds must be in (0, {CAPS['wall_seconds']}].", "limits/wall_seconds")
        self._start = self.clock()

    def spend(self, points: int) -> None:
        if self.stopped:
            raise BudgetExhausted(self.stopped)
        self.used += points
        if self.used > self.max_evaluations:
            self.stopped = "evaluation_limit"
        elif self.cancelled():
            self.stopped = "cancelled"
        elif self.clock() - self._start >= self.wall_seconds:
            self.stopped = "wall_clock_limit"
        if self.stopped:
            raise BudgetExhausted(self.stopped)

    def to_dict(self) -> dict:
        return {"max_evaluations": self.max_evaluations, "evaluations_used": self.used,
                "wall_seconds": self.wall_seconds, "stopped": self.stopped}
