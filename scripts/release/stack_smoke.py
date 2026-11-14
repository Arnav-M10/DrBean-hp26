#!/usr/bin/env python3
"""Provider-free actual-stack smoke through the ordinary launcher (launch acceptance).

Starts the real API, worker and web with scripts/dev/launcher.py on an
ISOLATED temporary store (your var/ is untouched), drives the manual HTTP path
with the shared synthetic five-row example, restarts, and reopens the same
evidence. No model provider is contacted: the launcher strips provider
credentials and the plan declares provider "none".

It reports two separate verdicts:
  launch_path      the documented start/stop/restart path works and state survives
  g1_actual_core   a real scientific result came back through the API (gate G1)

  python3 scripts/release/stack_smoke.py [--record] [--require-science]

Exit 0 when launch_path passes (and, with --require-science, G1 too). This is
a launch qualification, not Owner 5's HTTP invariant suite.
Ports 8000 and 4173 must be free; a running stack is never stopped by this script.
"""
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LAUNCHER = os.path.join(REPO, "scripts", "dev", "launcher.py")
API = "http://127.0.0.1:8000"
PREFIX = "/api/bean/v1"

# Shared synthetic integration example (values of fixtures/intake/clean.png). The domain and
# claim are team-selected assumptions for review, not values extracted from the image.
ROWS = [("0.25", "1/4", "4.80", "24/5"), ("0.5", "1/2", "7.20", "36/5"), ("1", "1/1", "8.00", "8/1"),
        ("2", "2/1", "6.80", "34/5"), ("4", "4/1", "5.70", "57/10")]
DOMAIN = {"A": {"lower": "1/1000", "upper": "30/1"}, "ke": {"lower": "3/200", "upper": "7/20"},
          "ka": {"lower": "2/5", "upper": "8/1"}, "rate_order": "ke_lt_ka"}
TARGET = {"parameter": "ke", "lower": "1/10", "upper": "17/100", "closed": True}


class Client:
    def __init__(self, token):
        self.token = token
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(self, method, path, body=None, key=None, raw=False):
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        data = None
        if body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
        if method == "POST":
            headers["Idempotency-Key"] = key or uuid.uuid4().hex
        request = urllib.request.Request(API + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=20) as response:
                payload = response.read()
                return response.status, (payload if raw else json.loads(payload)), dict(response.headers)
        except urllib.error.HTTPError as error:
            payload = error.read()
            try:
                return error.code, json.loads(payload), dict(error.headers)
            except ValueError:
                return error.code, None, dict(error.headers)


def launcher(command, var_dir):
    env = {**os.environ, "DRBEAN_VAR_DIR": var_dir}
    done = subprocess.run([sys.executable, LAUNCHER, command], env=env, capture_output=True, text=True, timeout=180)
    return done.returncode, done.stdout + done.stderr


