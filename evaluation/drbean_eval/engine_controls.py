"""Engine-level native controls, executed through Counterdex's public operations.

These controls run the installed engine in fresh CPython 3.11 isolated processes.
They are NOT through HTTP: they pin the scientific semantics the HTTP lane relies
on, using the audit's fixed regression pair (a regression oracle, never a
production lookup) and the hero packet's reviewed problem.

Controls:

* fixed-pair constraint controls: grid [6,8]/0.2 selects 8 h, [6]/0.2 selects 6 h,
  [6,8]/0.6 establishes no separation while both candidates stay compatible and
  fresh replay passes;
* three defenses kept distinct: a wrong expected identity fails binding, a changed
  byte fails integrity, and a mathematically false enclosure with internal hashes
  recomputed (test only) fails fresh computation. The original external anchor
  rejects the mutation first; the deliberately changed test anchor is used only to
  reach the mathematical check and authenticates nothing;
* the closed claim endpoint is inside (equality is not a counterexample);
* touching bands do not separate: an allowance equal to half the computed centre
  gap gives a non-positive exact margin;
* hypothetical follow-ups at 8 h / 0.2 mg/L: 3.4 keeps the reference and excludes
  the outside candidate, 4.57 the reverse, 4.0 excludes both; per-candidate
  results agree with the independent decimal oracle and aggregate pair status is
  reported as scientific exclusion, not corruption.

Fresh replay is the same project checker run again, not an independent proof.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
from fractions import Fraction

from . import kinetics, native

_WORKER = r"""
import base64, json, os, sys
sys.path.insert(0, os.environ["DRBEAN_COUNTERDEX_DIR"])
from counterdex import create_suggestion, normalize_problem, normalize_design
from counterdex.errors import AdapterError
from counterdex.exact import canonical_bytes, semantic_digest, artifact_digest, strict_json_loads
job = json.loads(sys.stdin.read())
out = {}
try:
    if job["op"] == "suggest":
        problem = normalize_problem(job["problem"])
        design = normalize_design({**job["design"], "problem_digest": problem.digest,
                                   "candidates": [{**c, "problem_digest": problem.digest} for c in job["design"]["candidates"]]},
                                  problem)
        payload = {**job["design"], "problem_digest": problem.digest,
                   "candidates": [{**c, "problem_digest": problem.digest} for c in job["design"]["candidates"]]}
        bundle = create_suggestion(job["problem"], payload, expected_problem_digest=problem.digest,
                                   expected_design_digest=design.digest, workflow=job["workflow"])
        body = strict_json_loads(bundle)
        out = {"bundle_b64": base64.b64encode(bundle).decode(), "problem_digest": problem.digest,
               "design_digest": design.digest, "suggestion_digest": body["suggestion_digest"],
               "report": body["report"]}
    elif job["op"] == "mutate":
        bundle = strict_json_loads(base64.b64decode(job["bundle_b64"]))
        old = bundle["report"]["checked"]["pair_digest"]
        item = next(a for a in bundle["artifacts"] if a["digest"] == old)
        pair = strict_json_loads(base64.b64decode(item["content"]))
        candidate = pair["candidates"][job["candidate_index"]]
        sample = next(s for s in candidate["samples"] if s["time"] == job["time"])
        from fractions import Fraction
        def shift(text):
            n, d = text.split("/"); v = Fraction(int(n), int(d)) + Fraction(job["delta"])
            return f"{v.numerator}/{v.denominator}"
        sample["lower"], sample["upper"] = shift(sample["lower"]), shift(sample["upper"])
        content = canonical_bytes(pair)
        new = artifact_digest(content)
        text = canonical_bytes({k: v for k, v in bundle.items() if k != "suggestion_digest"}).decode()
        body = json.loads(text.replace(old, new))
        for a in body["artifacts"]:
            if a["digest"] == new:
                a["content"] = base64.b64encode(content).decode()
        body["suggestion_digest"] = semantic_digest("suggestion", body)
        out = {"bundle_b64": base64.b64encode(canonical_bytes(body)).decode(), "suggestion_digest": body["suggestion_digest"],
               "old_pair_digest": old, "new_pair_digest": new}
except AdapterError as error:
    out = {"error": error.to_dict()}
