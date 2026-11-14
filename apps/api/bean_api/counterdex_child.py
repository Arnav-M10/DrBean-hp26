"""Fixed server-owned CPython 3.11 bridge; stdin is data, never executable scope."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import sys

# This path is server source configuration, never supplied by evidence or model output.
PACKAGE_ROOT = Path(__file__).resolve().parents[3] / "packages" / "groundwork_adapter"
sys.path.insert(0, str(PACKAGE_ROOT))


def dispatch(request: dict) -> dict:
    from counterdex.errors import AdapterError
    from counterdex.identity import implementation_identity
    identity = implementation_identity()
    if request.get("protocol") == "counterdex.bridge.v1":
        # The prepared package owns discovery, its application projection, and
        # native replay. The server-owned launcher only carries bounded data.
        from counterdex.bridge import dispatch as native_dispatch
        return native_dispatch(request)
    operation = request["operation"]
    if operation == "probe":
        from counterdex import capabilities
        return {"identity": identity, "capabilities": capabilities(), "baseline_discovery": True}
    if operation == "replay":
        from counterdex.replay import replay_bundle
        content = base64.b64decode(request["content_base64"], validate=True)
        if len(content) > 4 * 1024 * 1024:
            raise AdapterError("resource_exhaustion", "Native bundle exceeds the admitted byte limit.")
        return replay_bundle(content, expected_problem_digest=request["expected_problem_digest"],
                             expected_suggestion_digest=request["expected_suggestion_digest"])
    if operation != "design":
        raise AdapterError("unsupported_operation", "This operation requires the supported native bridge protocol.")
    from counterdex import normalize_design, normalize_problem
    from counterdex.pipeline import create_suggestion
    from counterdex.replay import replay_bundle
    from counterdex.resource import ExecutionContext
    problem = normalize_problem(request["problem"])
    design = normalize_design(request["design"], problem)
    if design.requested_tier == "checked_pair_separation" and design.limits.max_pair_verifications < 2:
        raise AdapterError("resource_exhaustion", "Initial checking and fresh native replay require two approved pair verifications.")
    artifacts = {}
    total = 0
    for item in request.get("artifacts", []):
        content = base64.b64decode(item["content_base64"], validate=True)
        total += len(content)
        if len(content) > design.limits.max_certificate_bytes or total > design.limits.max_bundle_bytes:
            raise AdapterError("resource_exhaustion", "Supplied native evidence exceeds the approved byte limits.")
        digest = hashlib.sha256(content).hexdigest()
        if digest != item["sha256"] or digest in artifacts:
            raise AdapterError("artifact_mismatch", "Source evidence hash or uniqueness check failed.")
        artifacts[digest] = content
    context = ExecutionContext(design.limits.wall_seconds)
    content = create_suggestion(problem.to_payload(), design.to_payload(), expected_problem_digest=request["expected_problem_digest"],
        expected_design_digest=request["expected_design_digest"], workflow=request["workflow"], context=context, artifacts=artifacts)
    bundle = json.loads(content)
    fresh = replay_bundle(content, expected_problem_digest=request["expected_problem_digest"],
                          expected_suggestion_digest=bundle["suggestion_digest"], context=context)
    return {"content_base64": base64.b64encode(content).decode("ascii"), "sha256": hashlib.sha256(content).hexdigest(),
            "byte_size": len(content), "problem_digest": problem.digest, "design_digest": design.digest,
            "suggestion_digest": bundle["suggestion_digest"], "report": bundle["report"], "native_replay": fresh,
            "identity": identity}


def main() -> None:
    try:
        raw = sys.stdin.buffer.read(12 * 1024 * 1024 + 1)
        if len(raw) > 12 * 1024 * 1024:
            raise ValueError("request_limit")
        result = dispatch(json.loads(raw))
    except Exception as exc:
        from counterdex.errors import AdapterError
        if isinstance(exc, AdapterError):
            result = {"engine_error": exc.to_dict()}
        else:
            result = {"engine_error": {"code": "scientific_bridge_failure", "message": "The prepared scientific bridge could not complete.", "field_paths": [], "retryable": False}}
    encoded = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    if len(encoded) > 12 * 1024 * 1024:
        encoded = b'{"engine_error":{"code":"resource_exhaustion","message":"Scientific bridge output exceeds its limit.","field_paths":[],"retryable":false}}'
    sys.stdout.buffer.write(encoded)


if __name__ == "__main__":
    main()
