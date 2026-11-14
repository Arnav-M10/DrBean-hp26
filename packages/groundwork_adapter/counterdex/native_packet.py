"""Application-bound native bytes and offline replay, with bounded lineage.

This module does not import the numerical search or design producers. A packet
is content-bound evidence, not an authorization record or a digital signature.
"""
import base64

from .application import (DESIGN_BINDING, MAPPING_POLICY,
                          verify_application_binding, verify_design_binding)
from .errors import AdapterError
from .exact import artifact_digest, canonical_bytes, strict_json_loads
from .models import counter, digest_value, fields, text_value
from .replay import replay_bundle
from .replay_baseline import decode_artifact, replay_baseline
from .resource import ExecutionContext

PACKET_PROFILE = "counterdex.application-bundle.v1"
ANCHOR_FIELDS = {"artifact_sha256", "dataset_digest", "problem_digest", "projection_digest",
                 "app_request_digest", "design_digest", "scenario_id", "run_id"}
PACKET_FIELDS = {"schema_version", "operation", "binding", "run_id", "scenario_id", "scientific", "history"}


def _object_with(value: object, required: set[str], path: str) -> dict:
    """Validate a nested container before selecting fields owned by its profile."""
    if type(value) is not dict or not required.issubset(value):
        raise AdapterError("invalid_input", "Required native evidence fields are missing or malformed.", (path,))
    return value


def _anchors(value: dict) -> dict:
    anchors = fields(value, ANCHOR_FIELDS, "expected")
    for key in ("artifact_sha256", "dataset_digest", "problem_digest", "projection_digest"):
        digest_value(anchors[key], "expected/" + key)
    for key in ("app_request_digest", "design_digest"):
        if anchors[key] is not None:
            digest_value(anchors[key], "expected/" + key)
    for key in ("scenario_id", "run_id"):
        text_value(anchors[key], "expected/" + key, identifier=True)
    return anchors


def _packet(value: dict) -> dict:
    packet = fields(value, PACKET_FIELDS, "packet")
    if packet["schema_version"] != PACKET_PROFILE or packet["operation"] not in ("investigate", "design", "review"):
        raise AdapterError("unsupported_model", "Unsupported native application packet profile.")
    for key in ("run_id", "scenario_id"):
        text_value(packet[key], "packet/" + key, identifier=True)
    scientific = fields(packet["scientific"], {"sha256", "bytes_base64"}, "packet/scientific")
    digest_value(scientific["sha256"], "packet/scientific/sha256")
    if type(scientific["bytes_base64"]) is not str:
        raise AdapterError("invalid_input", "Native artifact encoding must be base64 text.", ("packet/scientific/bytes_base64",))
    if packet["operation"] == "design":
        binding = fields(packet["binding"], {"schema_version", "mapping_policy", "application", "request",
            "request_digest", "historical_evidence", "design_digest", "approved_grid_order"}, "packet/binding")
        if binding["schema_version"] != DESIGN_BINDING or binding["mapping_policy"] != MAPPING_POLICY:
            raise AdapterError("unsupported_model", "Unsupported application design mapping policy.")
        digest_value(binding["request_digest"], "packet/binding/request_digest")
        digest_value(binding["design_digest"], "packet/binding/design_digest")
        _object_with(binding["request"], {"scenario_id", "historical_run_id"}, "packet/binding/request")
        _object_with(binding["historical_evidence"], {"run_id", "scenario_id", "result"}, "packet/binding/historical_evidence")
        _object_with(binding["historical_evidence"]["result"], {"artifacts"}, "packet/binding/historical_evidence/result")
        application = binding["application"]
    else:
        application = packet["binding"]
    # This also validates all identity-bearing source bodies before anchors are
    # selected. No stored projection digest is trusted merely for being present.
    verify_application_binding(application)
    if (packet["operation"] == "investigate") != (packet["history"] is None):
        raise AdapterError("incomplete_export", "Discovery has no parent; design and follow-up require complete parent evidence.")
    if packet["history"] is not None:
        history = fields(packet["history"], {"id", "sha256", "bytes_base64", "anchors"}, "packet/history")
        text_value(history["id"], "packet/history/id", identifier=True)
        digest_value(history["sha256"], "packet/history/sha256")
        if type(history["bytes_base64"]) is not str:
            raise AdapterError("invalid_input", "Historical artifact encoding must be base64 text.", ("packet/history/bytes_base64",))
        _anchors(history["anchors"])
    return packet