sys.stdout.write(json.dumps(out))
"""

POLICIES = {"numerical_policy": "pair-gap-over-allowance-12sig-half-even.v1",
            "checked_policy": "positive-margin-descending-time-ids.v1"}
LIMITS = {"max_bundle_bytes": 4194304, "max_certificate_bytes": 2097152, "max_constructions": 2,
          "max_pair_verifications": 2, "max_times": 64, "wall_seconds": 120}


def exact(decimal_text: str) -> str:
    value = Fraction(decimal_text)
    return f"{value.numerator}/{value.denominator}"


def engine_problem(packet: dict, extra_rows: list[dict] | None = None) -> dict:
    """Project the reviewed hero packet into the engine's groundwork.problem.v1 input."""
    rows = packet["dataset"]["rows"] + (extra_rows or [])
    domain = packet["problem"]["domain"]
    target = packet["problem"]["target"]
    return {
        "schema_version": "groundwork.problem.v1", "model": "two_rate_kinetics_v1", "model_revision": 1,
        "units": {"time": "h", "concentration": "mg/L", "rate": "1/h"},
        "initial_conditions": {"x": "1/1", "c": "0/1"},
        "time_origin": "elapsed hours from the fixed initial state",
        "domain": {k: [domain[k]["lower"], domain[k]["upper"]] for k in ("A", "ke", "ka")},
        "claim": {"parameter": "ke", "interval": [target["lower"], target["upper"]]},
        "dataset_kind": "hypothetical",
        "observations": [{"id": r["id"], "time": r["time"], "value": r["concentration"],
                          "allowance": r["hard_allowance"], "included": r["included"],
                          "allowance_origin": r.get("allowance_origin", "Reviewed synthetic hard allowance"),
                          "origin": "hypothetical", "notes": r.get("notes") or "Synthetic control row",
                          "provenance": "Workstream 5 control; synthetic, not a measurement"} for r in rows],
        "notes": "Workstream 5 engine control built from evaluation/cases/science/hero-v1.json",
        "provenance": "Team-selected synthetic values; not collected measurements",
    }


def engine_design(pair: list[dict], times: list[str], allowance: str, scenario: str,
                  maximum_horizon: str = "8/1") -> dict:
    return {"schema_version": "groundwork.design.v1", "scenario_id": scenario,
            "candidates": [{"id": c["id"], "parameters": {k: exact(c[k]) for k in ("A", "ke", "ka")},
                            "source_artifact_digest": None} for c in pair],
            "grid": [{"time": t, "feasible": True, "reason": "Reviewed feasible time (control)"} for t in times],
            "time_origin": "elapsed hours from the fixed initial state", "future_allowance": allowance,
            "allowance_origin": {"kind": "hypothetical", "description": "Reviewed future hard allowance (control)"},
            "horizon_policy": {"maximum_horizon": maximum_horizon, "allow_construction": True,
                               "allow_extension": True},
            "requested_tier": "checked_pair_separation", "observable": "c", "limits": LIMITS, **POLICIES}


def _worker(science_python: str, package_dir: str, job: dict, timeout: float = 180.0) -> dict:
    with tempfile.TemporaryDirectory(prefix="drbean-control-") as work:
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": work, "TMPDIR": work,
               "DRBEAN_COUNTERDEX_DIR": os.path.abspath(package_dir)}
        done = subprocess.run([science_python, "-I", "-c", _WORKER], input=json.dumps(job), capture_output=True,
                              text=True, timeout=timeout, env=env, cwd=work)
    if done.returncode:
        raise RuntimeError(f"engine control worker failed: {done.stderr.strip().splitlines()[-1:]}")
    return json.loads(done.stdout)


def replay_class(result: dict) -> str:
    """Name what a replay outcome establishes; exclusion is scientific feedback, not corruption."""
    if result["status"] == "passed":
        return "passed"
    error = result.get("error") or {}
    if error.get("code") == "wrong_specification_binding":
        return "binding_failure"
    if error.get("code") == "artifact_mismatch":
        return "integrity_failure"
    if error.get("code") == "exact_check_failure":
        return "mathematical_failure"
    report = result.get("report") or {}
    if (report.get("integrity") == "passed" and report.get("expected_binding") == "matches"
            and report.get("verification") == "invalid"):
        return "scientific_exclusion"
    return f"rejected:{error.get('code') or report.get('reason_code') or result['status']}"


def _selected(report: dict) -> tuple[str | None, dict]:
    checked = report.get("checked") or {}
    return checked.get("selected_time"), checked


