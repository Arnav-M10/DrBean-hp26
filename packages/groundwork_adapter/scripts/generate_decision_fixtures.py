#!/usr/bin/env python3
"""Execute the controlled decision loop through the actual local bridge.

All measurements are transparently synthetic. The main loop discovers vectors
from the supplied rows. Fixed-vector audit oracles occur only in the separately
labeled regression controls below. No provider, credential or network is used.
"""

from copy import deepcopy
from decimal import Decimal, localcontext
from fractions import Fraction
import base64
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_application import application_records
from counterdex.bridge import PROTOCOL, transport_bytes, transport_loads
from counterdex.exact import artifact_digest, canonical_bytes, rational_text, semantic_digest, strict_json_loads
from counterdex.identity import implementation_identity
from counterdex.models import normalize_design, normalize_problem
from counterdex.pipeline import create_suggestion
from counterdex.replay import replay_bundle

DESTINATION = ROOT / "fixtures" / "decision"
LIMITS = {"wall_seconds": 120, "max_bundle_bytes": 4 * 1024 * 1024}


def decimal_text(value: str | Fraction) -> str:
    exact = Fraction(value)
    with localcontext() as context:
        context.prec = 100
        return format(Decimal(exact.numerator) / Decimal(exact.denominator), ".6f")


def scalar(value: str | Fraction | None, unit: str | None = None) -> dict | None:
    if value is None:
        return None
    exact = Fraction(value)
    result = {"exact": rational_text(exact), "decimal_6_places": decimal_text(exact)}
    if unit is not None:
        result["unit"] = unit
    return result


def write_json(name: str, value: dict) -> None:
    (DESTINATION / name).write_bytes(transport_bytes(value) + b"\n")


def workflow(name: str) -> dict:
    return {key: "controlled-" + name + "-" + key for key in ("plan_id", "approval_id", "operation_id", "execution_id")}


def bridge(request: dict) -> tuple[dict, str]:
    started = time.monotonic()
    process = subprocess.run([sys.executable, "-m", "counterdex.bridge"],
        input=transport_bytes(request), capture_output=True, timeout=125,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT), "PYTHONNOUSERSITE": "1"})
    elapsed = format(time.monotonic() - started, ".6f")
    response = transport_loads(process.stdout)
    if process.returncode != 0 or response.get("ok") is not True:
        raise RuntimeError(f"Controlled {request['operation']} failed: {response.get('error')}")
    return response, elapsed


def rebind(problem: dict, dataset: dict) -> None:
    dataset["digest"] = semantic_digest("dataset", dataset["body"])
    problem["body"]["dataset_id"] = dataset["id"]
    problem["body"]["dataset_digest"] = dataset["digest"]
    problem["digest"] = semantic_digest("problem", problem["body"])


def historical_artifact(response: dict) -> dict:
    artifact = response["native_artifacts"][0]
    return {key: artifact[key] for key in ("id", "sha256", "bytes_base64")} | {"anchors": response["anchors"]}


def investigate_request(name: str, problem: dict, dataset: dict) -> dict:
    return {"protocol": PROTOCOL, "operation": "investigate", "problem": problem, "dataset": dataset,
            "run_id": "run-" + name, "scenario_id": "scenario-" + name, "workflow": workflow(name),
            "limits": LIMITS, "search_settings": None}


