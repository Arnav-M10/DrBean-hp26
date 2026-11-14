"""Single-request stdin/stdout protocol for a server-selected CPython 3.11.

No command, import, URL, path, credential or model service comes from evidence.
The parent owns approval and hard process-group termination (see BRIDGE.md).
"""
import base64
import json
import sys

from .application import project_application, project_design, restore_approved_grid
from .errors import AdapterError
from .exact import (MAX_JSON_DEPTH, MAX_JSON_NODES, MAX_STRUCTURAL_INTEGER,
                    _preflight, _validate_tree, artifact_digest, strict_json_loads)
from .identity import VERSION, implementation_identity
from .models import counter, fields, normalize_problem
from .native_packet import ANCHOR_FIELDS, packet_anchors, packet_bytes, replay_packet, validate_followup
from .replay_baseline import decode_artifact
from .resource import ExecutionContext

PROTOCOL = "counterdex.bridge.v1"
TRANSPORT_CAP = 12 * 1024 * 1024


def transport_loads(data: bytes) -> dict:
    """A distinct transport cap covers base64; scientific JSON stays at 4 MiB."""
    if type(data) is not bytes or len(data) > TRANSPORT_CAP:
        raise AdapterError("resource_exhaustion", "Bridge request exceeds its transport byte cap.")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise AdapterError("invalid_input", "Bridge input must be UTF-8 JSON.") from None
    _preflight(text, MAX_JSON_DEPTH, MAX_JSON_NODES)
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise AdapterError("invalid_input", "Duplicate bridge JSON fields are not admitted.")
            result[key] = value
        return result
    def integer(token):
        if token.startswith("-") or len(token) > 16 or int(token) > MAX_STRUCTURAL_INTEGER:
            raise AdapterError("invalid_input", "Bridge counters must be nonnegative safe integers.")
        return int(token)
    def reject_number(_):
        raise AdapterError("invalid_input", "Scientific scalars must be exact strings.")
    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_int=integer,
                           parse_float=reject_number, parse_constant=reject_number)
    except (ValueError, RecursionError) as error:
        if isinstance(error, AdapterError):
            raise
        raise AdapterError("invalid_input", "Malformed bridge JSON.") from None
    _validate_tree(value, MAX_JSON_DEPTH, MAX_JSON_NODES)
    if type(value) is not dict:
        raise AdapterError("invalid_input", "Expected a bridge request object.")
    return value


def transport_bytes(value: dict) -> bytes:
    _validate_tree(value, MAX_JSON_DEPTH, MAX_JSON_NODES)
    content = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
    if len(content) > TRANSPORT_CAP:
        raise AdapterError("resource_exhaustion", "Bridge response exceeds its transport byte cap.")
    return content


def _artifact(content: bytes) -> dict:
    digest = artifact_digest(content)
    return {"id": "native-" + digest[:24], "sha256": digest, "byte_size": len(content),
            "media_type": "application/vnd.counterdex.native+json", "bytes_base64": base64.b64encode(content).decode("ascii")}


def _verification(ref, app_problem, verification, proposition):
    return {"checker_name": "counterdex", "checker_version": VERSION, "artifact_id": ref["id"],
            "artifact_sha256": ref["sha256"], "proposition": proposition,
            "verification": verification, "expected_binding": "matches",
            "expected_problem_digest": app_problem["digest"], "observed_problem_digest": app_problem["digest"]}


def _baseline_result(projection, scientific, fresh, ref):
    app = projection["binding"]["problem"]
    checked = fresh["candidate_results"]
    verification = "valid" if fresh["replay"] == "passed" else "not_checked"
    outcome = fresh["outcome"]
    return {"scientific_outcome": outcome["scientific_outcome"], "verification": verification,
        "expected_binding": "matches", "replay": fresh["replay"], "reason_code": outcome["reason_code"],
        "problem_id": app["id"], "problem_digest": app["digest"],
        "candidates": [{"id": c["candidate_id"], "parameter_vector": c["parameters"],
            "problem_id": app["id"], "problem_digest": app["digest"], "observable": "concentration",
            "checked_horizon": scientific["report"]["checked"]["historical_horizon"],
            "verification": c["verification"], "artifact_ids": [ref["id"]]} for c in checked],
        "artifacts": [ref], "verification_record": _verification(ref, app, verification,
            "Exact enclosure recomputation checks these selected fixed vectors against every included hard bound and the closed claim; no search completeness is asserted.") if checked else None}


