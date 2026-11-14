"""Scientific acceptance of the public offline comparison contract.

These tests exercise computed results rather than naming a particular numerical
backend. The public synthetic fixture is the baseline, never a special-case key.
"""

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import socket

import pytest
from pydantic import ValidationError

from bean_api.canonical import canonical_bytes
from bean_api.model_comparison.compute import compute_comparison
from bean_api.model_comparison.contract import Channel, Instrument, ModelComparisonRequest, ModelComparisonResult
from bean_api.model_comparison.models import ANISOTROPIC, ISOTROPIC, predict_current


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/model-comparison/synthetic.request.json"


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def no_network(*args, **kwargs):
        pytest.fail("Scientific numerical comparison must not dispatch network/provider calls")
    monkeypatch.setattr(socket.socket, "connect", no_network)


@pytest.fixture
def request_body():
    return json.loads(FIXTURE.read_text())


def run(body):
    before = deepcopy(body)
    result = compute_comparison(ModelComparisonRequest.model_validate(body))
    assert body == before, "Computation mutated the supplied reviewed observations"
    assert result["request"] == body
    assert result["input_digest"] == hashlib.sha256(canonical_bytes(body)).hexdigest()
    assert result["exact_verification"] == "not_performed"
    return result


def fits_by_model(result):
    return {fit["model_id"]: fit for fit in result["fits"]}


def all_simulations(result):
    for case in result["noise_sweep"]:
        yield from case["selected_channel_simulations"]
        for setting in case["settings"]:
            yield from setting["conditional_simulations"]


def replace_observations_with_forward_means(body, parameters):
    channels = {item["id"]: Channel.model_validate(item) for item in body["channels"]}
    instrument = Instrument.model_validate(body["instrument"])
    for row in body["observations"]:
        row["current_A"] = format(predict_current(parameters, channels[row["channel_id"]], instrument), ".17g")


def test_known_synthetic_anisotropy_recovers_parameters_and_bounded_fit_evidence(request_body):
    result = run(request_body)
    assert result["status"] == "completed" and result["failures"] == []
    fits = fits_by_model(result)
    isotropic, anisotropic = fits[ISOTROPIC], fits[ANISOTROPIC]
    assert float(anisotropic["parameters"]["density_m3"]) == pytest.approx(1e15, rel=1e-12)
    assert float(anisotropic["parameters"]["parallel_eV"]) == 4
    assert float(anisotropic["parameters"]["perpendicular_eV"]) == 16
    assert anisotropic["parameter_count"] == 3 and isotropic["parameter_count"] == 2
    assert anisotropic["adequate_under_declared_threshold"] is True
    assert isotropic["adequate_under_declared_threshold"] is False
    assert float(anisotropic["rmse_A"]) < 1e-17
    assert float(isotropic["rmse_A"]) > 1e-6
    assert anisotropic["rank_estimate"] == 3 and anisotropic["rank_deficient"] is False
    for fit in fits.values():
        assert fit["status"] == "bounded_grid_completed"
        assert fit["degrees_of_freedom"] == len(request_body["observations"]) - fit["parameter_count"]
        expected_chi_square = 0.0
        for prediction, observation in zip(fit["predictions"], request_body["observations"], strict=True):
            assert prediction["channel_id"] == observation["channel_id"]
            assert prediction["observed_A"] == observation["current_A"]
            assert prediction["sigma_A"] == observation["sigma_A"]
            residual = float(prediction["observed_A"]) - float(prediction["predicted_A"])
            assert float(prediction["residual_A"]) == pytest.approx(residual, abs=2e-19)
            expected_chi_square += (residual / float(prediction["sigma_A"]))**2
        assert float(fit["chi_square"]) == pytest.approx(expected_chi_square, rel=1e-11, abs=1e-20)
        assert {entry["parameter"] for entry in fit["sensitivity"]} == set(fit["parameters"])
        assert all(entry["unit"] == "A" and len(entry["values"]) == len(request_body["observations"])
                   for entry in fit["sensitivity"])


def test_isotropic_limit_is_ambiguous_not_preference_for_more_parameters(request_body):
    replace_observations_with_forward_means(request_body, {"density_m3": 1e15, "temperature_eV": 8})
    result = run(request_body)
    assert result["status"] == "completed"
    isotropic, anisotropic = (fits_by_model(result)[model] for model in (ISOTROPIC, ANISOTROPIC))
    assert float(isotropic["parameters"]["temperature_eV"]) == 8
    assert float(anisotropic["parameters"]["parallel_eV"]) == 8
    assert float(anisotropic["parameters"]["perpendicular_eV"]) == 8
    assert all(fit["adequate_under_declared_threshold"] for fit in result["fits"])
    assert "do not distinguish" in result["decision"]
    assert not any(case["selected_channel_bands_separated_numerically"] for case in result["noise_sweep"])
    assert all(case["suggested_setting_id"] is None for case in result["noise_sweep"])
    for simulation in all_simulations(result):
        assert simulation["outcomes"]["generating_band_only"]["count"] == 0
        assert simulation["outcomes"]["other_band_only"]["count"] == 0