def main(argv):
    checks, facts = [], {}

    def check(name, ok, detail=""):
        checks.append({"id": name, "passed": bool(ok), "detail": str(detail)[:300]})
        return ok

    var_dir = tempfile.mkdtemp(prefix="drbean-smoke-")
    started = False
    try:
        # A decoy credential in this process's environment must not reach the product.
        os.environ.update(GEMINI_API_KEY="decoy-not-a-real-key", GEMINI_MODEL="decoy-model",
                          BEAN_GEMINI_ACCOUNT_GATE="approved", BEAN_GEMINI_ACCOUNT_DECISION_ID="decoy")
        code, text = subprocess.run([os.path.join(REPO, ".venv", "bin", "python"), "-m", "bean_api.bootstrap"],
                                    env={"BEAN_AUTH_FILE": os.path.join(var_dir, "auth.json"),
                                         "PATH": os.environ.get("PATH", "")},
                                    capture_output=True, text=True).returncode, ""
        if not check("isolated-auth-created", code == 0, "bootstrap in a temporary store"):
            raise RuntimeError("backend runtime missing: run scripts/dev/setup.sh")
        code, text = launcher("start", var_dir)
        started = code == 0
        if not check("start-one-command", started, text.strip().splitlines()[-1] if text.strip() else ""):
            raise RuntimeError(text[-1500:])
        with open(os.path.join(var_dir, "auth.json"), encoding="utf-8") as handle:
            client = Client(next(iter(json.load(handle).values())))  # this smoke's own throwaway token

        _, caps, _ = Client(None).call("GET", PREFIX + "/capabilities")
        science, gemini = caps["science"], caps["gemini"]
        facts["science_capabilities"] = {k: science.get(k) for k in (
            "implemented", "configured", "available", "verified_in_environment", "adapter", "adapter_version",
            "reason", "baseline_discovery", "design_tiers", "native_replay", "browser_replay")}
        facts["ai_mode_reported_by_api"] = caps.get("ai_mode")
        check("gemini-live-disabled-despite-decoy-key", not gemini["configured"] and not gemini["account_gate_passed"]
              and gemini["model"] is None and not gemini.get("dispatch_enabled", False),
              f"configured={gemini['configured']} model={gemini['model']} "
              f"dispatch_enabled={gemini.get('dispatch_enabled')} ai_mode={caps.get('ai_mode')}")
        status, _, _ = Client(None).call("GET", PREFIX + "/workspaces")
        check("unauthenticated-request-refused", status == 401, status)

        _, workspace, _ = client.call("POST", PREFIX + "/workspaces", {"name": "stack smoke (synthetic)"})
        w = workspace["id"]
        dataset_body = {
            "schema_version": "DB-SC-1", "experiment_id": "synthetic_shared_example",
            "time_origin": "Elapsed hours from the synthetic experiment's declared t=0", "origin": "synthetic",
            "parent_id": None, "change_reason": "Shared synthetic integration example; stack smoke",
            "rows": [{"id": f"row_{i}", "time": t, "concentration": c, "hard_allowance": "1/2", "included": True,
                      "original_values": {"time": ts, "concentration": cs, "hard_allowance": "0.50"},
                      "source_asset_id": None, "notes": ""} for i, (ts, t, cs, c) in enumerate(ROWS, 1)]}
        status, dataset, _ = client.call("POST", f"{PREFIX}/workspaces/{w}/datasets", dataset_body)
        check("dataset-accepted", status == 201, dataset if status != 201 else dataset["id"])
        status, problem, _ = client.call("POST", f"{PREFIX}/workspaces/{w}/problems", {
            "schema_version": "DB-SC-1", "dataset_id": dataset["id"], "dataset_digest": dataset["digest"],
            "model": "two_rate_concentration", "domain": DOMAIN, "initial_concentration": "0/1",
            "observable": "concentration", "time_unit": "h", "concentration_unit": "mg/L", "rate_unit": "1/h",
            "target": TARGET})
        check("problem-accepted", status == 201, problem if status != 201 else problem["id"])
        bad = json.loads(json.dumps(dataset_body))
        bad["rows"][0]["concentration"] = 4.8  # a float must be refused, not repaired
        status, error, _ = client.call("POST", f"{PREFIX}/workspaces/{w}/datasets", bad)
        check("float-input-refused-not-repaired", status == 422, f"{status} {error.get('code') if error else ''}")
        facts["float_refusal_names_the_field"] = bool(error and error.get("field_paths"))  # see issue ledger I-011
        plan_request = {"expected_current_revision_id": problem["id"], "plan": {
            "schema_version": "DB-SC-1", "problem_id": problem["id"], "problem_digest": problem["digest"],
            "dataset_id": dataset["id"],
            "scenarios": [{"id": "baseline", "problem_id": problem["id"], "problem_digest": problem["digest"],
                           "kind": "baseline", "label": "Reviewed manual baseline"}],
            "permitted_tools": ["read_scoped_evidence", "execute_approved_scenario", "record_allowed_skip",
                                "return_grounded_explanation"],
            "budget": {"provider_turns": 0, "tool_calls": 2, "scientific_reservations": 1, "wall_seconds": 120,
                       "scientific_wall_seconds": 120},
            "provider_disclosure": {"provider": "none", "model": None, "source_asset_ids": [],
                                    "context_fields": [], "permission_id": None}, "parent_plan_id": None,
            "scientific_profile": "counterdex.v1", "objective": {
                "question": "Do the reviewed synthetic measurements force ke into the claimed closed interval?",
                "success_criterion": "A checked compatible candidate outside the interval, or an honest "
                                     "unresolved or unavailable status."}}}
        status, plan, _ = client.call("POST", f"{PREFIX}/workspaces/{w}/plans", plan_request)
        check("plan-frozen", status == 201, plan if status != 201 else plan["digest"][:12])
        run_body = {"approval_id": "missing", "expected_plan_digest": plan["digest"]}
        status, _, _ = client.call("POST", f"{PREFIX}/plans/{plan['id']}/runs", run_body)
        check("run-without-approval-refused", status >= 400, status)
        status, approval, _ = client.call("POST", f"{PREFIX}/plans/{plan['id']}/approvals", {
            "expected_plan_digest": plan["digest"], "expected_current_revision_id": problem["id"], "accepted": True})
        check("approval-recorded", status == 201, approval if status != 201 else approval["id"])
        run_body["approval_id"] = approval["id"]
        key = uuid.uuid4().hex
        status, run, _ = client.call("POST", f"{PREFIX}/plans/{plan['id']}/runs", run_body, key)
        check("run-accepted", status == 202, run if status != 202 else run["id"])
        status2, again, _ = client.call("POST", f"{PREFIX}/plans/{plan['id']}/runs", run_body, key)
        check("duplicate-start-returns-same-run", status2 in (200, 202) and again.get("id") == run["id"], status2)
        status_k, conflict, _ = client.call("POST", f"{PREFIX}/plans/{plan['id']}/approvals", {
            "expected_plan_digest": "0" * 64, "expected_current_revision_id": problem["id"], "accepted": True}, key)
        check("same-key-different-body-conflicts", status_k >= 400, f"{status_k} {(conflict or {}).get('code')}")
        status3, other, _ = client.call("POST", f"{PREFIX}/plans/{plan['id']}/runs", run_body, uuid.uuid4().hex)
        check("fresh-key-cannot-create-second-run", status3 >= 400 or other.get("id") == run["id"], status3)

        deadline, current = time.monotonic() + 150, run
        while time.monotonic() < deadline:
            _, current, _ = client.call("GET", f"{PREFIX}/runs/{run['id']}")
            if current.get("state") in ("completed", "failed", "cancelled", "interrupted"):
                break
            time.sleep(1)
        execution = current.get("state")
        check("worker-finished-the-run", execution == "completed", execution)
        results = []
        for scenario in current.get("scenarios", []):
            if scenario.get("result_id"):
                _, record, _ = client.call("GET", f"{PREFIX}/records/{scenario['result_id']}")
                results.append(record)
        body = (results[0]["body"].get("result") or {}) if results else {}
        check("evidence-bound-to-this-run-and-problem", bool(results) and results[0]["body"]["run_id"] == run["id"]
              and results[0]["body"]["expected_problem_digest"] == problem["digest"], "run id and problem digest match")
        facts["baseline_result"] = {k: body.get(k) for k in ("scientific_outcome", "verification",
                                                             "expected_binding", "replay", "reason_code")}
        facts["baseline_candidates"] = len(body.get("candidates") or [])
        facts["baseline_artifacts"] = len(body.get("artifacts") or [])
        check("result-record-present", bool(results), f"{len(results)} result record(s)")

        status, report, _ = client.call("POST", f"{PREFIX}/runs/{run['id']}/reports", None)
        status_d, report_bytes, headers = client.call("GET", f"{PREFIX}/reports/{report['id']}/download", raw=True)
        digest = hashlib.sha256(report_bytes).hexdigest() if status_d == 200 else None
        check("report-bytes-match-declared-hash", digest and digest == headers.get("x-artifact-sha256",
              headers.get("X-Artifact-SHA256")), digest)
        _, attempts, _ = client.call("GET", f"{PREFIX}/workspaces/{w}/provider-attempts")
        check("zero-provider-attempts-recorded", attempts == [] or attempts == {"attempts": []}
              or (isinstance(attempts, dict) and not any(attempts.values())), json.dumps(attempts)[:120])

        # Restart: accepted evidence reopens; the consumed approval cannot start another run.
        code, text = launcher("stop", var_dir)
        started = False
        check("stop-only-owned-processes", code == 0, text.strip().splitlines()[0])
        code, text = launcher("recover", var_dir)
        check("recover-after-stop", code == 0, text.strip().splitlines()[0] if text.strip() else "")
        code, text = launcher("start", var_dir)
        started = code == 0
        check("restart", started, "")
        _, reopened, _ = client.call("GET", f"{PREFIX}/runs/{run['id']}")
        check("run-reopens-unchanged-after-restart", reopened == current, reopened.get("id"))
        _, report_again, _ = client.call("GET", f"{PREFIX}/reports/{report['id']}/download", raw=True)
        check("report-bytes-identical-after-restart", report_again == report_bytes, digest)
        status, replay_attempt, _ = client.call("POST", f"{PREFIX}/plans/{plan['id']}/runs", run_body, uuid.uuid4().hex)
        check("consumed-approval-not-replayed-after-restart",
              status >= 400 or replay_attempt.get("id") == run["id"], status)
    except Exception as error:  # report, never hide
        check("smoke-completed", False, f"{type(error).__name__}: {error}")
    finally:
        if started:
            launcher("stop", var_dir)
        shutil.rmtree(var_dir, ignore_errors=True)

    launch_ok = all(item["passed"] for item in checks)
    result = facts.get("baseline_result") or {}
    science = facts.get("science_capabilities") or {}
    real_science = result.get("scientific_outcome") in (
        "certified_counterexample", "numerical_candidate", "no_counterexample_found", "inconclusive") \
        and result.get("reason_code") != "explicit_regression_seed_not_discovery"
    if real_science:
        reason = (f"baseline returned {result.get('scientific_outcome')!r} with {facts.get('baseline_candidates')} "
                  f"candidate(s) and {facts.get('baseline_artifacts')} artifact(s) through ordinary startup")
    elif science.get("available"):
        reason = (f"not passed: the {science.get('adapter')} adapter is available for design and replay, but "
                  f"baseline discovery is not ({science.get('reason')}); the approved baseline returned "
                  f"{result.get('scientific_outcome')!r} ({result.get('reason_code')}). With no discovered "
                  "candidates, no design can be requested over HTTP. No scientific computation ran.")
    else:
        reason = (f"not passed: the API's scientific adapter is unavailable ({science.get('reason')}); the "
                  f"baseline returned {result.get('scientific_outcome')!r}. No scientific computation ran.")
    g1 = {"passed": launch_ok and real_science, "reason": reason}
    commit = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    record = {"recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tested_commit": commit,
              "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
              "lane": "offline actual stack; AI placeholder; zero provider dispatch by construction",
              "launch_path": {"passed": launch_ok, "passed_checks": sum(c["passed"] for c in checks),
                              "total_checks": len(checks)},
              "g1_actual_core": g1, "facts": facts, "checks": checks}
    for item in checks:
        print(f"  {'ok  ' if item['passed'] else 'FAIL'} {item['id']}  {item['detail']}")
    print(f"\nlaunch_path: {'PASSED' if launch_ok else 'FAILED'} "
          f"({record['launch_path']['passed_checks']}/{len(checks)})")
    print(f"g1_actual_core: {'PASSED' if g1['passed'] else 'NOT PASSED'}: {g1['reason']}")
    if "--record" in argv:
        path = os.path.join(REPO, "docs", "release-evidence", "stack-smoke.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print("recorded", os.path.relpath(path, REPO))
    return 0 if launch_ok and (g1["passed"] or "--require-science" not in argv) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