def _design_result(projection, mapping, scientific, fresh, ref):
    report = scientific["report"]
    checked = fresh.get("fresh_checked", {})
    valid = checked.get("verification") == "valid" and fresh["replay"] == "passed"
    grid = checked.get("rows") if valid else report["numerical"]["rows"]
    options = [{"time": row["time"], "state": row["status"],
                "reason_code": row["reason_code"] or ("exact_margin_checked" if valid else "numerical_only"),
                "exact_margin": row.get("margin") if valid else None} for row in grid]
    return {"design_tier": checked["tier"] if valid else report["tier"],
        "verification": fresh["verification"], "replay": fresh["replay"],
        "reason_code": (checked.get("reason_code") or "strict_positive_margin") if valid else fresh["reason_code"],
        "selected_time": checked["selected_time"] if valid else report["numerical"]["selected_time"],
        "options": restore_approved_grid(options, mapping["approved_grid_order"]),
        "algorithm": scientific["design"]["checked_policy"] if valid else scientific["design"]["numerical_policy"],
        "candidate_ids": [c["id"] for c in scientific["design"]["candidates"]],
        "future_hard_allowance": scientific["design"]["future_allowance"], "artifacts": [ref],
        "verification_record": _verification(ref, projection["binding"]["problem"], fresh["verification"],
            "Fresh selected-pair compatibility and exact finite-grid margins under the separately reviewed future allowance.")}


def _limits(value):
    fields(value, {"wall_seconds", "max_bundle_bytes"}, "limits")
    return (counter(value["wall_seconds"], "limits/wall_seconds", 1, 120),
            counter(value["max_bundle_bytes"], "limits/max_bundle_bytes", 1, 4 * 1024 * 1024))


