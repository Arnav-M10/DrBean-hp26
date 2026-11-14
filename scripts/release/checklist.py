#!/usr/bin/env python3
"""Release checks tied to the tested commit.

  python3 scripts/release/checklist.py                  inventory: status report
  python3 scripts/release/checklist.py --strict-offline  offline release gate
  add --record to write docs/release-evidence/release-checklist.json
  add --fast to skip the stack and browser checks (they need ports 8000 and 4173)

Inventory mode is a status report and says so in its last line. It exits 1
when a check that ran has FAILED and 0 otherwise; its exit status is never a
release verdict. Use --strict-offline for a verdict.

Strict offline mode exits 1 unless every offline gate (G0-G4) has all of its
required evidence present and passing. Missing evidence fails the gate. Future
live-Gemini checks are listed as intentionally unrun and never block, and no
check here contacts a model provider: AI is in placeholder mode.

Gate and boundary definitions live in tests/integration/release_checklist.json.
Owner 5's suite (tests/integration/test_*.py) and harness (evaluation/) are
consumed here, not reimplemented.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BACKEND_PY = os.path.join(REPO, ".venv", "bin", "python")
ENGINE_PY = os.path.join(REPO, ".venv-engine", "bin", "python")
FIXTURES = os.path.join("packages", "groundwork_adapter", "fixtures")
sys.path.insert(0, os.path.join(REPO, "scripts", "dev"))
import launcher  # noqa: E402

ENV = launcher.child_env()  # placeholder AI: provider credentials never reach a check
EVIDENCE_PREFIXES = ("evaluation/results/", "evaluation/ledger/", "docs/release-evidence/")


def run(command, cwd=REPO, timeout=600, env=None):
    started = time.monotonic()
    try:
        done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env or ENV)
        code, text = done.returncode, done.stdout + done.stderr
    except FileNotFoundError as error:
        return {"status": "unrun", "detail": f"{error.filename} is not installed (run scripts/dev/setup.sh)"}
    except subprocess.TimeoutExpired:
        code, text = -1, f"timed out after {timeout} s"
    lines = text.strip().splitlines()
    return {"status": "passed" if code == 0 else "failed", "exit_code": code, "command": " ".join(command),
            "duration_s": round(time.monotonic() - started, 2), "detail": lines[-1][:200] if lines else "",
            "tail": lines[-8:], "output": text}


def git_state():
    def git(*args):
        return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True).stdout
    changed = [line for line in git("status", "--porcelain").splitlines()
               if not line[3:].startswith(EVIDENCE_PREFIXES)]
    return git("rev-parse", "HEAD").strip(), changed


def clean_tree():
    _, changed = git_state()
    return {"status": "passed" if not changed else "failed",
            "detail": "no untracked or modified files" if not changed else
            "uncommitted files could be hidden inputs: " + "; ".join(changed[:8])}


def runtimes():
    rows, ok = launcher.summarize(launcher.static_facts(), None)
    missing = [f"{fact}: {detail}" for state, fact, detail in rows if state == "MISSING"]
    return {"status": "passed" if ok else "failed", "detail": "backend .venv and engine .venv-engine qualified"
            if ok else "; ".join(missing)[:300]}


def engine_replay():
    """Engine standalone: fresh native replay of the prepared synthetic bundle against its anchors."""
    result = run([ENGINE_PY, "-m", "counterdex", "replay", os.path.join(FIXTURES, "checked_success.bundle.json"),
                  "--anchors", os.path.join(FIXTURES, "checked_success.anchors.json")],
                 env={"PATH": os.environ.get("PATH", "")})
    if result["status"] != "passed":
        return result
    try:
        report = json.loads(result["output"])
    except ValueError:
        return {**result, "status": "failed", "detail": "replay did not return JSON"}
    good = (report.get("replay") == "passed" and report.get("expected_binding") == "matches"
            and report.get("integrity") == "passed" and report.get("verification") == "valid")
    return {**result, "status": "passed" if good else "failed",
            "detail": f"replay={report.get('replay')} binding={report.get('expected_binding')} "
                      f"verification={report.get('verification')} (prepared synthetic fixture, engine CLI only)"}


def contracts_current():
    result = run([BACKEND_PY, "scripts/export_contracts.py"])
    if result["status"] != "passed":
        return result
    drift = subprocess.run(["git", "-C", REPO, "status", "--porcelain", "shared/contracts"],
                           capture_output=True, text=True).stdout.strip()
    return {**result, "status": "passed" if not drift else "failed",
            "detail": "exported schemas match the committed ones" if not drift else "schema drift: " + drift[:200]}


def node_check(script, unrun_code=3, extra_env=None):
    if not shutil.which("node"):
        return {"status": "unrun", "detail": "node is not installed"}
    probe = subprocess.run(["node", "-e", "require('playwright')"], cwd=os.path.join(REPO, "tests", "integration"),
                           capture_output=True)
    if probe.returncode != 0:
        return {"status": "unrun", "detail": "playwright is not installed (npm install in tests/integration)"}
    result = run(["node", script], env={**ENV, **(extra_env or {})}, timeout=300)
    if result.get("exit_code") == unrun_code:
        result.update(status="unrun", detail="playwright is not installed")
    return result


def stack_smoke():
    result = run([sys.executable, "scripts/release/stack_smoke.py", "--record"], env=dict(os.environ), timeout=400)
    path = os.path.join(REPO, "docs", "release-evidence", "stack-smoke.json")
    if result.get("status") == "unrun" or not os.path.exists(path):
        return {name: {"status": "unrun", "detail": result.get("detail", "")} for name in
                ("stack_launch_path", "stack_g1_real_science", "placeholder_ai_no_provider_attempts")}
    with open(path, encoding="utf-8") as handle:
        record = json.load(handle)
    commit, _ = git_state()
    if record["tested_commit"] != commit:
        stale = {"status": "unrun", "detail": "recorded smoke is for another commit"}
        return {"stack_launch_path": stale, "stack_g1_real_science": stale,
                "placeholder_ai_no_provider_attempts": stale}
    by_id = {c["id"]: c for c in record["checks"]}
    ai = [by_id.get(name) for name in ("gemini-live-disabled-despite-decoy-key", "zero-provider-attempts-recorded")]
    launch = record["launch_path"]
    return {
        "stack_launch_path": {"status": "passed" if launch["passed"] else "failed",
                              "detail": f"{launch['passed_checks']}/{launch['total_checks']} checks; isolated store; "
                                        f"{record['platform']}",
                              "tail": [f"{c['id']}: {c['detail']}" for c in record["checks"] if not c["passed"]]},
        "stack_g1_real_science": {"status": "passed" if record["g1_actual_core"]["passed"] else "failed",
                                  "detail": record["g1_actual_core"]["reason"], "missing_dependency": True},
        "placeholder_ai_no_provider_attempts": {
            "status": "passed" if all(c and c["passed"] for c in ai) else "failed",
            "detail": "a planted decoy key left Gemini unconfigured; the provider-attempt ledger stayed empty. "
                      "Process-level network denial is Owner 5's guard."},
    }


def owner5_suite():
    files = sorted(glob.glob(os.path.join(REPO, "tests", "integration", "test_*.py")))
    if not files:
        return {"status": "unrun", "detail": "Owner 5's HTTP/invariant suite (tests/integration/test_*.py) "
                                             "has not been delivered"}
    return run([BACKEND_PY, "-m", "pytest", "-q", *files], timeout=900)


def collect(fast):
    checks = {
        "clean_tree": clean_tree(),
        "runtimes": runtimes(),
        "launcher_tests": run([sys.executable, "-m", "unittest", "scripts/dev/test_launcher.py"]),
        "backend_tests": run([BACKEND_PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests",
                              "--ignore=tests/integration"]),
        "backend_lint": run([BACKEND_PY, "-m", "ruff", "check", "apps", "tests", "scripts"]),
        "contracts_current": contracts_current(),
        "engine_tests": run([ENGINE_PY, "-m", "unittest", "discover", "-s", "packages/groundwork_adapter/tests"],
                            env={"PATH": os.environ.get("PATH", "")}),
        "engine_native_replay_fixture": engine_replay(),
        "web_unit_tests": run(["node", "--test"], cwd=os.path.join(REPO, "apps", "web")),
        "harness_unit_tests": run([sys.executable, "-W", "error", "-m", "unittest", "discover", "-s",
                                   "evaluation/tests"]),
        "harness_manifest_verify": run([sys.executable, "evaluation/cli.py", "verify"]),
        "harness_grader_selftest": run([sys.executable, "evaluation/cli.py", "selftest"]),
        "secret_scan": run([sys.executable, "scripts/release/secret_scan.py"]),
        "owner5_http_suite": owner5_suite(),
        "web_source_review_browser_check": {"status": "unrun", "detail": "no source/value review control exists "
                                                                         "in the web workspace yet"},
    }
    skipped = {"status": "unrun", "detail": "skipped by --fast"}
    if fast:
        checks.update({name: skipped for name in ("web_manual_smoke", "web_backend_browser_check",
                                                  "stack_launch_path", "stack_g1_real_science",
                                                  "placeholder_ai_no_provider_attempts")})
    else:
        checks["web_manual_smoke"] = node_check("tests/integration/web_manual_smoke.mjs")
        checks["web_backend_browser_check"] = node_check("apps/web/check-backend.mjs", unrun_code=None)
        checks.update(stack_smoke())
    for check in checks.values():
        check.pop("output", None)
    return checks


def evaluate(items, checks):
    rows = []
    for item in items:
        required = [checks.get(name, {"status": "unrun"})["status"] for name in item["required"]]
        partial = [checks.get(name, {"status": "unrun"})["status"] for name in item.get("partial", [])]
        blockers = [name for name in item["required"] if checks.get(name, {"status": "unrun"})["status"] != "passed"]
        if required and all(s == "passed" for s in required):
            status = "passed"
        elif any(checks.get(n, {}).get("status") == "failed" and not checks[n].get("missing_dependency")
                 for n in item["required"]):
            status = "failed"
        elif any(s == "passed" for s in partial) or any(s == "passed" for s in required):
            status = "partial"
        else:
            status = "unrun"
        rows.append({**item, "status": status, "blocked_by": blockers})
    return rows


def main(argv):
    strict, fast = "--strict-offline" in argv, "--fast" in argv
    with open(os.path.join(REPO, "tests", "integration", "release_checklist.json"), encoding="utf-8") as handle:
        definition = json.load(handle)
    checks = collect(fast)
    gates = evaluate(definition["offline_gates"], checks)
    boundaries = evaluate(definition["boundaries"], checks)
    commit, changed = git_state()
    print(f"tested commit {commit} (uncommitted files: {len(changed)})  AI mode: placeholder, live Gemini not run\n")
    print("Checks:")
    for name, check in checks.items():
        print(f"  {check['status']:<7} {name:<36} {check.get('detail', '')[:150]}")
        if check["status"] == "failed" and not check.get("missing_dependency"):
            for line in check.get("tail", [])[-6:]:
                print(f"            {line[:160]}")
    print("\nOffline gates:")
    for gate in gates:
        print(f"  {gate['id']} {gate['status']:<8} {gate['gate']}"
              + (f"   missing or failing: {', '.join(gate['blocked_by'])}" if gate["blocked_by"] else ""))
    print("\nCross-owner boundaries:")
    for row in boundaries:
        print(f"  {row['id']} {row['status']:<8} {row['boundary']:<26} owners {','.join(row['owners'])}: {row['gap']}")
    print("\nFuture live checks (intentionally unrun; do not block the offline release):")
    for item in definition["future_live_checks_intentionally_unrun"]:
        print(f"  unrun    {item}")
    failed = [name for name, c in checks.items() if c["status"] == "failed" and not c.get("missing_dependency")]
    ready = all(gate["status"] == "passed" for gate in gates) and not failed
    tally = {s: sum(r["status"] == s for r in boundaries) for s in ("passed", "partial", "failed", "unrun")}
    print(f"\nboundaries: {tally}; gates passed: {sum(g['status'] == 'passed' for g in gates)}/{len(gates)}")
    verdict = ("OFFLINE RELEASE-READY (live Gemini still not run)." if ready else
               "NOT RELEASE-READY for the offline release: " + "; ".join(
                   f"{g['id']} needs {', '.join(g['blocked_by'])}" for g in gates if g["status"] != "passed"))
    if strict:
        print(f"STRICT OFFLINE GATE: {'PASS' if ready else 'FAIL'}. {verdict}")
    else:
        print(f"INVENTORY ONLY: this exit status is not a release verdict. The strict offline gate would "
              f"{'pass' if ready else 'FAIL'}. {verdict}")
    if "--record" in argv:
        out = os.path.join(REPO, "docs", "release-evidence", "release-checklist.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        strip = lambda rows: [{k: r[k] for k in ("id", "status", "blocked_by")} for r in rows]  # noqa: E731
        with open(out, "w", encoding="utf-8") as handle:
            json.dump({"recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "tested_commit": commit, "uncommitted_files": len(changed), "mode": "strict-offline"
                       if strict else "inventory", "fast": fast, "ai_mode": "placeholder",
                       "live_gemini": "not run", "platform": launcher.static_facts(),
                       "checks": {n: {k: v for k, v in c.items() if k != "tail"} for n, c in checks.items()},
                       "gates": strip(gates), "boundaries": strip(boundaries), "boundary_tally": tally,
                       "offline_release_ready": ready}, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print("recorded", os.path.relpath(out, REPO))
    if strict:
        return 0 if ready else 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