def design_request(name: str, baseline_request: dict, baseline: dict) -> dict:
    candidates = baseline["result"]["candidates"]
    if len(candidates) != 2 or any(candidate["verification"] != "valid" for candidate in candidates):
        raise RuntimeError("This controlled design requires two actually discovered compatible vectors")
    problem = baseline_request["problem"]
    request = {"schema_version": "DB-SC-1", "historical_run_id": baseline_request["run_id"],
        "scenario_id": baseline_request["scenario_id"], "problem_id": problem["id"], "problem_digest": problem["digest"],
        "candidate_ids": [c["id"] for c in candidates], "candidate_vectors": [c["parameter_vector"] for c in candidates],
        "observable": "concentration", "feasible_times": ["8/1", "6/1"], "future_hard_allowance": "1/5",
        "allow_construction": True, "allow_continuation": True,
        "budget": {"wall_seconds": 120, "fixed_vector_constructions": 2, "pair_verifications": 2, "bundle_bytes": 4194304}}
    evidence = {"run_id": baseline_request["run_id"], "scenario_id": baseline_request["scenario_id"],
        "problem_id": problem["id"], "expected_problem_digest": problem["digest"],
        "result": baseline["result"], "arrived_after_cancel": False}
    return {"protocol": PROTOCOL, "operation": "design", "problem": problem, "dataset": baseline_request["dataset"],
        "run_id": "run-" + name, "workflow": workflow(name), "request": request,
        "expected_request_digest": semantic_digest("design-request", request), "historical_evidence": evidence,
        "historical_artifact": historical_artifact(baseline)}


def review_request(name: str, original: dict, design: dict, reading: str) -> dict:
    problem, dataset = deepcopy(original["problem"]), deepcopy(original["dataset"])
    dataset["id"] = "dataset-" + name
    dataset["body"]["parent_id"] = original["dataset"]["id"]
    dataset["body"]["origin"] = "hypothetical"
    dataset["body"]["change_reason"] = "Append one hypothetical reading at the actual checked selected time; original rows preserved"
    time = design["result"]["selected_time"]
    allowance = design["result"]["future_hard_allowance"]
    dataset["body"]["rows"].append({"id": "row-" + name, "time": time,
        "concentration": rational_text(Fraction(reading)), "hard_allowance": allowance, "included": True,
        "original_values": {"time": decimal_text(time), "concentration": reading}, "source_asset_id": None,
        "notes": "Hypothetical follow-up; not an acquired measurement"})
    problem["id"] = "problem-" + name
    rebind(problem, dataset)
    return {"protocol": PROTOCOL, "operation": "review", "problem": problem, "dataset": dataset,
        "run_id": "run-" + name, "scenario_id": original["scenario_id"], "workflow": workflow(name),
        "limits": LIMITS, "historical_artifact": historical_artifact(design)}


def display(request: dict, response: dict) -> dict:
    details = response["details"]
    checked = details["scientific_report"]["checked"]
    result = {"label": "Controlled synthetic scientific result; no acquired measurements or live AI",
              "operation": request["operation"], "dataset_origin": details["dataset_origin"],
              "problem_digest": request["problem"]["digest"], "artifact_sha256": response["anchors"]["artifact_sha256"],
              "replay": response["result"]["replay"], "display_rounding": "Six decimal places only; exact values and native checks control every verdict",
              "observations": [{"id": row["id"], "time": scalar(row["time"], "h"),
                  "concentration": scalar(row["concentration"], "mg/L"), "allowance": scalar(row["hard_allowance"], "mg/L"),
                  "included": row["included"], "notes": row["notes"]} for row in request["dataset"]["body"]["rows"]]}
    result["candidate_results"] = []
    for candidate in checked["candidate_results"] if checked else []:
        row = {key: value for key, value in candidate.items() if key not in ("parameters", "rows")}
        if "parameters" in candidate:
            row["parameters"] = {key: scalar(value, "mg/L" if key == "A" else "1/h") for key, value in candidate["parameters"].items()}
        row["rows"] = []
        for observed in candidate.get("rows", []):
            value = {key: item for key, item in observed.items() if key not in
                     ("time", "lower", "upper", "measurement", "allowance", "residual_lower", "residual_upper")}
            value.update({key: scalar(observed[key], "h" if key == "time" else "mg/L") for key in
                          ("time", "lower", "upper", "measurement", "allowance", "residual_lower", "residual_upper")})
            if observed["lower"] is not None:
                value["prediction_center"] = scalar((Fraction(observed["lower"]) + Fraction(observed["upper"])) / 2, "mg/L")
            row["rows"].append(value)
        result["candidate_results"].append(row)
    if request["operation"] == "design":
        result.update(design_tier=response["result"]["design_tier"], selected_time=scalar(response["result"]["selected_time"], "h"),
                      future_hard_allowance=scalar(response["result"]["future_hard_allowance"], "mg/L"))
        result["future_rows"] = [{"time": scalar(row["time"], "h"), "status": row["status"],
            "reason_code": row["reason_code"], "margin": scalar(row["margin"], "mg/L"), "separated": row["separated"],
            "predictions": {cid: {"center": scalar(value, "mg/L"), "error": scalar(row["errors"][cid], "mg/L"),
                "possible_reading_band": [scalar(endpoint, "mg/L") for endpoint in row["bands"][cid]]}
                for cid, value in (row["centers"] or {}).items()}} for row in checked["rows"]]
    else:
        result.update(outcome=details["scientific_report"]["outcome"], search=details["search"], exact_trials=details["exact_trials"])
    return result


