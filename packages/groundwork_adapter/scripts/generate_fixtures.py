"""Regenerate new synthetic packets and their actual execution ledger offline."""
from copy import deepcopy
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from helpers import synthetic_problem_payload, synthetic_design_payload
from counterdex import ExecutionContext, create_suggestion, normalize_design, normalize_problem, replay_bundle
from counterdex.exact import artifact_digest, canonical_bytes, semantic_digest, strict_json_loads
from counterdex.identity import implementation_identity


def main() -> None:
    destination = ROOT / "fixtures"
    destination.mkdir(exist_ok=True)
    entries = []
    for name in ("numerical_success", "numerical_partial", "numerical_invalid_range", "numerical_no_useful", "checked_success", "checked_no_separation", "new_datum_excludes_both"):
        p = synthetic_problem_payload()
        if name == "new_datum_excludes_both":
            row = deepcopy(p["observations"][0])
            row.update(id="hypothetical-followup", time="6/1", value="10/1", allowance="1/5",
                       notes="Explicit hypothetical follow-up, not an acquired reading")
            p["observations"].append(row)
        problem = normalize_problem(p)
        d = synthetic_design_payload(problem)
        if name.startswith("numerical"):
            d["requested_tier"] = "numerical_guidance"
            d["horizon_policy"]["allow_construction"] = False
            d["horizon_policy"]["allow_extension"] = False
            d["limits"]["max_constructions"] = 0
            d["limits"]["max_pair_verifications"] = 0
        if name == "numerical_invalid_range":
            d["grid"] = [{"time": "100000/1", "feasible": True, "reason": "Synthetic binary64 range failure"}]
        if name == "numerical_no_useful":
            d["grid"] = [{"time": "0/1", "feasible": True, "reason": "Both analytic predictions are exactly zero at the initial time"}]
        if name == "checked_no_separation":
            d["future_allowance"] = "10/1"
        design = normalize_design(d, problem)
        workflow = {key: "fixture-" + name + "-" + key for key in ("plan_id", "approval_id", "operation_id", "execution_id")}
        request = {"problem": problem.to_payload(), "design": design.to_payload(), "workflow": workflow}
        checks = 0

        def cancel_after_one_row() -> bool:
            nonlocal checks
            checks += 1
            return checks >= 2

        context = ExecutionContext(cancelled=cancel_after_one_row) if name == "numerical_partial" else None
        started = time.monotonic()
        packet = create_suggestion(problem.to_payload(), design.to_payload(), workflow=workflow,
            expected_problem_digest=problem.digest, expected_design_digest=design.digest, context=context)
        elapsed = time.monotonic() - started
        bundle = strict_json_loads(packet)
        anchors = {"problem_digest": problem.digest, "design_digest": design.digest,
                   "suggestion_digest": bundle["suggestion_digest"]}
        fresh = replay_bundle(packet, expected_problem_digest=problem.digest,
                              expected_suggestion_digest=bundle["suggestion_digest"])
        for suffix, value in (("request", request), ("anchors", anchors), ("replay", fresh)):
            (destination / f"{name}.{suffix}.json").write_bytes(canonical_bytes(value) + b"\n")
        (destination / f"{name}.bundle.json").write_bytes(packet)
        entries.append({"name": name, "provenance": "new synthetic control; no acquired measurements",
            "oracle": "fresh analytic exact checker" if not name.startswith("numerical") else "operational cancellation" if name.endswith("partial") else "numerical diagnostic",
            "expected_scope": "two fixed parameter choices only; no whole-set conclusion",
            "execution": bundle["report"]["execution"], "tier": bundle["report"]["tier"],
            "numeric_outcome": bundle["report"]["numerical"]["outcome"],
            "verification": bundle["report"]["checked"]["verification"], "replay": fresh["replay"],
            "elapsed_seconds_diagnostic": format(elapsed, ".6f"), "artifact_bytes": len(packet),
            "raw_sha256": artifact_digest(packet), "problem_digest": problem.digest,
            "design_digest": design.digest, "suggestion_digest": bundle["suggestion_digest"]})
    ledger = {"schema_version": "groundwork.fixture-ledger.v1", "command": "python3 packages/groundwork_adapter/scripts/generate_fixtures.py",
              "python": platform.python_version(), "platform": platform.platform(),
              "implementation": implementation_identity(), "entries": entries,
              "limits": "These are measured synthetic fixture runs, not general throughput or external integration evidence."}
    (destination / "manifest.json").write_bytes(canonical_bytes(ledger) + b"\n")
    golden_body = {"unicode": "é/é/😀/\u2028/\u2029", "controls": "\b\f\n\r\t\x00\x1f/\\\"",
                   "array": ["2/1", "1/1", {"z": "0/1", "a": "1/10"}],
                   "exact": str(10**200 + 1) + "/3", "counter": 9007199254740991, "null": None, "boolean": True}
    golden = {"profile": "DB-SC-1", "oracle": "exact canonical byte fixture; no scientific claim", "body": golden_body,
              "canonical_utf8_hex": canonical_bytes(golden_body).hex(), "semantic_digest": semantic_digest("report", golden_body)}
    (destination / "canonicalization_golden.json").write_bytes(canonical_bytes(golden) + b"\n")
    print(f"Generated {len(entries)} synthetic packets with fresh replay records.")


if __name__ == "__main__":
    main()