def test_noise_sweep_changes_detectability_and_feasible_suggestions_without_refitting(request_body):
    result = run(request_body)
    low, high = result["noise_sweep"][0], result["noise_sweep"][-1]
    assert float(low["sigma_A"]) < float(high["sigma_A"])
    assert low["selected_channel_bands_separated_numerically"] is True
    assert high["selected_channel_bands_separated_numerically"] is False
    assert low["suggested_setting_id"] in {item["id"] for item in request_body["feasible_settings"]}
    assert high["suggested_setting_id"] is None
    assert "do not distinguish" in high["decision"]
    assert {setting["setting"]["id"] for setting in result["settings"]} == {
        item["id"] for item in request_body["feasible_settings"]
    }
    for case in result["noise_sweep"]:
        for setting in case["settings"]:
            if float(setting["numerical_band_margin_A"]) > 0:
                assert all(sim["outcomes"]["both_bands"]["count"] == 0
                           for sim in setting["conditional_simulations"])
        if case["selected_channel_bands_separated_numerically"]:
            assert all(sim["outcomes"]["both_bands"]["count"] == 0
                       for sim in case["selected_channel_simulations"])
    noisy = deepcopy(request_body)
    noisy["noise"]["sigma_grid_A"] = ["0.001"]
    noisy_result = run(noisy)
    assert noisy_result["fits"] == result["fits"]
    assert noisy_result["input_digest"] != result["input_digest"]
    assert "do not distinguish" in noisy_result["decision"]


def test_touching_selected_prediction_bands_are_not_separated(request_body):
    baseline = run(request_body)
    predictions = [fit["predictions"] for fit in baseline["fits"]]
    maximum_gap = max(abs(float(left["predicted_A"]) - float(right["predicted_A"]))
                      for left, right in zip(*predictions, strict=True))
    request_body["noise"]["z_thresholds"] = ["1"]
    request_body["noise"]["sigma_grid_A"] = [format(maximum_gap / 2, ".17g")]
    result = run(request_body)
    assert result["noise_sweep"][0]["selected_channel_bands_separated_numerically"] is False


@pytest.mark.parametrize("boundary", ["touching", "rounding_midpoint"])
def test_feasible_margin_and_suggestion_use_the_returned_prediction_pair(request_body, boundary):
    baseline = run(request_body)

    def returned_gap(setting):
        return abs(float(setting["predictions_A"][ISOTROPIC]) - float(setting["predictions_A"][ANISOTROPIC]))

    # Select the worst potential discrepancy between the advertised gap and
    # the actual exported pair. Before round-trip serialization, this fixture
    # could suggest a setting whose two exported bands overlapped.
    setting = max(baseline["settings"],
                  key=lambda item: float(item["absolute_difference_A"]) - returned_gap(item))
    gap = returned_gap(setting)
    assert gap > 0
    assert float(setting["absolute_difference_A"]) == gap
    twice_sigma = gap
    if boundary == "rounding_midpoint":
        rounded_up_gap = max(float(format(gap, ".15g")), math.nextafter(gap, math.inf))
        twice_sigma = (gap + rounded_up_gap) / 2
    request_body["feasible_settings"] = [setting["setting"]]
    request_body["noise"]["z_thresholds"] = ["1"]
    request_body["noise"]["sigma_grid_A"] = [format(twice_sigma / 2, ".17g")]
    result = run(request_body)
    case = result["noise_sweep"][0]
    current_gap = returned_gap(result["settings"][0])
    expected_margin = current_gap - 2 * float(case["sigma_A"])
    assert float(case["settings"][0]["numerical_band_margin_A"]) == expected_margin
    assert expected_margin <= 0
    assert case["suggested_setting_id"] is None


@pytest.mark.parametrize("failure_kind", ["inadequate_grid", "all_predictions_underflow"])
def test_bounded_fit_failure_retains_scope_and_never_claims_all_models_excluded(request_body, failure_kind):
    request_body["fit"]["temperature_grid_eV"] = ["0.1", "0.2"]
    if failure_kind == "all_predictions_underflow":
        for item in request_body["channels"]:
            item["energy_min_eV"] = "10000"
            item["energy_max_eV"] = None
    result = run(request_body)
    assert result["status"] == "fit_failed"
    assert result["failures"] and result["settings"] == [] and result["noise_sweep"] == []
    assert not any(fit["adequate_under_declared_threshold"] for fit in result["fits"])
    assert "grid" in result["decision"] or "bounded" in result["decision"]
    if failure_kind == "inadequate_grid":
        assert "does not rule out" in result["decision"]