def execute(name: str, request: dict, entries: list[dict]) -> tuple[dict, dict]:
    response, elapsed = bridge(request)
    artifact = response["native_artifacts"][0]
    native = base64.b64decode(artifact["bytes_base64"], validate=True)
    replay_request = {"protocol": PROTOCOL, "operation": "replay", "native_artifact_base64": artifact["bytes_base64"],
                      "expected": response["anchors"]}
    replay, replay_elapsed = bridge(replay_request)
    if replay["result"]["replay"] != "passed":
        raise RuntimeError("Controlled native artifact did not freshly replay")
    readable = display(request, response)
    for suffix, value in (("request", request), ("response", response), ("anchors", response["anchors"]),
                          ("replay-request", replay_request), ("replay", replay), ("display", readable)):
        write_json(f"{name}.{suffix}.json", value)
    (DESTINATION / f"{name}.native.json").write_bytes(native)
    checked = response["details"]["scientific_report"]["checked"]
    search = response["details"]["search"]
    entries.append({"name": name, "operation": request["operation"], "provenance": "controlled synthetic inputs",
        "actual_execution": "CPython 3.11 bridge subprocess plus a separate bridge replay subprocess",
        "elapsed_seconds_diagnostic": elapsed, "replay_elapsed_seconds_diagnostic": replay_elapsed,
        "artifact_bytes": len(native), "artifact_sha256": artifact_digest(native), "anchors": response["anchors"],
        "replay": replay["result"]["replay"], "scientific_outcome": response["result"].get("scientific_outcome"),
        "design_tier": response["result"].get("design_tier"), "selected_time": response["result"].get("selected_time"),
        "search_counts": None if search is None else {key: search[key] for key in ("attempted_count", "evaluated_count", "feasible_count", "retained_count", "possible_count")},
        "exact_candidate_trials": len(response["details"]["exact_trials"] or []),
        "fixed_vector_construction_attempts": checked.get("construction_attempts") if checked else None,
        "pair_verification_passes_in_scientific_design": checked.get("pair_verification_passes") if checked else None})
    return response, readable


