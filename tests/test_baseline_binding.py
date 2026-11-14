"""Publication and checked-fact boundaries using a freshly computed baseline."""
import base64
from copy import deepcopy
import hashlib
import json

import pytest

from bean_api.contracts import ScientificResult
from bean_api.worker import Worker
from bean_api.workflow import DomainError
import test_scientific_http as scientific_http
from test_scientific_http import prepare_approved_history

scientific_client = scientific_http.scientific_client


@pytest.fixture
def baseline_publication(scientific_client):
    client = scientific_client
    _, dataset, problem, plan, _, queued, _ = prepare_approved_history(client)
    worker = Worker(client.app.state.workflow, settings=client.app.state.settings)
    job = worker.workflow.mark_running("alice", queued["id"], worker.id)
    scope = {"run_id": job["id"], "scenario_id": "baseline", "workflow": {
        "plan_id": plan["id"], "approval_id": job["approval_id"],
        "operation_id": job["id"], "execution_id": job["id"]}}
    computed = worker.adapter.investigate(problem, dataset, plan["body"]["budget"], scope)
    native = computed.pop("_native_artifacts")
    projection = computed.pop("_application_projection")
    result = ScientificResult.model_validate(computed).model_dump(mode="json")
    assert worker._checked_result_allowed(result)
    result["_native_artifacts"] = native
    return worker, job, problem, dataset, result, projection


def publish(context, result=None, projection=None, *, scenario="baseline"):
    worker, job, problem, dataset, original, admitted = context
    return worker._publish_native("alice", job, deepcopy(original if result is None else result),
        problem=problem, dataset=dataset, aggregate_limit=4 * 1024 * 1024,
        application_projection=admitted if projection is None else projection, scenario_id=scenario)


def assert_unpublished(context):
    worker, job, *_ = context
    assert worker.workflow.list_records("alice", job["workspace_id"], "native_artifact") == []
    assert list(worker.artifacts.blob_dir.iterdir()) == []


def test_native_baseline_preserves_origin_bytes_and_external_anchor(baseline_publication):
    worker, job, _, _, original, _ = baseline_publication
    result = publish(baseline_publication)
    record, content = worker.artifacts.read("alice", result["artifacts"][0]["id"])
    assert content == base64.b64decode(original["_native_artifacts"][0]["content_base64"])
    assert record["body"]["origin"] == {"run_id": job["id"], "scenario_id": "baseline",
        "plan_id": job["plan_id"], "approval_id": job["approval_id"]}
    assert record["body"]["anchor"] == original["native_replay"]["anchors"]
    assert result["verification_record"]["artifact_id"] == record["id"]
    assert all(candidate["artifact_ids"] == [record["id"]] for candidate in result["candidates"])
    assert publish(baseline_publication) == result


@pytest.mark.parametrize("field,value", [
    ("run_id", "wrong-run"), ("scenario_id", "wrong-scenario"),
    ("dataset_digest", "0" * 64), ("problem_digest", "0" * 64),
    ("projection_digest", "0" * 64), ("app_request_digest", "0" * 64),
    ("design_digest", "0" * 64), ("artifact_sha256", "0" * 64),
])
def test_baseline_anchor_cannot_change_scope(baseline_publication, field, value):
    result = deepcopy(baseline_publication[4])
    result["_native_artifacts"][0]["anchor"][field] = value
    result["native_replay"]["anchors"][field] = value
    with pytest.raises(DomainError, match="anchor|identit|scope"):
        publish(baseline_publication, result)
    assert_unpublished(baseline_publication)


def test_baseline_cannot_publish_under_another_scenario(baseline_publication):
    with pytest.raises(DomainError):
        publish(baseline_publication, scenario="unapproved-scenario")
    assert_unpublished(baseline_publication)


def test_baseline_summary_must_describe_retained_search(baseline_publication):
    result = deepcopy(baseline_publication[4])
    result["baseline_search"]["attempted_count"] -= 1
    with pytest.raises(DomainError) as caught:
        publish(baseline_publication, result)
    assert caught.value.code == "binding_mismatch"
    assert_unpublished(baseline_publication)


def test_rehashed_baseline_cannot_replace_approved_workflow(baseline_publication):
    result = deepcopy(baseline_publication[4])
    native = result["_native_artifacts"][0]
    packet = json.loads(base64.b64decode(native["content_base64"]))
    scientific = json.loads(base64.b64decode(packet["scientific"]["bytes_base64"]))
    scientific["workflow"]["approval_id"] = "unrelated-approval"
    science_bytes = json.dumps(scientific, separators=(",", ":")).encode()
    packet["scientific"] = {"bytes_base64": base64.b64encode(science_bytes).decode(),
                             "sha256": hashlib.sha256(science_bytes).hexdigest()}
    content = json.dumps(packet, separators=(",", ":")).encode()
    digest = hashlib.sha256(content).hexdigest()
    native.update(content_base64=base64.b64encode(content).decode(), sha256=digest, byte_size=len(content))
    result["artifacts"][0].update(sha256=digest, byte_size=len(content))
    result["verification_record"]["artifact_sha256"] = digest
    native["anchor"]["artifact_sha256"] = digest
    result["native_replay"]["anchors"]["artifact_sha256"] = digest
    with pytest.raises(DomainError) as caught:
        publish(baseline_publication, result)
    assert caught.value.code == "binding_mismatch"
    assert_unpublished(baseline_publication)


@pytest.mark.parametrize("mutation", ["candidate", "outcome", "integrity", "projection"])
def test_checked_baseline_requires_matching_fresh_facts(baseline_publication, mutation):
    worker = baseline_publication[0]
    result = deepcopy(baseline_publication[4])
    if mutation == "candidate":
        result["candidates"][0]["parameter_vector"]["A"] = "1/1"
    elif mutation == "outcome":
        result["scientific_outcome"] = "no_counterexample_found"
    elif mutation == "integrity":
        result["native_replay"]["integrity"] = "failed"
    else:
        result["native_replay"]["anchors"]["projection_digest"] = "0" * 64
    assert worker._checked_result_allowed(result) is False