def test_finite_tiny_forward_signals_do_not_fail_only_because_wls_squares_underflow(request_body):
    request_body["fit"]["temperature_grid_eV"] = ["1", "2"]
    for item in request_body["channels"]:
        item["energy_min_eV"] = "800"
        item["energy_max_eV"] = None
    for row in request_body["observations"]:
        row["current_A"] = "0"
        row["sigma_A"] = "1e-15"
    request_body["noise"]["sigma_grid_A"] = ["1e-15"]
    instrument = Instrument.model_validate(request_body["instrument"])
    measurement = Channel.model_validate(request_body["channels"][0])
    unit_density_signal = predict_current({"density_m3": 1, "temperature_eV": 2}, measurement, instrument)
    assert 0 < unit_density_signal < 1e-180
    assert (unit_density_signal / 1e-15)**2 == 0  # The former unscaled WLS denominator vanished.
    result = run(request_body)
    assert result["status"] == "completed" and result["failures"] == []
    assert all(fit["parameters"] for fit in result["fits"])
    assert "do not distinguish" in result["decision"]
    assert not result["noise_sweep"][0]["selected_channel_bands_separated_numerically"]


def test_changed_observations_change_computed_fit_with_same_description(request_body):
    original = run(request_body)
    changed = deepcopy(request_body)
    for row in changed["observations"]:
        row["current_A"] = format(1.5 * float(row["current_A"]), ".17g")
    result = run(changed)
    assert result["status"] == "completed"
    assert result["input_digest"] != original["input_digest"]
    original_fit, changed_fit = (fits_by_model(item)[ANISOTROPIC] for item in (original, result))
    assert float(changed_fit["parameters"]["density_m3"]) == pytest.approx(
        1.5 * float(original_fit["parameters"]["density_m3"]), rel=1e-12,
    )
    assert changed_fit["parameters"]["parallel_eV"] == original_fit["parameters"]["parallel_eV"]
    assert changed_fit["parameters"]["perpendicular_eV"] == original_fit["parameters"]["perpendicular_eV"]
    for before, after in zip(original_fit["predictions"], changed_fit["predictions"], strict=True):
        assert float(after["predicted_A"]) == pytest.approx(1.5 * float(before["predicted_A"]), rel=1e-12)
    assert result["settings"] != original["settings"]


def test_seeded_simulation_repeats_and_reports_counts_and_sampling_uncertainty(request_body):
    first, second = run(request_body), run(request_body)
    assert first["simulation_seed"] == request_body["noise"]["seed"]
    assert first["simulation_samples"] == request_body["noise"]["samples"]
    assert first["noise_sweep"] == second["noise_sweep"]
    assert first["fits"] == second["fits"]
    for simulation in all_simulations(first):
        assert simulation["generating_model_id"] in (ISOTROPIC, ANISOTROPIC)
        samples = simulation["samples"]
        assert samples == request_body["noise"]["samples"] and simulation["failures"] == 0
        assert sum(item["count"] for item in simulation["outcomes"].values()) == samples
        for outcome in simulation["outcomes"].values():
            fraction = outcome["count"] / samples
            assert float(outcome["frequency"]) == pytest.approx(fraction, abs=1e-14)
            low, high = map(float, outcome["wilson_95"])
            assert 0 <= low <= fraction + 1e-14 and fraction - 1e-14 <= high <= 1
            assert high > low  # Even zero/all successes retain finite simulation uncertainty.
    request_body["noise"]["seed"] += 1
    different_seed = run(request_body)
    assert different_seed["fits"] == first["fits"]
    assert different_seed["noise_sweep"] != first["noise_sweep"]
    assert "no parameter refit" in first["methods"]["simulation"]
    assert any("probability a model is true" in item for item in first["limitations"])


def test_missing_response_is_unsupported_without_fabricating_predictions(request_body):
    request_body["instrument"] = None
    result = run(request_body)
    assert result["status"] == "unsupported"
    assert result["fits"] == [] and result["settings"] == [] and result["noise_sweep"] == []
    assert result["failures"][0]["code"] == "missing_instrument_response"


