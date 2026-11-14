"""Private, idempotent persistence for the provider-free numerical comparison.

The synchronous HTTP operation uses a fresh, bounded computation process. SQLite
locks cover reservation and publication only, never numerical work. A completed
operation retains its exact reviewed input alongside its result; recovery or a
lost acknowledgement cannot silently execute a second computation.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys
from threading import BoundedSemaphore

from ..canonical import canonical_bytes, parse_json_strict
from ..store import utc_now
from ..workflow import DomainError, Workflow, _json
from .contract import ModelComparisonRequest, ModelComparisonResult
from .compute import source_digest

RESULT_KIND = "model_comparison"
OPERATION = "model-comparison"
MAX_COMPUTE_SECONDS = 10
MAX_RESULT_BYTES = 2 * 1024 * 1024


def run_computation(request: ModelComparisonRequest) -> dict:
    """Run this checkout's implementation, with no inherited credentials.

    The child receives only the reviewed JSON request. It has a hard wall-clock
    deadline and cannot leave a continuing compute task after an HTTP timeout.
    Source is prepended explicitly so an older installed backend cannot win.
    """
    source = str(Path(__file__).resolve().parents[2])
    program = (
        f"import sys; sys.path.insert(0, {source!r}); "
        "from bean_api.model_comparison.contract import ModelComparisonRequest; "
        "from bean_api.model_comparison.compute import compute_comparison; "
        "from bean_api.canonical import canonical_bytes, parse_json_strict; "
        "request = ModelComparisonRequest.model_validate(parse_json_strict(sys.stdin.buffer.read())); "
        "sys.stdout.buffer.write(canonical_bytes(compute_comparison(request)))"
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-c", program], input=canonical_bytes(request.model_dump(mode="json")),
            capture_output=True, timeout=MAX_COMPUTE_SECONDS, check=False,
            env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"},
            cwd=str(Path(__file__).resolve().parent),
        )
    except subprocess.TimeoutExpired:
        raise DomainError("comparison_timeout", "The bounded comparison exceeded its execution deadline. "
                          "No scientific result was published.", 503) from None
    except OSError:
        raise DomainError("comparison_unavailable", "The numerical process could not be started.", 503) from None
    if completed.returncode:
        raise DomainError("comparison_execution_failed", "The numerical process did not complete. "
                          "No scientific result was published.", 503)
    try:
        result = parse_json_strict(completed.stdout, max_bytes=MAX_RESULT_BYTES)
        if not isinstance(result, dict) or result.get("schema_version") != "DB-MODEL-COMPARISON-RESULT-1":
            raise ValueError("Unexpected comparison result")
        return result
    except (TypeError, ValueError):
        raise DomainError("comparison_invalid_result", "The numerical process returned an invalid result.", 503) from None


class ModelComparisonService:
    def __init__(self, workflow: Workflow, *, runner=None):
        self.workflow = workflow
        self.runner = runner or run_computation
        self._slots = BoundedSemaphore(2)

    def compare(self, actor: str, workspace_id: str, request: ModelComparisonRequest, key: str) -> dict:
        body = request.model_dump(mode="json")
        reservation = self.workflow.begin_operation(actor, workspace_id, OPERATION, key, body)
        if not reservation["created_new"]:
            if reservation["state"] == "completed":
                return self.get(actor, workspace_id, reservation["response"]["comparison_id"])
            raise DomainError("operation_pending" if reservation["state"] == "reserved" else "operation_interrupted",
                              "The original operation must be reconciled; no duplicate computation was started.", 409)
        if not self._slots.acquire(blocking=False):
            self.workflow.fail_operation(actor, workspace_id, OPERATION, key, "comparison_busy")
            raise DomainError("comparison_busy", "The comparison execution slots are occupied. "
                              "No computation was started; a new explicit operation is required.", 503)
        try:
            result = self.runner(request)
            # Also validate the persistence format for injected/embedded runners.
            ModelComparisonResult.model_validate(result)
            canonical_bytes(result)
            if (result.get("schema_version") != "DB-MODEL-COMPARISON-RESULT-1"
                    or result.get("request") != body
                    or result.get("source_digest") != source_digest()
                    or result.get("input_digest") != hashlib.sha256(canonical_bytes(body)).hexdigest()):
                raise DomainError("comparison_invalid_result", "The numerical result is not bound to the reviewed request and current implementation.", 503)
            return self._publish(actor, workspace_id, key, body, result)
        except DomainError as exc:
            self.workflow.fail_operation(actor, workspace_id, OPERATION, key, exc.code)
            raise
        except Exception:
            self.workflow.fail_operation(actor, workspace_id, OPERATION, key, "comparison_execution_failed")
            raise DomainError("comparison_execution_failed", "The comparison could not be completed. "
                              "No scientific result was published.", 503) from None
        finally:
            self._slots.release()

    def _publish(self, actor: str, workspace_id: str, key: str, request: dict, result: dict) -> dict:
        with self.workflow.store.transaction() as conn:
            self.workflow.authorize(actor, workspace_id, conn)
            operation = self.workflow._operation(conn, actor, workspace_id, OPERATION, key, request)
            if operation is None or operation["state"] != "reserved":
                raise DomainError("operation_interrupted", "Execution authority changed before publication. "
                                  "No scientific result was published.", 409)
            record = self.workflow._insert(conn, actor, workspace_id, RESULT_KIND, result)
            conn.execute("UPDATE operations SET state='completed',response=?,finished_at=? WHERE id=?",
                         (_json({"comparison_id": record["id"]}), utc_now(), operation["id"]))
            return record

    def get(self, actor: str, workspace_id: str, comparison_id: str) -> dict:
        with self.workflow.store.read() as conn:
            self.workflow.authorize(actor, workspace_id, conn)
            record = self.workflow._get(conn, actor, comparison_id, RESULT_KIND)
            self.workflow._same_workspace(workspace_id, record)
            return record

    def list(self, actor: str, workspace_id: str) -> list[dict]:
        return self.workflow.list_records(actor, workspace_id, RESULT_KIND)

    def download(self, actor: str, workspace_id: str, comparison_id: str) -> tuple[bytes, str]:
        result = self.get(actor, workspace_id, comparison_id)
        data = canonical_bytes({"schema_version": "DB-MODEL-COMPARISON-EXPORT-1", "result": result})
        return data, hashlib.sha256(data).hexdigest()


def comparison_capabilities() -> dict:
    return {"available": True, "contract_version": "DB-MODEL-COMPARISON-1",
            "result_contract_version": "DB-MODEL-COMPARISON-RESULT-1",
            "execution_mode": "numerical_offline", "provider_calls": 0,
            "verification": "not_performed", "data_origin": "synthetic",
            "max_compute_seconds": MAX_COMPUTE_SECONDS, "max_concurrent_per_api_process": 2,
            "review_required": True, "explicit_compute_required": True,
            "persistence": "private_workspace_immutable_records",
            "retry_policy": "same_key_returns_completed_result_never_reexecutes",
            "instrument": "idealized_normal_energy_planar_collector"}
