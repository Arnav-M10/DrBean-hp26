#!/usr/bin/env python3
"""Dr. Bean local launcher: setup, doctor, start, stop, status, recover.

Standard library only, so it runs before any environment exists. It never
picks "whatever python3 is on PATH" for product code: the backend runs in the
uv-managed `.venv` (Python 3.12/3.13 per pyproject.toml) and the Counterdex
engine in `.venv-engine` (CPython 3.11, its only qualified runtime).

AI is in placeholder mode. Every child process is started with provider and
tracing credentials removed from its environment, so a key that happens to be
set in your shell cannot enable a live model call. This script never reads,
prints or validates a key, and never contacts a model provider.

  scripts/dev/setup.sh      install both runtimes, create local auth (keeps existing data)
  scripts/dev/doctor.py     report prerequisites and, if running, service facts
  scripts/dev/start.sh      start API, worker and web; wait until ready
  scripts/dev/stop.sh       stop only the processes this launcher started
  python3 scripts/dev/launcher.py status | recover
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# One store. DRBEAN_VAR_DIR lets a test use an isolated store instead of your real one.
VAR = os.path.abspath(os.environ.get("DRBEAN_VAR_DIR") or os.path.join(REPO, "var"))
RUN = os.path.join(VAR, "run")
BACKEND_PY = os.path.join(REPO, ".venv", "bin", "python")
ENGINE_VENV = os.path.join(REPO, ".venv-engine")
ENGINE_PY = os.path.join(ENGINE_VENV, "bin", "python")
ENGINE_SRC = os.path.join(REPO, "packages", "groundwork_adapter")
HOST = "127.0.0.1"  # loopback only; a hosted boundary is a separate, unimplemented decision
API_PORT, WEB_PORT = 8000, 4173  # apps/web/serve.mjs proxies /api/bean/v1/ to the fixed port 8000
AI_MODE = "placeholder"

# Removed from every child environment. Names only; values are never read.
PROVIDER_ENV_EXACT = {
    "GEMINI_API_KEY", "GEMINI_MODEL", "GOOGLE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS",
    "BEAN_GEMINI_ACCOUNT_GATE", "BEAN_GEMINI_ACCOUNT_DECISION_ID", "BEAN_GEMINI_IMAGE_TOKEN_BOUND",
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "LANGCHAIN_API_KEY", "LANGCHAIN_TRACING_V2", "LANGCHAIN_ENDPOINT",
    "DATABASE_URL",
}
PROVIDER_ENV_PREFIXES = ("GOOGLE_GENAI_", "GOOGLE_CLOUD_", "VERTEX", "LANGSMITH_", "ANTHROPIC_", "OPENAI_")
SERVICES = ("api", "worker", "web")

# Explicit opt-in to live Gemini, read as JSON data (never shell-sourced) from an ignored file.
# Only these keys are accepted. The values are passed to the API and worker processes only;
# the web server, the scientific engine (Owner 2 clears its environment) and the PDF/image
# workers (minimal environments) never receive them. A key on its own changes nothing: "mode"
# must also be "live", and the server must itself report that live dispatch is enabled.
LIVE_CONFIG = os.path.join(VAR, "gemini.local.json")
LIVE_CHECK = os.path.join(VAR, "gemini-live-check.json")  # written only by a completed opted-in live check
LIVE_KEYS = {"GEMINI_API_KEY", "GEMINI_MODEL", "BEAN_GEMINI_ACCOUNT_GATE", "BEAN_GEMINI_ACCOUNT_DECISION_ID",
             "BEAN_GEMINI_IMAGE_TOKEN_BOUND", "BEAN_GEMINI_MAX_INPUT_TOKENS", "BEAN_GEMINI_MAX_OUTPUT_TOKENS"}


def live_config() -> dict:
    """{'state', 'detail', 'env'}; 'env' is empty unless mode is live and a key is present. Never prints values."""
    if not os.path.exists(LIVE_CONFIG):
        return {"state": "absent", "detail": f"no {os.path.relpath(LIVE_CONFIG, REPO)}: live Gemini is off", "env": {}}
    try:
        if os.stat(LIVE_CONFIG).st_size > 16384:
            raise ValueError("file is larger than 16 KiB")
        with open(LIVE_CONFIG, encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("top level must be a JSON object")
        unknown = sorted(set(data) - LIVE_KEYS - {"mode"})
        if unknown:
            raise ValueError(f"unsupported key(s) {', '.join(unknown)}")
        if data.get("mode", "disabled") not in {"disabled", "live"}:
            raise ValueError('"mode" must be "disabled" or "live"')
        if any(not isinstance(v, str) or len(v) > 4096 or "\n" in v for k, v in data.items()):
            raise ValueError("every value must be a single-line string")
    except (OSError, ValueError) as error:
        return {"state": "invalid", "detail": f"{os.path.relpath(LIVE_CONFIG, REPO)} ignored: {error}", "env": {}}
    loose = os.stat(LIVE_CONFIG).st_mode & 0o077
    note = " (warning: readable by other users; chmod 600 it)" if loose else ""
    key = bool(data.get("GEMINI_API_KEY"))
    if data.get("mode", "disabled") != "live":
        return {"state": "disabled", "detail": f"opt-in file present, mode disabled; key {'present' if key else 'missing'}{note}", "env": {}}
    if not key:
        return {"state": "missing_key", "detail": f"mode live but GEMINI_API_KEY is missing: live Gemini stays off{note}", "env": {}}
    env = {k: v for k, v in data.items() if k in LIVE_KEYS}
    return {"state": "configured", "detail": f"mode live, key present, model {data.get('GEMINI_MODEL') or 'not set'}{note}",
            "env": {**env, "BEAN_AI_MODE": "live_opt_in"}}


def live_check_record() -> str:
    try:
        with open(LIVE_CHECK, encoding="utf-8") as handle:
            record = json.load(handle)
        if record.get("status") == "completed" and record.get("provider_requests", 0) > 0:
            return f"completed {record.get('completed_at', '?')} ({record.get('provider_requests')} request(s))"
    except (OSError, ValueError, AttributeError):
        pass
    return "not run"


def child_env() -> dict:
    """Environment for product processes: explicit placeholder AI, one store, absolute paths."""
    env = {key: os.environ[key] for key in os.environ
           if key not in PROVIDER_ENV_EXACT and not key.startswith(PROVIDER_ENV_PREFIXES)}
    # The server source is explicit even when a filesystem hides .venv's
    # editable-install .pth file. Preserve an operator's guard/search path.
    application_path = os.path.join(REPO, "apps", "api")
    paths = [path for path in env.get("PYTHONPATH", "").split(os.pathsep) if path]
    env["PYTHONPATH"] = os.pathsep.join([application_path, *(path for path in paths if path != application_path)])
    env.update(
        BEAN_AI_MODE=AI_MODE,
        BEAN_DATABASE_PATH=os.path.join(VAR, "bean.sqlite3"),
        BEAN_BLOB_DIR=os.path.join(VAR, "sources"),
        BEAN_AUTH_FILE=os.path.join(VAR, "auth.json"),
        BEAN_ARTIFACT_DIR=os.path.join(VAR, "artifacts"),
        BEAN_SCIENCE_ADAPTER="counterdex",
        BEAN_COUNTERDEX_PYTHON=ENGINE_PY,  # the qualified CPython 3.11 engine runtime, never a python3.11 found on PATH
        PYTHONDONTWRITEBYTECODE="1",
        # Defence in depth only, never relied on: if anything did try to dispatch, send it to a closed
        # loopback port instead of a provider. Owner 5 supplies the real process-level network guard.
        GOOGLE_GEMINI_BASE_URL="http://127.0.0.1:9",
        LANGSMITH_TRACING="false",
    )
    return env


def out(cmd, env=None, cwd=REPO, timeout=120):
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, env=child_env() if env is None else env,
                              cwd=cwd, timeout=timeout)
        return done.returncode, (done.stdout + done.stderr).strip()
    except (FileNotFoundError, PermissionError) as error:
        return 127, str(error)
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout} s"


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((HOST, port)) == 0


def http_json(url: str, timeout=3.0):
    """Loopback GET only."""
    assert url.startswith(f"http://{HOST}:"), url
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never route loopback via a proxy
    with opener.open(url, timeout=timeout) as response:
        body = response.read(1 << 20)
        return response.status, (json.loads(body) if "json" in response.headers.get("content-type", "") else None)


# ---------------------------------------------------------------- owned processes
def started_at(pid: int) -> str | None:
    """Process start time as reported by ps; used to prove a pid is still the one we started."""
    code, text = out(["ps", "-p", str(pid), "-o", "stat=,lstart="])
    if code != 0 or not text.strip():
        return None
    state, _, stamp = text.strip().partition(" ")
    return None if state.startswith("Z") else stamp.strip()  # an exited, unreaped process is gone


def pidfile(name: str) -> str:
    return os.path.join(RUN, f"{name}.json")


def owned(name: str) -> dict | None:
    """The live process this launcher started for `name`, or None. A reused pid is not ours."""
    try:
        with open(pidfile(name), encoding="utf-8") as handle:
            record = json.load(handle)
    except (OSError, ValueError):
        return None
    return record if record.get("started_at") and started_at(record["pid"]) == record["started_at"] else None


def spawn(name: str, command: list[str], env: dict) -> dict:
    os.makedirs(RUN, exist_ok=True)
    log_path = os.path.join(RUN, f"{name}.log")
    with open(log_path, "ab") as log:
        log.write(f"\n--- {name} started {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} ---\n".encode())
        log.flush()
        process = subprocess.Popen(command, cwd=REPO, env=env, stdin=subprocess.DEVNULL, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
    stamp = None
    for _ in range(20):
        stamp = started_at(process.pid)
        if stamp:
            break
        time.sleep(0.05)
    record = {"name": name, "pid": process.pid, "started_at": stamp, "command": command, "log": log_path}
    with open(pidfile(name), "w", encoding="utf-8") as handle:
        json.dump(record, handle)
    return record


def stop_one(name: str, grace: float = 10.0) -> str:
    record = owned(name)
    if record is None:
        if os.path.exists(pidfile(name)):
            os.remove(pidfile(name))  # stale record; the pid is gone or belongs to someone else
            return "not running (stale record removed)"
        return "not running"
    pid = record["pid"]
    try:
        os.killpg(pid, signal.SIGTERM)  # its own session, so this reaches only its process group
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline and started_at(pid) == record["started_at"]:
        time.sleep(0.2)
    forced = False
    if started_at(pid) == record["started_at"]:
        forced = True
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        time.sleep(0.3)
    os.remove(pidfile(name))
    return "killed after grace period" if forced else "stopped"


def log_tail(name: str, lines: int = 15) -> str:
    try:
        with open(os.path.join(RUN, f"{name}.log"), encoding="utf-8", errors="replace") as handle:
            return "".join(handle.readlines()[-lines:])
    except OSError:
        return ""


# ---------------------------------------------------------------- facts
def static_facts() -> dict:
    facts = {"os": platform.system(), "os_release": platform.release(), "arch": platform.machine(),
             "launcher_python": platform.python_version()}
    code, text = out(["uv", "--version"])
    facts["uv"] = text if code == 0 else None
    code, text = out(["node", "--version"])
    facts["node"] = text if code == 0 else None
    probe = ("import json,sys,bean_api,importlib.metadata as m;"
             "v=lambda n:(m.version(n) if any(d.metadata['Name'].lower()==n for d in m.distributions()) else None);"
             "print(json.dumps({'python':sys.version.split()[0],'application_importable':True,"
             "'packages':{n:v(n) for n in %r}}))")
    code, text = out([BACKEND_PY, "-c", probe % (["dr-bean-backend", "fastapi", "uvicorn", "pydantic", "deepagents",
                                                   "langchain", "langchain-google-genai", "google-genai"],)])
    facts["backend"] = json.loads(text.splitlines()[-1]) if code == 0 else None
    code, text = out([ENGINE_PY, "-m", "counterdex", "capabilities"], env={"PATH": os.environ.get("PATH", "")})
    engine = None
    if code == 0:
        try:
            caps = json.loads(text)
            engine = {"python": caps["runtime"]["version"], "runtime_qualified": caps["runtime"]["qualified"],
                      "counterdex": caps["adapter"]["version"],
                      "native_replay_supported": caps["capabilities"]["native_suggestion_replay"]["supported"],
                      "checked_pair_supported": caps["capabilities"]["checked_fixed_pair_separation"]["supported"],
                      "browser_replay_supported": caps["capabilities"]["browser_suggestion_replay"]["supported"]}
        except (ValueError, KeyError):
            engine = None
    facts["engine"] = engine
    facts["auth_file_present"] = os.path.isfile(os.path.join(VAR, "auth.json"))  # presence only; never read
    facts["store_dir"] = VAR
    facts["store_writable"] = os.access(VAR if os.path.isdir(VAR) else os.path.dirname(VAR), os.W_OK)
    try:
        facts["store_free_mb"] = shutil.disk_usage(VAR if os.path.isdir(VAR) else os.path.dirname(VAR)).free // 2**20
    except OSError:
        facts["store_free_mb"] = None
    facts["database_present"] = os.path.isfile(os.path.join(VAR, "bean.sqlite3"))
    return facts


def service_facts() -> dict:
    facts = {name: ({"pid": rec["pid"]} if (rec := owned(name)) else None) for name in SERVICES}
    report = {"owned_processes": facts, "api_ready": False, "web_ready": False, "worker_observed_by_api": None,
              "worker_ready": facts["worker"] is not None, "capabilities": None}
    try:
        status, body = http_json(f"http://{HOST}:{API_PORT}/healthz")
        report["api_ready"] = status == 200 and (body or {}).get("service") == "dr-bean"
        report["worker_observed_by_api"] = ((body or {}).get("worker") or {}).get("state")
        report["capabilities"] = http_json(f"http://{HOST}:{API_PORT}/api/bean/v1/capabilities")[1]
    except (urllib.error.URLError, OSError, ValueError):
        pass
    try:
        report["web_ready"] = http_json(f"http://{HOST}:{WEB_PORT}/")[0] == 200
    except (urllib.error.URLError, OSError, ValueError):
        pass
    return report


def summarize(static: dict, service: dict | None) -> tuple[list[tuple[str, str, str]], bool]:
    """Rows of (state, fact, detail) and whether the prerequisites for `start` hold."""
    rows, ok = [], True

    def row(good, fact, detail, required=True):
        nonlocal ok
        rows.append(("ok" if good else ("MISSING" if required else "note"), fact, detail))
        ok = ok and (good or not required)

    row(True, "platform", f"{static['os']} {static['os_release']} {static['arch']}")
    row(bool(static["uv"]), "uv", static["uv"] or "not found. Install uv (https://docs.astral.sh/uv/), then rerun setup.")
    row(bool(static["node"]) and int(static["node"].lstrip("v").split(".")[0]) >= 20, "node",
        static["node"] or "not found. Install Node 20 or newer for the web workspace.")
    backend = static["backend"]
    backend_ok = bool(backend) and backend["python"].startswith(("3.12.", "3.13.")) \
        and backend.get("application_importable") is True and bool(backend["packages"].get("dr-bean-backend"))
    row(backend_ok, "backend runtime (.venv)",
        (f"Python {backend['python']}; " + ", ".join(f"{k} {v}" for k, v in backend["packages"].items() if v))
        if backend else "not installed. Run scripts/dev/setup.sh")
    engine = static["engine"]
    row(bool(engine) and engine["runtime_qualified"], "engine runtime (.venv-engine)",
        f"CPython {engine['python']}, counterdex {engine['counterdex']}, qualified runtime: {engine['runtime_qualified']}"
        if engine else "not installed. Run scripts/dev/setup.sh (needs CPython 3.11; uv can install it)")
    row(bool(engine) and engine["native_replay_supported"], "native replay (engine CLI)",
        "supported by the installed engine" if engine else "unknown: engine not installed")
    row(False, "browser replay", "unsupported: no browser runtime is qualified", required=False)
    row(static["auth_file_present"], "local auth file", "var/auth.json present (private; not read here)"
        if static["auth_file_present"] else "missing. Run scripts/dev/setup.sh")
    free = static.get("store_free_mb")
    row(static.get("store_writable", True) and (free is None or free >= 64), "storage",
        f"{static.get('store_dir', 'var')} writable, {free} MiB free; database "
        f"{'present' if static.get('database_present') else 'not created yet'}"
        if static.get("store_writable", True) else f"{static.get('store_dir')} is not writable")
    live = live_config()
    row(True, "AI mode", "controlled placeholder only. Provider credentials from your shell are removed from every "
        "launched process; no model provider is contacted." if live["state"] != "configured" else
        "live opt-in: the key from the opt-in file goes to the API and worker only; the web server, "
        "scientific engine and document workers never receive it.")
    row(live["state"] != "invalid", "Gemini opt-in file", live["detail"], required=False)
    row(True, "Gemini live check", live_check_record())
    if service is None:
        return rows, ok
    caps = service["capabilities"] or {}
    science, gemini = caps.get("science") or {}, caps.get("gemini") or {}
    run = lambda good, fact, detail: rows.append(("ok" if good else "no", fact, detail))  # noqa: E731
    run(service["api_ready"], "API ready", f"http://{HOST}:{API_PORT}" if service["api_ready"] else "not answering /healthz")
    seen = service.get("worker_observed_by_api")
    run(service["worker_ready"] and seen in (None, "observed", "stale_or_busy"), "worker ready",
        (f"owned worker process alive; API reports worker {seen}" if seen else "owned worker process alive")
        if service["worker_ready"] else "no worker started by this launcher")
    run(service["web_ready"], "web ready", f"http://{HOST}:{WEB_PORT}" if service["web_ready"] else "not answering")
    if caps:
        run(bool(science.get("implemented")), "scientific adapter available in the API",
            f"yes ({science.get('adapter') or science.get('name') or 'adapter'})" if science.get("implemented")
            else f"no ({science.get('reason')})")
        run(bool(science.get("verified_in_environment")), "scientific adapter qualified",
            "yes" if science.get("verified_in_environment") else "no")
        run(bool(science.get("native_replay")), "native replay through the API",
            "yes" if science.get("native_replay") else "no (engine CLI replay is separate, see above)")
        run(bool(science.get("baseline_discovery")), "baseline discovery through the API",
            "yes" if science.get("baseline_discovery") else f"no ({science.get('reason')})")
        live = bool(gemini.get("configured")) or bool(gemini.get("account_gate_passed")) \
            or bool(gemini.get("dispatch_enabled"))
        opted = live_config()["state"] == "configured"
        if live and not opted:
            rows.append(("ALERT", "Gemini live", "the API reports a configured provider but no live opt-in was given; "
                         "stop it and start with scripts/dev/start.sh"))
            ok = False
        elif opted:
            rows.append(("ok", "Gemini live", "opted in; API reports dispatch "
                         f"{'enabled' if gemini.get('dispatch_enabled') else 'still disabled by the server'}; "
                         f"live check: {live_check_record()}"))
        else:
            rows.append(("ok", "Gemini live", "disabled, not tested"
                         + (f" (API reports ai_mode {caps['ai_mode']})" if caps.get("ai_mode") else "")))
    return rows, ok


def print_rows(rows):
    width = max(len(fact) for _, fact, _ in rows)
    for state, fact, detail in rows:
        print(f"  {state:<8}{fact:<{width + 2}}{detail}")


# ---------------------------------------------------------------- commands
def cmd_setup(_args) -> int:
    if not shutil.which("uv"):
        print("uv is required and was not found. Install it from https://docs.astral.sh/uv/ and rerun.\n"
              "Nothing was changed.")
        return 1
    steps = [
        ("backend runtime: uv sync --locked", ["uv", "sync", "--locked"]),
        ("engine runtime: CPython 3.11 virtual environment",
         ["uv", "venv", "--python", "3.11", "--allow-existing", ENGINE_VENV]),
        ("engine package: counterdex (no dependencies)",
         ["uv", "pip", "install", "--python", ENGINE_PY, "--no-deps", "--reinstall", ENGINE_SRC]),
    ]
    for label, command in steps:
        print(f"== {label}")
        code, text = out(command, timeout=900)
        if code != 0:
            print(text[-2000:])
            print(f"\nsetup stopped at: {label}. Nothing in var/ was changed. Fix the message above and rerun.")
            return 1
    print("== local auth (existing file is preserved)")
    code, text = out([BACKEND_PY, "-m", "bean_api.bootstrap"], env=child_env())
    print("   " + text.replace("\n", "\n   "))
    if code != 0:
        return 1
    os.makedirs(RUN, exist_ok=True)
    print()
    return cmd_doctor(argparse.Namespace(json=False))


def cmd_doctor(args) -> int:
    static = static_facts()
    running = any(owned(name) for name in SERVICES) or port_in_use(API_PORT)
    service = service_facts() if running else None
    rows, ok = summarize(static, service)
    if args.json:
        print(json.dumps({"ok": ok, "ai_mode": AI_MODE, "gemini_live": "disabled, not tested",
                          "static": static, "service": service}, indent=2))
    else:
        print("Dr. Bean doctor")
        print_rows(rows)
        if service is None:
            print("  (services are not running; start them with scripts/dev/start.sh for live service facts)")
        print("\nready to start." if ok else "\nNOT ready: see MISSING/ALERT rows above.")
    return 0 if ok else 1


def cmd_start(_args) -> int:
    static = static_facts()
    rows, ok = summarize(static, None)
    if not ok:
        print_rows(rows)
        print("\nCannot start: run scripts/dev/setup.sh first.")
        return 1
    already = [name for name in SERVICES if owned(name)]
    if already:
        print(f"Already running (started by this launcher): {', '.join(already)}. "
              "Use scripts/dev/stop.sh first, or `launcher.py status`.")
        return 1
    busy = [port for port in (API_PORT, WEB_PORT) if port_in_use(port)]
    if busy:
        print(f"Port(s) {busy} on {HOST} are in use by a process this launcher did not start. "
              "Nothing was started and nothing was killed. Free the port and retry.")
        return 1
    env = child_env()
    provider_env = {**env, **live_config()["env"]}  # identical to env unless explicitly opted in
    try:
        spawn("api", [BACKEND_PY, "-m", "uvicorn", "bean_api.main:create_app", "--factory", "--host", HOST,
                      "--port", str(API_PORT), "--no-access-log"], provider_env)
        spawn("worker", [BACKEND_PY, "-m", "bean_api.worker"], provider_env)
        spawn("web", ["node", os.path.join("apps", "web", "serve.mjs"), str(WEB_PORT)], env)
    except (OSError, KeyboardInterrupt) as error:
        for name in reversed(SERVICES):
            stop_one(name)
        print(f"Start interrupted ({type(error).__name__}); started services were stopped. See logs in {RUN}.")
        return 1
    deadline = time.monotonic() + 30
    service = service_facts()
    while time.monotonic() < deadline:
        service = service_facts()
        dead = [name for name in SERVICES if not owned(name)]
        if dead or (service["api_ready"] and service["web_ready"] and service["worker_ready"]):
            break
        time.sleep(0.5)
    dead = [name for name in SERVICES if not owned(name)]
    if dead or not (service["api_ready"] and service["web_ready"]):
        for name in dead or SERVICES:
            print(f"--- last lines of var/run/{name}.log ---\n{log_tail(name)}")
        for name in SERVICES:
            stop_one(name)
        print("Start failed; everything this launcher started was stopped. See the log lines above.")
        if "worker" in dead:
            print("If the worker says another worker holds the lock, an older worker is still running on this "
                  "database. Stop it; then `python3 scripts/dev/launcher.py recover`.")
        return 1
    rows, _ = summarize(static, service)
    print("Dr. Bean is running (loopback only)")
    print_rows(rows)
    print(f"\n  open      http://{HOST}:{WEB_PORT}\n  API docs  http://{HOST}:{API_PORT}/docs"
          f"\n  token     private file var/auth.json (read it locally; never paste it into a URL or chat)"
          f"\n  logs      var/run/*.log\n  stop      scripts/dev/stop.sh")
    live = any(state == "ALERT" for state, _, _ in rows)
    return 1 if live else 0


def cmd_stop(_args) -> int:
    for name in ("web", "worker", "api"):
        print(f"  {name:<7}{stop_one(name)}")
    print("Data in var/ is preserved. If a run was in progress, run "
          "`python3 scripts/dev/launcher.py recover` before the next start.")
    return 0


def cmd_status(_args) -> int:
    for name in SERVICES:
        record = owned(name)
        print(f"  {name:<7}{'running, pid ' + str(record['pid']) if record else 'not running'}")
    for port in (API_PORT, WEB_PORT):
        print(f"  port {port}: {'in use' if port_in_use(port) else 'free'}")
    return 0


def cmd_recover(_args) -> int:
    if any(owned(name) for name in ("api", "worker")) or port_in_use(API_PORT):
        print("Stop the API and worker first (scripts/dev/stop.sh). Recovery must not run beside them.")
        return 1
    code, text = out([BACKEND_PY, "-m", "bean_api.worker", "--recover"], env=child_env())
    print(text or "recovery finished")
    print("Interrupted reservations are marked interrupted; nothing is rerun and no approval is reused.")
    return code


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("setup", "start", "stop", "status", "recover"):
        command = sub.add_parser(name)
        if name == "start":
            command.add_argument("--controlled-source-examples", action="store_true",
                                 help="Enable only the packaged controlled source examples; Gemini remains disabled.")
    sub.add_parser("doctor").add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if getattr(args, "controlled_source_examples", False):
        os.environ["BEAN_SOURCE_INTAKE_MODE"] = "controlled"
        os.environ["BEAN_CONTROLLED_SOURCE_MANIFEST"] = os.path.join(REPO, "scripts", "ai", "fixtures", "source-previews.v1.json")
    return {"setup": cmd_setup, "doctor": cmd_doctor, "start": cmd_start, "stop": cmd_stop,
            "status": cmd_status, "recover": cmd_recover}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
