"""Four explicit evidence lanes and their machine-readable reports (Workstream 5, papers/Gemini sprint).

No lane may stand in for another:

* ``controlled_callbacks``: controlled model and controlled callbacks. Deterministic authority and error-handling
  tests on the in-process application; every provider response and agent decision is authored by the test.
* ``controlled_science``: controlled model and actual Counterdex. A launched API and worker with the real engine.
  The egress guard runs in every process, so no provider request is possible.
* ``live_gemini``: live Gemini with the actual tools and engine. It may run only inside a budget the user enabled
  for one shared qualification. Nothing here can start it, so its report is ``not_run``.
* ``historical_replay``: a fresh run of the project's checker over retained native bytes. It makes no discovery,
  does no fresh model inference, and does not show that the application generated the packet now.

Each report records the commit, the dirty flag, the source identity, versions, fixture digests, platform, actual
requests and usage, artifacts, the exit status and timestamps. The source identity is the git tree digests of the
application, harness and fixtures, plus the engine source digest. Unknown telemetry stays unknown and is never
recorded as zero. Reports are append-only and hash-chained in ``lanes/reports.jsonl``. The ``evidence_lanes`` gate
counts a report only when its source identity equals the tested checkout's.
"""
from __future__ import annotations

import ast
import glob
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import time
import tomllib
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from . import engine_controls, history, launcher, native
from .runner import git_state

SCHEMA = "drbean-lane-report/v1"
REPORTS = os.path.join("lanes", "reports.jsonl")

LANES = {
    "controlled_callbacks": {
        "model": "controlled doubles authored by the tests (never Gemini)",
        "science": "controlled callbacks and in-process application records",
        "establishes": "deterministic authority, review, accounting and error handling of the application code",
        "does_not_establish": "Gemini extraction quality, live model adaptivity, or real scientific computation",
        "pytest_marker": "not real_stack and not real_science",
    },
    "controlled_science": {
        "model": "controlled doubles or no model; zero provider dispatch verified by the egress guard",
        "science": "actual Counterdex through the launched API and worker",
        "establishes": "orchestration and real scientific integration through published HTTP routes",
        "does_not_establish": "anything about live Gemini behaviour or usefulness",
        "pytest_marker": "real_stack or real_science",
    },
    "live_gemini": {
        "model": "live Gemini (only within a user-enabled shared qualification budget)",
        "science": "actual tools and engine",
        "establishes": "real model extraction, decisions and usefulness on a predeclared subset only",
        "does_not_establish": "general accuracy; anything outside the observed subset and its denominator",
        "pytest_marker": None,
    },
    "historical_replay": {
        "model": "none (no inference of any kind)",
        "science": "fresh run of the project's own checker over retained native bytes",
        "establishes": "the retained packets still bind to their recorded anchors and replay under this checker",
        "does_not_establish": "discovery, fresh Gemini inference, or that the application generated the packet now",
        "pytest_marker": None,
    },
}
REQUIRED_LANES = ("controlled_callbacks", "controlled_science", "historical_replay")
LIVE_NOT_RUN = ("not_run: no user-enabled live budget exists for this qualification; no key was inspected and no "
                "provider was called. There is deliberately no command here that starts live requests.")

APPLICATION_PATHS = ("apps", "packages", "shared", "scripts", "pyproject.toml", "uv.lock")
FIXTURE_PATHS = ("fixtures",)
HARNESS_PATHS = ("evaluation", "tests/integration")
# Recorded evidence and written summaries; changing them cannot change the application or the harness behaviour.
EVIDENCE_ONLY_PATHS = ("evaluation/results/", "evaluation/FINDINGS.md", "evaluation/findings.json",
                       "evaluation/README.md", "docs/evaluation-protocol.md", "docs/workstreams/05-validation.md")
IDENTITY_KEYS = ("application_tree_sha256", "harness_tree_sha256", "fixtures_tree_sha256", "engine_source_sha256")
BACKEND_PACKAGES = ("google-genai", "deepagents", "langchain", "langchain-core", "langchain-google-genai",
                    "langgraph", "fastapi", "pydantic", "pillow", "pypdf", "pdfplumber", "pymupdf", "pypdfium2")
