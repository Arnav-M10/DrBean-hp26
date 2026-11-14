#!/usr/bin/env python3
"""Does the backend's scientific process boundary work for an ordinary desktop user?

Why this exists: development containers and some CI images run as root, where a
per-user process-count limit (RLIMIT_NPROC) is not enforced. A person on a laptop
is not root and already owns dozens or hundreds of processes. A guard that passes
as root can therefore refuse every scientific job for a real user.

This check runs the backend's own boundary tests (tests/test_science_boundary.py,
Owner 2's) as an unprivileged user who already owns at least 64 other processes.
It changes nothing in the product and contacts no network service.

  python3 scripts/release/user_conditions_check.py [--processes 64]

Exit 0 passed, 1 failed, 3 unrun (cannot arrange the condition here).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BACKEND_PY = os.path.join(REPO, ".venv", "bin", "python")

# Runs as the target user: hold N idle processes, then run the boundary tests.
INNER = r"""
import json, os, subprocess, sys
repo, python, wanted = sys.argv[1], sys.argv[2], int(sys.argv[3])
uid = os.getuid()
def owned():
    out = subprocess.run(["ps", "-u", str(uid), "-o", "pid="], capture_output=True, text=True).stdout
    return len(out.split())
idle = []
while owned() < wanted and len(idle) < wanted:
    idle.append(subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"]))
count = owned()
done = subprocess.run([python, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_science_boundary.py"],
                      cwd=repo, capture_output=True, text=True)
for process in idle:
    process.kill()
lines = (done.stdout + done.stderr).strip().splitlines()
print(json.dumps({"uid": uid, "processes_owned_by_user": count, "exit_code": done.returncode,
                  "summary": lines[-1] if lines else "", "failed": [l for l in lines if l.startswith("FAILED")]}))
"""


def main(argv):
    wanted = int(argv[argv.index("--processes") + 1]) if "--processes" in argv else 64
    if not os.path.isfile(BACKEND_PY):
        print(json.dumps({"status": "unrun", "reason": "backend runtime missing: run scripts/dev/setup.sh"}))
        return 3
    home = tempfile.mkdtemp(prefix="drbean-user-")
    os.chmod(home, 0o777)
    env = {"PATH": os.environ.get("PATH", ""), "HOME": home, "TMPDIR": home, "PYTHONDONTWRITEBYTECODE": "1",
           "BEAN_COUNTERDEX_PYTHON": os.path.join(REPO, ".venv-engine", "bin", "python")}
    command = [sys.executable, "-c", INNER, REPO, BACKEND_PY, str(wanted)]
    try:
        if os.getuid() == 0:
            if not shutil.which("setpriv"):
                print(json.dumps({"status": "unrun", "reason": "running as root and setpriv is not available to "
                                                               "drop privileges; run this as an ordinary user"}))
                return 3
            drop = ["setpriv", "--reuid=65534", "--regid=65534", "--clear-groups"]
            readable = subprocess.run([*drop, "test", "-x", BACKEND_PY], capture_output=True).returncode == 0
            if not readable:
                print(json.dumps({"status": "unrun", "reason": "the checkout is not readable by an unprivileged "
                                                               "user here; run this as an ordinary user"}))
                return 3
            command = [*drop, *command]
        done = subprocess.run(command, capture_output=True, text=True, env=env, timeout=300)
    finally:
        shutil.rmtree(home, ignore_errors=True)
    try:
        report = json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        print(json.dumps({"status": "unrun", "reason": "could not run the inner check",
                          "detail": (done.stdout + done.stderr)[-400:]}))
        return 3
    report["status"] = "passed" if report["exit_code"] == 0 else "failed"
    report["condition"] = f"unprivileged user owning at least {wanted} processes"
    print(json.dumps(report))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