def fixed_pair_controls(problem_payload: dict) -> list[dict]:
    """The supplied audit vectors are oracles only, never discovery inputs."""
    problem = normalize_problem(problem_payload)
    vectors = (("audit-reference", ("9.041075603155", "0.122", "3.54")),
               ("audit-outside", ("8.267973235218", "0.074", "4.17")))
    results = []
    for name, grid, allowance, selected in (("fixed-pair-8h", ["6/1", "8/1"], "1/5", "8/1"),
                                           ("fixed-pair-6h-only", ["6/1"], "1/5", "6/1"),
                                           ("fixed-pair-wide-allowance", ["6/1", "8/1"], "3/5", None)):
        design = normalize_design({"schema_version": "groundwork.design.v1", "problem_digest": problem.digest,
            "scenario_id": "controlled-audit-fixed-pair", "candidates": [
                {"id": cid, "problem_digest": problem.digest, "parameters": {k: rational_text(Fraction(v)) for k, v in zip(("A", "ke", "ka"), vector)},
                 "source_artifact_digest": None} for cid, vector in vectors],
            "grid": [{"time": t, "feasible": True, "reason": "Reviewed synthetic constraint control"} for t in grid],
            "time_origin": problem.time_origin, "observable": "c", "future_allowance": allowance,
            "allowance_origin": {"kind": "hypothetical", "description": "Synthetic fixed-pair regression allowance"},
            "requested_tier": "checked_pair_separation", "horizon_policy": {"allow_construction": True, "allow_extension": True, "maximum_horizon": max(grid, key=Fraction)},
            "numerical_policy": "pair-gap-over-allowance-12sig-half-even.v1", "checked_policy": "positive-margin-descending-time-ids.v1",
            "limits": {"wall_seconds": 120, "max_times": len(grid), "max_constructions": 2, "max_pair_verifications": 2,
                       "max_bundle_bytes": 4194304, "max_certificate_bytes": 2097152}}, problem)
        request = {"problem": problem.to_payload(), "design": design.to_payload(), "workflow": workflow(name)}
        started = time.monotonic()
        content = create_suggestion(problem.to_payload(), design.to_payload(), workflow=request["workflow"],
            expected_problem_digest=problem.digest, expected_design_digest=design.digest)
        bundle = strict_json_loads(content)
        replay = replay_bundle(content, expected_problem_digest=problem.digest, expected_suggestion_digest=bundle["suggestion_digest"])
        elapsed = format(time.monotonic() - started, ".6f")
        checked = replay["fresh_checked"]
        if checked["selected_time"] != selected or replay["replay"] != "passed" or checked["verification"] != "valid":
            raise RuntimeError("A fixed-pair regression control failed its exact oracle")
        for row in checked["rows"]:
            expected = {"6/1": ("0.55534", "0.55536"), "8/1": ("0.76718", "0.76720")}[row["time"]]
            delta = Fraction(0) if allowance == "1/5" else Fraction("0.8")
            if not Fraction(expected[0]) < Fraction(row["margin"]) + delta < Fraction(expected[1]):
                raise RuntimeError("A fixed-pair margin did not match its independent narrow audit interval")
        if selected is None and (checked["tier"] != "no_separation_established" or any(row["separated"] for row in checked["rows"])):
            raise RuntimeError("Wide-allowance control must retain valid compatibility without separated times")
        anchors = {"problem_digest": problem.digest, "design_digest": design.digest, "suggestion_digest": bundle["suggestion_digest"]}
        readable = {"label": "Fixed audit vector regression control, not a discovered production result", "anchors": anchors,
            "grid": grid, "future_allowance": scalar(allowance, "mg/L"), "selected_time": scalar(selected, "h"), "tier": checked["tier"],
            "rows": [{"time": scalar(row["time"], "h"), "margin": scalar(row["margin"], "mg/L"), "separated": row["separated"],
                "bands": {cid: [scalar(endpoint, "mg/L") for endpoint in band] for cid, band in row["bands"].items()}} for row in checked["rows"]]}
        for suffix, value in (("engine-input", request), ("anchors", anchors), ("replay", replay), ("display", readable)):
            write_json(f"{name}.{suffix}.json", value)
        (DESTINATION / f"{name}.bundle.json").write_bytes(content)
        results.append({"name": name, "elapsed_seconds_diagnostic": elapsed, "artifact_bytes": len(content),
                        "artifact_sha256": artifact_digest(content), "anchors": anchors, "display": readable})
    return results


