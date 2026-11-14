"""Trusted prediction adapter for counterdex-models.interface.v1.

This optional bridge requires the separately installed numerical package. It is
not an alternate fitter and never expands the approved discrete temperature grid.
The engine's scalar coordinate is an explicit channel index, never elapsed time.
"""
from __future__ import annotations

import math

from .contract import ModelComparisonRequest
from .models import ANISOTROPIC, ISOTROPIC, predict_current


def build_counterdex_registry(request: ModelComparisonRequest):
    """Return (registry, channels) for bounded predictions / fixed-vector ranking.

    The tuple indexes request channels followed by feasible settings, preserving
    their full angle/normal-energy metadata. The callable refuses unknown indices,
    substituted parameter keys and points outside the approved grid/bounds.
    Continuous fitting/sensitivity is deliberately not authorized by this bridge.
    """
    from counterdex_models import INTERFACE_VERSION, Model, ModelRegistry, Parameter

    if INTERFACE_VERSION != "counterdex-models.interface.v1":
        raise ValueError("Unsupported numerical model interface")
    if request.instrument is None:
        raise ValueError("An explicit reviewed instrument response is required")
    scoped = request.model_copy(deep=True)
    channels = tuple(scoped.channels + scoped.feasible_settings)
    temperatures = frozenset(map(float, scoped.fit.temperature_grid_eV))
    lower, upper = float(scoped.fit.density_min_m3), float(scoped.fit.density_max_m3)
    registry = ModelRegistry()
    for model_id, names, title in (
        (ISOTROPIC, ("temperature_eV",), "Zero-drift isotropic Maxwellian electrons"),
        (ANISOTROPIC, ("parallel_eV", "perpendicular_eV"), "Zero-drift gyrotropic bi-Maxwellian electrons"),
    ):
        parameters = (Parameter("density_m3", "m^-3", lower, upper, "log"), *(
            Parameter(name, "eV", min(temperatures), max(temperatures), "log") for name in names))

        def prediction(values, indices, temperature_names=names):
            expected = {"density_m3", *temperature_names}
            if set(values) != expected or any(type(value) not in (int, float) or not math.isfinite(value) for value in values.values()):
                raise ValueError("Exactly the finite named parameters are required")
            if not lower <= values["density_m3"] <= upper or any(values[name] not in temperatures for name in temperature_names):
                raise ValueError("Parameters exceed the approved density bounds or discrete temperature grid")
            if any(type(index) not in (int, float) or not math.isfinite(index) or int(index) != index
                   or not 0 <= index < len(channels) for index in indices):
                raise ValueError("Only declared integer channel indices are supported")
            return [predict_current(values, channels[int(index)], scoped.instrument) for index in indices]

        registry.register(Model(id=model_id, revision=1, title=title, time_unit="channel_index", response_unit="A",
                                parameters=parameters, predict=prediction, synthetic_example=True,
                                description="Idealized normal-energy planar collector. Coordinates index captured reviewed channels; temperatures are limited to the approved discrete grid. Prediction/ranking adapter only; no continuous fitting authority."))
    # Return copies so a consumer cannot mutate the callable's captured settings.
    return registry, tuple(channel.model_copy(deep=True) for channel in channels)