_VERSION_NAME = re.compile(r"^[A-Z][A-Z0-9_]*VERSION$")
_ARTIFACT = re.compile(r"^(?P<label>.+)-(?P<artifact>native_artifact_[0-9a-f]{32})\.bin$")
INCOMPATIBLE_CODES = ("source_version_mismatch", "unsupported_schema_version", "unsupported_profile")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_file(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


# -- identity and versions --------------------------------------------------------------------------------------

def tree_digest(repo: str, paths: tuple[str, ...], exclude: tuple[str, ...] = ()) -> dict:
    """Digest of the committed blobs under ``paths`` at HEAD (mode, type, object id, path), minus ``exclude``."""
    done = subprocess.run(["git", "-C", repo, "ls-tree", "-r", "-z", "--full-tree", "HEAD", "--", *paths],
                          capture_output=True)
    entries = [item for item in done.stdout.decode("utf-8", "replace").split("\0") if item]
    kept = [item for item in entries if not item.split("\t", 1)[-1].startswith(exclude)] if exclude else entries
    if done.returncode or not kept:
        return {"sha256": None, "files": 0}
    return {"sha256": hashlib.sha256("\n".join(kept).encode()).hexdigest(), "files": len(kept)}


def source_identity(repo: str) -> dict:
    """What a lane report is evidence about. The gate compares the four digests, not commit ids, so an
    evidence-only descendant keeps its identity while any application, harness, fixture or engine change does not."""
    state = git_state(repo)
    application = tree_digest(repo, APPLICATION_PATHS)
    harness = tree_digest(repo, HARNESS_PATHS, EVIDENCE_ONLY_PATHS)
    fixtures = tree_digest(repo, FIXTURE_PATHS)
    engine = engine_controls.engine_source_identity(os.path.join(repo, "packages", "groundwork_adapter"))
    return {"commit": state["commit"], "worktree_dirty": state["dirty"], "changed_paths": state["changed"],
            "application_tree_sha256": application["sha256"], "application_files": application["files"],
            "harness_tree_sha256": harness["sha256"], "harness_files": harness["files"],
            "fixtures_tree_sha256": fixtures["sha256"], "fixtures_files": fixtures["files"],
            "engine_source_sha256": engine["source_sha256"], "engine_source_files": engine["files"],
            "application_paths": list(APPLICATION_PATHS), "harness_paths": list(HARNESS_PATHS),
            "fixture_paths": list(FIXTURE_PATHS), "excluded_evidence_paths": list(EVIDENCE_ONLY_PATHS)}


def identity_matches(report_identity: dict, current: dict) -> bool:
    return all(report_identity.get(key) and report_identity.get(key) == current.get(key) for key in IDENTITY_KEYS)


def application_versions(repo: str) -> dict:
    """Module-level ``*VERSION`` string constants in the backend (prompt, policy, contract, projection versions).
    Read with ``ast``; the application is never imported into the harness."""
    root = os.path.join(repo, "apps", "api", "bean_api")
    found = {}
    for directory, subdirs, files in os.walk(root):
        subdirs[:] = sorted(d for d in subdirs if d != "__pycache__")
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(directory, name)
            try:
                with open(path, encoding="utf-8") as handle:
                    tree = ast.parse(handle.read())
            except (OSError, SyntaxError, UnicodeDecodeError, ValueError):
                continue
            for node in tree.body:
                target = node.targets[0] if isinstance(node, ast.Assign) and len(node.targets) == 1 else \
                    node.target if isinstance(node, ast.AnnAssign) else None
                value = getattr(node, "value", None)
                if isinstance(target, ast.Name) and _VERSION_NAME.match(target.id) and \
                        isinstance(value, ast.Constant) and isinstance(value.value, str):
                    found[f"{os.path.relpath(path, repo)}:{target.id}"] = value.value
    return found


def dependency_pins(repo: str) -> list[str]:
    try:
        with open(os.path.join(repo, "pyproject.toml"), "rb") as handle:
            return list((tomllib.load(handle).get("project") or {}).get("dependencies") or [])
    except (OSError, tomllib.TOMLDecodeError):
        return []


_INSTALLED = ("import json, sys, importlib.metadata as m\n"
              "out = {}\n"
              "for name in json.loads(sys.argv[1]):\n"
              "    try:\n"
              "        out[name] = m.version(name)\n"
              "    except m.PackageNotFoundError:\n"
              "        out[name] = None\n"
              "print(json.dumps(out))\n")


def installed_versions(python: str, names: tuple[str, ...] = BACKEND_PACKAGES) -> dict:
    """Distribution versions in an interpreter, read from metadata only (nothing is imported)."""
    done = subprocess.run([python, "-I", "-c", _INSTALLED, json.dumps(list(names))], capture_output=True,
                          text=True, timeout=60)
    try:
        return json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"error": "installed-version probe failed"}