def run(science_python: str, package_dir: str, repo: str) -> list[dict]:
    """Execute every control; each returns id, passed, expected, observed and scope."""
    root = os.path.join(repo, "evaluation", "cases", "science")
    with open(os.path.join(root, "hero-v1.json"), encoding="utf-8") as handle:
        hero = json.load(handle)
    with open(os.path.join(root, "fixed-pair-regression-v1.json"), encoding="utf-8") as handle:
        regression = json.load(handle)
    pair = regression["pair"]
    problem = engine_problem(hero)
    workflow = {"plan_id": "wk5-control-plan", "approval_id": "wk5-control-approval",
                "execution_id": "wk5-control-execution", "operation_id": "wk5-control-operation"}
    results = []

    def record(control_id, passed, expected, observed, scope):
        results.append({"id": control_id, "passed": bool(passed), "expected": expected, "observed": observed,
                        "scope": scope})

    bundles = {}
    for control in regression["controls"]:
        times = [exact(t) for t in control["feasible_times"]]
        out = _worker(science_python, package_dir, {"op": "suggest", "problem": problem, "workflow": workflow,
                      "design": engine_design(pair, times, exact(control["future_allowance"]),
                                              "wk5-" + control["control"])})
        if "error" in out:
            record(f"fixed_pair:{control['control']}", False, control["expected"], out["error"],
                   "engine create_suggestion")
            continue
        bundle = base64.b64decode(out["bundle_b64"])
        bundles[control["control"]] = (bundle, out)
        selected, checked = _selected(out["report"])
        anchors = {"problem_digest": out["problem_digest"], "suggestion_digest": out["suggestion_digest"]}
        replayed = native.replay(science_python, package_dir, bundle, anchors)
        candidates = {c["candidate_id"]: c for c in (replayed.get("report") or {}).get("fresh_checked", {})
                      .get("candidate_results", [])}
        expected = control["expected"]
        rows = {r["time"]: r for r in checked.get("rows", [])} if isinstance(checked.get("rows"), list) else {}
        margin = rows.get(selected, {}).get("margin") if selected else None
        if expected["tier"] == "checked_pair_separation":
            ok = (checked.get("tier") == "checked_pair_separation" and selected == exact(expected["selected_time"])
                  and margin is not None and Fraction(margin) > 0 and replay_class(replayed) == "passed")
        else:
            ok = (checked.get("tier") != "checked_pair_separation" and selected is None
                  and replay_class(replayed) == "passed"
                  and all(c.get("verification") == "valid" for c in candidates.values()) and len(candidates) == 2)
        record(f"fixed_pair:{control['control']}", ok, expected,
               {"tier": checked.get("tier"), "selected_time": selected,
                "selected_margin_approx": float(Fraction(margin)) if margin else None,
                "replay": replay_class(replayed),
                "candidates": {k: v.get("verification") for k, v in candidates.items()},
                "suggestion_digest": out["suggestion_digest"], "problem_digest": out["problem_digest"]},
               "fixed audit pair on this exact grid and allowance; not a global optimum or instrument claim")

    base = bundles.get("grid-6-8-allowance-0.2")
    if base:
        bundle, out = base
        anchors = {"problem_digest": out["problem_digest"], "suggestion_digest": out["suggestion_digest"]}
        wrong = native.replay(science_python, package_dir, bundle,
                              {**anchors, "problem_digest": native.wrong_anchor(anchors["problem_digest"])})
        record("defense:wrong_expected_identity", replay_class(wrong) == "binding_failure",
               "binding_failure", replay_class(wrong), "expected identity supplied separately from the bundle")
        flipped = native.replay(science_python, package_dir, native.flip_one_byte(bundle), anchors)
        record("defense:changed_byte", replay_class(flipped) == "integrity_failure", "integrity_failure",
               replay_class(flipped), "one byte changed; original anchors")
        mutated = _worker(science_python, package_dir, {"op": "mutate", "bundle_b64": out["bundle_b64"],
                          "candidate_index": 0, "time": "6/1", "delta": "1/10"})
        mutated_bytes = base64.b64decode(mutated["bundle_b64"])
        original_anchor = native.replay(science_python, package_dir, mutated_bytes, anchors)
        record("defense:mutation_rejected_by_original_anchor", replay_class(original_anchor) == "integrity_failure",
               "integrity_failure", replay_class(original_anchor),
               "false enclosure (+1/10 at 6 h) with internal hashes recomputed; real original anchor")
        diagnostic = native.replay(science_python, package_dir, mutated_bytes,
                                   {**anchors, "suggestion_digest": mutated["suggestion_digest"]})
        record("defense:mutation_rejected_by_fresh_mathematics", replay_class(diagnostic) == "mathematical_failure",
               "mathematical_failure", {"class": replay_class(diagnostic),
                                        "field_paths": (diagnostic.get("error") or {}).get("field_paths")},
               "DIAGNOSTIC ONLY: a deliberately changed test anchor isolates the mathematical check. It sacrifices "
               "packet authentication on purpose and authenticates nothing; real releases use the original anchor")
        # Touching bands: allowance = half the engine's own centre gap at 8 h gives a non-positive exact margin.
        rows = {r["time"]: r for r in (out["report"]["checked"].get("rows") or [])}
        replayed = native.replay(science_python, package_dir, bundle, anchors)
        fresh_rows = {r["time"]: r for r in (replayed.get("report") or {}).get("fresh_checked", {}).get("rows", [])}
        centres = (fresh_rows.get("8/1") or {}).get("centers") or {}
        if len(centres) == 2:
            values = [Fraction(v) for v in centres.values()]
            touching = abs(values[0] - values[1]) / 2
            eta = f"{touching.numerator}/{touching.denominator}"
            touch = _worker(science_python, package_dir, {"op": "suggest", "problem": problem, "workflow": workflow,
                            "design": engine_design(pair, ["8/1"], eta, "wk5-touching-bands")})
            selected, checked = _selected(touch.get("report") or {})
            touch_rows = {r["time"]: r for r in checked.get("rows", [])} if isinstance(checked.get("rows"), list) else {}
            margin = (touch_rows.get("8/1") or {}).get("margin")
            ok = ("error" not in touch and selected is None and checked.get("tier") != "checked_pair_separation"
                  and (margin is None or Fraction(margin) <= 0))
            record("semantics:touching_bands_do_not_separate", ok,
                   "no selection; exact margin <= 0", {"selected_time": selected, "tier": checked.get("tier"),
                                                        "margin": margin, "error": touch.get("error")},
                   "allowance set to half the computed centre gap at 8 h: closed bands touch, equality fails")
        else:
            record("semantics:touching_bands_do_not_separate", False, "centres available", centres,
                   "replay report did not expose centres at 8 h")

    # Endpoint equality: a candidate with ke exactly on the closed claim's lower endpoint is inside.
    endpoint = [dict(pair[0], id="endpoint-ke-0.10", ke="0.10"), pair[1]]
    out = _worker(science_python, package_dir, {"op": "suggest", "problem": problem, "workflow": workflow,
                  "design": engine_design(endpoint, ["8/1"], "1/5", "wk5-endpoint")})
    if "error" in out:
        record("semantics:closed_endpoint_is_inside", False, "outside_closed_claim false", out["error"],
               "engine create_suggestion")
    else:
        replayed = native.replay(science_python, package_dir, base64.b64decode(out["bundle_b64"]),
                                 {"problem_digest": out["problem_digest"], "suggestion_digest": out["suggestion_digest"]})
        found = {c["candidate_id"]: c for c in (replayed.get("report") or {}).get("fresh_checked", {})
                 .get("candidate_results", [])}
        item = found.get("endpoint-ke-0.10", {})
        record("semantics:closed_endpoint_is_inside", item.get("outside_closed_claim") is False
               and item.get("is_counterexample") is False,
               {"outside_closed_claim": False, "is_counterexample": False},
               {k: item.get(k) for k in ("outside_closed_claim", "is_counterexample", "verification")},
               "ke = 1/10 equals the closed claim's lower endpoint; whether it fits the data does not matter here")

    # Follow-ups: per-candidate outcomes, aggregate reported as scientific exclusion.
    vectors = {c["id"]: {k: exact(c[k]) for k in ("A", "ke", "ka")} for c in pair}
    for follow in regression["followups_at_8h_allowance_0.2"]:
        row = {"id": "hypothetical-followup", "time": "8/1", "concentration": exact(follow["reading"]),
               "hard_allowance": "1/5", "included": True, "notes": "Hypothetical follow-up reading",
               "allowance_origin": "Reviewed hypothetical future hard allowance"}
        out = _worker(science_python, package_dir, {"op": "suggest", "problem": engine_problem(hero, [row]),
                      "workflow": workflow, "design": engine_design(pair, ["10/1", "12/1"], "1/5",
                                                                    "wk5-followup", maximum_horizon="12/1")})
        if "error" in out:
            record(f"followup:{follow['reading']}", False, follow["expected"], out["error"], "engine")
            continue
        replayed = native.replay(science_python, package_dir, base64.b64decode(out["bundle_b64"]),
                                 {"problem_digest": out["problem_digest"], "suggestion_digest": out["suggestion_digest"]})
        found = {c["candidate_id"]: ("compatible" if c.get("verification") == "valid" else
                                     "excluded" if c.get("verification") == "invalid" else c.get("verification"))
                 for c in (replayed.get("report") or {}).get("fresh_checked", {}).get("candidate_results", [])}
        oracle = {cid: kinetics.band_verdict(vec, "8", follow["reading"], "0.2") for cid, vec in vectors.items()}
        excluded_any = "excluded" in found.values()
        aggregate = replay_class(replayed)
        ok = (found == follow["expected"] == oracle
              and (aggregate == "scientific_exclusion" if excluded_any else aggregate == "passed"))
        record(f"followup:{follow['reading']}", ok, {"per_candidate": follow["expected"],
                                                     "aggregate": "scientific_exclusion" if excluded_any else "passed"},
               {"per_candidate": found, "independent_oracle": oracle, "aggregate": aggregate},
               "hypothetical 8 h reading, allowance 0.2: candidate-specific feedback; proves nothing about the "
               "original interval or every possible model")
    return results