def record_documented_run(manifest: dict) -> None:
    """Keep observed timing/source metadata synchronized with generated bytes."""
    destination = ROOT / "docs" / "DECISION_EXAMPLE.md"
    text = destination.read_text(encoding="utf-8")
    start = "<!-- decision-run:start -->"
    end = "<!-- decision-run:end -->"
    identity = manifest["implementation"]
    lines = [start, "## Recorded local execution", "",
        f"The current fixtures were generated with Counterdex {identity['adapter_version']} on CPython {manifest['python']}. "
        f"The engine source digest is `{identity['source_digest']}`. "
        "Seven scientific bridge subprocesses and seven separate replay subprocesses completed; all replayed successfully. "
        "Three separately labeled fixed-pair controls also freshly replayed.", "",
        "| Operation | Observed bridge seconds | Observed separate replay seconds | Native bytes |",
        "|---|---:|---:|---:|"]
    for entry in manifest["bridge_executions"]:
        lines.append(f"| `{entry['name']}` | {entry['elapsed_seconds_diagnostic']} | {entry['replay_elapsed_seconds_diagnostic']} | {entry['artifact_bytes']} |")
    lines += ["", "These are measured local runs with no provider requests. The complete per-operation counters, "
              "source manifest and exact artifact hashes are retained in `fixtures/decision/manifest.json`; "
              "latencies are not an HTTP result or a general performance guarantee.", end]
    recorded = "\n".join(lines) + "\n"
    if start in text and end in text:
        prefix, remainder = text.split(start, 1)
        _, suffix = remainder.split(end, 1)
        text = prefix + recorded + suffix.lstrip("\n")
    else:
        text = text.rstrip() + "\n\n" + recorded
    destination.write_text(text, encoding="utf-8")