_INSTALLED_ENGINE = ("import json, os, counterdex\n"
                     "print(json.dumps({'version': getattr(counterdex, '__version__', None),\n"
                     "                  'module_dir': os.path.dirname(os.path.abspath(counterdex.__file__))}))\n")


def installed_engine(science_python: str, repo: str) -> dict:
    """The Counterdex the engine interpreter imports by itself (what the application's worker runs), compared file
    by file with the repository source. A stale copy with the same version string is not the tested engine."""
    done = subprocess.run([science_python, "-I", "-c", _INSTALLED_ENGINE], capture_output=True, text=True,
                          timeout=60, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
    try:
        seen = json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"installed": False, "matches_repository": False}
    installed = engine_controls.engine_source_files(os.path.dirname(seen["module_dir"]))
    repository = engine_controls.engine_source_files(os.path.join(repo, "packages", "groundwork_adapter"))
    return {"installed": True, "version": seen.get("version"),
            "installed_source_sha256": engine_controls.engine_source_identity(
                os.path.dirname(seen["module_dir"]))["source_sha256"],
            "matches_repository": bool(installed) and installed == repository,
            "differing_files": sorted(name for name in set(installed) | set(repository)
                                      if installed.get(name) != repository.get(name))[:20]}


def platform_identity(backend: str | None, science: str | None) -> dict:
    return {"host": {**launcher.host_identity(), "macos": platform.mac_ver()[0] or None},
            "backend_interpreter": launcher.interpreter_identity(backend) if backend else None,
            "engine_interpreter": launcher.interpreter_identity(science) if science else None}


def versions(repo: str, backend: str | None, science: str | None) -> dict:
    app_versions = application_versions(repo)
    contracts = tree_digest(repo, ("shared/contracts",))
    return {"application_constants": app_versions,
            "prompt_and_policy_versions": {k: v for k, v in app_versions.items()
                                           if "PROMPT" in k.rsplit(":", 1)[-1] or "POLICY" in k.rsplit(":", 1)[-1]},
            "contracts_tree_sha256": contracts["sha256"], "contract_files": contracts["files"],
            "dependency_pins": dependency_pins(repo),
            "installed_backend_packages": installed_versions(backend) if backend else None,
            "engine_repository": engine_controls.engine_identity(science, os.path.join(
                repo, "packages", "groundwork_adapter")) if science else None,
            "engine_installed": installed_engine(science, repo) if science else None}


def fixture_digests(repo: str) -> dict:
    return {"fixtures": tree_digest(repo, ("fixtures",)),
            "science_packets": tree_digest(repo, ("evaluation/cases/science",)),
            "independent_cases": tree_digest(repo, ("evaluation/cases", "evaluation/sources")),
            "paper_corpus": tree_digest(repo, ("evaluation/corpus",)),
            "engine_retained_packets": tree_digest(repo, ("packages/groundwork_adapter/fixtures",
                                                          "packages/groundwork_adapter/docs/review-evidence"))}


# -- guard accounting -----------------------------------------------------------------------------------------

