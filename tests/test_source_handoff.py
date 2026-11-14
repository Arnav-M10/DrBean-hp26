"""Public source handoff controls; proposed values grant no execution authority."""
from copy import deepcopy
import sqlite3

import pytest

from bean_api.main import PREFIX
from bean_api.source_materialization import reviewed_input_values
from test_controlled_intake import controlled_client as controlled_client, controlled_request, upload, workspace
from test_counterdex_adapter import reviewed_history
from test_scientific_http import post


def proposal_for(client, scope, **context):
    source = upload(client, scope)
    return post(client, f"/workspaces/{scope}/intake-proposals", controlled_request(source, **context), "prepare")


def review_body(proposal):
    return {"expected_proposal_digest": proposal["digest"], "reviewed_fields": [
        {"field_path": f["field_path"], "value": f["candidate_exact"] or f["original_value"],
         "origin": "confirmed_transcription"} for f in proposal["body"]["fields"]]}


def materialization_body(proposal, review):
    history = reviewed_history()
    dataset = deepcopy(history["dataset"]["body"])
    problem = {k: v for k, v in history["problem"]["body"].items()
               if k not in {"schema_version", "dataset_id", "dataset_digest"}}
    accepted = {f["field_path"]: f["normalized_value"] for f in review["body"]["reviewed_fields"]}
    # The fixture's printed target and measurements are the accepted inputs.
    for index, row in enumerate(dataset["rows"]):
        for field in ("time", "concentration", "hard_allowance"):
            row[field] = accepted.get(f"rows[{index}].{field}", row[field])
    for side in ("lower", "upper"):
        problem["target"][side] = accepted.get(f"target.{side}", problem["target"][side])
    return {"expected_review_digest": review["digest"], "dataset": dataset, "problem": problem,
            "human_assumptions": {p: "Explicit reviewed synthetic assumption." for p in reviewed_input_values(dataset, problem)
                                  if p not in accepted and not p.endswith(".notes")}}


def mutate_context(client, scope, kind):
    dataset = post(client, f"/workspaces/{scope}/datasets", reviewed_history()["dataset"]["body"], "dataset")
    if kind == "problem":
        problem = {**reviewed_history()["problem"]["body"], "dataset_id": dataset["id"], "dataset_digest": dataset["digest"]}
        post(client, f"/workspaces/{scope}/problems", problem, "problem")
    return dataset


@pytest.mark.parametrize("stage", ["review", "materialize"])
def test_initial_context_change_requires_new_source_review(controlled_client, stage):
    client = controlled_client
    scope = workspace(client)
    proposal = proposal_for(client, scope)
    path = f"/workspaces/{scope}/intake-proposals/{proposal['id']}/review"
    body = review_body(proposal)
    if stage == "materialize":
        review = post(client, path, body, "review")
        body = materialization_body(proposal, review)
        path = f"/workspaces/{scope}/intake-reviews/{review['id']}/materialize"
    prior = mutate_context(client, scope, "problem")
    response = client.post(PREFIX + path, json=body, headers={"Idempotency-Key": "stale"})
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "stale_revision"
    assert client.get(PREFIX + f"/workspaces/{scope}").json()["current_dataset_id"] == prior["id"]


def test_dataset_context_does_not_authorize_changed_problem(controlled_client):
    client = controlled_client
    scope = workspace(client)
    prior = mutate_context(client, scope, "problem")
    proposal = proposal_for(client, scope, current_revision_id=prior["id"])
    path = f"/workspaces/{scope}/intake-proposals/{proposal['id']}/review"
    review = post(client, path, review_body(proposal), "review")
    current = client.get(PREFIX + f"/workspaces/{scope}").json()
    problem = client.get(PREFIX + f"/records/{current['current_problem_id']}").json()
    changed = deepcopy(problem["body"])
    changed["target"]["upper"] = "1/4"
    post(client, f"/workspaces/{scope}/problems", changed, "changed-problem")
    response = client.post(PREFIX + f"/workspaces/{scope}/intake-reviews/{review['id']}/materialize",
        json=materialization_body(proposal, review), headers={"Idempotency-Key": "stale"})
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "stale_revision"
    # Completed identical review retries remain retrievable after context changes.
    assert post(client, path, review_body(proposal), "review") == review


def test_stale_digests_and_changed_idempotency_payload_cannot_accept(controlled_client):
    client = controlled_client
    scope = workspace(client)
    proposal = proposal_for(client, scope)
    path = f"/workspaces/{scope}/intake-proposals/{proposal['id']}/review"
    body = review_body(proposal)
    response = client.post(PREFIX + path, json={**body, "expected_proposal_digest": "0" * 64},
        headers={"Idempotency-Key": "bad-review"})
    assert response.status_code == 409 and response.json()["code"] == "stale_proposal"
    review = post(client, path, body, "review")
    changed = deepcopy(body)
    changed["reviewed_fields"][0].update(value="99/20", origin="corrected_transcription", correction_reason="Reviewed correction.")
    response = client.post(PREFIX + path, json=changed, headers={"Idempotency-Key": "review"})
    assert response.status_code == 409 and response.json()["code"] == "idempotency_conflict"
    body = materialization_body(proposal, review)
    path = f"/workspaces/{scope}/intake-reviews/{review['id']}/materialize"
    response = client.post(PREFIX + path, json={**body, "expected_review_digest": "0" * 64},
        headers={"Idempotency-Key": "bad-materialize"})
    assert response.status_code == 409 and response.json()["code"] == "stale_review"
    result = post(client, path, body, "materialize")
    assert post(client, path, body, "retry-materialize") == result
    store = client.app.state.workflow.store
    with pytest.raises(sqlite3.IntegrityError), store.transaction() as conn:
        conn.execute("UPDATE entities SET body='{}' WHERE id=?", (review["id"],))
    assert client.get(PREFIX + f"/records/{review['id']}").json() == review


