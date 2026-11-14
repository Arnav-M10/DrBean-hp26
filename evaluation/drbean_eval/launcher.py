"""Launch an isolated local Dr. Bean test stack: one API process and one worker.

Everything here is a *test* deployment chosen by the operator, never by evidence:

* fresh temporary database, source/blob directory and in-memory bearer tokens;
  the developer's ``var/`` database, provider ledger and accepted history are
  never opened, reset or migrated;
* an environment built from an allowlist. Provider credential variables are never
  inherited. A test may pass an obviously fake ``DRBEAN-DUMMY-...`` value to prove
  that configuration alone cannot dispatch; a real-looking value is refused;
* the egress guard (``guard/sitecustomize.py``) is loaded into the API, the worker
  and every scientific child that inherits the environment;
* only processes this module started are tracked and stopped. Their descendants
  are snapshotted while running so that a child that outlives teardown is reported
  as an orphan instead of being silently ignored.

Readiness is reported separately for the API, the worker and the scientific
capability. A responding health URL does not establish a usable engine.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from . import API_PREFIX

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD_DIR = os.path.join(HERE, "guard")
REVIEWER = "eval-reviewer"
OTHER_ACTOR = "eval-other-workspace"
DUMMY_VALUE = re.compile(r"^DRBEAN-DUMMY-[A-Z0-9-]{4,64}$")
# Opt-in diagnostics that relax one named product guard to observe downstream behaviour. Never acceptance evidence.
DIAGNOSTIC_OVERRIDES = {"relax_nproc", "science_barrier"}
_CREDENTIAL_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|^GEMINI_|^GOOGLE_|^LANGSMITH_|^LANGCHAIN_)")
# Non-credential configuration a teammate's stack may legitimately need.
_PASSTHROUGH = re.compile(r"^BEAN_[A-Z0-9_]+$")


class StackError(RuntimeError):
    """The local stack could not be started; the reason names what is missing."""


def backend_python(repo: str) -> str:
    """Operator-selected backend interpreter (DRBEAN_BACKEND_PYTHON or the locked .venv)."""
    candidate = os.environ.get("DRBEAN_BACKEND_PYTHON") or os.path.join(repo, ".venv", "bin", "python")
    if not os.path.isfile(candidate):
        raise StackError(f"backend interpreter not found at {candidate}; create the locked environment "
                         "(uv sync --locked) or set DRBEAN_BACKEND_PYTHON")
    return candidate


def science_python(repo: str | None = None) -> str:
    """Operator-selected CPython 3.11: DRBEAN_SCIENCE_PYTHON, else Owner 4's qualified .venv-engine, else python3.11."""
    engine = os.path.join(repo or os.path.dirname(os.path.dirname(HERE)), ".venv-engine", "bin", "python")
    candidate = (os.environ.get("DRBEAN_SCIENCE_PYTHON") or (engine if os.path.isfile(engine) else None)
                 or shutil.which("python3.11"))
    if not candidate or not os.path.isfile(candidate):
        raise StackError("CPython 3.11 for native replay not found; set DRBEAN_SCIENCE_PYTHON")
    out = subprocess.run([candidate, "-I", "-c", "import sys,platform;print(platform.python_implementation(),"
                          "'%d.%d.%d' % sys.version_info[:3])"], capture_output=True, text=True, timeout=20)
    implementation, _, version = out.stdout.strip().partition(" ")
    if out.returncode or implementation != "CPython" or not version.startswith("3.11."):
        raise StackError(f"{candidate} is {out.stdout.strip() or 'unusable'}; native replay is qualified on CPython 3.11")
    return candidate


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def process_table() -> dict[int, dict]:
    """pid -> {ppid, pgid, command}; read with ps so no third-party module is needed."""
    out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,pgid=,command="], capture_output=True, text=True,
                         timeout=10).stdout
    table = {}
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) >= 3 and parts[0].isdigit():
            table[int(parts[0])] = {"ppid": int(parts[1]), "pgid": int(parts[2]),
                                    "command": parts[3][:200] if len(parts) > 3 else ""}
    return table


def descendants(roots: set[int], table: dict[int, dict] | None = None) -> dict[int, dict]:
    table = process_table() if table is None else table
    found, frontier = {}, set(roots)
    while frontier:
        nxt = set()
        for pid, row in table.items():
            if row["ppid"] in frontier and pid not in found and pid not in roots:
                found[pid] = row
                nxt.add(pid)
        frontier = nxt
    return found


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:  # a zombie of ours still answers kill(0); reap it if it is our child
        reaped, _ = os.waitpid(pid, os.WNOHANG)
        return reaped == 0
    except ChildProcessError:
        return True


