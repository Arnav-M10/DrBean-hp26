#!/usr/bin/env python3
"""Dr. Bean evaluation harness command line. Standard library only.

  python3 evaluation/cli.py verify                 check the frozen manifest
  python3 evaluation/cli.py selftest               prove the grader on exemplars (not product evidence)
  python3 evaluation/cli.py run --lane LANE [--subject SPEC] [--only ID ...]
  python3 evaluation/cli.py report                 write evaluation/results/REPORT.md
  python3 evaluation/cli.py budget status
  python3 evaluation/cli.py budget open --cohort ID --authorized-by NAME --spending-note TEXT [--model M]
  python3 evaluation/cli.py admission-assets DIR   generate negative admission assets
  python3 evaluation/cli.py freeze                 (re)freeze the manifest; changed content bumps its version

Subjects: none (default) | recorded:<dir> | http:<base-url>.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
sys.path.insert(0, ROOT)

from drbean_eval import admission, manifest, report, runner  # noqa: E402
from drbean_eval.assertions import grade  # noqa: E402
from drbean_eval.budget import BudgetLedger, BudgetStop  # noqa: E402
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
        records = runner.run_lane(args.lane, make_subject(args.subject), ROOT, args.results, REPO, args.only,
                                  LEDGER)
        tally = {}
        for record in records:
            tally[record["status"]] = tally.get(record["status"], 0) + 1
            print(f"{record['entry_id']:<14} {record['status']:<14} {record['reason'] or ''}")
        print(f"{args.lane}: {len(records)} attempt(s) recorded: {tally}")
        return 0 if all(r["status"] == "passed" for r in records) else 2
    if args.command == "budget":
        ledger = BudgetLedger(LEDGER)
        if args.action == "open":
            caps = {k: v for k, v in (("provider_requests", args.requests), ("input_tokens", args.input_tokens),
                                      ("output_tokens", args.output_tokens)) if v}
            try:
                ledger.open_cohort(args.cohort or "", args.authorized_by or "", args.spending_note or "", caps,
                                   args.model)
            except (BudgetStop, ValueError) as error:
                print("refused:", error)
                return 1
        state = ledger.state()
        print(json.dumps({k: state[k] for k in ("cohort", "committed", "remaining", "unreconciled")}, indent=2))
        return 0
    if args.command == "admission-assets":
        written = admission.generate(args.out_dir, os.path.join(ROOT, "sources", "c01a.png"))
        print(json.dumps({"generated": written, "unrun_by_decision": admission.UNRUN_BY_DECISION}, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
