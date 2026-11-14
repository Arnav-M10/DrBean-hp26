"""Optional numerical-engine handoff: run with PR56's qualified source on PYTHONPATH."""
import json
from pathlib import Path

import pytest

from bean_api.model_comparison.contract import ModelComparisonRequest
from bean_api.model_comparison.models import ANISOTROPIC, ISOTROPIC, predict_current
from bean_api.model_comparison.registry import build_counterdex_registry

engine = pytest.importorskip("counterdex_models", reason="Separate numerical engine package not installed; registry bridge not available")


def test_real_registered_models_and_grid_ranking_preserve_physical_settings_and_units():
    body = json.loads((Path(__file__).parents[1] / "fixtures/model-comparison/synthetic.request.json").read_text())
    request = ModelComparisonRequest.model_validate(body)
    registry, channels = build_counterdex_registry(request)
    vectors = [{"density_m3": 1e15, "temperature_eV": 8},
               {"density_m3": 1e15, "parallel_eV": 4, "perpendicular_eV": 16}]
    indices = list(range(len(channels)))
    for identity, parameters in zip((ISOTROPIC, ANISOTROPIC), vectors, strict=True):
        model = registry.get(identity)
        assert model.time_unit == "channel_index" and model.response_unit == "A"
        budget = engine.Budget(max_evaluations=1000)
        assert model.evaluate(parameters, indices, budget) == [predict_current(parameters, channel, request.instrument) for channel in channels]
        assert budget.used == len(indices)
        assert model.evaluate({**parameters, "density_m3": 1e17}, indices) is None
        assert model.evaluate({**parameters, "extra": 0}, indices) is None
        assert model.evaluate(parameters, [0.5]) is None
        assert model.evaluate(parameters, [len(channels)]) is None
        temperature_name = "temperature_eV" if identity == ISOTROPIC else "parallel_eV"
        assert model.evaluate({**parameters, temperature_name: 6}, indices) is None
    start = len(request.channels)
    result = engine.rank_grid([(identity, registry.get(identity), parameters)
                              for identity, parameters in zip((ISOTROPIC, ANISOTROPIC), vectors, strict=True)],
                             list(range(start, len(channels))), engine.NoiseModel(absolute_sd=1e-6),
                             budget=engine.Budget(max_evaluations=1000))
    assert result["certification"] == "none" and result["execution"] == "completed"
    assert result["inputs"]["detection_threshold"] is None  # z-band is not a censoring threshold.
    assert {row["time"] for row in result["rows"]} == set(range(start, len(channels)))
    for row in result["rows"]:
        expected = [predict_current(parameters, channels[int(row["time"])], request.instrument) for parameters in vectors]
        assert row["score"] == pytest.approx(abs(expected[1]-expected[0]) / 1e-6)
    # Neither caller mutation may substitute the approved geometry.
    reference = registry.get(ANISOTROPIC).evaluate(vectors[1], [0])
    channels[0].angle_deg = "90"
    request.channels[0].angle_deg = "90"
    assert registry.get(ANISOTROPIC).evaluate(vectors[1], [0]) == reference
