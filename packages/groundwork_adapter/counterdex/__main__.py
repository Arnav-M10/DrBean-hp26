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
    commands.add_parser("bridge", help="Read one bounded application request from stdin and write one response")
    baseline = commands.add_parser("baseline", help="Discover and exactly check candidates for a reviewed historical problem")
    baseline.add_argument("request")
    baseline.add_argument("--output", required=True)
    historical = commands.add_parser("replay-baseline", help="Fresh exact historical replay")
    historical.add_argument("bundle")
    native = commands.add_parser("replay-native", help="Replay an application-bound native packet and its full lineage")
    native.add_argument("bundle")
    native.add_argument("--anchors", required=True)
    run = commands.add_parser("run", help="Run a frozen scientific request (approval is the caller's responsibility)")
    run.add_argument("request")
    run.add_argument("--output", required=True)
    replay = commands.add_parser("replay", help="Fresh exact replay against separately supplied trust anchors")
    replay.add_argument("bundle")
    for command in (run, replay, baseline, historical):
        command.add_argument("--anchors", help="Separate trusted local identity file; never selected by evidence")
        command.add_argument("--expected-problem")
    run.add_argument("--expected-design")
    replay.add_argument("--expected-suggestion")
    historical.add_argument("--expected-baseline")
    historical.add_argument("--expected-scenario")
    args = parser.parse_args(argv)
    try:
        if args.command == "bridge":
            from .bridge import main as bridge_main
            return bridge_main()
        if args.command == "capabilities":
            from .capabilities import capabilities
            result = capabilities()
        elif args.command == "replay-native":
            from .native_packet import replay_packet
            result = replay_packet(_read(args.bundle), expected=strict_json_loads(_read(args.anchors, 4096)))
        else:
            anchors = strict_json_loads(_read(args.anchors, 4096), max_bytes=4096) if args.anchors else {}
            allowed = {"problem_digest", "baseline_digest", "scenario_id"} if args.command in ("baseline", "replay-baseline") else {"problem_digest", "design_digest", "suggestion_digest"}
            if not isinstance(anchors, dict) or set(anchors) - allowed:
                raise AdapterError("invalid_input", "Unexpected trust-anchor fields.")
            expected_problem = args.expected_problem or anchors.get("problem_digest")
            if args.command == "baseline":
                from .baseline import create_baseline
                request = fields(strict_json_loads(_read(args.request)), {"problem", "scenario_id", "workflow", "search_settings"}, "request")
                content = create_baseline(request["problem"], expected_problem_digest=expected_problem,
                    scenario_id=request["scenario_id"], workflow=request["workflow"], settings=request["search_settings"])
                _write_complete(args.output, content)
                result = {"output": args.output, "artifact_bytes": len(content), "baseline_digest": strict_json_loads(content)["baseline_digest"]}
            elif args.command == "replay-baseline":
                from .replay_baseline import replay_baseline
                result = replay_baseline(_read(args.bundle), expected_problem_digest=expected_problem,
                    expected_baseline_digest=args.expected_baseline or anchors.get("baseline_digest"),
                    expected_scenario_id=args.expected_scenario or anchors.get("scenario_id"))
            elif args.command == "run":
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
