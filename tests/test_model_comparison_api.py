"""Real offline computation through authenticated persistence; no provider calls."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import socket
import subprocess
from threading import Event

from fastapi.testclient import TestClient
import pytest

from bean_api.canonical import canonical_bytes
from bean_api.config import Settings
from bean_api.main import PREFIX, create_app
from bean_api.model_comparison.contract import Channel, Instrument, ModelComparisonRequest
from bean_api.model_comparison.models import predict_current
from bean_api.model_comparison.service import OPERATION, RESULT_KIND, run_computation
from bean_api.sessions import LOCAL_COOKIE, LOCAL_GATEWAY_HEADER, LOCAL_ORIGIN_HEADER
from bean_api.workflow import DomainError

ALICE = "DRBEAN-DUMMY-comparison-alice-" + "a" * 32
BOB = "DRBEAN-DUMMY-comparison-bob-" + "b" * 32


def example_request():
    instrument = {"kind": "idealized_normal_energy_planar_collector", "acceptance": "full_incident_half_space",
                  "area_m2": "1e-6", "efficiency": "1", "current_convention": "electron_current_magnitude"}
    channels = [{"id": f"c{index}", "angle_deg": angle, "energy_min_eV": energy, "energy_max_eV": None}
                for index, (angle, energy) in enumerate((('0', '0'), ('0', '10'), ('90', '0'),
                                                        ('90', '10'), ('45', '0'), ('45', '10')))]
    parameters = {"density_m3": 1e15, "parallel_eV": 20.0, "perpendicular_eV": 5.0}
    observations = [{"channel_id": channel["id"], "current_A": format(predict_current(
        parameters, Channel.model_validate(channel), Instrument.model_validate(instrument)), ".17g"), "sigma_A": "1e-8"}
                    for channel in channels]
    return {"schema_version": "DB-MODEL-COMPARISON-1", "approval": "approved_for_this_request",
            "review": {"reviewed": True, "origin": "synthetic", "description": "New public-equation synthetic data."},
            "instrument": instrument, "channels": channels, "observations": observations,
            "selected_channel_ids": [channel["id"] for channel in channels],
            "fit": {"density_min_m3": "1e14", "density_max_m3": "1e16", "temperature_grid_eV": ["5", "10", "20"],
                    "max_evaluations": 100, "max_reduced_chi_square": "10"},
            "noise": {"kind": "independent_gaussian", "sigma_grid_A": ["1e-8", "1e-3"],
                      "z_thresholds": ["2"], "seed": 173, "samples": 32},
            "feasible_settings": channels[:2]}


@pytest.fixture
def application(tmp_path, monkeypatch):
    monkeypatch.setenv("BEAN_AI_MODE", "placeholder")
    monkeypatch.setattr(socket.socket, "connect", lambda *args: (_ for _ in ()).throw(AssertionError("No network dispatch")))
    settings = Settings(database_path=str(tmp_path / "app.sqlite3"), blob_dir=str(tmp_path / "sources"),
                        artifact_dir=str(tmp_path / "artifacts"), auth_tokens={"alice": ALICE, "bob": BOB},
                        science_adapter="unavailable", research_mode="disabled")
    app = create_app(settings)
    client = TestClient(app, headers={"Authorization": "Bearer " + ALICE})
    workspace = client.post(PREFIX + "/workspaces", json={"name": "Numerical comparison"}).json()["id"]
    return app, client, workspace, settings


def path(workspace, record=None):
    return PREFIX + f"/workspaces/{workspace}/model-comparisons" + (f"/{record}" if record else "")


def post(client, workspace, body=None, key="comparison-1"):
    return client.post(path(workspace), json=body or example_request(), headers={"Idempotency-Key": key})


def counts(app):
    with app.state.workflow.store.read() as conn:
        return {table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                for table in ("provider_attempts", "jobs", "approvals")}


def test_real_comparison_persists_reopens_and_downloads_exact_bytes(application):
    app, client, workspace, settings = application
    before = counts(app)
    body = example_request()
    response = post(client, workspace, body)
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["kind"] == RESULT_KIND and record["workspace_id"] == workspace
    result = record["body"]
    assert result["request"] == body and result["exact_verification"] == "not_performed"
    assert result["input_digest"] == hashlib.sha256(canonical_bytes(body)).hexdigest()
    assert result["status"] == "completed" and len(result["fits"]) == 2
    assert record["digest"] == hashlib.sha256(canonical_bytes(result)).hexdigest()
    assert client.get(path(workspace, record["id"])).json() == record
    assert client.get(path(workspace)).json() == [record]
    download = client.get(path(workspace, record["id"]) + "/download")
    assert download.status_code == 200
    exported = {"schema_version": "DB-MODEL-COMPARISON-EXPORT-1", "result": record}
    assert download.content == canonical_bytes(exported)
    assert download.headers["x-artifact-sha256"] == hashlib.sha256(download.content).hexdigest()
    assert download.headers["content-disposition"].startswith("attachment;")
    assert post(client, workspace, body).json() == record
    reopened = create_app(settings)
    reopened.state.model_comparison.runner = lambda _: pytest.fail("Cached operation must not execute")
    with TestClient(reopened, headers={"Authorization": "Bearer " + ALICE}) as fresh:
        assert fresh.get(path(workspace, record["id"])).json() == record
        assert post(fresh, workspace, body).json() == record
    assert counts(app) == before


def test_review_approval_and_numerical_boundary_refuse_before_dispatch(application):
    app, client, workspace, _ = application
    app.state.model_comparison.runner = lambda _: pytest.fail("Invalid request must not compute")
    changes = [lambda b: b["review"].update(reviewed=False), lambda b: b["review"].update(reviewed=1),
               lambda b: b.pop("approval"),
               lambda b: b.update(approval="approved_another_request"),
               lambda b: b["observations"][0].update(current_A=0.2),
               lambda b: b["noise"].update(samples=1025),
               lambda b: b["fit"].update(temperature_grid_eV=["5", "5.0"])]
    for change in changes:
        body = example_request()
        change(body)
        assert post(client, workspace, body).status_code == 422
    with app.state.workflow.store.read() as conn:
        assert conn.execute("SELECT count(*) FROM operations WHERE operation=?", (OPERATION,)).fetchone()[0] == 0


def test_authentication_and_workspace_ownership_precede_execution(application):
    app, client, workspace, _ = application
    record = post(client, workspace).json()
    app.state.model_comparison.runner = lambda _: pytest.fail("Foreign workspace must not compute")
    with TestClient(app, headers={"Authorization": "Bearer " + BOB}) as bob:
        own = bob.post(PREFIX + "/workspaces", json={"name": "Bob"}).json()["id"]
        for route in (path(workspace), path(workspace, record["id"]), path(own, record["id"]),
                      path(workspace, record["id"]) + "/download"):
            assert bob.get(route).status_code == 404
        assert post(bob, workspace).status_code == 404
    second = client.post(PREFIX + "/workspaces", json={"name": "Second"}).json()["id"]
    assert client.get(path(second, record["id"])).status_code == 404
    with TestClient(app) as anonymous:
        assert post(anonymous, workspace).status_code == 401


def test_ordinary_private_cookie_lane_reuses_session_and_isolates_results(application, tmp_path):
    _, _, _, settings = application
    origin = "http://127.0.0.1:19273"
    proof = "DRBEAN-DUMMY-comparison-gateway-".ljust(43, "x")
    gateway = tmp_path / "local-gateway.json"
    gateway.write_text(json.dumps({"version": 1, "secret": proof}))
    gateway.chmod(0o600)
    settings = replace(settings, local_gateway_file=str(gateway), local_browser_origin=origin)
    app = create_app(settings)
    headers = {LOCAL_GATEWAY_HEADER: proof, LOCAL_ORIGIN_HEADER: origin,
               "Origin": origin, "Sec-Fetch-Site": "same-origin"}
    with TestClient(app, base_url=origin, client=("127.0.0.1", 49152), headers=headers) as alice, \
            TestClient(app, base_url=origin, client=("127.0.0.1", 49153), headers=headers) as bob:
        first = alice.get(PREFIX + "/shared-session").json()["workspace_id"]
        second = bob.get(PREFIX + "/shared-session").json()["workspace_id"]
        assert first != second and alice.cookies.get(LOCAL_COOKIE)
        record = post(alice, first).json()
        assert "body" in record, record
        assert alice.get(PREFIX + "/shared-session/current").json()["workspace_id"] == first
        assert alice.get(path(first, record["id"])).json() == record
        assert bob.get(path(first, record["id"])).status_code == 404
        assert bob.get(path(second, record["id"])).status_code == 404
        assert post(bob, first).status_code == 404
        assert alice.post(PREFIX + "/shared-session/logout").status_code == 200
        assert alice.get(path(first, record["id"])).status_code == 401
    assert counts(app)["provider_attempts"] == 0


def test_missing_instrument_is_retained_as_unsupported_not_verified(application):
    _, client, workspace, _ = application
    body = example_request()
    body["instrument"] = None
    response = post(client, workspace, body)
    assert response.status_code == 201, response.text
    result = response.json()["body"]
    assert result["status"] == "unsupported" and result["exact_verification"] == "not_performed"
    assert result["request"] == body and result["fits"] == []


def test_changed_inputs_need_new_operation_and_change_computation(application):
    _, client, workspace, _ = application
    body = example_request()
    first = post(client, workspace, body).json()
    changed = deepcopy(body)
    for row in changed["observations"]:
        row["current_A"] = format(float(row["current_A"]) * 2, ".17g")
    conflict = post(client, workspace, changed)
    assert conflict.status_code == 409 and conflict.json()["code"] == "idempotency_conflict"
    second = post(client, workspace, changed, key="comparison-2")
    assert second.status_code == 201, second.text
    second = second.json()
    assert second["body"]["input_digest"] != first["body"]["input_digest"]
    assert second["body"]["fits"] != first["body"]["fits"]
    assert client.get(path(workspace, first["id"])).json() == first


def test_pending_duplicate_never_computes_twice_or_holds_database_lock(application):
    app, _, workspace, _ = application
    service = app.state.model_comparison
    request = ModelComparisonRequest.model_validate(example_request())
    computed = run_computation(request)
    entered, release = Event(), Event()
    calls = []

    def runner(body):
        calls.append(body)
        # This independent write would deadlock if compute held the reservation transaction.
        app.state.workflow.create_workspace("alice", "Concurrent write")
        entered.set()
        assert release.wait(5)
        return computed

    service.runner = runner
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(service.compare, "alice", workspace, request, "pending")
        assert entered.wait(5)
        try:
            with pytest.raises(DomainError) as error:
                service.compare("alice", workspace, request, "pending")
            assert error.value.code == "operation_pending"
        finally:
            release.set()
        record = pending.result(timeout=5)
    assert service.compare("alice", workspace, request, "pending") == record and len(calls) == 1


@pytest.mark.parametrize("mode", ["timeout", "interrupted", "substitution"])
def test_failed_or_interrupted_execution_never_publishes_or_retries(application, mode):
    app, client, workspace, _ = application
    calls = []
    request = ModelComparisonRequest.model_validate(example_request())
    computed = run_computation(request)

    def runner(body):
        calls.append(body)
        if mode == "timeout":
            raise DomainError("comparison_timeout", "Test deadline", 503)
        if mode == "interrupted":
            app.state.workflow.recover_interrupted()
        if mode == "substitution":
            computed["request"]["noise"]["seed"] += 1
        return computed

    app.state.model_comparison.runner = runner
    response = post(client, workspace)
    assert response.status_code == (409 if mode == "interrupted" else 503), response.text
    duplicate = post(client, workspace)
    assert duplicate.status_code == 409 and duplicate.json()["code"] == "operation_interrupted"
    assert len(calls) == 1 and client.get(path(workspace)).json() == []


def test_subprocess_deadline_uses_credential_free_environment(monkeypatch):
    def timeout(command, **kwargs):
        assert command[0] and "compute_comparison" in command[2]
        assert set(kwargs["env"]) == {"PYTHONDONTWRITEBYTECODE", "PYTHONNOUSERSITE"}
        assert kwargs["timeout"] == 10
        assert json.loads(kwargs["input"])["approval"] == "approved_for_this_request"
        raise subprocess.TimeoutExpired(command, 10)
    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(DomainError) as error:
        run_computation(ModelComparisonRequest.model_validate(example_request()))
    assert error.value.code == "comparison_timeout"
