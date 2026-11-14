"""Local commands; supplied evidence can never select a path, URL, or import."""
import argparse
import os
from pathlib import Path
import sys
import tempfile

from .errors import AdapterError
from .exact import canonical_bytes, strict_json_loads
from .models import fields


def _read(path: str, maximum: int = 4 * 1024 * 1024) -> bytes:
    with Path(path).open("rb") as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise AdapterError("resource_exhaustion", "Input file exceeds the admitted byte limit.")
    return data


def _write_complete(path: str, content: bytes) -> None:
    """Link a fully written same-filesystem file without replacing a destination."""
    destination = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".counterdex-", delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Counterdex bounded scientific adapter")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("capabilities", help="Print qualified scientific capability metadata")
    run = commands.add_parser("run", help="Run a frozen scientific request (approval is the caller's responsibility)")
    run.add_argument("request")
    run.add_argument("--output", required=True)
    replay = commands.add_parser("replay", help="Fresh exact replay against separately supplied trust anchors")
    replay.add_argument("bundle")
    for command in (run, replay):
        command.add_argument("--anchors", help="Separate trusted local identity file; never selected by evidence")
        command.add_argument("--expected-problem")
    run.add_argument("--expected-design")
    replay.add_argument("--expected-suggestion")
    args = parser.parse_args(argv)
    try:
        if args.command == "capabilities":
            from .capabilities import capabilities
            result = capabilities()
        else:
            anchors = strict_json_loads(_read(args.anchors, 4096), max_bytes=4096) if args.anchors else {}
            if not isinstance(anchors, dict) or set(anchors) - {"problem_digest", "design_digest", "suggestion_digest"}:
                raise AdapterError("invalid_input", "Unexpected trust-anchor fields.")
            expected_problem = args.expected_problem or anchors.get("problem_digest")
            if args.command == "run":
                from .pipeline import create_suggestion
                request = fields(strict_json_loads(_read(args.request)), {"problem", "design", "workflow"}, "request")
                content = create_suggestion(request["problem"], request["design"], workflow=request["workflow"],
                    expected_problem_digest=expected_problem,
                    expected_design_digest=args.expected_design or anchors.get("design_digest"))
                # User-specified destination only; never replace an existing file.
                _write_complete(args.output, content)
                result = {"output": args.output, "artifact_bytes": len(content),
                          "suggestion_digest": strict_json_loads(content)["suggestion_digest"]}
            else:
                from .replay import replay_bundle
                result = replay_bundle(_read(args.bundle), expected_problem_digest=expected_problem,
                    expected_suggestion_digest=args.expected_suggestion or anchors.get("suggestion_digest"))
        sys.stdout.buffer.write(canonical_bytes(result) + b"\n")
        return 0 if result.get("replay") != "failed" else 1
    except AdapterError as error:
        sys.stderr.buffer.write(canonical_bytes({"error": error.to_dict()}) + b"\n")
        return 2
    except OSError:
        sys.stderr.buffer.write(canonical_bytes({"error": {"code": "local_io_failure", "message": "Could not read or exclusively create the supplied local file."}}) + b"\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
