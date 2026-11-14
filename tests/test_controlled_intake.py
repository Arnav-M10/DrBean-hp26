"""Controlled sources use ordinary review without hosted inference or spending."""
from copy import deepcopy
from pathlib import Path
import json
import socket

from fastapi.testclient import TestClient
import pytest

from bean_api.config import Settings
from bean_api.contracts import ControlledIntakeProposalRecordBody, IntakeProposalRecordBody
from bean_api.main import PREFIX, create_app
from bean_api.source_materialization import reviewed_input_values
from test_counterdex_adapter import reviewed_history
from test_intake import png
from test_scientific_http import post

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "scripts/ai/fixtures/source-previews.v1.json"


@pytest.fixture
def controlled_client(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Controlled intake must not construct or dispatch a hosted request")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr("bean_api.providers.GeminiProvider.generate", forbidden)
    settings = Settings(database_path=str(tmp_path / "db.sqlite"), blob_dir=str(tmp_path / "sources"),
        artifact_dir=str(tmp_path / "artifacts"), auth_tokens={"alice": "a" * 40, "bob": "b" * 40},
        science_adapter="unavailable", source_intake_mode="controlled", controlled_source_manifest_path=str(MANIFEST))
    with TestClient(create_app(settings)) as client:
        client.headers["Authorization"] = "Bearer " + "a" * 40
        yield client


def upload(client, workspace, *, case="clean", raw=None, origin="synthetic", key="upload"):
    raw = raw if raw is not None else (ROOT / "fixtures/intake" / f"{case}.png").read_bytes()
    response = client.post(PREFIX + f"/workspaces/{workspace}/source-assets?origin={origin}&retention=retain",
        content=raw, headers={"Content-Type": "image/png", "Idempotency-Key": key})
    assert response.status_code == 201, response.text
    return response.json()


def controlled_request(source, **updates):
    return {"execution_mode": "controlled", "source_id": source["id"],
            "expected_source_digest": source["body"]["sha256"], **updates}


def workspace(client):
    return post(client, "/workspaces", {"name": "Controlled source review"}, "workspace")["id"]


def test_controlled_source_is_reviewed_corrected_and_materialized_once(controlled_client):
    client = controlled_client
    scope = workspace(client)
    source = upload(client, scope)
    proposal = post(client, f"/workspaces/{scope}/intake-proposals", controlled_request(source), "prepare")
    parsed = ControlledIntakeProposalRecordBody.model_validate(proposal["body"])
    assert parsed.status == "controlled_example" and parsed.authorship == "controlled_fixture"
    assert all(field.method == "controlled_fixture" for field in parsed.fields)
    assert "provider_attempt_id" not in proposal["body"]
    assert str(MANIFEST) not in json.dumps(client.get(PREFIX + "/capabilities").json())
    attempt = client.get(PREFIX + f"/records/{parsed.provenance.local_attempt_id}").json()
    assert attempt["kind"] == "controlled_attempt" and "consent_id" not in attempt["body"]
    assert attempt["body"]["external_provider_calls"] == attempt["body"]["actual_model_tokens"] == 0
    assert post(client, f"/workspaces/{scope}/intake-proposals", controlled_request(source), "prepare") == proposal
    assert len(client.get(PREFIX + f"/workspaces/{scope}/records?kind=controlled_attempt").json()) == 1
    fields = []
    for field in proposal["body"]["fields"]:
        corrected = field["field_path"] == "rows[0].concentration"
        fields.append({"field_path": field["field_path"], "value": "97/20" if corrected else field["candidate_exact"],
            "origin": "corrected_transcription" if corrected else "confirmed_transcription",
            **({"correction_reason": "Explicit synthetic correction after inspecting the source."} if corrected else {})})
    review = post(client, f"/workspaces/{scope}/intake-proposals/{proposal['id']}/review", {
        "expected_proposal_digest": proposal["digest"], "reviewed_fields": fields}, "review")
    original = next(field for field in review["body"]["reviewed_fields"] if field["field_path"] == "rows[0].concentration")
    assert original["normalized_value"] == "97/20" and original["original_proposal"]["candidate_exact"] == "24/5"
    history = reviewed_history()
    dataset = deepcopy(history["dataset"]["body"])
    dataset["rows"][0]["concentration"] = "97/20"
    problem = {key: value for key, value in history["problem"]["body"].items()
               if key not in {"schema_version", "dataset_id", "dataset_digest"}}
    reviewed_paths = {field["field_path"] for field in fields}
    assumptions = {path: "Explicit synthetic assumption reviewed separately from the fixture."
        for path in reviewed_input_values(dataset, problem) if path not in reviewed_paths and not path.endswith(".notes")}
    body = {"expected_review_digest": review["digest"], "dataset": dataset, "problem": problem,
            "human_assumptions": assumptions}
    result = post(client, f"/workspaces/{scope}/intake-reviews/{review['id']}/materialize", body, "materialize")
    assert result["dataset"]["body"]["rows"][0]["concentration"] == "97/20"
    assert result["dataset"]["body"]["rows"][0]["source_asset_id"] == source["id"]
    assert result["dataset"]["body"]["rows"][0]["original_values"]["concentration"] == "4.80"
    assert result["materialization"]["body"]["review_id"] == review["id"]
    assert result["problem"]["body"]["dataset_digest"] == result["dataset"]["digest"]
    assert post(client, f"/workspaces/{scope}/intake-reviews/{review['id']}/materialize", body, "retry") == result
    unchanged = client.get(PREFIX + f"/records/{proposal['id']}").json()
    assert unchanged == proposal
    assert client.get(PREFIX + f"/workspaces/{scope}/provider-attempts").json() == []
    with client.app.state.workflow.store.read() as conn:
        assert conn.execute("SELECT count(*) FROM approvals").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


@pytest.mark.parametrize("case", [None, "unreadable", "unsupported_model"])
def test_unavailable_controlled_source_preserves_manual_input_and_cannot_be_reviewed(controlled_client, case):
    client = controlled_client
    scope = workspace(client)
    prior = post(client, f"/workspaces/{scope}/datasets", reviewed_history()["dataset"]["body"], "prior")
    source = upload(client, scope, case=case or "clean", raw=png() if case is None else None)
    proposal = post(client, f"/workspaces/{scope}/intake-proposals", controlled_request(source), "prepare")
    assert proposal["body"]["status"] == "unavailable"
    assert proposal["body"]["fields"] == [] and proposal["body"]["next_action"] == "manual_review"
    response = client.post(PREFIX + f"/workspaces/{scope}/intake-proposals/{proposal['id']}/review", json={
        "expected_proposal_digest": proposal["digest"], "reviewed_fields": [{
            "field_path": "rows[0].time", "value": "1/1", "origin": "human_assumption", "correction_reason": "Manual entry."}]},
        headers={"Idempotency-Key": "review"})
    assert response.status_code == 409 and response.json()["code"] == "intake_unavailable"
    assert client.get(PREFIX + f"/records/{prior['id']}").json() == prior
    assert client.get(PREFIX + f"/workspaces/{scope}").json()["current_dataset_id"] == prior["id"]
    assert client.get(PREFIX + f"/workspaces/{scope}/provider-attempts").json() == []


@pytest.mark.parametrize("failure", ["digest", "workspace", "revision", "corrupt_source", "public_origin"])
def test_source_and_revision_failures_precede_local_attempts(controlled_client, failure):
    client = controlled_client
    scope = workspace(client)
    source = upload(client, scope, origin="public" if failure == "public_origin" else "synthetic")
    body = controlled_request(source)
    expected = (422, "source_binding_mismatch")
    target_scope = scope
    if failure == "digest":
        body["expected_source_digest"] = "0" * 64
    elif failure == "workspace":
        target_scope = post(client, "/workspaces", {"name": "Other workspace"}, "other")["id"]
        expected = (404, "not_found")
    elif failure == "revision":
        first = post(client, f"/workspaces/{scope}/datasets", reviewed_history()["dataset"]["body"], "first")
        post(client, f"/workspaces/{scope}/datasets", {
            **first["body"], "parent_id": first["id"], "change_reason": "A separately reviewed new revision."}, "second")
        body["current_revision_id"] = first["id"]
        expected = (409, "stale_revision")
    elif failure == "corrupt_source":
        private = client.app.state.workflow.get("alice", source["id"], "source_asset")
        (Path(client.app.state.settings.blob_dir) / private["body"]["blob_key"]).write_bytes(b"corrupt")
        expected = (409, "source_integrity_failed")
    elif failure == "public_origin":
        expected = (422, "controlled_source_origin_mismatch")
    response = client.post(PREFIX + f"/workspaces/{target_scope}/intake-proposals", json=body,
                           headers={"Idempotency-Key": "invalid-prepare"})
    assert (response.status_code, response.json()["code"]) == expected
    assert client.get(PREFIX + f"/workspaces/{scope}/records?kind=controlled_attempt").json() == []
    assert client.get(PREFIX + f"/workspaces/{scope}/provider-attempts").json() == []


@pytest.mark.parametrize("extra", [{"consent": {}}, {"client_factory": "live"}, {"manifest_path": "other.json"}, {"execution_mode": "live"}])
def test_request_cannot_change_transport_or_deployment_mode(controlled_client, extra):
    client = controlled_client
    scope = workspace(client)
    source = upload(client, scope)
    response = client.post(PREFIX + f"/workspaces/{scope}/intake-proposals", json={**controlled_request(source), **extra},
                           headers={"Idempotency-Key": "invalid-body"})
    assert response.status_code == 422
    assert client.get(PREFIX + f"/workspaces/{scope}/records?kind=controlled_attempt").json() == []


def test_legacy_request_cannot_select_a_controlled_mode_with_extra_fields(controlled_client):
    client = controlled_client
    scope = workspace(client)
    source = upload(client, scope)
    response = client.post(PREFIX + f"/workspaces/{scope}/intake-proposals", json={
        "source_id": source["id"], "execution_mode": "controlled", "consent": {
            "provider": "gemini", "model": "unqualified", "source_asset_ids": [source["id"]],
            "include_notes": True, "include_existing_values": True, "accepted": True}},
        headers={"Idempotency-Key": "ambiguous-mode"})
    assert response.status_code == 422
    assert client.get(PREFIX + f"/workspaces/{scope}/records?kind=controlled_attempt").json() == []


@pytest.mark.parametrize("failure", ["source_binding", "grounding", "unavailable_fields"])
def test_invalid_controlled_response_retains_a_failed_local_trace_without_accepting_data(controlled_client, monkeypatch, failure):
    client = controlled_client
    scope = workspace(client)
    source = upload(client, scope)
    proposer = client.app.state.controlled_source_proposer
    prepare = proposer.prepare
    def broken_preview(**kwargs):
        result = prepare(**kwargs)
        if failure == "source_binding":
            result["source_digest"] = "0" * 64
        elif failure == "grounding":
            result["fields"][0]["grounding"] = "human_reviewed"
        else:
            result["status"] = "unavailable"
            result["next_action"] = "manual_review"
        return result
    monkeypatch.setattr(proposer, "prepare", broken_preview)
    response = client.post(PREFIX + f"/workspaces/{scope}/intake-proposals", json=controlled_request(source),
                           headers={"Idempotency-Key": "failed-preview"})
    assert response.status_code in {422, 503}
    assert client.get(PREFIX + f"/workspaces/{scope}/records?kind=intake_proposal").json() == []
    assert client.get(PREFIX + f"/workspaces/{scope}/records?kind=dataset").json() == []
    attempts = client.get(PREFIX + f"/workspaces/{scope}/records?kind=controlled_attempt").json()
    outcomes = client.get(PREFIX + f"/workspaces/{scope}/records?kind=controlled_outcome").json()
    assert len(attempts) == len(outcomes) == 1
    assert outcomes[0]["body"]["local_attempt_id"] == attempts[0]["id"]
    assert outcomes[0]["body"]["status"] == "failed"
    assert client.get(PREFIX + f"/workspaces/{scope}/provider-attempts").json() == []


def test_controlled_exception_preserves_accepted_work_and_cannot_retry_under_the_same_key(controlled_client, monkeypatch):
    client = controlled_client
    scope = workspace(client)
    prior = post(client, f"/workspaces/{scope}/datasets", reviewed_history()["dataset"]["body"], "accepted-prior")
    source = upload(client, scope)
    private_text = "PRIVATE_SOURCE_CONTROL_DO_NOT_LOG"
    def fail_preparation(**kwargs):
        raise RuntimeError(private_text)
    monkeypatch.setattr(client.app.state.controlled_source_proposer, "prepare", fail_preparation)
    path = PREFIX + f"/workspaces/{scope}/intake-proposals"
    body = controlled_request(source, current_revision_id=prior["id"])
    response = client.post(path, json=body, headers={"Idempotency-Key": "interrupted-prepare"})
    assert response.status_code == 503 and response.json()["code"] == "invalid_controlled_output"
    assert private_text not in response.text
    retry = client.post(path, json=body, headers={"Idempotency-Key": "interrupted-prepare"})
    assert retry.status_code == 409 and retry.json()["code"] == "operation_pending"
    attempts = client.get(PREFIX + f"/workspaces/{scope}/records?kind=controlled_attempt").json()
    outcomes = client.get(PREFIX + f"/workspaces/{scope}/records?kind=controlled_outcome").json()
    assert len(attempts) == len(outcomes) == 1
    assert outcomes[0]["body"]["status"] == "failed"
    assert outcomes[0]["body"]["code"] == "invalid_controlled_output"
    assert private_text not in json.dumps([attempts, outcomes])
    assert client.get(PREFIX + f"/records/{prior['id']}").json() == prior
    assert client.get(PREFIX + f"/workspaces/{scope}").json()["current_dataset_id"] == prior["id"]
    assert client.get(PREFIX + f"/workspaces/{scope}/provider-attempts").json() == []


def test_disabled_default_does_not_read_manifest_or_enable_from_credentials(tmp_path, monkeypatch):
    manifest = tmp_path / "must-not-be-read.json"
    original_open = Path.open
    import os
    getenv = os.getenv
    def guarded_getenv(name, *args):
        assert name not in {"GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS"}, "Offline startup must not inspect provider keys"
        return getenv(name, *args)
    def guarded_open(path, *args, **kwargs):
        assert path != manifest, "Disabled mode must not read a controlled manifest"
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setenv("GOOGLE_API_KEY", "synthetic-unspent-key")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-unspent-key")
    key_file = tmp_path / "dummy-key.json"
    key_file.write_bytes(b'{"dummy":"nonsecret-local-control"}')
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(key_file))
    monkeypatch.setattr(os, "getenv", guarded_getenv)
    initial = key_file.read_bytes()
    settings = Settings(database_path=str(tmp_path / "db.sqlite"), blob_dir=str(tmp_path / "sources"),
        artifact_dir=str(tmp_path / "artifacts"), auth_tokens={"alice": "a" * 40}, science_adapter="unavailable",
        controlled_source_manifest_path=str(manifest))
    with TestClient(create_app(settings)) as client:
        client.headers["Authorization"] = "Bearer " + "a" * 40
        capabilities = client.get(PREFIX + "/capabilities").json()
        assert capabilities["source_intake"]["execution_mode"] == "disabled"
        assert capabilities["gemini"]["dispatch_enabled"] is False
        scope = workspace(client)
        source = upload(client, scope)
        response = client.post(PREFIX + f"/workspaces/{scope}/intake-proposals", json=controlled_request(source),
                               headers={"Idempotency-Key": "disabled"})
        assert response.status_code == 503 and response.json()["code"] == "controlled_intake_disabled"
        assert client.get(PREFIX + f"/workspaces/{scope}/provider-attempts").json() == []
    assert key_file.read_bytes() == initial