def _events(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.strip():
                try:
                    out.append(json.loads(line))
                except ValueError:
                    out.append({"kind": "unparsed_guard_line"})
    return out


def dispatch_accounting(session_log: str | None, archive: str | None, *, replay_logs: list[str] = ()) -> dict:
    """External model requests are a verified zero only if the guard was installed everywhere it should have been
    and recorded no blocked attempt. A missing guard log makes the count unknown, never zero."""
    logs = {}
    if session_log:
        logs["pytest_process"] = _events(session_log)
    started = sorted(glob.glob(os.path.join(archive, "*.started"))) if archive else []
    archived = sorted(glob.glob(os.path.join(archive, "*.guard.jsonl"))) if archive else []
    for path in archived:
        logs[os.path.basename(path)] = _events(path)
    for path in replay_logs:
        logs[os.path.basename(path)] = _events(path)
    events = [event for items in logs.values() for event in items]
    probes, blocked = _split_probes(logs)
    installed = sum(1 for e in events if e.get("kind") == "guard_installed")
    names = sorted({name for e in events if e.get("kind") == "guard_installed"
                    for name in e.get("credential_names_present") or []})
    reads = sorted({e.get("name") for e in events if e.get("kind") == "credential_read"})
    complete = bool(logs) and len(archived) == len(started) and all(
        any(e.get("kind") == "guard_installed" for e in items) for items in logs.values())
    if blocked:
        requests = {"value": None, "status": "attempted_and_blocked", "blocked_attempts": len(blocked),
                    "hosts_or_clients": sorted({str(e.get("host") or e.get("client")) for e in blocked})[:10]}
    elif complete:
        requests = {"value": 0, "status": "verified_zero",
                    "basis": "egress guard installed in every launched process; no blocked attempt recorded"}
    else:
        requests = {"value": None, "status": "unknown",
                    "basis": f"guard coverage incomplete: {len(started)} stack(s) started, {len(archived)} log(s) kept"}
    requests["deliberate_guard_probes"] = probes
    return {"external_model_requests": requests,
            "provider_tokens": {"value": None, "status": "not_applicable" if requests["status"] == "verified_zero"
                                else "unknown", "reason": "no provider request was dispatched" if requests[
                                    "status"] == "verified_zero" else "dispatch was not verified"},
            "controlled_model_invocations": {"value": None, "status": "not_measured",
                                             "reason": "controlled doubles are authored and asserted inside each "
                                                       "test; their call counts are not exported"},
            "guard": {"logs": len(logs), "guard_installed_events": installed, "stacks_started": len(started),
                      "stack_logs_kept": len(archived), "events": len(events),
                      "credential_variable_names_present": names, "credential_variable_names_read": reads,
                      "note": "names only; no credential value is read, logged or transmitted"}}


def _split_probes(logs: dict[str, list[dict]]) -> tuple[list[dict], list[dict]]:
    """Separate announced guard self-tests from real attempts. An announcement covers exactly the next blocked event
    of its expected kind from the same process; every other blocked event is an attempted external request."""
    probes, blocked = [], []
    for items in logs.values():
        pending: dict[tuple, list[str]] = {}
        for event in items:
            kind = event.get("kind")
            if kind == "guard_self_test_probe":
                pending.setdefault((event.get("pid"), event.get("expect")), []).append(event.get("test"))
            elif kind in ("egress_blocked", "provider_client_blocked"):
                waiting = pending.get((event.get("pid"), kind))
                if waiting:
                    probes.append({"test": waiting.pop(0), "kind": kind,
                                   "target": str(event.get("host") or event.get("client"))})
                else:
                    blocked.append(event)
        unmatched = [test for tests in pending.values() for test in tests]
        if unmatched:
            probes.append({"unmatched_announcements": unmatched})
    return probes, blocked


# -- pytest lanes ----------------------------------------------------------------------------------------------

def parse_junit(path: str) -> dict:
    """Outcome per test from pytest's JUnit XML (xunit2). xfail is reported by pytest as a skip of type pytest.xfail;
    a NOT_AVAILABLE reason marks a capability absent from this candidate (not run, never passed)."""
    counts = {"passed": 0, "failed": 0, "xfailed": 0, "skipped": 0, "not_available": 0}
    notable = []
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return {"counts": None, "tests": [], "error": "junit report missing or unreadable"}
    for case in root.iter("testcase"):
        test_id = f"{case.get('classname')}::{case.get('name')}"
        failure = case.find("failure") if case.find("failure") is not None else case.find("error")
        skipped = case.find("skipped")
        if failure is not None:
            outcome, reason = "failed", (failure.get("message") or "")[:300]
        elif skipped is not None:
            reason = (skipped.get("message") or "")[:300]
            if "NOT_AVAILABLE" in reason:
                outcome = "not_available"
            elif skipped.get("type") == "pytest.xfail":
                outcome = "xfailed"
            else:
                outcome = "skipped"
        else:
            outcome, reason = "passed", None
        counts[outcome] += 1
        if outcome != "passed":
            notable.append({"id": test_id, "outcome": outcome, "reason": reason})
    return {"counts": counts, "tests": notable}


def _strip_credentials(env: dict) -> dict:
    return {name: value for name, value in env.items() if not launcher._CREDENTIAL_NAME.search(name)}


def run_pytest_lane(lane: str, repo: str, results_dir: str, *, app_repo: str | None = None,
                    timeout: float = 3600.0, extra_args: tuple[str, ...] = ()) -> dict:
    spec = LANES[lane]
    app = os.path.abspath(app_repo or repo)
    backend = launcher.backend_python(app)
    science = launcher.science_python(app)
    before = source_identity(repo)
    work = tempfile.mkdtemp(prefix=f"drbean-lane-{lane}-")
    try:
        session_log = os.path.join(work, "session-guard.jsonl")
        archive = os.path.join(work, "stack-guards")
        os.makedirs(archive)
        junit = os.path.join(work, "junit.xml")
        env = _strip_credentials(dict(os.environ))  # a real key can never reach a test; tests add labelled dummies
        env.update({"DRBEAN_SESSION_GUARD_LOG": session_log, "DRBEAN_STACK_GUARD_ARCHIVE": archive,
                    "DRBEAN_BACKEND_PYTHON": backend, "PYTHONDONTWRITEBYTECODE": "1"})
        argv = [backend, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "junit_family=xunit2",
                f"--junitxml={junit}", "-m", spec["pytest_marker"], *extra_args, "tests/integration"]
        started, clock = _now(), time.monotonic()
        try:
            done = subprocess.run(argv, cwd=app, env=env, capture_output=True, text=True, timeout=timeout)
            exit_code, tail = done.returncode, (done.stdout + done.stderr).splitlines()[-40:]
        except subprocess.TimeoutExpired:
            exit_code, tail = None, [f"timed out after {timeout} s"]
        finished, duration = _now(), round(time.monotonic() - clock, 1)
        results = parse_junit(junit)
        accounting = dispatch_accounting(session_log, archive)
        report = _base_report(lane, repo, app, app_repo, backend, science, before)
        engine = report["versions"]["engine_installed"] or {}
        preconditions = [{"id": "engine_runtime_matches_repository_source",
                          "passed": engine.get("matches_repository") is True,
                          "detail": f"installed Counterdex {engine.get('version')} differs in "
                                    f"{engine.get('differing_files')}" if not engine.get("matches_repository")
                          else "installed engine copy is identical to the repository source"},
                         _unchanged(before, repo)]
        counts = results.get("counts") or {}
        ok = (exit_code == 0 and counts and not counts.get("failed") and all(p["passed"] for p in preconditions)
              and accounting["external_model_requests"]["status"] == "verified_zero")
        report.update({
            "command": {"argv": ["<backend-python>", *argv[1:8], "--junitxml=<artifact>", *argv[9:]],
                        "cwd": "<application checkout>", "exit_code": exit_code},
            "started_at": started, "finished_at": finished, "duration_s": duration,
            "preconditions": preconditions, "results": results, "requests_and_usage": accounting,
            "output_tail": tail[-12:],
            "status": "passed" if ok else "failed" if exit_code is not None else "error"})
        return _store(report, results_dir, {"junit.xml": junit,
                                            "guard-summary.json": _write_json(work, "guard-summary.json",
                                                                              accounting)})
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _write_json(directory: str, name: str, value) -> str:
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=1, sort_keys=True)
        handle.write("\n")
    return path