def packet_bytes(operation: str, binding: dict, scientific: bytes, *, run_id: str, scenario_id: str,
                 history: dict | None = None, maximum: int = 4 * 1024 * 1024) -> bytes:
    value = {"schema_version": PACKET_PROFILE, "operation": operation, "binding": binding,
             "run_id": text_value(run_id, "run_id", identifier=True),
             "scenario_id": text_value(scenario_id, "scenario_id", identifier=True),
             "scientific": {"sha256": artifact_digest(scientific), "bytes_base64": base64.b64encode(scientific).decode("ascii")},
             "history": history}
    _packet(value)
    encoded = canonical_bytes(value)
    if len(encoded) > maximum:
        raise AdapterError("resource_exhaustion", "Complete application evidence and lineage exceed the approved byte limit.")
    return encoded


def packet_anchors(content: bytes) -> dict:
    """Return export identities for the caller to persist independently of bytes."""
    p = _packet(strict_json_loads(content))
    b = p["binding"]["application"] if p["operation"] == "design" else p["binding"]
    return {"artifact_sha256": artifact_digest(content), "dataset_digest": b["dataset"]["digest"],
        "problem_digest": b["problem"]["digest"], "projection_digest": b["projection_digest"],
        "app_request_digest": p["binding"]["request_digest"] if p["operation"] == "design" else None,
        "design_digest": p["binding"]["design_digest"] if p["operation"] == "design" else None,
        "scenario_id": p["scenario_id"], "run_id": p["run_id"]}


def _history(packet: dict, context, depth: int) -> tuple[bytes, dict, dict]:
    if packet["history"] is None:
        raise AdapterError("incomplete_export", "The complete original native evidence is required.")
    h = fields(packet["history"], {"id", "sha256", "bytes_base64", "anchors"}, "history")
    text_value(h["id"], "history/id", identifier=True)
    content = decode_artifact(h["bytes_base64"], h["sha256"])
    anchors = _anchors(h["anchors"])
    if anchors["artifact_sha256"] != h["sha256"]:
        raise AdapterError("artifact_mismatch", "Historical raw bytes and independent reference disagree.")
    replay = replay_packet(content, expected=h["anchors"], context=context, _depth=depth + 1)
    return content, strict_json_loads(content), replay