def test_invalid_controlled_configuration_cannot_fall_back(tmp_path):
    with pytest.raises(ValueError, match="disabled, controlled or live"):
        Settings(source_intake_mode="automatic")
    with pytest.raises(ValueError, match="explicit trusted"):
        Settings(source_intake_mode="controlled")
    manifest = tmp_path / "invalid.json"
    manifest.write_text("{}")
    settings = Settings(database_path=str(tmp_path / "db.sqlite"), source_intake_mode="controlled",
                        controlled_source_manifest_path=str(manifest))
    with pytest.raises(ValueError, match="valid bounded local"):
        create_app(settings)
    manifest.write_bytes(b"x" * (128 * 1024 + 1))
    with pytest.raises(ValueError, match="valid bounded local"):
        create_app(settings)
    assert not (tmp_path / "db.sqlite").exists()


def test_source_mode_is_selected_only_from_explicit_deployment_configuration(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("BEAN_AUTH_TOKENS_JSON", json.dumps({"alice": "a" * 40}))
    monkeypatch.setenv("BEAN_SOURCE_INTAKE_MODE", "controlled")
    monkeypatch.setenv("BEAN_CONTROLLED_SOURCE_MANIFEST", str(MANIFEST))
    settings = Settings.from_env()
    assert settings.source_intake_mode == "controlled" and settings.controlled_source_manifest_path == str(MANIFEST)
    monkeypatch.setenv("BEAN_SOURCE_INTAKE_MODE", "live")
    assert Settings.from_env().source_intake_mode == "live"
    # Naming a source mode alone never supplies consent or enables credentials.
    monkeypatch.delenv("BEAN_AI_MODE", raising=False)
    from bean_api.main import provider_config_from_env
    assert provider_config_from_env().api_key is None


def test_legacy_schema_and_record_types_keep_their_meanings():
    from bean_api.contracts import IntakeProposalBody, IntakeRequest
    for model in (IntakeRequest, IntakeProposalBody, IntakeProposalRecordBody):
        exported = json.loads((ROOT / "shared/contracts/DB-SC-1" / f"{model.__name__}.schema.json").read_text())
        exported.pop("$schema")
        exported.pop("$id")
        assert model.model_json_schema() == exported
    assert "controlled_fixture" not in IntakeProposalBody.model_json_schema()["$defs"]["IntakeField"]["properties"]["method"]["enum"]
