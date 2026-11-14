"""Local worker liveness observation, separate from scientific qualification."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile


def write_status(database_path, worker_id, adapter):
    target = Path(str(Path(database_path).resolve()) + ".worker-status.json")
    body = {"worker_id": worker_id, "pid": os.getpid(), "updated_at": datetime.now(timezone.utc).isoformat(),
            "science": adapter.capabilities()}
    fd, temporary = tempfile.mkstemp(dir=target.parent, prefix=".worker-status-")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(body, stream)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_status(database_path):
    target = Path(str(Path(database_path).resolve()) + ".worker-status.json")
    try:
        body = json.loads(target.read_text())
        os.kill(body["pid"], 0)
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(body["updated_at"])).total_seconds()
        return {"state": "observed" if age < 10 else "stale_or_busy", "updated_at": body["updated_at"],
                "science": body["science"], "worker_id": body["worker_id"]}
    except (OSError, ValueError, KeyError, TypeError):
        return {"state": "not_observed", "reason": "Start the worker using the same database and runtime configuration."}
