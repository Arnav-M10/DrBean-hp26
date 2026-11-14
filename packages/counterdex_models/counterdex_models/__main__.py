"""Command line: ``python -m counterdex_models {models,run}``.

``--registry module:function`` lets the operator add trusted models (the
function returns a ModelRegistry). Request files can only name models.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys

from .interface import ModelError, ModelRegistry
from .public_models import default_registry
from .requests import MAX_REQUEST_BYTES, run_request


def _registry(spec: str | None) -> ModelRegistry:
    if not spec:
        return default_registry()
    module, _, name = spec.partition(":")
    registry = getattr(importlib.import_module(module), name or "registry")()
    if not isinstance(registry, ModelRegistry):
        raise ModelError("invalid_model", "--registry must name a function returning a ModelRegistry.")
    return registry


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="counterdex-models", description="Bounded numerical comparison of registered models. "
                                     "Results are numerical analysis, never certification.")
    parser.add_argument("--registry", help="operator-trusted module:function returning a ModelRegistry")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("models", help="list registered models")
    run = sub.add_parser("run", help="run one JSON request")
    run.add_argument("request")
    run.add_argument("--output", help="write here; the file must not already exist")
    args = parser.parse_args(argv)
    try:
        registry = _registry(args.registry)
        if args.command == "models":
            result = {"models": registry.describe()}
        else:
            if os.path.getsize(args.request) > MAX_REQUEST_BYTES:
                raise ModelError("invalid_input", "Request is larger than 1 MiB.", "request")
            with open(args.request, encoding="utf-8") as handle:
                result = run_request(json.load(handle), registry)
    except ModelError as error:
        print(json.dumps({"status": "refused", "error": error.to_dict()}, indent=2), file=sys.stderr)
        return 2
    except (OSError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "refused", "error": {"code": "invalid_input", "message": str(error), "path": "request"}}, indent=2), file=sys.stderr)
        return 2
    text = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if getattr(args, "output", None):
        try:
            with open(args.output, "x", encoding="utf-8") as handle:
                handle.write(text)
        except FileExistsError:
            print(json.dumps({"status": "refused", "error": {"code": "output_exists", "message": "The output file already exists.", "path": "output"}}, indent=2), file=sys.stderr)
            return 2
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
