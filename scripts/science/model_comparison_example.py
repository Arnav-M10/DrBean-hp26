"""Generate public synthetic comparison inputs and a real computed response.

Run from repository root with PYTHONPATH=apps/api and the prepared backend Python.
All data are newly generated; no experimental/private data or provider is used.
"""
import json
from pathlib import Path

from bean_api.model_comparison.contract import Channel, Instrument, ModelComparisonRequest, ModelComparisonResult
from bean_api.model_comparison.compute import compute_comparison, number
from bean_api.model_comparison.models import predict_current


def example():
    instrument = Instrument(kind="idealized_normal_energy_planar_collector", acceptance="full_incident_half_space",
                            current_convention="electron_current_magnitude", area_m2="0.000001", efficiency="0.8")
    channels = [Channel(id=f"a{angle}_e{energy}", angle_deg=str(angle), energy_min_eV=str(energy), energy_max_eV=None)
                for angle in (0, 45, 90) for energy in (0, 8)]
    parameters = {"density_m3": 1e15, "parallel_eV": 4.0, "perpendicular_eV": 16.0}
    observations = [{"channel_id": channel.id,
                     "current_A": number(predict_current(parameters, channel, instrument)), "sigma_A": "0.0000002"}
                    for channel in channels]
    return ModelComparisonRequest.model_validate({
        "schema_version": "DB-MODEL-COMPARISON-1", "approval": "approved_for_this_request",
        "review": {"reviewed": True, "origin": "synthetic", "description": "New synthetic zero-drift electron distribution; density 1e15 m^-3, parallel 4 eV, perpendicular 16 eV. Exact forward means with declared independent Gaussian measurement standard deviations; not acquired data."},
        "instrument": instrument.model_dump(), "channels": [channel.model_dump() for channel in channels],
        "observations": observations, "selected_channel_ids": [channel.id for channel in channels],
        "fit": {"density_min_m3": "100000000000000", "density_max_m3": "10000000000000000",
                "temperature_grid_eV": ["2", "4", "8", "12", "16", "24"], "max_evaluations": 100,
                "max_reduced_chi_square": "10"},
        "noise": {"kind": "independent_gaussian", "sigma_grid_A": ["0.0000001", "0.000002", "0.00002"],
                  "z_thresholds": ["2"], "seed": 1729, "samples": 128},
        "feasible_settings": [Channel(id=f"next_a{angle}_e{energy}", angle_deg=str(angle), energy_min_eV=str(energy),
                                      energy_max_eV=None).model_dump() for angle in (0, 90) for energy in (0, 4, 8, 16)]})


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    destination = root / "fixtures/model-comparison"
    destination.mkdir(parents=True, exist_ok=True)
    request = example()
    response = compute_comparison(request)
    assert response["status"] == "completed"
    for name, value in (("synthetic.request.json", request.model_dump(mode="json")), ("synthetic.response.json", response),
                        ("request.schema.json", ModelComparisonRequest.model_json_schema()),
                        ("result.schema.json", ModelComparisonResult.model_json_schema())):
        (destination / name).write_text(json.dumps(value, indent=2) + "\n")
    print(json.dumps({"status": response["status"], "input_digest": response["input_digest"],
                      "fits": [{"model_id": fit["model_id"], "parameters": fit["parameters"], "chi_square": fit["chi_square"]} for fit in response["fits"]],
                      "noise_decisions": [case["decision"] for case in response["noise_sweep"]]}))
