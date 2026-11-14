#!/usr/bin/env python3
"""Dr. Bean evaluation harness command line. Standard library only; never dispatches a model request.

  python3.11 evaluation/cli.py verify               check the frozen manifest and its archived ancestry
  python3.11 evaluation/cli.py selftest             prove the grader on exemplars (not product evidence)
  python3.11 evaluation/cli.py run --lane LANE [--subject SPEC] [--only ID ...]
  python3.11 evaluation/cli.py run --lane offline_real_science --subject http-launch
                                                    launch an isolated local API + worker, drive real HTTP
  python3.11 evaluation/cli.py controls             engine-level native controls (fresh CPython 3.11 replay)
  python3.11 evaluation/cli.py gate [--require release] [--output FILE]
                                                    machine-readable release gates; nonzero if a requested gate fails
  python3.11 evaluation/cli.py inventory            offline inventory (same gates, informational, exit 0)
  python3.11 evaluation/cli.py history              verify the append-only, hash-chained attempt history
  python3.11 evaluation/cli.py findings             render evaluation/FINDINGS.md from evaluation/findings.json
  python3.11 evaluation/cli.py report               write evaluation/results/REPORT.md
  python3.11 evaluation/cli.py budget status
  python3.11 evaluation/cli.py admission-assets DIR generate negative admission assets
  python3.11 evaluation/cli.py freeze               (re)freeze the manifest; changed content bumps its version

Subjects: none (default) | http-launch | recorded:<dir> | http:<base-url> (capabilities probe only).
Live lanes are disabled (NOT_RUN). There is deliberately no command or flag that activates them, and
no cohort is opened by any current procedure.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
sys.path.insert(0, ROOT)

from drbean_eval import admission, gates, history, manifest, report, runner  # noqa: E402
from drbean_eval.assertions import grade  # noqa: E402
from drbean_eval.budget import BudgetLedger  # noqa: E402
from drbean_eval.subject import make_subject  # noqa: E402

RESULTS = os.path.join(ROOT, "results")
LEDGER = os.path.join(ROOT, "ledger", "provider_budget.jsonl")


def selftest() -> dict:
    """Grade the exemplar observations. Returns counts; raises on any mismatch."""
    counts = {"variants": 0, "passing_exemplars": 0, "failing_exemplars": 0, "assertions": 0, "exercised": set()}
    for case_id in manifest.CASE_IDS:
        case = manifest.load_case(ROOT, case_id)
        with open(os.path.join(ROOT, "selftest", case_id + ".json"), encoding="utf-8") as handle:
            exemplars = json.load(handle)
        for letter, variant in case["variants"].items():
            counts["variants"] += 1
            counts["assertions"] += len(variant["expected"])
            result = grade(variant["expected"], exemplars[letter]["pass"])
            if not result["passed"]:
                raise AssertionError(f"{case_id}-{letter}: compliant exemplar fails {result['failed_ids']}")
            counts["passing_exemplars"] += 1
            for exemplar in exemplars[letter]["fails"]:
                result = grade(variant["expected"], exemplar["observation"])
                if sorted(result["failed_ids"]) != exemplar["must_fail"]:
                    raise AssertionError(f"{case_id}-{letter} '{exemplar['name']}': failed "
                                         f"{sorted(result['failed_ids'])}, expected {exemplar['must_fail']}")
                counts["failing_exemplars"] += 1
                counts["exercised"].update(result["failed_ids"])
    counts["exercised"] = len(counts["exercised"])
    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify")
    sub.add_parser("selftest")
    sub.add_parser("freeze")
    sub.add_parser("report")
    run = sub.add_parser("run")
    run.add_argument("--lane", required=True, choices=manifest.LANES)
    run.add_argument("--subject", default="none")
    run.add_argument("--only", nargs="*")
    run.add_argument("--results", default=RESULTS)
    run.add_argument("--stack-env", action="append", default=[], metavar="BEAN_NAME=VALUE",
                     help="non-credential BEAN_* setting passed to the launched test stack (repeatable)")
    controls = sub.add_parser("controls")
    controls.add_argument("--results", default=RESULTS)
    gate = sub.add_parser("gate")
    gate.add_argument("--require", choices=("release",))
    gate.add_argument("--results", default=RESULTS)
    gate.add_argument("--output")
    inventory = sub.add_parser("inventory")
    inventory.add_argument("--results", default=RESULTS)
    sub.add_parser("history")
    sub.add_parser("findings")
    budget = sub.add_parser("budget")
    budget.add_argument("action", choices=("status", "open"))
    budget.add_argument("--cohort")
    budget.add_argument("--authorized-by")
    budget.add_argument("--spending-note")
    budget.add_argument("--model")
    budget.add_argument("--requests", type=int)
    budget.add_argument("--input-tokens", type=int)
    budget.add_argument("--output-tokens", type=int)
    assets = sub.add_parser("admission-assets")
    assets.add_argument("out_dir")
    args = parser.parse_args(argv)

    if args.command == "verify":
        problems = manifest.verify(ROOT)
        for problem in problems:
            print("PROBLEM:", problem)
        loaded = manifest.load(ROOT)
        print(f"manifest v{loaded['manifest_version']}: {len(loaded['cases'])} cases, "
              f"{len(loaded['schedule']['fixture_contract'])} fixture entries, {len(loaded['sources'])} sources, "
              f"{len(loaded['holdouts']['items'])} holdouts; {'OK' if not problems else 'FAILED'}")
        return 1 if problems else 0
    if args.command == "selftest":
        counts = selftest()
        print("grader self-test (harness only, not product evidence):", json.dumps(counts))
        return 0
    if args.command == "freeze":
        loaded = manifest.freeze(ROOT)
        print(f"manifest v{loaded['manifest_version']} frozen at {loaded['frozen_at']}")
        return 0
    if args.command == "report":
        text = report.render(ROOT, RESULTS)
        os.makedirs(RESULTS, exist_ok=True)
        with open(os.path.join(RESULTS, "REPORT.md"), "w", encoding="utf-8") as handle:
            handle.write(text)
        print(f"wrote {os.path.relpath(os.path.join(RESULTS, 'REPORT.md'), REPO)}")
        return 0
    if args.command == "run":
        stack_env = dict(item.split("=", 1) for item in args.stack_env if "=" in item)
        records = runner.run_lane(args.lane, make_subject(args.subject, REPO, stack_env), ROOT, args.results, REPO,
                                  args.only, LEDGER)
        tally = {}
        for record in records:
            tally[record["status"]] = tally.get(record["status"], 0) + 1
            print(f"{record['entry_id']:<14} {record['status']:<14} {record['reason'] or ''}")
        print(f"{args.lane}: {len(records)} attempt(s) recorded: {tally}")
        return 0 if all(r["status"] == "passed" for r in records) else 2
    if args.command == "controls":
        return run_controls(args.results)
    if args.command in ("gate", "inventory"):
        state = runner.git_state(REPO)
        result = gates.compute(ROOT, args.results, state["commit"], state["dirty"],
                               os.path.join(ROOT, "findings.json"))
        text = json.dumps(result, indent=2, sort_keys=True)
        if getattr(args, "output", None):
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(text + "\n")
        for item in result["gates"]:
            print(f"{item['gate']:<36} {item['status']}")
        print(f"overall: {result['overall']} at {(result['tested_commit'] or '')[:12]}"
              f"{' (dirty worktree)' if result['worktree_dirty'] else ''}")
        if args.command == "inventory":
            return 0 if result["gates"][0]["status"] == "passed" else 1
        return 0 if result["overall"] == "passed" else 3
    if args.command == "findings":
        with open(os.path.join(ROOT, "findings.json"), encoding="utf-8") as handle:
            data = json.load(handle)
        lines = ["# Findings (generated from evaluation/findings.json; edit the JSON, then run `cli.py findings`)", "",
                 f"Application code commit `{data['application_code_commit'][:12]}`, observed with harness "
                 f"`{data['observed_at_harness_commit']}` on {data['host']}.", "",
                 "| ID | Sev | Owner | Status | Title |", "|---|---|---|---|---|"]
        lines += [f"| {f['id']} | {f['severity']} | {f['owner']} | {f['status']} | {f['title']} |"
                  for f in data["findings"]]
        for f in data["findings"]:
            if f.get("command"):
                lines += ["", f"## {f['id']} ({f['severity']}, owner {f['owner']}, {f['status']})", "",
                          f"- **Input:** {f.get('minimal_input', '')}", f"- **Command:** `{f['command']}`",
                          f"- **Expected:** {f.get('expected', '')}", f"- **Observed:** {f.get('observed', '')}",
                          f"- **Evidence:** {json.dumps(f.get('evidence', {}), sort_keys=True)}"]
        with open(os.path.join(ROOT, "FINDINGS.md"), "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        print("wrote evaluation/FINDINGS.md")
        return 0
    if args.command == "history":
        problems = history.verify(RESULTS)
        for problem in problems:
            print("PROBLEM:", problem)
        print(f"history {'OK' if not problems else 'FAILED'}: {len(runner.read_attempts(RESULTS))} attempt(s)")
        return 1 if problems else 0
    if args.command == "budget":
        ledger = BudgetLedger(LEDGER)
        if args.action == "open":
            print("refused: live lanes are disabled and the evaluation ledger is not the authoritative dispatch "
                  "budget. Opening a cohort needs a new explicit user instruction and the single shared ledger "
                  "agreed by Owners 2, 3 and 5 (docs/evaluation-protocol.md).")
            return 1
        state = ledger.state()
        print(json.dumps({k: state[k] for k in ("cohort", "committed", "remaining", "unreconciled")}, indent=2))
        return 0
    if args.command == "admission-assets":
        written = admission.generate(args.out_dir, os.path.join(ROOT, "sources", "c01a.png"))
        print(json.dumps({"generated": written, "unrun_by_decision": admission.UNRUN_BY_DECISION}, indent=2))
        return 0
    return 1


def run_controls(results_dir: str) -> int:
    """Engine-level native controls in fresh CPython 3.11 processes; appended to controls.jsonl."""
    from datetime import datetime, timezone
    from drbean_eval import engine_controls, launcher
    state = runner.git_state(REPO)
    try:
        python = launcher.science_python()
    except launcher.StackError as error:
        print("blocked:", error)
        return 2
    results = engine_controls.run(python, os.path.join(REPO, "packages", "groundwork_adapter"), REPO)
    entry = {"schema": "drbean-engine-controls/v1", "tested_commit": state["commit"],
             "worktree_dirty": state["dirty"], "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "interpreter": launcher.interpreter_identity(python), "results": results,
             "scope": "engine public operations, not HTTP; fresh replay re-runs the project checker"}
    os.makedirs(results_dir, exist_ok=True)
    with open(os.path.join(results_dir, "controls.jsonl"), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    for item in results:
        print(f"{'passed' if item['passed'] else 'FAILED':<7} {item['id']}")
    return 0 if all(item["passed"] for item in results) else 2


if __name__ == "__main__":
    sys.exit(main())