def dispatch(request: dict) -> dict:
    if type(request) is not dict or request.get("protocol") != PROTOCOL:
        raise AdapterError("invalid_input", "Unsupported bridge protocol.")
    operation = request.get("operation")
    common = {"protocol", "operation"}
    if operation == "handshake":
        fields(request, common, "request")
        from .capabilities import capabilities
        metadata = capabilities()
        qualified = metadata["runtime"]["qualified"]
        return {"protocol": PROTOCOL, "ok": True, "configured": None, "configuration_owner": "server",
            "available": True, "qualified": qualified, "implementation": implementation_identity() if qualified else None,
            "capabilities": metadata, "transport_bytes": TRANSPORT_CAP, "native_bundle_bytes": 4 * 1024 * 1024}
    implementation_identity()
    if operation == "replay":
        fields(request, common | {"native_artifact_base64", "expected"}, "request")
        expected = fields(request["expected"], ANCHOR_FIELDS, "expected")
        content = decode_artifact(request["native_artifact_base64"], expected["artifact_sha256"])
        return {"protocol": PROTOCOL, "ok": True, "result": replay_packet(content, expected=request["expected"])}
    scientific_fields = {"problem", "dataset"}
    if operation == "admission":
        fields(request, common | scientific_fields, "request")
        return {"protocol": PROTOCOL, "ok": True, "result": project_application(request["problem"], request["dataset"])}
    execution_fields = {"run_id", "workflow"}
    if operation == "investigate":
        fields(request, common | scientific_fields | execution_fields | {"scenario_id", "limits", "search_settings"}, "request")
    elif operation == "design":
        fields(request, common | scientific_fields | execution_fields | {"request", "expected_request_digest", "historical_evidence", "historical_artifact"}, "request")
    elif operation == "review":
        fields(request, common | scientific_fields | execution_fields | {"scenario_id", "limits", "historical_artifact"}, "request")
    else:
        raise AdapterError("invalid_input", "Unknown bridge operation.")
    projection = project_application(request["problem"], request["dataset"])
    history, mapping = None, None
    if operation == "design":
        if type(request["request"]) is not dict or type(request["request"].get("budget")) is not dict:
            raise AdapterError("invalid_input", "A normalized application design and budget are required.", ("request/budget",))
        budget = request["request"]["budget"]
        wall, maximum = _limits({"wall_seconds": budget.get("wall_seconds"), "max_bundle_bytes": budget.get("bundle_bytes")})
    else:
        wall, maximum = _limits(request["limits"])
    context = ExecutionContext(wall)
    if operation in ("design", "review"):
        history = fields(request["historical_artifact"], {"id", "sha256", "bytes_base64", "anchors"}, "historical_artifact")
        history_bytes = decode_artifact(history["bytes_base64"], history["sha256"])
        historical_packet = strict_json_loads(history_bytes)
        historical_fresh = replay_packet(history_bytes, expected=history["anchors"], context=context)
    if operation == "design":
        from .pipeline import create_suggestion
        if historical_packet["operation"] != "investigate" or historical_fresh["replay"] != "passed":
            raise AdapterError("incomplete_export", "Design requires a freshly replayed actual baseline.")
        mapping = project_design(request["request"], expected_request_digest=request["expected_request_digest"],
            projection=projection, historical_evidence=request["historical_evidence"], native_candidate_results=historical_fresh["candidate_results"])
        scenario = request["request"]["scenario_id"]
        native = create_suggestion(projection["problem"], mapping["design"], expected_problem_digest=projection["projection_digest"],
            expected_design_digest=mapping["design_digest"], workflow=request["workflow"], context=context)
        binding = mapping["binding"]
    else:
        from .baseline import create_baseline
        from .search import SearchSettings, normalize_search_settings
        frozen = None
        settings = SearchSettings(wall_seconds=wall).to_payload()
        if operation == "investigate" and request["search_settings"] is not None:
            settings = normalize_search_settings(request["search_settings"]).to_payload()
            if settings["wall_seconds"] > wall:
                raise AdapterError("invalid_input", "Search wall budget exceeds the approved operation budget.")
        if operation == "review":
            from .historical import normalize_candidates
            if historical_packet["operation"] != "design" or historical_fresh["replay"] != "passed":
                raise AdapterError("incomplete_export", "Follow-up requires the freshly replayed selected design.")
            source = strict_json_loads(decode_artifact(historical_packet["scientific"]["bytes_base64"], historical_packet["scientific"]["sha256"]))
            payloads = [{**candidate, "problem_digest": projection["projection_digest"], "source_artifact_digest": None}
                        for candidate in source["design"]["candidates"]]
            frozen = normalize_candidates(normalize_problem(projection["problem"]), payloads)
            validate_followup(projection["binding"], historical_packet,
                {"operation": "fixed_candidate_review", "candidates": payloads})
        scenario = request["scenario_id"]
        native = create_baseline(projection["problem"], expected_problem_digest=projection["projection_digest"],
            scenario_id=scenario, workflow=request["workflow"], settings=settings, context=context,
            max_bundle_bytes=maximum, frozen_candidates=frozen)
        binding = projection["binding"]
    packet = packet_bytes(operation, binding, native, run_id=request["run_id"], scenario_id=scenario, history=history, maximum=maximum)
    anchors = packet_anchors(packet)
    fresh = replay_packet(packet, expected=anchors, context=context)
    artifact = _artifact(packet)
    ref = {key: value for key, value in artifact.items() if key != "bytes_base64"}
    scientific = strict_json_loads(native)
    result = (_design_result(projection, mapping, scientific, fresh, ref) if operation == "design" else
              _baseline_result(projection, scientific, fresh, ref))
    return {"protocol": PROTOCOL, "ok": True, "result": result, "native_artifacts": [artifact], "anchors": anchors,
        "details": {"dataset_origin": projection["binding"]["dataset_origin"], "scientific_report": scientific["report"],
                    "search": scientific.get("search"), "exact_trials": scientific.get("exact_trials"), "fresh_replay": fresh}}


def main() -> int:
    try:
        # Parent supplies EOF and supervises both pipe caps and hard deadline.
        response = dispatch(transport_loads(sys.stdin.buffer.read(TRANSPORT_CAP + 1)))
        encoded = transport_bytes(response)
        code = 0
    except AdapterError as error:
        encoded = transport_bytes({"protocol": PROTOCOL, "ok": False, "error": error.to_dict()})
        code = 2
    except Exception:
        encoded = transport_bytes({"protocol": PROTOCOL, "ok": False,
            "error": {"code": "bridge_failure", "message": "Scientific bridge could not complete this request.", "field_paths": [], "retryable": False}})
        code = 2
    sys.stdout.buffer.write(encoded + b"\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