class LocalStack:
    """Context manager for one isolated API + worker test deployment."""

    def __init__(self, repo: str, *, workdir: str | None = None, worker: bool = True,
                 stack_env: dict[str, str] | None = None, allow_dummy_provider_config: bool = False,
                 startup_timeout: float = 60.0, diagnostic_overrides: tuple[str, ...] = ()):
        unknown = set(diagnostic_overrides) - DIAGNOSTIC_OVERRIDES  # refuse before touching any interpreter
        if unknown:
            raise StackError(f"unknown diagnostic override(s) {sorted(unknown)}; known: {sorted(DIAGNOSTIC_OVERRIDES)}")
        self.diagnostic_overrides = tuple(sorted(set(diagnostic_overrides)))
        self.repo = os.path.abspath(repo)
        self.python = backend_python(self.repo)
        self._own_workdir = workdir is None
        self.workdir = workdir or tempfile.mkdtemp(prefix="drbean-stack-")
        self.with_worker = worker
        self.startup_timeout = startup_timeout
        self.tokens = {REVIEWER: secrets.token_urlsafe(40), OTHER_ACTOR: secrets.token_urlsafe(40)}
        self.port = free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.guard_log = os.path.join(self.workdir, "egress-guard.jsonl")
        self.database = os.path.join(self.workdir, "state", "bean.sqlite3")
        self.blob_dir = os.path.join(self.workdir, "state", "sources")
        self.artifact_dir = os.path.join(self.workdir, "state", "artifacts")
        self.barrier_path = os.path.join(self.workdir, "science.barrier")
        try:  # Owner 2's declared runtime selection: an absolute, operator-chosen CPython 3.11
            self.counterdex_python = science_python(self.repo)
        except StackError:
            self.counterdex_python = None
        self.processes: dict[str, subprocess.Popen] = {}
        self.seen_descendants: dict[int, dict] = {}
        self.events: list[dict] = []
        self.extra_env = self._checked_extra_env(stack_env or {}, allow_dummy_provider_config)

    # -- environment -------------------------------------------------------
    @staticmethod
    def _checked_extra_env(stack_env: dict[str, str], allow_dummy: bool) -> dict[str, str]:
        checked = {}
        for name, value in stack_env.items():
            if not isinstance(name, str) or not isinstance(value, str):
                raise StackError("stack environment entries must be strings")
            provider_setting = name == "GEMINI_MODEL" or name.startswith("BEAN_GEMINI_")
            if provider_setting:
                # Model names and gate flags are not secrets, but they only belong in tests that prove
                # configuration alone cannot dispatch.
                if not allow_dummy or not re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", value):
                    raise StackError(f"refusing provider setting {name} outside a dummy-configuration test")
            elif _CREDENTIAL_NAME.search(name):
                if not allow_dummy or not DUMMY_VALUE.match(value):
                    raise StackError(f"refusing credential-shaped variable {name}: the offline lane accepts only "
                                     "explicit DRBEAN-DUMMY-... values in dummy-configuration tests")
            elif not _PASSTHROUGH.match(name):
                raise StackError(f"refusing unrecognized stack variable {name}")
            checked[name] = value
        return checked

    def environment(self) -> dict[str, str]:
        home = os.path.join(self.workdir, "home")
        tmp = os.path.join(self.workdir, "tmp")
        os.makedirs(home, exist_ok=True)
        os.makedirs(tmp, exist_ok=True)
        env = {
            "PATH": os.pathsep.join(p for p in ("/usr/bin", "/bin", "/usr/sbin", "/sbin") if os.path.isdir(p)),
            "HOME": home, "TMPDIR": tmp, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
            "PYTHONPATH": os.pathsep.join((GUARD_DIR, os.path.join(self.repo, "apps", "api"))),
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1",
            "DRBEAN_EGRESS_GUARD_LOG": self.guard_log,
            "BEAN_DATABASE_PATH": self.database, "BEAN_BLOB_DIR": self.blob_dir,
            "BEAN_ARTIFACT_DIR": self.artifact_dir, "BEAN_SCIENCE_ADAPTER": "counterdex",
            "BEAN_AUTH_FILE": os.path.join(self.workdir, "state", "no-auth-file.json"),
            "BEAN_AUTH_TOKENS_JSON": json.dumps(self.tokens),
            "BEAN_ALLOWED_ORIGINS": self.base_url,
            # Defense in depth for any HTTP library that honours proxies: never route out.
            "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost",
            "LANGSMITH_TRACING": "false", "LANGCHAIN_TRACING_V2": "false",
        }
        if self.counterdex_python:
            env["BEAN_COUNTERDEX_PYTHON"] = self.counterdex_python
        if self.diagnostic_overrides:
            env["DRBEAN_DIAGNOSTIC_OVERRIDES"] = ",".join(self.diagnostic_overrides)
        if "science_barrier" in self.diagnostic_overrides:
            env["DRBEAN_DIAGNOSTIC_BARRIER"] = self.barrier_path
        env.update(self.extra_env)
        return env

    def startup_path(self) -> dict:
        """Exactly which ordinary entry points this harness exercised (until Owner 4's launcher is qualified)."""
        return {"launcher": "evaluation harness isolated launch (Owner 4 launcher not yet used)",
                "api": "python -m uvicorn bean_api.main:create_app --factory --host 127.0.0.1",
                "worker": "python -m bean_api.worker", "pythonpath": ["evaluation guard", "apps/api"],
                "science_adapter": self.environment().get("BEAN_SCIENCE_ADAPTER"),
                "counterdex_python_configured": bool(self.counterdex_python),
                "state": "fresh temporary SQLite, sources and artifacts; in-memory bearer tokens",
                "diagnostic_overrides": list(self.diagnostic_overrides)}

    # -- lifecycle ---------------------------------------------------------
    def _spawn(self, name: str, argv: list[str]) -> subprocess.Popen:
        logs = os.path.join(self.workdir, "logs")
        os.makedirs(logs, exist_ok=True)
        out = open(os.path.join(logs, f"{name}.log"), "ab")
        process = subprocess.Popen(argv, cwd=self.repo, env=self.environment(), stdin=subprocess.DEVNULL,
                                   stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
        out.close()
        self.processes[name] = process
        self.events.append({"event": "spawned", "name": name, "pid": process.pid, "at": time.time()})
        return process

    def start(self) -> "LocalStack":
        os.makedirs(os.path.dirname(self.database), exist_ok=True, mode=0o700)
        self._spawn("api", [self.python, "-m", "uvicorn", "bean_api.main:create_app", "--factory",
                            "--host", "127.0.0.1", "--port", str(self.port), "--log-level", "warning",
                            "--no-access-log"])
        deadline = time.monotonic() + self.startup_timeout
        while True:
            if self.processes["api"].poll() is not None:
                raise StackError(f"API exited during startup with code {self.processes['api'].returncode}; "
                                 f"see {os.path.join(self.workdir, 'logs', 'api.log')}")
            try:
                with urllib.request.urlopen(self.base_url + "/healthz", timeout=2) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, OSError):
                pass
            if time.monotonic() > deadline:
                raise StackError("API did not answer /healthz before the startup deadline")
            time.sleep(0.2)
        if self.with_worker:
            self.start_worker()
        return self

    def start_worker(self, *extra: str) -> subprocess.Popen:
        process = self._spawn("worker" if not extra else "worker-" + "-".join(a.strip("-") for a in extra),
                              [self.python, "-m", "bean_api.worker", *extra])
        if extra:
            return process
        deadline = time.monotonic() + self.startup_timeout
        while not self.worker_holds_lock():
            if process.poll() is not None:
                raise StackError(f"worker exited during startup with code {process.returncode}; "
                                 f"see {os.path.join(self.workdir, 'logs', 'worker.log')}")
            if time.monotonic() > deadline:
                raise StackError("worker did not take the SQLite worker lock before the startup deadline")
            time.sleep(0.2)
        return process

    @property
    def has_barrier(self) -> bool:
        return "science_barrier" in self.diagnostic_overrides

    def hold_barrier(self) -> None:
        """Diagnostic: scientific children started from now on wait inside the adapter until released."""
        with open(self.barrier_path, "w", encoding="utf-8") as handle:
            handle.write("held by the evaluation harness\n")

    def release_barrier(self) -> None:
        try:
            os.unlink(self.barrier_path)
        except FileNotFoundError:
            pass

    def worker_holds_lock(self) -> bool:
        path = os.path.realpath(self.database) + ".worker.lock"
        if not os.path.exists(path):
            return False
        with open(path, "a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(handle, fcntl.LOCK_UN)
            return False

    def snapshot_descendants(self) -> dict[int, dict]:
        roots = {p.pid for p in self.processes.values() if p.poll() is None}
        found = descendants(roots) if roots else {}
        self.seen_descendants.update(found)
        return found

    def capabilities(self) -> dict:
        with urllib.request.urlopen(self.base_url + API_PREFIX + "/capabilities", timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def readiness(self) -> dict:
        """Three separate answers. Only a configured, verified scientific adapter is science-ready."""
        result = {"api": {"ready": False}, "worker": {"ready": False}, "science": {"ready": False}}
        try:
            with urllib.request.urlopen(self.base_url + "/healthz", timeout=5) as response:
                result["api"] = {"ready": response.status == 200, "health": json.loads(response.read())}
        except (urllib.error.URLError, OSError, ValueError) as error:
            result["api"] = {"ready": False, "error": f"{type(error).__name__}"}
        worker = self.processes.get("worker")
        result["worker"] = {"ready": bool(worker and worker.poll() is None and self.worker_holds_lock()),
                            "process_alive": bool(worker and worker.poll() is None),
                            "holds_sqlite_worker_lock": self.worker_holds_lock()}
        try:
            capabilities = self.capabilities()
            science = capabilities.get("science") or {}
            runtime = bool(science.get("implemented") and science.get("configured")
                           and science.get("available", science.get("verified_in_environment")))
            discovery = science.get("baseline_discovery")
            result["science"] = {"ready": bool(runtime and discovery is not False), "runtime_available": runtime,
                                 "baseline_discovery": discovery, "native_replay": science.get("native_replay"),
                                 "reason": science.get("reason"), "reported": science}
            result["ai_mode"] = capabilities.get("ai_mode")
        except (urllib.error.URLError, OSError, ValueError) as error:
            result["science"] = {"ready": False, "error": f"{type(error).__name__}"}
        return result

    def kill(self, name: str, sig: int = signal.SIGKILL) -> None:
        """Abruptly stop one owned process group (used by restart tests)."""
        process = self.processes[name]
        self.snapshot_descendants()
        if process.poll() is None:
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                pass
            process.wait(timeout=10)
        self.events.append({"event": "killed", "name": name, "signal": int(sig), "at": time.time()})

    def guard_events(self) -> list[dict]:
        if not os.path.exists(self.guard_log):
            return []
        with open(self.guard_log, encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def credential_reads(self) -> list[dict]:
        return [e for e in self.guard_events() if e.get("kind") == "credential_read"]

    def external_attempts(self) -> list[dict]:
        return [e for e in self.guard_events() if e.get("kind") in ("egress_blocked", "provider_client_blocked")]

    def stop(self) -> dict:
        """Stop owned process groups, then report any tracked descendant that is still alive."""
        self.snapshot_descendants()
        for name, process in self.processes.items():
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        deadline = time.monotonic() + 10
        for process in self.processes.values():
            try:
                process.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
        time.sleep(0.3)
        orphans = {pid: row for pid, row in self.seen_descendants.items() if alive(pid)}
        for pid in orphans:  # clean up, but the report keeps them as a finding
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        report = {"orphans": [{"pid": pid, **row} for pid, row in orphans.items()],
                  "tracked_descendants": len(self.seen_descendants),
                  "exit_codes": {name: p.returncode for name, p in self.processes.items()}}
        self.events.append({"event": "stopped", "at": time.time(), **report})
        return report

    def cleanup(self) -> None:
        if self._own_workdir:
            shutil.rmtree(self.workdir, ignore_errors=True)

    def __enter__(self) -> "LocalStack":
        try:
            return self.start()
        except BaseException:
            self.stop()
            raise

    def __exit__(self, *exc) -> None:
        self.teardown = self.stop()


def interpreter_identity(python: str) -> dict:
    out = subprocess.run([python, "-I", "-c", "import sys,platform,json;print(json.dumps({'implementation':"
                          "platform.python_implementation(),'version':platform.python_version(),"
                          "'machine':platform.machine(),'system':platform.system()}))"],
                         capture_output=True, text=True, timeout=20)
    try:
        return json.loads(out.stdout)
    except ValueError:
        return {"error": "interpreter did not report its identity"}


def host_identity() -> dict:
    import platform
    return {"system": platform.system(), "release": platform.release(), "machine": platform.machine(),
            "harness_python": platform.python_version(), "executable": os.path.basename(sys.executable)}


def git_commit(repo: str) -> dict:
    def run(*args):
        return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True).stdout.strip()
    changed = [line[3:] for line in subprocess.run(["git", "-C", repo, "status", "--porcelain", "--untracked-files=no"],
                                                   capture_output=True, text=True).stdout.splitlines()
               if line.strip() and not line[3:].startswith(("evaluation/results/", "evaluation/ledger/"))]
    return {"commit": run("rev-parse", "HEAD") or None, "branch": run("rev-parse", "--abbrev-ref", "HEAD") or None,
            "dirty": bool(changed)}