def _unchanged(before: dict, repo: str) -> dict:
    after = source_identity(repo)
    same = all(before.get(k) == after.get(k) for k in (*IDENTITY_KEYS, "commit", "worktree_dirty"))
    return {"id": "source_identity_unchanged_during_run", "passed": same,
            "detail": "identity, commit and dirty flag identical before and after the run" if same else
            f"changed during the run: {[k for k in (*IDENTITY_KEYS, 'commit', 'worktree_dirty') if before.get(k) != after.get(k)]}"}


def _base_report(lane: str, repo: str, app: str, app_repo: str | None, backend: str | None,
                 science: str | None, identity: dict | None = None) -> dict:
    return {"schema": SCHEMA, "report_id": f"lane_{uuid.uuid4().hex[:16]}", "lane": lane,
            "lane_definition": {k: v for k, v in LANES[lane].items() if k != "pytest_marker"},
            "pytest_marker": LANES[lane]["pytest_marker"],
            "evidence_class": "preview" if app_repo else "executed_acceptance",
            "app_under_test": launcher.git_commit(app) if app_repo else None,
            "source_identity": identity or source_identity(repo),
            "application_identity": source_identity(app) if app_repo else None,
            "versions": versions(app, backend, science), "fixtures": fixture_digests(app),
            "platform": platform_identity(backend, science)}


# -- historical replay ----------------------------------------------------------------------------------------