def validate_followup(binding: dict, parent: dict, scientific: dict) -> None:
    """One appended hypothetical reading at the selected time/allowance.

    Original history, model, domain, target and elapsed-time convention remain
    exact. The application still owns revision creation and approval.
    """
    binding = verify_application_binding(binding)["binding"]
    parent = _packet(parent)
    scientific = _object_with(scientific, {"operation", "candidates"}, "scientific")
    if parent["operation"] != "design":
        raise AdapterError("wrong_specification_binding", "Follow-up requires the actual original design packet.")
    previous = parent["binding"]["application"]
    if binding["problem"]["id"] == previous["problem"]["id"]:
        raise AdapterError("wrong_specification_binding", "Follow-up must use a distinct application problem revision.")
    old, new = previous["dataset"], binding["dataset"]
    d, prior = new["body"], old["body"]
    if (new["id"] == old["id"] or d.get("parent_id") != old["id"] or d.get("origin") != "hypothetical"
        or d.get("experiment_id") != prior["experiment_id"] or d.get("time_origin") != prior["time_origin"]
        or len(d.get("rows", [])) != len(prior["rows"]) + 1 or d["rows"][:-1] != prior["rows"]):
        raise AdapterError("wrong_specification_binding", "Follow-up must append one labeled hypothetical row in a new dataset revision.")
    old_problem, new_problem = previous["problem"]["body"], binding["problem"]["body"]
    if {k: v for k, v in old_problem.items() if k not in ("dataset_id", "dataset_digest")} != {
            k: v for k, v in new_problem.items() if k not in ("dataset_id", "dataset_digest")}:
        raise AdapterError("wrong_specification_binding", "Follow-up cannot silently change the reviewed model, domain or target.")
    parent_native = strict_json_loads(decode_artifact(parent["scientific"]["bytes_base64"], parent["scientific"]["sha256"]))
    _object_with(parent_native, {"report", "design"}, "parent/scientific")
    report = _object_with(parent_native["report"], {"checked"}, "parent/scientific/report")
    checked = _object_with(report["checked"], {"tier", "selected_time"}, "parent/scientific/report/checked")
    request = _object_with(parent["binding"]["request"], {"future_hard_allowance"}, "parent/binding/request")
    row = d["rows"][-1]
    if (checked.get("tier") != "checked_pair_separation" or row.get("time") != checked.get("selected_time")
        or row.get("hard_allowance") != request["future_hard_allowance"] or row.get("included") is not True
        or row.get("source_asset_id") is not None):
        raise AdapterError("wrong_specification_binding", "Hypothetical row must use the checked selected time and reviewed allowance.")
    design = _object_with(parent_native["design"], {"candidates"}, "parent/scientific/design")
    def vectors(value, path):
        if type(value) is not list or len(value) != 2:
            raise AdapterError("candidate_mismatch", "Follow-up requires exactly the selected pair.", (path,))
        result = {}
        for candidate in value:
            c = _object_with(candidate, {"id", "parameters"}, path)
            cid = text_value(c["id"], path + "/id", identifier=True)
            if cid in result:
                raise AdapterError("candidate_mismatch", "Selected candidate IDs must be distinct.", (path,))
            result[cid] = fields(c["parameters"], {"A", "ke", "ka"}, path + "/parameters")
        return result
    old_vectors = vectors(design["candidates"], "parent/scientific/design/candidates")
    new_vectors = vectors(scientific["candidates"], "scientific/candidates")
    if old_vectors != new_vectors or scientific["operation"] != "fixed_candidate_review":
        raise AdapterError("candidate_mismatch", "Follow-up must check exactly the original selected vectors.")


