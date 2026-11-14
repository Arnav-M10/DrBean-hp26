#!/usr/bin/env python3
"""Validate bridge fixtures with the actual application's authoritative DTOs.

Run in the prepared API environment (Python 3.12/3.13 and its dependencies).
This reads local JSON only and makes no provider or network calls.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True, help="Directory containing paired *.request.json and *.response.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(root / "apps" / "api"))
    try:
        from bean_api.canonical import semantic_digest
        from bean_api.contracts import DatasetBody, DesignRequestBody, DesignResult, ProblemBody, ScientificResult
    except ImportError as error:
        parser.exit(2, f"Run this command in the prepared API environment; missing dependency: {error.name}\n")
    if not args.fixtures.is_dir():
        parser.error("--fixtures must name an existing directory")
    counts = {"requests": 0, "results": 0, "error_responses": 0}
    admitted = {"investigate", "design", "review"}

    def normalized(model, value, location):
        actual = model.model_validate(value).model_dump(mode="json")
        if value != actual:
            raise ValueError(f"{location}: fixture must contain the complete normalized authoritative DTO")

    requests = {}
    try:
        for path in sorted(args.fixtures.rglob("*.request.json")):
            request = json.loads(path.read_text(encoding="utf-8"))
            operation = request.get("operation")
            if operation not in admitted:
                continue
            for kind, model in (("dataset", DatasetBody), ("problem", ProblemBody)):
                record = request[kind]
                normalized(model, record["body"], f"{path.name}/{kind}")
                if record["digest"] != semantic_digest(kind, record["body"]):
                    raise ValueError(f"{path.name}/{kind}: record digest differs from the authoritative canonical body")
            problem, dataset = request["problem"], request["dataset"]
            if problem["body"]["dataset_id"] != dataset["id"] or problem["body"]["dataset_digest"] != dataset["digest"]:
                raise ValueError(f"{path.name}: problem does not bind the supplied dataset")
            if operation == "design":
                normalized(DesignRequestBody, request["request"], f"{path.name}/request")
                if request["expected_request_digest"] != semantic_digest("design-request", request["request"]):
                    raise ValueError(f"{path.name}: expected design request identity differs from its body")
            requests[path.resolve()] = operation
            counts["requests"] += 1
        for path in sorted(args.fixtures.rglob("*.response.json")):
            request_path = path.with_name(path.name.removesuffix(".response.json") + ".request.json").resolve()
            if request_path not in requests:
                # Other protocol operations have different result shapes. A
                # response without any request is not silently accepted.
                if request_path.exists():
                    continue
                raise ValueError(f"{path.name}: corresponding request fixture is missing")
            response = json.loads(path.read_text(encoding="utf-8"))
            if response.get("ok") is not True:
                if response.get("ok") is not False or type(response.get("error")) is not dict:
                    raise ValueError(f"{path.name}: malformed bridge error response")
                counts["error_responses"] += 1
                continue
            model = DesignResult if requests[request_path] == "design" else ScientificResult
            normalized(model, response["result"], f"{path.name}/result")
            counts["results"] += 1
        if not counts["requests"]:
            raise ValueError("No investigation, design or review request fixtures were found")
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Authoritative application schema check failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "passed", "schema_authority": "apps/api/bean_api/contracts.py", **counts}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