def _attempt_index(results_dir: str) -> dict:
    out = {}
    path = os.path.join(results_dir, "attempts.jsonl")
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if isinstance(record, dict) and record.get("attempt_id"):
                    out[record["attempt_id"]] = record
    return out


def retained_packets(repo: str, results_dirs: tuple[str, ...]) -> list[dict]:
    """Native packets kept with their separately recorded anchors: engine-package fixtures and review evidence
    (``.native.json`` beside ``.anchors.json``), and packets saved by executed acceptance attempts beside the anchor
    each run read from the authenticated anchor route."""
    items = []
    package = os.path.join(repo, "packages", "groundwork_adapter")
    for path in sorted(glob.glob(os.path.join(package, "**", "*.native.json"), recursive=True)):
        anchor = path[: -len(".native.json")] + ".anchors.json"
        items.append({"packet": path, "anchor": anchor if os.path.exists(anchor) else None, "anchor_key": None,
                      "origin": {"source": "engine_package_retained", "path": os.path.relpath(path, repo)}})
    for results in results_dirs:
        attempts = _attempt_index(results)
        for path in sorted(glob.glob(os.path.join(results, "traces", "att_*", "artifacts", "*.bin"))):
            match = _ARTIFACT.match(os.path.basename(path))
            trace = os.path.dirname(os.path.dirname(path))
            attempt = attempts.get(os.path.basename(trace), {})
            anchor = os.path.join(trace, "records", f"{match['label']}-anchor-{match['artifact']}.json") \
                if match else None
            items.append({"packet": path, "anchor": anchor if anchor and os.path.exists(anchor) else None,
                          "anchor_key": "anchor",
                          "origin": {"source": "acceptance_attempt", "path": os.path.relpath(path, repo),
                                     "attempt_id": attempt.get("attempt_id"), "entry_id": attempt.get("entry_id"),
                                     "tested_commit": attempt.get("tested_commit"),
                                     "evidence_class": attempt.get("evidence_class"),
                                     "original_mode": attempt.get("mode"),
                                     "original_provider_requests": attempt.get("provider_requests"),
                                     "original_external_model_requests": attempt.get("external_model_requests"),
                                     "recorded_at": attempt.get("ended_at")}})
    return items


def classify_replay(result: dict) -> str:
    """replayed | bound_not_checked | incompatible_version | rejected | failed | error.

    ``incompatible_version`` is an unsupported environment (the packet names a different checker version), kept
    apart from failure; ``bound_not_checked`` is a numerical-only packet whose bytes bind but carry no checked
    claim to re-execute."""
    body = result.get("report") or {}
    if result.get("status") == "passed":
        return "replayed"
    if result.get("status") == "rejected":
        return "incompatible_version" if (result.get("error") or {}).get("code") in INCOMPATIBLE_CODES else "rejected"
    if result.get("status") == "failed":
        bound = body.get("integrity") == "passed" and body.get("expected_binding") == "matches"
        return "bound_not_checked" if bound and body.get("replay") in ("not_applicable", "not_checked", None) \
            else "failed"
    return "error"