def main() -> None:
    DESTINATION.mkdir(parents=True, exist_ok=True)
    identity = implementation_identity()
    entries = []
    problem, dataset = application_records()
    original = investigate_request("hero-baseline", problem, dataset)
    baseline, baseline_display = execute("hero-baseline", original, entries)
    design_input = design_request("hero-design", original, baseline)
    design, design_display = execute("hero-design", design_input, entries)
    if design["result"]["selected_time"] is None:
        raise RuntimeError("The actual discovered pair has no separating time; update the controlled task without forcing a result")
    selected = next(row for row in design["details"]["scientific_report"]["checked"]["rows"] if row["time"] == design["result"]["selected_time"])
    positions = {c["candidate_id"]: c for c in baseline["details"]["scientific_report"]["checked"]["candidate_results"]}
    reference_id = next(cid for cid, c in positions.items() if not c["outside_closed_claim"])
    outside_id = next(cid for cid, c in positions.items() if c["outside_closed_claim"])
    reference_reading = decimal_text(selected["centers"][reference_id])
    outside_reading = decimal_text(selected["centers"][outside_id])
    ordered_bands = sorted(selected["bands"].values(), key=lambda band: Fraction(band[0]))
    between_bands = decimal_text((Fraction(ordered_bands[0][1]) + Fraction(ordered_bands[1][0])) / 2)
    feedback = {}
    for name, reading, expected_valid in (("hero-reference-survives", reference_reading, [reference_id]),
                                         ("hero-outside-survives", outside_reading, [outside_id]),
                                         ("hero-both-excluded", between_bands, [])):
        response, readable = execute(name, review_request(name, original, design, reading), entries)
        valid = [c["id"] for c in response["result"]["candidates"] if c["verification"] == "valid"]
        if sorted(valid) != sorted(expected_valid):
            raise RuntimeError("Hypothetical reading did not produce the stated candidate-specific feedback")
        feedback[name] = {"reading": scalar(reading, "mg/L"), "valid_candidate_ids": valid, "display": readable}
    alternate_problem, alternate_dataset = deepcopy(problem), deepcopy(dataset)
    alternate_problem["id"], alternate_dataset["id"] = "problem-alternate", "dataset-alternate"
    alternate_dataset["body"]["parent_id"] = dataset["id"]
    alternate_dataset["body"]["rows"][-1]["concentration"] = "53/10"
    alternate_dataset["body"]["rows"][-1]["original_values"]["concentration"] = "5.30"
    alternate_dataset["body"]["change_reason"] = "Controlled synthetic alternative: reviewed 4-hour value is 5.30 instead of 5.70 mg/L"
    rebind(alternate_problem, alternate_dataset)
    alternate_input = investigate_request("alternate-baseline", alternate_problem, alternate_dataset)
    alternate, alternate_display = execute("alternate-baseline", alternate_input, entries)
    alternate_design, alternate_design_display = execute("alternate-design", design_request("alternate-design", alternate_input, alternate), entries)
    native = strict_json_loads(base64.b64decode(baseline["native_artifacts"][0]["bytes_base64"]))
    projection_problem = native["binding"]["projection_digest"]
    scientific = strict_json_loads(base64.b64decode(native["scientific"]["bytes_base64"]))
    controls = fixed_pair_controls(scientific["problem"])
    curves = []
    for candidate in baseline_display["candidate_results"]:
        cid = candidate["candidate_id"]
        points = [{"time": row["time"], "center": row["prediction_center"], "lower": row["lower"], "upper": row["upper"],
                   "source": "fresh historical certificate"} for row in candidate["rows"] if row["included"]]
        for row in design_display["future_rows"]:
            prediction = row["predictions"][cid]
            center, error = Fraction(prediction["center"]["exact"]), Fraction(prediction["error"]["exact"])
            points.append({"time": row["time"], "center": prediction["center"], "lower": scalar(center - error, "mg/L"),
                           "upper": scalar(center + error, "mg/L"), "source": "fresh selected-pair certificate"})
        curves.append({"candidate_id": cid, "parameters": candidate["parameters"], "points": points,
                       "interpolation_scope": "Only listed points are exported; connecting them is a display aid"})
    summary = {"label": "Controlled synthetic feature comparison, not an evaluation of all scientific software",
        "model": "c(t) = A(exp(-ke*t) - exp(-ka*t)); fixed initial state; hours and mg/L",
        "source_identity": identity, "projection_digest": projection_problem,
        "reference_candidate_id": reference_id, "outside_candidate_id": outside_id,
        "both_candidate_curves": curves,
        "contributions": [
            {"component": "Numerical reference fit", "result": "A retained inside-claim grid fit and per-row residuals", "adds": "An explicit explanation of the reviewed readings; no confidence interval assertion", "evidence": "hero-baseline.display.json"},
            {"component": "Exact outside witness", "result": baseline["result"]["scientific_outcome"], "adds": "The closed claim is not forced by these reviewed hard bounds under this model", "evidence": "hero-baseline.native.json"},
            {"component": "Reviewed finite-grid measurement", "result": design["result"]["design_tier"], "adds": "A separately approved allowance and grid yield a pair-specific strict positive margin", "evidence": "hero-design.display.json"},
            {"component": "Hypothetical follow-up", "result": "reference-only, outside-only and both-excluded outcomes freshly replay", "adds": "Candidate-specific feedback while preserving the original run and assumptions", "evidence": "hero-reference-survives.display.json"}],
        "hero": {"baseline": baseline_display, "design": design_display, "followup": feedback},
        "alternate": {"changed_input": "4-hour concentration 5.70 → 5.30 mg/L; all original hard allowances stay 0.50 mg/L",
                      "baseline": alternate_display, "design": alternate_design_display},
        "limitations": "Finite deterministic grid only; no search completeness, whole-model impossibility, confidence interval, global experiment optimum, actual experiment or live-model claim."}
    write_json("decision-summary.json", summary)
    if identity != implementation_identity():
        raise RuntimeError("Engine source changed during generation; rerun after source edits finish")
    manifest = {"schema_version": "groundwork.decision-fixtures.v1", "command": "python3.11 packages/groundwork_adapter/scripts/generate_decision_fixtures.py",
        "python": platform.python_version(), "platform": platform.platform(), "implementation": identity,
        "provider_calls": 0, "provider_mode": "disabled; no AI generation in these scientific fixtures",
        "provenance": "Controlled synthetic experiment and hypothetical follow-up readings; no actual collection or literature validation",
        "bridge_executions": entries, "fixed_pair_regression_controls": controls,
        "timing_scope": "Observed local subprocess latency, not a throughput guarantee or an HTTP integration result"}
    write_json("manifest.json", manifest)
    record_documented_run(manifest)
    print(f"Generated {len(entries)} actual bridge executions with fresh offline replay and {len(controls)} fixed-pair controls.")
    print(f"Hero: {design['result']['design_tier']} at {design['result']['selected_time']}; alternate: {alternate_design['result']['design_tier']} at {alternate_design['result']['selected_time']}.")


if __name__ == "__main__":
    main()
