#!/usr/bin/env python3
"""Release checks tied to the tested commit (work order sections 9 and 12).

Runs every automated check that exists today, then maps the twelve
cross-owner boundaries to passed / partial / failed / unrun. A boundary is
never marked passed from component tests alone.

  python3 scripts/release/checklist.py [--record]

--record writes evaluation/results/release-checklist.json. Exit 1 if any
automated check fails. Unrun boundaries do not fail the script, but the
summary states plainly that the build is not release-ready.
Optional: DRBEAN_API_BASE=http://127.0.0.1:PORT probes GET /api/bean/v1/capabilities.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "evaluation"))
from drbean_eval import contract, sanitize  # noqa: E402
from drbean_eval.runner import git_state  # noqa: E402
from drbean_eval.subject import HttpSubject  # noqa: E402

PY = sys.executable


def run(command, cwd=REPO, timeout=300):
    started = time.monotonic()
    try:
        done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        code, tail = done.returncode, (done.stdout + done.stderr).strip().splitlines()[-6:]
    except FileNotFoundError as error:
        return {"status": "unrun", "detail": f"{error.filename} is not installed"}
    except subprocess.TimeoutExpired:
        code, tail = -1, [f"timed out after {timeout} s"]
    return {"status": "passed" if code == 0 else "failed", "exit_code": code, "command": " ".join(command),
            "duration_s": round(time.monotonic() - started, 2), "tail": tail}


def clean_tree():
    dirty = subprocess.run(["git", "-C", REPO, "status", "--porcelain"], capture_output=True, text=True).stdout
    # Results written by a prior --record run are evidence, not hidden inputs.
    lines = [line for line in dirty.splitlines() if not line[3:].startswith("evaluation/results/")]
    return {"status": "passed" if not lines else "failed",
            "detail": "no untracked or modified files" if not lines else
            "the run could depend on files that are not in the commit: " + "; ".join(lines[:8])}


def web_smoke():
    if not shutil.which("node"):
        return {"status": "unrun", "detail": "node is not installed"}
    result = run(["node", "tests/integration/web_manual_smoke.mjs"])
    if result.get("exit_code") == 3:
        result.update(status="unrun", detail="playwright is not installed")
    return result


def capabilities():
    base = os.environ.get("DRBEAN_API_BASE")
    if not base:
        return {"status": "unrun", "detail": "DRBEAN_API_BASE is not set; no backend exists in this checkout"}
    info = HttpSubject(base).describe()
    if "capabilities" not in info:
        return {"status": "failed", "detail": info.get("capabilities_error")}
    text = json.dumps(info["capabilities"])
    leaks = sanitize.find_leaks(text)
    return {"status": "passed" if not leaks else "failed",
            "detail": "capabilities answered without credentials or sentinels" if not leaks else str(leaks)}


CHECKS = {
    "clean_tree": clean_tree,
    "harness_unit_tests": lambda: run([PY, "-W", "error", "-m", "unittest", "discover", "-s", "evaluation/tests"]),
    "manifest_verify": lambda: run([PY, "evaluation/cli.py", "verify"]),
    "grader_selftest": lambda: run([PY, "evaluation/cli.py", "selftest"]),
    "web_unit_tests": lambda: run(["node", "--test"], cwd=os.path.join(REPO, "apps", "web")),
    "web_manual_smoke": web_smoke,
    "secret_scan": lambda: run([PY, "scripts/release/secret_scan.py"]),
    "capabilities_probe": capabilities,
}


def main(argv):
    results = {name: check() for name, check in CHECKS.items()}
    with open(os.path.join(REPO, "tests", "integration", "release_checklist.json"), encoding="utf-8") as handle:
        boundaries = json.load(handle)["boundaries"]
    rows = []
    for item in boundaries:
        statuses = [results[name]["status"] for name in item["checks"]]
        if "failed" in statuses:
            status = "failed"
        elif not statuses or "unrun" in statuses and item["best_possible_today"] == "unrun":
            status = "unrun"
        elif all(s == "passed" for s in statuses):
            status = item["best_possible_today"]
        else:
            status = "unrun"
        rows.append({"id": item["id"], "boundary": item["boundary"], "status": status, "gap": item["gap"],
                     "owners": item["owners"], "evidence_checks": item["checks"]})
    state = git_state(REPO)
    print(f"tested commit {state['commit']} (dirty={state['dirty']})\n\nAutomated checks:")
    for name, result in results.items():
        print(f"  {result['status']:<7} {name}  {result.get('detail') or ''}")
        if result["status"] == "failed":
            print("          " + "\n          ".join(result.get("tail", [])))
    print("\nCross-owner boundaries:")
    for row in rows:
        print(f"  {row['id']} {row['status']:<7} {row['boundary']:<26} owners {','.join(row['owners'])}: {row['gap']}")
    tally = {s: sum(r["status"] == s for r in rows) for s in ("passed", "partial", "failed", "unrun")}
    failed_checks = [name for name, result in results.items() if result["status"] == "failed"]
    ready = tally["passed"] == len(rows) and not failed_checks
    print(f"\nboundaries: {tally}. " + ("RELEASE-READY." if ready else
          "NOT RELEASE-READY: boundaries without end-to-end evidence remain."))
    if "--record" in argv:
        out = os.path.join(REPO, "evaluation", "results", "release-checklist.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as handle:
            json.dump({"recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "tested_commit": state["commit"], "worktree_dirty": state["dirty"],
                       "contract": {"revision": "GF-2", "wire_profile": "DB-SC-1"},
                       "checks": results, "boundaries": rows, "tally": tally, "release_ready": ready},
                      handle, indent=2, sort_keys=True)
            handle.write("\n")
        print("recorded", os.path.relpath(out, REPO))
    return 1 if failed_checks else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