def replay_packet(content: bytes, *, expected: dict, context=None, _depth: int = 0) -> dict:
    if _depth > 2:
        raise AdapterError("resource_exhaustion", "Native lineage exceeds this profile's bounded depth.")
    _anchors(expected)
    if artifact_digest(content) != digest_value(expected["artifact_sha256"], "expected/artifact_sha256"):
        raise AdapterError("artifact_mismatch", "Application packet bytes differ from the external artifact hash.")
    p = _packet(strict_json_loads(content))
    if p["scenario_id"] != expected["scenario_id"] or p["run_id"] != expected["run_id"]:
        raise AdapterError("wrong_scenario_binding", "Native packet belongs to another run or scenario.")
    if packet_anchors(content) != expected:
        raise AdapterError("wrong_specification_binding", "Application, projection or design identity differs from the external anchor.")
    s = fields(p["scientific"], {"sha256", "bytes_base64"}, "scientific")
    native = decode_artifact(s["bytes_base64"], s["sha256"])
    scientific = strict_json_loads(native)
    native_limits = _object_with(scientific, {"design"} if p["operation"] == "design" else {"limits"}, "scientific")
    if p["operation"] == "design":
        native_limits = _object_with(native_limits["design"], {"limits"}, "scientific/design")
    limits = _object_with(native_limits["limits"], {"wall_seconds", "max_bundle_bytes"}, "scientific/limits")
    wall = counter(limits["wall_seconds"], "limits/wall_seconds", 1, 120)
    maximum = counter(limits["max_bundle_bytes"], "limits/max_bundle_bytes", 1, 4 * 1024 * 1024)
    if len(content) > maximum:
        raise AdapterError("resource_exhaustion", "Complete application evidence and lineage exceed the approved byte limit.")
    # Create one cooperative budget for the whole offline lineage, not a new
    # allowance for each embedded baseline/design. The parent still owns the
    # hard wall deadline, including bounded JSON admission and pipe I/O.
    if context is None:
        context = ExecutionContext(wall)
    if type(context) is not ExecutionContext:
        raise AdapterError("invalid_input", "Expected a bounded execution context.")
    stop = context.stop_reason(wall)
    if stop:
        raise AdapterError(stop, "Native replay stopped at its shared execution budget.")
    _object_with(scientific, {"problem", "operation"} if p["operation"] != "design" else {"problem", "design", "suggestion_digest"}, "scientific")
    if p["operation"] == "design":
        _, parent, fresh_parent = _history(p, context, _depth)
        if parent["operation"] != "investigate":
            raise AdapterError("wrong_specification_binding", "Design requires an actual baseline discovery packet.")
        binding = p["binding"]
        evidence = binding["historical_evidence"]
        if (parent["run_id"] != evidence["run_id"] or parent["scenario_id"] != p["scenario_id"]
            or parent["binding"] != binding["application"]):
            raise AdapterError("wrong_scenario_binding", "Historical evidence and approved design belong to different scopes.")
        refs = evidence["result"]["artifacts"]
        if type(refs) is not list or not any(type(r) is dict and r.get("id") == p["history"]["id"] and r.get("sha256") == p["history"]["sha256"] for r in refs):
            raise AdapterError("artifact_mismatch", "Historical application reference does not name these native bytes.")
        mapping = verify_design_binding(binding, native_candidate_results=fresh_parent["candidate_results"])
        if scientific["design"] != mapping["design"] or scientific["problem"] != verify_application_binding(binding["application"])["problem"]:
            raise AdapterError("wrong_specification_binding", "Native design differs from the approved application projection.")
        fresh = replay_bundle(native, expected_problem_digest=expected["projection_digest"],
                              expected_suggestion_digest=scientific["suggestion_digest"], context=context)
        if "fresh_checked" in fresh:
            fresh["candidate_results"] = fresh["fresh_checked"]["candidate_results"]
    else:
        mapping = verify_application_binding(p["binding"])
        if scientific["problem"] != mapping["problem"]:
            raise AdapterError("wrong_specification_binding", "Native historical inputs differ from the application mapping.")
        if p["operation"] == "investigate":
            if p["history"] is not None or scientific["operation"] != "bounded_discovery":
                raise AdapterError("invalid_input", "Discovery cannot substitute fixed historical vectors.")
        else:
            _, parent, fresh_parent = _history(p, context, _depth)
            if fresh_parent["replay"] != "passed":
                raise AdapterError("incomplete_export", "Original design must freshly replay before follow-up.")
            validate_followup(p["binding"], parent, scientific)
        _object_with(scientific, {"baseline_digest"}, "scientific")
        fresh = replay_baseline(native, expected_problem_digest=expected["projection_digest"],
            expected_baseline_digest=scientific["baseline_digest"], expected_scenario_id=expected["scenario_id"], context=context)
    stop = context.stop_reason(wall)
    if stop:
        raise AdapterError(stop, "Native replay stopped at its shared execution budget.")
    return {**fresh, "packet_profile": PACKET_PROFILE, "operation": p["operation"], "anchors": expected,
            "dataset_origin": (p["binding"]["application"] if p["operation"] == "design" else p["binding"])["dataset_origin"]}
