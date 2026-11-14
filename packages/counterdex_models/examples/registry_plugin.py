"""How another team registers its own trusted models (for example plasma models).

    python3.11 -m counterdex_models --registry registry_plugin:registry models

(run with this examples directory on PYTHONPATH). The function returns a
ModelRegistry; request files can then name the added model by id.
"""
import math

from counterdex_models import Model, Parameter, default_registry


def _predict(params, times):
    return [params["A"] * math.exp(-params["k"] * t) + params["C"] for t in times]


EXPONENTIAL_PLUS_BASELINE = Model(
    id="example.exponential-plus-baseline",
    revision=1,
    title="Exponential decay to a constant baseline",
    description="y(t) = A·exp(-k·t) + C. Illustrative registration example.",
    time_unit="h", response_unit="mg/L",
    parameters=(Parameter("A", "mg/L", 1e-3, 1e3, "log", "Decaying amplitude"),
                Parameter("k", "1/h", 1e-3, 10.0, "log", "Decay rate"),
                Parameter("C", "mg/L", 0.0, 100.0, "linear", "Baseline")),
    predict=_predict,
)


def registry():
    reg = default_registry()
    reg.register(EXPONENTIAL_PLUS_BASELINE)
    return reg