@pytest.mark.parametrize("tiny_sigma_scope", ["reviewed_observations", "noise_sweep"])
def test_large_currents_with_unresolvable_noise_are_honestly_unsupported(request_body, tiny_sigma_scope):
    request_body["instrument"]["area_m2"] = "0.1"
    request_body["fit"]["density_min_m3"] = "1e18"
    request_body["fit"]["density_max_m3"] = "1e20"
    replace_observations_with_forward_means(
        request_body, {"density_m3": 1e19, "parallel_eV": 4, "perpendicular_eV": 16},
    )
    for row in request_body["observations"]:
        row["sigma_A"] = "1e-15" if tiny_sigma_scope == "reviewed_observations" else "1"
    request_body["noise"]["sigma_grid_A"] = ["1e-15" if tiny_sigma_scope == "noise_sweep" else "1"]
    largest_current = max(abs(float(row["current_A"])) for row in request_body["observations"])
    assert math.ulp(largest_current) > 1e-15
    result = run(request_body)
    assert result["status"] == "unsupported"
    assert any(failure["code"] == "numerical_resolution" for failure in result["failures"])
    assert result["noise_sweep"] == []


@pytest.mark.parametrize("limit", ["fit_evaluations", "simulation_work"])
def test_declared_and_service_budgets_stop_before_partial_scientific_results(request_body, limit):
    if limit == "fit_evaluations":
        points = len(request_body["fit"]["temperature_grid_eV"])
        request_body["fit"]["max_evaluations"] = points + points*points - 1
    else:
        request_body["noise"]["samples"] = 1024
        request_body["noise"]["sigma_grid_A"] = [str(10**power) for power in range(-12, -4)]
        request_body["noise"]["z_thresholds"] = ["1", "2", "3", "4"]
    result = run(request_body)
    assert result["status"] == "budget_exceeded"
    assert result["fits"] == [] and result["settings"] == [] and result["noise_sweep"] == []
    assert result["failures"][0]["code"] == "declared_or_service_work_limit"


def test_only_selected_rows_enter_fit_without_losing_source_rows_or_identity(request_body):
    request_body["selected_channel_ids"] = ["a90_e8", "a0_e0", "a90_e0", "a0_e8"]
    for row in request_body["observations"]:
        if row["channel_id"] not in request_body["selected_channel_ids"]:
            row["current_A"] = "-1"  # Deliberately incompatible, explicitly unselected.
    result = run(request_body)
    assert result["status"] == "completed"
    expected_indices = [index for index, row in enumerate(request_body["observations"])
                        if row["channel_id"] in request_body["selected_channel_ids"]]
    for fit in result["fits"]:
        assert [row["observation_index"] for row in fit["predictions"]] == expected_indices
        assert {row["channel_id"] for row in fit["predictions"]} == set(request_body["selected_channel_ids"])
        assert len(fit["predictions"]) == 4
    assert fits_by_model(result)[ANISOTROPIC]["adequate_under_declared_threshold"] is True
    included = deepcopy(request_body)
    included["selected_channel_ids"] = [item["id"] for item in included["channels"]]
    included_result = run(included)
    assert included_result["status"] == "fit_failed"
    assert included_result["input_digest"] != result["input_digest"]


def test_one_angle_fit_reports_parameter_degeneracy(request_body):
    # Repeat independent observations at the existing 0-degree channels so
    # residual degrees of freedom exist, while angular information does not.
    request_body["selected_channel_ids"] = ["a0_e0", "a0_e8"]
    repeated = [deepcopy(row) for row in request_body["observations"] if row["channel_id"].startswith("a0_")]
    request_body["observations"].extend(repeated)
    result = run(request_body)
    assert result["status"] == "completed"
    anisotropic = fits_by_model(result)[ANISOTROPIC]
    assert anisotropic["rank_deficient"] is True and anisotropic["rank_estimate"] < 3
    assert all(not case["selected_channel_bands_separated_numerically"] for case in result["noise_sweep"])


def test_numerical_recomputation_cannot_upgrade_verification_contract(request_body):
    result = run(request_body)
    assert result["status"] == "completed"
    assert any("floating-point" in item for item in result["limitations"])
    upgraded = deepcopy(result)
    upgraded["exact_verification"] = "passed"
    with pytest.raises(ValidationError):
        ModelComparisonResult.model_validate(upgraded)
    assert math.isfinite(float(fits_by_model(result)[ANISOTROPIC]["rmse_A"]))


@pytest.mark.parametrize("value", ["1e999", "-1e999", "NaN", "Infinity"])
@pytest.mark.parametrize("field", ["predicted_A", "chi_square", "parameter"])
def test_returned_scientific_numbers_must_be_finite_binary64(request_body, value, field):
    result = run(request_body)
    if field == "predicted_A":
        result["fits"][0]["predictions"][0][field] = value
    elif field == "parameter":
        result["fits"][0]["parameters"]["density_m3"] = value
    else:
        result["fits"][0][field] = value
    with pytest.raises(ValidationError):
        ModelComparisonResult.model_validate(result)
