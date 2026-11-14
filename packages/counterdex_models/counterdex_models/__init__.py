"""Bounded numerical comparison of trusted, registered models.

Separate from the Counterdex exact checker: nothing here certifies a result,
and nothing here is imported by the exact-checking path.
"""
from .interface import (CAPS, INTERFACE_VERSION, Budget, BudgetExhausted, DetectionThreshold, Model,
                        ModelError, ModelRegistry, NoiseModel, Observation, Observations, Parameter)
from .public_models import SINGLE_EXPONENTIAL, TWO_COMPONENT_MIXTURE, default_registry

VERSION = "0.1.0"
__version__ = VERSION

__all__ = ["CAPS", "INTERFACE_VERSION", "VERSION", "Budget", "BudgetExhausted", "DetectionThreshold", "Model",
           "ModelError", "ModelRegistry", "NoiseModel", "Observation", "Observations", "Parameter",
           "SINGLE_EXPONENTIAL", "TWO_COMPONENT_MIXTURE", "default_registry"]

from .analysis import compare_scenarios, fit_models, monte_carlo, rank_grid, sensitivity  # noqa: E402
from .fitting import fit_model, rank_fits  # noqa: E402
from .requests import REQUEST_SCHEMA, run_request  # noqa: E402

__all__ += ["compare_scenarios", "fit_models", "monte_carlo", "rank_grid", "sensitivity", "fit_model", "rank_fits",
            "REQUEST_SCHEMA", "run_request"]