def test_restart_never_reexecutes_an_interrupted_controlled_attempt(controlled_client, monkeypatch):
    client = controlled_client
    scope = workspace(client)
    source = upload(client, scope)
    workflow = client.app.state.workflow
    request = controlled_request(source)
    from bean_api.contracts import ControlledIntakeRequest
    workflow.begin_operation("alice", scope, "intake", "interrupted", ControlledIntakeRequest.model_validate(request).model_dump())
    assert workflow.recover_interrupted()["operations"] == 1
    def forbidden(**kwargs):
        pytest.fail("An interrupted operation cannot rerun proposal preparation")
    monkeypatch.setattr(client.app.state.controlled_source_proposer, "prepare", forbidden)
    response = client.post(PREFIX + f"/workspaces/{scope}/intake-proposals", json=request,
        headers={"Idempotency-Key": "interrupted"})
    assert response.status_code == 409 and response.json()["code"] in {"operation_interrupted", "operation_pending"}
    assert client.get(PREFIX + f"/workspaces/{scope}/records?kind=intake_proposal").json() == []


def test_missing_historical_controlled_context_requires_new_preparation(controlled_client):
    client = controlled_client
    scope = workspace(client)
    proposal = proposal_for(client, scope)
    old_body = deepcopy(proposal["body"])
    del old_body["input_context"]
    # This constructs a historical versioned record, not an accepted input or result.
    historical = client.app.state.workflow.create_record("alice", scope, "intake_proposal", old_body, "historical")
    assert client.get(PREFIX + f"/records/{historical['id']}").json() == historical
    response = client.post(PREFIX + f"/workspaces/{scope}/intake-proposals/{historical['id']}/review",
        json=review_body(historical), headers={"Idempotency-Key": "old-review"})
    assert response.status_code == 409 and response.json()["code"] == "stale_revision"


def test_source_integrity_is_required_at_review_and_other_workspace_cannot_accept(controlled_client):
    client = controlled_client
    scope = workspace(client)
    proposal = proposal_for(client, scope)
    other = post(client, "/workspaces", {"name": "Other workspace"}, "other")["id"]
    path = f"/workspaces/{other}/intake-proposals/{proposal['id']}/review"
    response = client.post(PREFIX + path, json=review_body(proposal), headers={"Idempotency-Key": "other-review"})
    assert response.status_code == 404
    from pathlib import Path
    source = client.app.state.workflow.get("alice", proposal["body"]["source_asset_id"], "source_asset")
    (Path(client.app.state.settings.blob_dir) / source["body"]["blob_key"]).write_bytes(b"changed source")
    response = client.post(PREFIX + f"/workspaces/{scope}/intake-proposals/{proposal['id']}/review",
        json=review_body(proposal), headers={"Idempotency-Key": "corrupt-review"})
    assert response.status_code == 409 and response.json()["code"] == "source_integrity_failed"
    assert client.get(PREFIX + f"/workspaces/{scope}/records?kind=intake_review").json() == []


def test_blocking_source_diagnostics_require_explicit_human_resolution(controlled_client):
    client = controlled_client
    scope = workspace(client)
    source = upload(client, scope, case="ambiguous_decimal")
    proposal = post(client, f"/workspaces/{scope}/intake-proposals", controlled_request(source), "ambiguous")
    path = PREFIX + f"/workspaces/{scope}/intake-proposals/{proposal['id']}/review"
    body = review_body(proposal)
    response = client.post(path, json=body, headers={"Idempotency-Key": "unresolved"})
    assert response.status_code == 422 and response.json()["code"] == "unresolved_clarification"
    blocking = [d for d in proposal["body"]["diagnostics"] if d["blocking"]]
    assert blocking
    body["resolved_diagnostics"] = [f"{d['code']}:{d['field_path']}" for d in blocking]
    for field in body["reviewed_fields"]:
        if any(d["field_path"] == field["field_path"] for d in blocking):
            field["value"] = "1/20"
    response = client.post(path, json=body, headers={"Idempotency-Key": "confirmed-ambiguity"})
    assert response.status_code == 422 and response.json()["code"] == "correction_reason_required"
    for field in body["reviewed_fields"]:
        if any(d["field_path"] == field["field_path"] for d in blocking):
            field.update(value="1/20", origin="corrected_transcription", correction_reason="Human inspected the original ambiguous decimal.")
    response = client.post(path, json=body, headers={"Idempotency-Key": "resolved"})
    assert response.status_code == 201, response.text
    corrected = [f for f in response.json()["body"]["reviewed_fields"] if f["origin"] == "corrected_transcription"]
    assert corrected and all(f["original_proposal"]["ambiguity"] for f in corrected)
