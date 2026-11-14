"""Public synthetic example models.

These are generic textbook forms used for demonstration and tests. They are
not plasma-specific, not fitted to any real study and carry no claim about
any compound. Plasma-specific models register through the same interface.
"""
from __future__ import annotations

import math

from .interface import Model, ModelRegistry, Parameter


def _single(params, times):
    a, k = params["A"], params["k"]
    return [a * math.exp(-k * t) for t in times]


def _mixture(params, times):
    a1, k1, a2, k2 = params["A1"], params["k1"], params["A2"], params["k2"]
    return [a1 * math.exp(-k1 * t) + a2 * math.exp(-k2 * t) for t in times]


def _order_components(params: dict) -> dict:
    """Report the faster-decaying component as component 1."""
    if params["k1"] >= params["k2"]:
        return dict(params)
    return {"A1": params["A2"], "k1": params["k2"], "A2": params["A1"], "k2": params["k1"]}


SINGLE_EXPONENTIAL = Model(
    id="public.single-exponential",
    revision=1,
    title="Single-exponential decay",
    description="y(t) = A·exp(-k·t). Public synthetic example.",
    time_unit="h", response_unit="mg/L",
    parameters=(
        Parameter("A", "mg/L", 1e-3, 1e3, "log", "Value at t = 0"),
        Parameter("k", "1/h", 1e-3, 10.0, "log", "Decay rate"),
    ),
    predict=_single,
    synthetic_example=True,
)

TWO_COMPONENT_MIXTURE = Model(
    id="public.two-exponential-mixture",
    revision=1,
    title="Two-component exponential mixture",
    description="y(t) = A1·exp(-k1·t) + A2·exp(-k2·t), reported with k1 ≥ k2. Public synthetic example.",
    time_unit="h", response_unit="mg/L",
    parameters=(
        Parameter("A1", "mg/L", 1e-3, 1e3, "log", "Fast-component amplitude"),
        Parameter("k1", "1/h", 1e-3, 10.0, "log", "Fast-component rate"),
        Parameter("A2", "mg/L", 1e-3, 1e3, "log", "Slow-component amplitude"),
        Parameter("k2", "1/h", 1e-3, 10.0, "log", "Slow-component rate"),
    ),
    predict=_mixture,
    synthetic_example=True,
    canonicalize=_order_components,
)


def default_registry() -> ModelRegistry:
    """A fresh registry holding only the public synthetic examples."""
    return ModelRegistry([SINGLE_EXPONENTIAL, TWO_COMPONENT_MIXTURE])
