"""Subjects: how the harness reaches the product under test.

The harness never implements the product. A subject either relays normalized
observations that the owning component emitted through its own controlled
test boundary (RecordedSubject), probes a running API (HttpSubject), or launches
an isolated local API + worker and drives the real routes itself
(LaunchedHttpSubject, ``--subject http-launch``). With nothing configured, every
scheduled entry is recorded as unrun.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from . import API_PREFIX


class SubjectUnavailable(Exception):
    """The entry could not be attempted; recorded as unrun with this reason."""


class SubjectRefused(Exception):
    """The provider or product refused; recorded as refused."""


class SubjectTimeout(Exception):
    """The wall bound elapsed; recorded as timed_out (usage may be unknown)."""


class NoSubject:
    name = "none"

    def describe(self) -> dict:
        return {"subject": "none", "reason": "no product under test was configured"}

    def run_entry(self, entry: dict, variant: dict, lane: str) -> dict:
        raise SubjectUnavailable("no subject configured: pass --subject http-launch (local test stack), "
                                 "http:<base-url> or recorded:<dir>")


class RecordedSubject:
    """Reads `<dir>/<entry_id>.observation.json` emitted by the owning component.

    The file must attest the lane, tested commit and case digest it was
    produced for. The runner rejects relabelled or stale observations. Recorded
    observations are imported claims: they can be graded against frozen case
    assertions, but they never qualify a real-science entry.
    """
    name = "recorded"

    def __init__(self, directory: str):
        self.directory = directory

    def describe(self) -> dict:
        path = os.path.join(self.directory, "subject.json")
        info = {"subject": "recorded", "directory": os.path.basename(os.path.normpath(self.directory))}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                info["declared"] = json.load(handle)
        return info

    def run_entry(self, entry: dict, variant: dict, lane: str) -> dict:
        path = os.path.join(self.directory, f"{entry['entry_id']}.observation.json")
        if not os.path.exists(path):
            raise SubjectUnavailable(f"no recorded observation for {entry['entry_id']} in the recorded directory")
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)


class HttpSubject:
    """Probes an already running `/api/bean/v1` API that this harness did not start.

    It only reads capabilities: the harness cannot know the bearer token, data
    directory or worker of a stack it did not launch, and it never resets another
    deployment's state. Use ``http-launch`` to execute cases against an isolated
    test stack.
    """
    name = "http"

    def __init__(self, base_url: str, timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def capabilities(self) -> dict:
        request = urllib.request.Request(self.base_url + API_PREFIX + "/capabilities", method="GET")
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return {"status": response.status, "body": json.loads(response.read().decode("utf-8"))}

    def describe(self) -> dict:
        info = {"subject": "http", "base_url": self.base_url}
        try:
            info["capabilities"] = self.capabilities()
        except (urllib.error.URLError, OSError, ValueError) as error:
            info["capabilities_error"] = f"{type(error).__name__}: {error}"
        return info

    def run_entry(self, entry: dict, variant: dict, lane: str) -> dict:
        raise SubjectUnavailable("http:<url> only probes a stack this harness did not launch; case execution needs "
                                 "--subject http-launch, which starts an isolated API and worker it can drive")


class LaunchedHttpSubject:
    """Launches an isolated local API + worker and drives the published routes (offline real-science lane)."""
    name = "http-launch"
    accepts_context = True
    executes_acceptance = True

    def __init__(self, repo: str, *, stack_env: dict | None = None, poll_timeout: float = 240.0,
                 app_repo: str | None = None, diagnostic_overrides: tuple[str, ...] = (), launch: str = "harness"):
        from . import launcher
        if launch not in ("harness", "owner4"):
            raise ValueError(f"unknown launch path {launch!r}")
        if launch == "owner4" and stack_env:
            raise ValueError("Owner 4's launcher takes no extra stack environment from the harness")
        self.launch = launch
        self.name = "http-owner4-launcher" if launch == "owner4" else "http-launch"
        self.repo = os.path.abspath(repo)  # the harness: packets, guard, evaluation code
        self.app_repo = os.path.abspath(app_repo or repo)  # the application under test (may be a teammate checkout)
        self.stack_env = stack_env or {}
        self.poll_timeout = poll_timeout
        self.diagnostic_overrides = tuple(diagnostic_overrides)
        self.package_dir = os.path.join(self.app_repo, "packages", "groundwork_adapter")
        self.app_under_test = {**launcher.git_commit(self.app_repo), "is_harness_checkout": self.app_repo == self.repo}
        # A relaxed product guard or a different application checkout is never release acceptance.
        self.evidence_class = ("diagnostic" if self.diagnostic_overrides else
                               "preview" if self.app_repo != self.repo else "executed_acceptance")
        try:
            self.science_python = launcher.science_python(self.app_repo)
            self.science_error = None
        except launcher.StackError as error:
            self.science_python, self.science_error = None, str(error)
        self.stack = None
        self.flow = None
        self.attempt_context: dict = {}
        self.readiness: dict | None = None

    def describe(self) -> dict:
        from . import launcher
        info = {"subject": self.name, "launch": "Owner 4's scripts/dev/launcher.py start (unmodified), isolated "
                "DRBEAN_VAR_DIR, egress guard via PYTHONPATH" if self.launch == "owner4" else "fresh temporary API + "
                "worker, allowlisted environment, egress guard loaded", "host": launcher.host_identity(),
                "app_under_test": self.app_under_test,
                "evidence_class": self.evidence_class, "diagnostic_overrides": list(self.diagnostic_overrides)}
        try:
            info["backend_python"] = launcher.interpreter_identity(launcher.backend_python(self.app_repo))
        except launcher.StackError as error:
            info["backend_python_error"] = str(error)
        info["science_python"] = (launcher.interpreter_identity(self.science_python) if self.science_python
                                  else {"error": self.science_error})
        if self.readiness is not None:
            info["readiness"] = self.readiness
        return info

    def begin_lane(self, lane: str, results_dir: str) -> dict:
        from . import launcher, science_flow
        from .http_client import ApiClient
        if self.launch == "owner4":
            self.stack = launcher.Owner4LauncherStack(self.app_repo,
                                                      diagnostic_overrides=self.diagnostic_overrides).start()
        else:
            self.stack = launcher.LocalStack(self.app_repo, stack_env=self.stack_env,
                                             diagnostic_overrides=self.diagnostic_overrides).start()
        self.readiness = self.stack.readiness()
        self.readiness["startup_path"] = self.stack.startup_path()
        client = ApiClient(self.stack.base_url, self.stack.tokens[launcher.REVIEWER])
        other = ApiClient(self.stack.base_url, self.stack.tokens[launcher.OTHER_ACTOR])
        scratch = os.path.join(self.stack.workdir, "evidence-scratch")
        self.flow = science_flow.Flow(client, other, scratch, science_python=self.science_python,
                                      package_dir=self.package_dir, guard_log=self.stack.guard_log,
                                      poll_timeout=self.poll_timeout)
        return {"readiness": self.readiness}

    def end_lane(self) -> dict:
        if self.stack is None:
            return {}
        report = self.stack.stop()
        events = self.stack.guard_events()
        report["guard"] = {"installed_pids": len({e["pid"] for e in events if e["kind"] == "guard_installed"}),
                           "external_attempts": len(self.stack.external_attempts())}
        self.stack.cleanup()
        return report

    def _dispatch_summary(self) -> dict:
        events = self.stack.guard_events()
        installed = {e["pid"] for e in events if e["kind"] == "guard_installed"}
        owned = {p.pid for p in self.stack.processes.values()}
        attempts = self.stack.external_attempts()
        credential_names = sorted({n for e in events if e["kind"] == "guard_installed"
                                   for n in e.get("credential_names_present", [])})
        verified = bool(installed & owned) and self.stack.processes["api"].pid in installed and any(
            p.pid in installed for name, p in self.stack.processes.items() if name.startswith("worker"))
        return {"verified": verified, "egress_attempts": sum(e["kind"] == "egress_blocked" for e in attempts),
                "client_constructions": sum(e["kind"] == "provider_client_blocked" for e in attempts),
                "guarded_processes": len(installed), "credential_names_present": credential_names,
                "attempt_sites": sorted({(e.get("host") or e.get("client") or "?") for e in attempts})[:10]}

    def run_entry(self, entry: dict, variant: dict, lane: str) -> dict:
        from . import science_flow as sf
        if lane != "offline_real_science":
            raise SubjectUnavailable(f"http-launch executes the offline_real_science lane, not {lane}")
        if self.stack is None or self.flow is None:
            raise SubjectUnavailable("the local test stack is not running")
        context = self.attempt_context
        self.flow.begin_entry(context["evidence_dir"])
        packets = {name: _load_packet(self.repo, name) for name in ("hero-v2", "changed-input-v1")}
        hero = packets["hero-v2"]
        scenario = {
            "RS-HERO-FULL": lambda: sf.scenario_hero(self.flow, hero),
            "RS-CHANGED-INPUT": lambda: sf.scenario_changed_input(self.flow, hero, packets["changed-input-v1"]),
            "RS-RETRY-CONCURRENT": lambda: sf.scenario_retry_concurrent(self.flow, hero),
            "RS-DESIGN-AUTHORITY": lambda: sf.scenario_design_authority(self.flow, hero),
            "RS-FOLLOWUP": lambda: sf.scenario_followup(self.flow, hero),
            "RS-CANCEL-RESTART": lambda: sf.scenario_cancel_restart(self.flow, hero, self.stack),
            "RS-ZERO-DISPATCH": lambda: sf.scenario_zero_dispatch(self.flow, self.stack),
        }.get(entry["entry_id"])
        if scenario is None:
            raise SubjectUnavailable(f"no scenario implements {entry['entry_id']}")
        if self.launch == "owner4" and entry["entry_id"] == "RS-CANCEL-RESTART":
            raise SubjectUnavailable("worker kill/restart needs per-process control that Owner 4's launcher does not "
                                     "offer; observed on the harness launch path (--subject http-launch)")
        jobs_before = set(self.flow.jobs_executed)
        try:
            outcome = scenario()
            checks, details = outcome["checks"], outcome["observation"]
        except Exception as error:  # an unexpected API response is a failed check with its evidence kept
            from .http_client import ApiFailure
            checks = sf.Checks()
            code = error.code if isinstance(error, ApiFailure) else None
            checks.add("scenario_completed_without_unexpected_response", "failed",
                       f"{type(error).__name__}: {str(error)[:300]}" + (f" (code {code})" if code else ""))
            details = {}
        dispatch = self._dispatch_summary()
        return {
            "schema": "eval-observation/v1", "lane": lane, "lane_version": context.get("lane_version"),
            "tested_commit": context.get("tested_commit"), "case_sha256": context.get("case_sha256"),
            "operation": "science", "entry_id": entry["entry_id"],
            "provider": {"transport": "none", "placeholder_identity": None,
                         "note": "manual plans; no model, controlled or live, was invoked by these scenarios"},
            "tools": {"transport": "real"},
            "provider_requests": 0 if dispatch["verified"] and not (dispatch["egress_attempts"]
                                                                     or dispatch["client_constructions"]) else None,
            "external_dispatch": dispatch, "approvals_created": 0,
            "reviewer_approvals": sum(1 for x in self.flow.client.exchanges if x["route"].endswith("/approvals")
                                      and x["status"] in (200, 201)),
            "disclosed_text": [], "state": checks.status(), "checks": checks.items, "details": details,
            "records": details.get("records"), "job_ids": sorted(self.flow.jobs_executed - jobs_before),
            "scientific_jobs": len(self.flow.jobs_executed - jobs_before),
            "evidence_index": self.flow.evidence_index(), "native_artifacts": self.flow.native_saved,
            "exchanges": list(self.flow.client.exchanges), "readiness": self.readiness,
            "app_under_test": self.app_under_test, "diagnostic_overrides": list(self.diagnostic_overrides),
            "timings": _timings(self.flow.client.exchanges),
        }


def _load_packet(repo: str, name: str) -> dict:
    with open(os.path.join(repo, "evaluation", "cases", "science", name + ".json"), encoding="utf-8") as handle:
        return json.load(handle)


def _timings(exchanges: list[dict]) -> dict:
    latencies = [x["latency_ms"] for x in exchanges]
    return {"http_exchanges": len(exchanges), "http_latency_ms_total": round(sum(latencies), 3),
            "http_latency_ms_max": max(latencies) if latencies else None,
            "basis": "local loopback wall time measured by the harness; not provider latency"}


def make_subject(spec: str, repo: str | None = None, stack_env: dict | None = None, app_repo: str | None = None,
                 diagnostic_overrides: tuple[str, ...] = ()):
    if spec in ("", "none"):
        return NoSubject()
    if spec in ("http-launch", "http-owner4-launcher"):
        return LaunchedHttpSubject(repo or os.getcwd(), stack_env=stack_env, app_repo=app_repo,
                                   diagnostic_overrides=diagnostic_overrides,
                                   launch="owner4" if spec == "http-owner4-launcher" else "harness")
    kind, _, rest = spec.partition(":")
    if kind == "recorded" and rest:
        return RecordedSubject(rest)
    if kind == "http" and rest:
        return HttpSubject(rest)
    raise ValueError(f"unknown subject spec {spec!r}; use none, http-launch, http-owner4-launcher, recorded:<dir> "
                     "or http:<base-url>")