def run_historical_lane(repo: str, results_dir: str, *, include: tuple[str, ...] = ("results", "owner4-launcher"),
                        timeout: float = 120.0) -> dict:
    science = launcher.science_python(repo)
    backend = None
    try:
        backend = launcher.backend_python(repo)
    except launcher.StackError:
        pass
    package = os.path.join(repo, "packages", "groundwork_adapter")
    dirs = tuple(results_dir if name == "results" else os.path.join(results_dir, name) for name in include)
    before = source_identity(repo)
    work = tempfile.mkdtemp(prefix="drbean-lane-historical-")
    try:
        guard_log = os.path.join(work, "replay-guard.jsonl")
        started, clock = _now(), time.monotonic()
        rows = []
        for item in retained_packets(repo, dirs):
            with open(item["packet"], "rb") as handle:
                data = handle.read()
            row = {"origin": item["origin"], "packet_sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                   "profile": native.classify(data).get("profile")}
            if not item["anchor"]:
                row.update(outcome="no_anchor", detail="no separately recorded anchor; not replayed")
                rows.append(row)
                continue
            with open(item["anchor"], encoding="utf-8") as handle:
                saved = json.load(handle)
            anchor = saved.get(item["anchor_key"]) if item["anchor_key"] else saved
            recorded = (anchor or {}).get("artifact_sha256") or saved.get("sha256")
            row["anchor_sha256"] = _sha256_file(item["anchor"])
            if recorded and recorded != row["packet_sha256"]:
                row.update(outcome="failed", detail="retained bytes differ from the recorded artifact digest")
                rows.append(row)
                continue
            result = native.replay(science, package, data, {}, guard_log=guard_log, timeout=timeout,
                                   application_anchor=anchor)
            body = result.get("report") or {}
            row.update(outcome=classify_replay(result), replay_status=result.get("status"),
                       error_code=(result.get("error") or {}).get("code"),
                       replay=body.get("replay"), integrity=body.get("integrity"),
                       expected_binding=body.get("expected_binding"), reason_code=body.get("reason_code"))
            rows.append(row)
        finished, duration = _now(), round(time.monotonic() - clock, 1)
        tally = {}
        for row in rows:
            tally[row["outcome"]] = tally.get(row["outcome"], 0) + 1
        bad = {k: v for k, v in tally.items() if k in ("failed", "rejected", "error", "no_anchor")}
        accounting = dispatch_accounting(None, None, replay_logs=[guard_log])
        replays = sum(1 for row in rows if row.get("replay_status"))
        installed = accounting["guard"]["guard_installed_events"]
        if accounting["external_model_requests"]["status"] == "verified_zero" and installed < replays:
            accounting["external_model_requests"] = {"value": None, "status": "unknown",
                                                     "basis": f"guard installed in {installed} of {replays} replays"}
        report = _base_report("historical_replay", repo, repo, None, backend, science, before)
        preconditions = [_unchanged(before, repo)]
        report.update({
            "command": {"argv": ["counterdex replay-native <packet> --anchors <recorded anchor>"],
                        "cwd": "<temporary directory per packet>", "exit_code": 0 if not bad else 1},
            "started_at": started, "finished_at": finished, "duration_s": duration,
            "preconditions": preconditions, "results": {"counts": tally, "packets": rows},
            "requests_and_usage": accounting,
            "status": "passed" if rows and not bad and all(p["passed"] for p in preconditions) and accounting[
                "external_model_requests"]["status"] == "verified_zero" else "failed",
            "scope_note": "fresh re-execution of the same checker on retained bytes; no discovery, no inference. "
                          "Previews and diagnostics are excluded; incompatible_version packets name another "
                          "checker version and are reported apart from failure."})
        return _store(report, results_dir, {"guard-summary.json": _write_json(work, "guard-summary.json",
                                                                              accounting)})
    finally:
        shutil.rmtree(work, ignore_errors=True)


def live_not_run_statement() -> dict:
    return {"lane": "live_gemini", "status": "not_run", "reason": LIVE_NOT_RUN,
            "requests_and_usage": {"external_model_requests": {"value": 0, "status": "not_run",
                                                               "basis": "no live lane was started"},
                                   "provider_tokens": {"value": None, "status": "not_run"}},
            "lane_definition": {k: v for k, v in LANES["live_gemini"].items() if k != "pytest_marker"}}


# -- storage, verification and the gate ------------------------------------------------------------------------

def _store(report: dict, results_dir: str, artifacts: dict[str, str]) -> dict:
    directory = os.path.join(results_dir, "lanes", report["report_id"])
    os.makedirs(directory, exist_ok=True)
    kept = []
    for name, source in artifacts.items():
        if source and os.path.exists(source):
            target = os.path.join(directory, name)
            shutil.copyfile(source, target)
            kept.append({"path": os.path.relpath(target, results_dir), "sha256": _sha256_file(target),
                         "bytes": os.path.getsize(target)})
    report["artifacts"] = kept
    path = os.path.join(results_dir, REPORTS)
    report["prev_record_sha256"] = history.last_digest(path)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n")
    return report


def read_reports(results_dir: str) -> list[dict]:
    path = os.path.join(results_dir, REPORTS)
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.strip():
                try:
                    out.append(json.loads(line))
                except ValueError:
                    out.append({"schema": "unparsed"})
    return out


def verify(results_dir: str) -> list[str]:
    """Hash chain over report lines and digests of each report's artifacts."""
    path = os.path.join(results_dir, REPORTS)
    if not os.path.exists(path):
        return []
    problems, previous = [], history.GENESIS
    with open(path, "rb") as handle:
        lines = [line for line in handle if line.strip()]
    for number, line in enumerate(lines, 1):
        try:
            report = json.loads(line)
        except ValueError:
            problems.append(f"lanes report line {number} is not JSON")
            previous = history.line_digest(line)
            continue
        if report.get("prev_record_sha256") != previous:
            problems.append(f"lanes report line {number} ({report.get('report_id')}) breaks the hash chain")
        for artifact in report.get("artifacts") or []:
            target = os.path.join(results_dir, artifact.get("path", ""))
            if not os.path.isfile(target) or _sha256_file(target) != artifact.get("sha256"):
                problems.append(f"lanes report {report.get('report_id')} artifact {artifact.get('path')} changed "
                                "or missing")
        previous = history.line_digest(line)
    return problems


def report_problems(report: dict) -> list[str]:
    """Why a report at the right identity still cannot count as acceptance evidence."""
    problems = []
    identity = report.get("source_identity") or {}
    if identity.get("worktree_dirty") is not False:
        problems.append("worktree dirty or not recorded")
    if report.get("evidence_class") != "executed_acceptance" or report.get("app_under_test"):
        problems.append(f"not executed acceptance of this checkout ({report.get('evidence_class') or 'unclassified'})")
    if report.get("schema") != SCHEMA:
        problems.append("unknown report schema")
    return problems


def lanes_gate(results_dir: str, repo: str, current: dict | None = None) -> dict:
    """Each required lane is decided by its newest report whose source identity equals the tested checkout's.
    Reports from another identity never count; a dirty or preview newest report blocks the lane; a failed one fails
    it. live_gemini is listed as not_run and is not required."""
    current = current or source_identity(repo)
    reports = read_reports(results_dir)
    chain = verify(results_dir)
    lanes = {}
    for lane in REQUIRED_LANES:
        own = [r for r in reports if r.get("lane") == lane]
        matching = [r for r in own if identity_matches(r.get("source_identity") or {}, current)]
        if not matching:
            lanes[lane] = {"status": "blocked", "reason": "no report at the tested source identity",
                           "reports_at_other_identities": len(own)}
            continue
        newest = matching[-1]
        problems = report_problems(newest)
        status = "blocked" if problems else "passed" if newest.get("status") == "passed" else "failed"
        lanes[lane] = {"status": status, "report_id": newest.get("report_id"), "problems": problems,
                       "counts": (newest.get("results") or {}).get("counts"),
                       "external_model_requests": ((newest.get("requests_and_usage") or {})
                                                   .get("external_model_requests") or {}).get("status"),
                       "reports_at_other_identities": len(own) - len(matching)}
    lanes["live_gemini"] = {"status": "not_run", "required": False, "reason": LIVE_NOT_RUN}
    values = {item["status"] for name, item in lanes.items() if name in REQUIRED_LANES}
    status = "failed" if chain or "failed" in values else "blocked" if "blocked" in values else "passed"
    return {"gate": "evidence_lanes", "status": status,
            "description": "controlled_callbacks, controlled_science and historical_replay each pass in their "
                           "newest clean, executed report at the tested source identity (application, harness, "
                           "fixtures and engine digests); live_gemini is not_run and not required",
            "lanes": lanes, "history_problems": chain[:10],
            "tested_identity": {key: current.get(key) for key in IDENTITY_KEYS}}


def summary(results_dir: str, repo: str) -> dict:
    """Newest report per lane at the current identity, plus the live not_run statement (machine-readable)."""
    current = source_identity(repo)
    reports = read_reports(results_dir)
    out = {"schema": "drbean-lane-summary/v1", "generated_at": _now(), "source_identity": current, "lanes": {}}
    for lane in LANES:
        if lane == "live_gemini":
            out["lanes"][lane] = live_not_run_statement()
            continue
        matching = [r for r in reports if r.get("lane") == lane and identity_matches(
            r.get("source_identity") or {}, current)]
        newest = matching[-1] if matching else None
        out["lanes"][lane] = {"status": newest.get("status") if newest else "not_run_at_this_identity",
                              "report_id": newest.get("report_id") if newest else None,
                              "evidence_class": newest.get("evidence_class") if newest else None,
                              "counts": ((newest or {}).get("results") or {}).get("counts"),
                              "requests_and_usage": (newest or {}).get("requests_and_usage"),
                              "started_at": (newest or {}).get("started_at"),
                              "lane_definition": {k: v for k, v in LANES[lane].items() if k != "pytest_marker"}}
    out["gate"] = lanes_gate(results_dir, repo, current)
    return out
