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
  reported as scientific exclusion, not corruption;
* coordinator predicates SCI-06 and SCI-05 (added by C at DB-COORDINATOR-3OWNER-1):
  a reading at 8 h declared with its own allowance wider than the design's 0.2
  legitimately keeps both candidates, while the same reading at the separating
  allowance keeps neither, because the independent oracle shows the closed 0.2 bands
  are disjoint there. A forged packet claiming both compatible at that separating
  scope is refused: the real anchor fails integrity, and with a test-only anchor
  fresh recomputation reports a recorded-result mismatch. A requested
  numerical-guidance design never becomes checked separation, and its replay is
  unsupported rather than passed. Infeasible grid times are kept with their reasons
  but are never evaluated, ranked or selected.

Fresh replay is the same project checker run again, not an independent proof.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import subprocess
import tempfile
from fractions import Fraction

from . import kinetics, native

_WORKER = r"""
import base64, json, os, sys
if os.environ.get("DRBEAN_GUARD_FILE") and os.environ.get("DRBEAN_EGRESS_GUARD_LOG"):
    import importlib.util
    _spec = importlib.util.spec_from_file_location("drbean_guard", os.environ["DRBEAN_GUARD_FILE"])
    _spec.loader.exec_module(importlib.util.module_from_spec(_spec))
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
    elif job["op"] == "edit":
        body = strict_json_loads(base64.b64decode(job["bundle_b64"]))
        body.pop("suggestion_digest", None)
        kind = job["edit"]
        if kind == "drop_artifacts":
            body["artifacts"] = []
        elif kind == "duplicate_artifact":
            body["artifacts"] = body["artifacts"] + body["artifacts"][:1]
        elif kind == "claim_all_valid":
            # Test-only forgery: every claimed candidate result says the candidate kept every reading.
            for item in body["report"]["checked"]["candidate_results"]:
                item.update(verification="valid", violating_observation_ids=[], reason_code=None,
                            is_counterexample=bool(item.get("outside_closed_claim")))
        elif kind == "unknown_profile":
            body["schema_version"] = "groundwork.suggestion-bundle.v99"
        body["suggestion_digest"] = semantic_digest("suggestion", body)
        out = {"bundle_b64": base64.b64encode(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                                         ensure_ascii=False).encode()).decode(),
               "suggestion_digest": body["suggestion_digest"]}
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


GUARD_LOG: str | None = None  # set by run(); every control subprocess loads the egress guard with it


def _replay(*args, **kwargs):
    return native.replay(*args, guard_log=GUARD_LOG, **kwargs)


def engine_source_files(package_dir: str) -> dict:
    """{file: sha256} for counterdex/*.py in a checkout (the shape the engine reports as its source manifest)."""
    root = os.path.join(os.path.abspath(package_dir), "counterdex")
    files = {}
    for name in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        if name.endswith(".py"):
            with open(os.path.join(root, name), "rb") as handle:
                files[name] = hashlib.sha256(handle.read()).hexdigest()
    return files


def engine_source_identity(package_dir: str) -> dict:
    """Digest of the Counterdex source a run must exercise: sorted (file, sha256) of counterdex/*.py."""
    manifest = [[name, digest] for name, digest in sorted(engine_source_files(package_dir).items())]
    digest = hashlib.sha256(json.dumps(manifest, separators=(",", ":")).encode()).hexdigest() if manifest else None
    return {"source_sha256": digest, "files": len(manifest)}


_ENGINE_PROBE = (
    "import json, os, sys\n"
    "sys.path.insert(0, os.environ['DRBEAN_COUNTERDEX_DIR'])\n"
    "import counterdex\n"
    "print(json.dumps({'version': getattr(counterdex, '__version__', None),\n"
    "                  'module_dir': os.path.dirname(os.path.abspath(counterdex.__file__))}))\n")


_ENCLOSURE = (
    "import json, os, sys\n"
    "from fractions import Fraction\n"
    "sys.path.insert(0, os.environ['DRBEAN_COUNTERDEX_DIR'])\n"
    "from counterdex.analytical import concentration_interval\n"
    "from counterdex.exact import rational_text\n"
    "job = json.loads(sys.stdin.read())\n"
    "v = job['vector']\n"
    "lo, hi = concentration_interval(Fraction(v['A']), Fraction(v['ke']), Fraction(v['ka']), Fraction(job['time']))\n"
    "print(json.dumps([rational_text(lo), rational_text(hi)]))\n")


def engine_enclosure(science_python: str, package_dir: str, vector: dict, time: str) -> tuple[str, str]:
    """The engine's own exact concentration enclosure [lo, hi] for a vector at a time (its fixed proof profile)."""
    done = subprocess.run([science_python, "-I", "-c", _ENCLOSURE], input=json.dumps({"vector": vector, "time": time}),
                          capture_output=True, text=True, timeout=60,
                          env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
                               "DRBEAN_COUNTERDEX_DIR": os.path.abspath(package_dir)})
    if done.returncode:
        raise RuntimeError(f"engine enclosure probe failed: {done.stderr.strip().splitlines()[-1:]}")
    lo, hi = json.loads(done.stdout.strip().splitlines()[-1])
    return lo, hi


def engine_identity(science_python: str, package_dir: str) -> dict:
    """Which Counterdex the control workers import (same -I + sys.path as _worker), and its source digest."""
    package = os.path.abspath(package_dir)
    done = subprocess.run([science_python, "-I", "-c", _ENGINE_PROBE], capture_output=True, text=True, timeout=60,
                          env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "DRBEAN_COUNTERDEX_DIR": package})
    try:
        seen = json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"error": "engine identity probe failed", **engine_source_identity(package)}
    imported = os.path.realpath(seen.get("module_dir") or "")
    return {"version": seen.get("version"),
            "imported_from": "repository" if imported == os.path.realpath(os.path.join(package, "counterdex"))
            else "elsewhere", **engine_source_identity(package)}


def _worker(science_python: str, package_dir: str, job: dict, timeout: float = 180.0) -> dict:
    with tempfile.TemporaryDirectory(prefix="drbean-control-") as work:
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": work, "TMPDIR": work,
               "DRBEAN_COUNTERDEX_DIR": os.path.abspath(package_dir), "DRBEAN_GUARD_FILE": native.GUARD_FILE}
        if GUARD_LOG:
            env["DRBEAN_EGRESS_GUARD_LOG"] = GUARD_LOG
        done = subprocess.run([science_python, "-I", "-c", _WORKER], input=json.dumps(job), capture_output=True,
                              text=True, timeout=timeout, env=env, cwd=work)
    if done.returncode:
        raise RuntimeError(f"engine control worker failed: {done.stderr.strip().splitlines()[-1:]}")
    return json.loads(done.stdout)


def replay_class(result: dict) -> str:
    """Name what a replay outcome establishes; exclusion is scientific feedback, not corruption.

    Classes: passed, binding_failure, integrity_failure, mathematical_failure, unsupported_format,
    exhausted, infrastructure_failure, scientific_exclusion, incomplete_evidence, rejected:<code>.
    """
    if result["status"] == "passed":
        return "passed"
    if result["status"] in ("timed_out", "error"):
        return "infrastructure_failure"
    error = result.get("error") or {}
    code = error.get("code")
    if code in ("wrong_specification_binding", "wrong_scenario_binding"):
        return "binding_failure"
    if code == "artifact_mismatch":
        return "integrity_failure"
    if code == "exact_check_failure":
        return "mathematical_failure"
    if code in ("invalid_input", "unsupported_profile", "unsupported_version", "unsupported_model"):
        return "unsupported_format"
    if code in ("incomplete_export", "missing_artifact"):
        return "incomplete_evidence"
    if code == "resource_exhaustion":
        return "exhausted"
    report = result.get("report") or {}
    # Recorded claims that fresh recomputation contradicts are a mathematical failure, even when the fresh verdict
    # is itself an exclusion (harness finding H-REPLAY-CLASS-RECORDED-MISMATCH).
    if report.get("recorded_result_matches") is False or report.get("reason_code") == "recorded_result_mismatch":
        return "mathematical_failure"
    if (report.get("integrity") == "passed" and report.get("expected_binding") == "matches"
            and report.get("verification") == "invalid"):
        return "scientific_exclusion"
    if report.get("reason_code") in ("incomplete_export", "missing_artifact") or report.get("replay") == "unsupported":
        return "incomplete_evidence"
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
        replayed = _replay(science_python, package_dir, bundle, anchors)
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
        wrong = _replay(science_python, package_dir, bundle,
                              {**anchors, "problem_digest": native.wrong_anchor(anchors["problem_digest"])})
        record("defense:wrong_expected_identity", replay_class(wrong) == "binding_failure",
               "binding_failure", replay_class(wrong), "expected identity supplied separately from the bundle")
        flipped = _replay(science_python, package_dir, native.flip_one_byte(bundle), anchors)
        record("defense:changed_byte", replay_class(flipped) == "integrity_failure", "integrity_failure",
               replay_class(flipped), "one byte changed; original anchors")
        mutated = _worker(science_python, package_dir, {"op": "mutate", "bundle_b64": out["bundle_b64"],
                          "candidate_index": 0, "time": "6/1", "delta": "1/10"})
        mutated_bytes = base64.b64decode(mutated["bundle_b64"])
        original_anchor = _replay(science_python, package_dir, mutated_bytes, anchors)
        record("defense:mutation_rejected_by_original_anchor", replay_class(original_anchor) == "integrity_failure",
               "integrity_failure", replay_class(original_anchor),
               "false enclosure (+1/10 at 6 h) with internal hashes recomputed; real original anchor")
        diagnostic = _replay(science_python, package_dir, mutated_bytes,
                                   {**anchors, "suggestion_digest": mutated["suggestion_digest"]})
        record("defense:mutation_rejected_by_fresh_mathematics", replay_class(diagnostic) == "mathematical_failure",
               "mathematical_failure", {"class": replay_class(diagnostic),
                                        "field_paths": (diagnostic.get("error") or {}).get("field_paths")},
               "DIAGNOSTIC ONLY: a deliberately changed test anchor isolates the mathematical check. It sacrifices "
               "packet authentication on purpose and authenticates nothing; real releases use the original anchor")
        # Touching bands: allowance = half the engine's own centre gap at 8 h gives a non-positive exact margin.
        rows = {r["time"]: r for r in (out["report"]["checked"].get("rows") or [])}
        replayed = _replay(science_python, package_dir, bundle, anchors)
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

    # Packet-format and dependency attacks (master brief 2.11). Each uses the supported public replay path.
    if base and bundles.get("grid-6-allowance-0.2"):
        bundle, out = base
        anchors = {"problem_digest": out["problem_digest"], "suggestion_digest": out["suggestion_digest"]}
        truncated = _replay(science_python, package_dir, bundle[: len(bundle) // 2], anchors)
        record("defense:truncated_packet", replay_class(truncated) not in ("passed", "infrastructure_failure"),
               "rejected (not passed, not a crash)", {"class": replay_class(truncated),
                                                       "code": (truncated.get("error") or {}).get("code")},
               "packet cut in half; original anchors")
        oversized = bundle[:-1] + b"," + b'"pad":"' + b"x" * (4 * 1024 * 1024) + b'"}'
        big = _replay(science_python, package_dir, oversized, anchors)
        record("defense:oversized_packet", replay_class(big) in ("exhausted", "unsupported_format", "integrity_failure"),
               "exhausted (byte cap) before any parsing work", {"class": replay_class(big),
                                                                 "code": (big.get("error") or {}).get("code")},
               "packet padded past the 4 MiB admitted limit")
        other_bundle, other_out = bundles["grid-6-allowance-0.2"]
        crossed = _replay(science_python, package_dir, other_bundle, anchors)
        record("defense:another_runs_valid_packet", replay_class(crossed) in ("integrity_failure", "binding_failure"),
               "integrity or binding failure", {"class": replay_class(crossed),
                                                "code": (crossed.get("error") or {}).get("code")},
               "a valid packet of a different reviewed design replayed against this design's anchors")
        for edit, wanted in (("drop_artifacts", ("incomplete_evidence", "unsupported_format", "integrity_failure")),
                             ("duplicate_artifact", ("unsupported_format", "integrity_failure", "incomplete_evidence")),
                             ("unknown_profile", ("unsupported_format",))):
            edited = _worker(science_python, package_dir, {"op": "edit", "bundle_b64": out["bundle_b64"], "edit": edit})
            data = base64.b64decode(edited["bundle_b64"])
            real = _replay(science_python, package_dir, data, anchors)
            diagnostic = _replay(science_python, package_dir, data,
                                       {**anchors, "suggestion_digest": edited["suggestion_digest"]})
            # A format check may legitimately run before the digest check, so the real anchor may yield either.
            record(f"defense:{edit}", replay_class(real) in ("integrity_failure", "unsupported_format")
                   and replay_class(diagnostic) in wanted,
                   {"original_anchor": ["integrity_failure", "unsupported_format"], "diagnostic_anchor": list(wanted)},
                   {"original_anchor": replay_class(real), "diagnostic_anchor": replay_class(diagnostic),
                    "code": (diagnostic.get("error") or {}).get("code"),
                    "reason": ((diagnostic.get("report") or {}).get("reason_code"))},
                   "edited packet with recomputed suggestion digest: the real anchor rejects it first; a test-only "
                   "anchor then isolates format/dependency handling (it authenticates nothing)")

    # Metamorphic transformations (master brief 2.21): expectations follow from the admitted contract, and
    # assert binding plus predicates, never "every change must change every conclusion".
    def verdicts(rows_override=None, extra_rows=None, order=pair, times=("8/1",)):
        packet = json.loads(json.dumps(hero))
        if rows_override is not None:
            packet["dataset"]["rows"] = rows_override
        out = _worker(science_python, package_dir, {"op": "suggest", "problem": engine_problem(packet, extra_rows),
                      "workflow": workflow, "design": engine_design(order, list(times), "1/5", "wk5-metamorphic")})
        if "error" in out:
            return None, out, None
        replayed = _replay(science_python, package_dir, base64.b64decode(out["bundle_b64"]),
                                 {"problem_digest": out["problem_digest"], "suggestion_digest": out["suggestion_digest"]})
        found = {c["candidate_id"]: ("compatible" if c.get("verification") == "valid" else
                                     "excluded" if c.get("verification") == "invalid" else c.get("verification"))
                 for c in (replayed.get("report") or {}).get("fresh_checked", {}).get("candidate_results", [])}
        return found, out, replayed

    rows = hero["dataset"]["rows"]
    base_verdicts, base_out, base_replay = verdicts()
    def oracle_rows(rs):
        return {c["id"]: kinetics.history_verdict({k: exact(c[k]) for k in ("A", "ke", "ka")}, rs) for c in pair}
    tightened = [dict(r) for r in rows]
    tightened[2] = {**tightened[2], "hard_allowance": "1/20"}
    t_verdicts, _, _ = verdicts(tightened)
    record("metamorphic:tightened_row_allowance", t_verdicts == oracle_rows(tightened) and t_verdicts != base_verdicts,
           {"engine_equals_independent_oracle": oracle_rows(tightened)}, {"engine": t_verdicts, "baseline": base_verdicts},
           "row 3 allowance 0.5 -> 0.05; verdicts recomputed, compared with the independent decimal oracle")
    widened = [{**r, "hard_allowance": "3/5"} for r in rows]
    w_verdicts, _, _ = verdicts(widened)
    record("metamorphic:widened_allowances_keep_compatibility",
           bool(base_verdicts) and all(w_verdicts.get(c) == "compatible" for c, v in base_verdicts.items()
                                       if v == "compatible"),
           "every previously compatible candidate stays compatible", {"widened": w_verdicts, "baseline": base_verdicts},
           "all historical allowances 0.5 -> 0.6 (monotonicity); identities change, conclusions may not regress")
    wild = {"id": "excluded_wild_row", "time": "3/1", "concentration": "100/1", "hard_allowance": "1/2",
            "included": False, "notes": "Excluded control row with an absurd value"}
    x_verdicts, x_out, _ = verdicts(extra_rows=[wild])
    record("metamorphic:excluded_row_is_not_a_constraint",
           x_verdicts == base_verdicts and x_out.get("problem_digest") != base_out.get("problem_digest"),
           {"verdicts": "unchanged", "problem_digest": "changes (complete-body identity)"},
           {"verdicts": x_verdicts, "digest_changed": x_out.get("problem_digest") != base_out.get("problem_digest")},
           "an excluded row with value 100 mg/L must not exclude any candidate, yet it is part of the reviewed record")
    _, ordered, _ = verdicts(times=("6/1", "8/1"))
    s_verdicts, swapped, _ = verdicts(order=list(reversed(pair)), times=("6/1", "8/1"))
    sel_a, chk_a = _selected(ordered["report"]) if "report" in ordered else (None, {})
    sel_b, chk_b = _selected(swapped["report"]) if "report" in swapped else (None, {})
    def margin(chk, sel):
        return next((r.get("margin") for r in chk.get("rows", []) if r.get("time") == sel), None)
    record("metamorphic:swapped_pair_order", sel_a == sel_b and margin(chk_a, sel_a) == margin(chk_b, sel_b)
           and s_verdicts == base_verdicts,
           {"selected_time": sel_a, "margin": "identical", "verdicts_by_id": "identical"},
           {"selected": [sel_a, sel_b], "margins_equal": margin(chk_a, sel_a) == margin(chk_b, sel_b),
            "verdicts": s_verdicts}, "candidate order reversed; results keyed by candidate id, not position")

    # Endpoint equality: a candidate with ke exactly on the closed claim's lower endpoint is inside.
    endpoint = [dict(pair[0], id="endpoint-ke-0.10", ke="0.10"), pair[1]]
    out = _worker(science_python, package_dir, {"op": "suggest", "problem": problem, "workflow": workflow,
                  "design": engine_design(endpoint, ["8/1"], "1/5", "wk5-endpoint")})
    if "error" in out:
        record("semantics:closed_endpoint_is_inside", False, "outside_closed_claim false", out["error"],
               "engine create_suggestion")
    else:
        replayed = _replay(science_python, package_dir, base64.b64decode(out["bundle_b64"]),
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
        replayed = _replay(science_python, package_dir, base64.b64decode(out["bundle_b64"]),
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
    results.extend(_coordinator_science_controls(science_python, package_dir, hero, pair, problem, workflow, vectors))
    return results


def _ratio(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def _fresh_verdicts(replayed: dict) -> dict:
    return {c["candidate_id"]: ("compatible" if c.get("verification") == "valid" else
                                "excluded" if c.get("verification") == "invalid" else c.get("verification"))
            for c in (replayed.get("report") or {}).get("fresh_checked", {}).get("candidate_results", [])}


def _coordinator_science_controls(science_python: str, package_dir: str, hero: dict, pair: list[dict], problem: dict,
                                  workflow: dict, vectors: dict) -> list[dict]:
    """SCI-06 and SCI-05 controls for the frozen coordinator predicates (evaluation/coordinator/predicates.v1.json).

    Expectations come from the independent oracle (kinetics) and the admitted contract, never from engine output.
    """
    results = []

    def record(control_id, passed, expected, observed, scope):
        results.append({"id": control_id, "passed": bool(passed), "expected": expected, "observed": observed,
                        "scope": scope})

    # The design scope: 8 h with the reviewed future allowance 0.2, where the fixed pair separates (positive margin).
    disjoint = kinetics.separation_margin(list(vectors.values()), "8", "1/5") > 0
    centres = {cid: Fraction(kinetics.concentration(vec, "8")) for cid, vec in vectors.items()}
    reading = Fraction(round(sum(centres.values()) / 2 * 1000), 1000)  # midpoint of the two centres, 3 decimals
    declared = Fraction(math.ceil((max(abs(c - reading) for c in centres.values()) + Fraction(1, 10)) * 100), 100)
    history = hero["dataset"]["rows"]

    def followup(allowance: Fraction, scenario: str):
        row = {"id": "hypothetical-followup", "time": "8/1", "concentration": _ratio(reading),
               "hard_allowance": _ratio(allowance), "included": True, "notes": "Hypothetical follow-up reading",
               "allowance_origin": "Reviewed hypothetical hard allowance declared for this reading"}
        out = _worker(science_python, package_dir, {"op": "suggest", "problem": engine_problem(hero, [row]),
                      "workflow": workflow, "design": engine_design(pair, ["10/1", "12/1"], "1/5", scenario,
                                                                    maximum_horizon="12/1")})
        oracle = {cid: kinetics.history_verdict(vec, [*history, row]) for cid, vec in vectors.items()}
        return out, oracle

    wide, wide_oracle = followup(declared, "wk5-followup-declared-allowance")
    if "error" in wide:
        record("followup:both_compatible_declared_allowance", False, "both compatible", wide["error"], "engine")
    else:
        replayed = _replay(science_python, package_dir, base64.b64decode(wide["bundle_b64"]),
                           {"problem_digest": wide["problem_digest"], "suggestion_digest": wide["suggestion_digest"]})
        found = _fresh_verdicts(replayed)
        ok = (disjoint and declared > Fraction(1, 5) and found == wide_oracle
              and set(found.values()) == {"compatible"} and len(found) == 2 and replay_class(replayed) == "passed")
        record("followup:both_compatible_declared_allowance", ok,
               {"per_candidate": "both compatible (independent oracle)", "aggregate": "passed",
                "design_scope_bands_disjoint": True},
               {"reading": _ratio(reading), "declared_allowance": _ratio(declared), "per_candidate": found,
                "independent_oracle": wide_oracle, "aggregate": replay_class(replayed),
                "design_scope_bands_disjoint": disjoint},
               "hypothetical 8 h reading with its own declared allowance, wider than the design's 0.2: both original "
               "candidates legitimately stay compatible; this does not contradict the 0.2 separation")

    tight, tight_oracle = followup(Fraction(1, 5), "wk5-followup-design-allowance")
    if "error" in tight:
        record("semantics:same_reading_at_separating_allowance_is_not_both_compatible", False, "not both compatible",
               tight["error"], "engine")
        record("defense:forged_both_compatible_rejected", False, "rejected", tight["error"], "engine")
    else:
        anchors = {"problem_digest": tight["problem_digest"], "suggestion_digest": tight["suggestion_digest"]}
        replayed = _replay(science_python, package_dir, base64.b64decode(tight["bundle_b64"]), anchors)
        found = _fresh_verdicts(replayed)
        record("semantics:same_reading_at_separating_allowance_is_not_both_compatible",
               disjoint and found == tight_oracle and list(found.values()).count("compatible") <= 1 and len(found) == 2,
               {"per_candidate": "at most one compatible; equals the independent oracle", "design_scope_disjoint": True},
               {"reading": _ratio(reading), "per_candidate": found, "independent_oracle": tight_oracle,
                "design_scope_bands_disjoint": disjoint},
               "the same reading at the separating time and allowance: the closed 0.2 bands are disjoint, so no reading "
               "can keep both candidates there")
        edited = _worker(science_python, package_dir, {"op": "edit", "bundle_b64": tight["bundle_b64"],
                                                       "edit": "claim_all_valid"})
        data = base64.b64decode(edited["bundle_b64"])
        real = _replay(science_python, package_dir, data, anchors)
        diagnostic = _replay(science_python, package_dir, data, {**anchors, "suggestion_digest": edited["suggestion_digest"]})
        diagnostic_report = diagnostic.get("report") or {}
        fresh = _fresh_verdicts(diagnostic)
        record("defense:forged_both_compatible_rejected",
               replay_class(real) == "integrity_failure" and replay_class(diagnostic) == "mathematical_failure"
               and fresh == tight_oracle and "compatible" not in set(fresh.values()) - {None},
               {"original_anchor": "integrity_failure", "diagnostic_anchor": "mathematical_failure",
                "fresh_per_candidate": "the independent oracle's verdicts"},
               {"original_anchor": replay_class(real), "diagnostic_anchor": replay_class(diagnostic),
                "recorded_result_matches": diagnostic_report.get("recorded_result_matches"),
                "reason": diagnostic_report.get("reason_code"), "fresh_per_candidate": fresh},
               "test-only forgery: every claimed candidate result set to compatible at the separating 8 h / 0.2 scope "
               "(a contradiction). The real anchor rejects it first; a test-only anchor then shows that fresh "
               "recomputation flags the mismatch. The test anchor authenticates nothing")

    guidance_design = {**engine_design(pair, ["6/1", "8/1"], "1/5", "wk5-numerical-guidance"),
                       "requested_tier": "numerical_guidance"}
    out = _worker(science_python, package_dir, {"op": "suggest", "problem": problem, "workflow": workflow,
                                                "design": guidance_design})
    if "error" in out:
        record("semantics:numerical_guidance_is_not_checked_separation", False, "numerical guidance", out["error"],
               "engine")
    else:
        replayed = _replay(science_python, package_dir, base64.b64decode(out["bundle_b64"]),
                           {"problem_digest": out["problem_digest"], "suggestion_digest": out["suggestion_digest"]})
        report, checked = out["report"], out["report"].get("checked") or {}
        fresh = (replayed.get("report") or {})
        record("semantics:numerical_guidance_is_not_checked_separation",
               report.get("tier") == "numerical_guidance" and checked.get("tier") != "checked_pair_separation"
               and checked.get("selected_time") is None and replay_class(replayed) != "passed"
               and (fresh.get("fresh_checked") or {}).get("tier") != "checked_pair_separation"
               and fresh.get("verification") != "valid",
               {"tier": "numerical_guidance", "checked_selection": None, "replay": "not passed; never checked"},
               {"tier": report.get("tier"), "checked_tier": checked.get("tier"),
                "checked_selected_time": checked.get("selected_time"),
                "numerical_selected_time": (report.get("numerical") or {}).get("selected_time"),
                "replay": replay_class(replayed), "replay_reason": fresh.get("reason_code"),
                "replay_verification": fresh.get("verification")},
               "requested numerical guidance on the fixed pair's [6, 8] h grid at 0.2: ranking is guidance only; "
               "neither the record nor a replay may present it as checked separation")

    observed, ok = {}, True
    for label, grid, feasible_expected in (
            ("middle_time_unavailable", [("6/1", True), ("7/1", False), ("8/1", True)], {"6/1", "8/1"}),
            ("best_time_unavailable", [("6/1", True), ("8/1", False)], {"6/1"})):
        design = engine_design(pair, [t for t, _ in grid], "1/5", f"wk5-{label.replace('_', '-')}")
        design["grid"] = [{"time": t, "feasible": f, "reason": "Reviewed feasible time (control)" if f else
                           f"Declared unavailable at {t} h (control)"} for t, f in grid]
        out = _worker(science_python, package_dir, {"op": "suggest", "problem": problem, "workflow": workflow,
                                                    "design": design})
        if "error" in out:
            ok, observed[label] = False, out["error"]
            continue
        numerical, (selected, checked) = out["report"].get("numerical") or {}, _selected(out["report"])
        rows = {r.get("time"): r for r in numerical.get("rows") or []}
        unavailable = [t for t, f in grid if not f]
        kept = all(t in rows and rows[t].get("status") != "evaluated" and rows[t].get("rank") is None
                   and str(t) in (rows[t].get("feasibility_reason") or "") for t in unavailable)
        ranked = set(numerical.get("ranked_times") or []) | set(checked.get("ranked_times") or [])
        case_ok = (set(rows) == {t for t, _ in grid} and kept and not ranked & set(unavailable)
                   and numerical.get("evaluated_count") == len(feasible_expected)
                   and selected in feasible_expected and numerical.get("selected_time") in feasible_expected)
        ok = ok and case_ok
        observed[label] = {"rows": {t: {k: r.get(k) for k in ("status", "rank", "reason_code")} for t, r in rows.items()},
                           "ranked_times": sorted(ranked), "evaluated_count": numerical.get("evaluated_count"),
                           "checked_selected_time": selected, "numerical_selected_time": numerical.get("selected_time"),
                           "passed": case_ok}
    record("semantics:unavailable_grid_times_are_kept_and_never_selected", ok,
           {"unavailable_rows": "kept with their declared reason, not evaluated, ranked or selected",
            "evaluated_count": "the number of available times", "selection": "an available time only"},
           observed, "approved grid with declared unavailable times at 0.2; the evaluated subset is explicit and "
           "no continuous-time optimum is implied")
    return results
