"""Private session authority through the actual app; no external model calls."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
import secrets
import socket
import sqlite3

from fastapi.testclient import TestClient
import pytest

from bean_api.artifacts import ArtifactService
from bean_api.config import Settings
from bean_api.ledger import LedgerBudgetExceeded, ProviderLedger
from bean_api.main import PREFIX, create_app
from bean_api.sessions import COOKIE, GATEWAY_HEADER, ORIGIN_HEADER, gateway_digest
from bean_api.worker import Worker

ORIGIN = "https://private-test.trycloudflare.com"


@pytest.fixture
def shared(tmp_path, monkeypatch):
    monkeypatch.setenv("BEAN_AI_MODE", "placeholder")
    monkeypatch.setattr(socket.socket, "connect", lambda *args: (_ for _ in ()).throw(AssertionError("No external dispatch")))
    proof, owner = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    file = tmp_path / "share-gateway.json"
    file.write_text(json.dumps({"version": 1, "secret": proof}))
    file.chmod(0o600)
    settings = Settings(database_path=str(tmp_path / "app.sqlite3"), blob_dir=str(tmp_path / "sources"),
                        artifact_dir=str(tmp_path / "artifacts"), auth_file=str(tmp_path / "unused-auth.json"),
                        auth_tokens={"owner": owner}, science_adapter="unavailable", shared_gateway_file=str(file))
    app = create_app(settings)
    headers = {GATEWAY_HEADER: proof, ORIGIN_HEADER: ORIGIN, "Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"}
    return app, settings, headers, owner


def browser(shared):
    return TestClient(shared[0], base_url=ORIGIN, headers=shared[2])


def bootstrap(client):
    response = client.get(PREFIX + "/shared-session")
    assert response.status_code == 200, response.json()
    assert set(response.json()) == {"mode", "authenticated", "workspace_id", "credentials"}
    return response.json()["workspace_id"]


def post(client, path, body, key="control"):
    response = client.post(PREFIX + path, json=body, headers={"Idempotency-Key": key})
    assert response.status_code in {200, 201, 202}, response.json()
    return response.json()


def test_two_sessions_private_workspaces_hash_only_and_owner_preserved(shared):
    app, settings, _, owner = shared
    with TestClient(app, headers={"Authorization": "Bearer " + owner}) as local:
        private = post(local, "/workspaces", {"name": "Existing owner research"})["id"]
    with browser(shared) as alice, browser(shared) as bob:
        first, second = bootstrap(alice), bootstrap(bob)
        assert len({first, second, private}) == 3
        assert [x["id"] for x in alice.get(PREFIX + "/workspaces").json()] == [first]
        assert [x["id"] for x in bob.get(PREFIX + "/workspaces").json()] == [second]
        for client, forbidden in ((alice, second), (bob, first), (alice, private), (bob, private)):
            assert client.get(PREFIX + f"/workspaces/{forbidden}").status_code == 404
            assert client.get(PREFIX + f"/workspaces/{forbidden}/provider-attempts").status_code == 404
        token = alice.cookies.get(COOKIE)
        response = alice.get(PREFIX + "/shared-session")
        assert response.json()["workspace_id"] == first
        cookie = response.headers["set-cookie"]
        for attribute in ("Secure", "HttpOnly", "SameSite=strict", "Path=/", "Max-Age="):
            assert attribute in cookie
        assert "Domain=" not in cookie
        assert {value.strip() for value in response.headers["cache-control"].split(",")} == {"no-store"}
        with app.state.workflow.store.read() as conn:
            rows = [dict(row) for row in conn.execute("SELECT * FROM browser_sessions")]
            assert len(rows) == 2 and len({r["actor_id"] for r in rows}) == 2
            assert hashlib.sha256(token.encode()).hexdigest() in {r["token_hash"] for r in rows}
            assert token not in json.dumps(rows) and owner not in json.dumps(rows)
            assert conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0] == 0
        assert settings.auth_tokens == {"owner": owner}
    with TestClient(app, headers={"Authorization": "Bearer " + owner}) as local:
        assert [x["id"] for x in local.get(PREFIX + "/workspaces").json()] == [private]


def test_restart_reopen_parallel_reopen_and_rotation_revoke_old_cookie(shared):
    app, settings, headers, _ = shared
    with browser(shared) as client:
        workspace = bootstrap(client)
        original = client.cookies.get(COOKIE)
    app = create_app(settings)
    def reopen(_):
        with TestClient(app, base_url=ORIGIN, headers={**headers, "Cookie": COOKIE + "=" + original}) as client:
            return bootstrap(client)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(reopen, range(8))) == [workspace] * 8
    with app.state.workflow.store.read() as conn:
        original_row = dict(conn.execute("SELECT * FROM browser_sessions").fetchone())
        assert conn.execute("SELECT count(*) FROM workspaces").fetchone()[0] == 1
    with TestClient(app, base_url=ORIGIN, headers=headers) as client:
        client.cookies.set(COOKIE, original, domain="private-test.trycloudflare.com", path="/")
        rotated = client.post(PREFIX + "/shared-session/rotate")
        assert rotated.status_code == 200 and rotated.json()["workspace_id"] == workspace
        replacement = client.cookies.get(COOKIE)
        assert replacement != original
        with app.state.workflow.store.read() as conn:
            rows = [dict(row) for row in conn.execute("SELECT * FROM browser_sessions")]
            assert len(rows) == 2 and {r["expires_at"] for r in rows} == {original_row["expires_at"]}
            assert len({r["actor_id"] for r in rows}) == 1
        replay = client.get(PREFIX + "/workspaces", headers={"Cookie": COOKIE + "=" + original})
        assert replay.status_code == 401
        assert "Max-Age=0" in replay.headers["set-cookie"]
        client.cookies.set(COOKIE, replacement, domain="private-test.trycloudflare.com", path="/")
        assert client.post(PREFIX + "/shared-session/logout").status_code == 200
    with TestClient(create_app(settings), base_url=ORIGIN, headers={**headers, "Cookie": COOKIE + "=" + replacement}) as client:
        assert client.get(PREFIX + "/workspaces").status_code == 401
        assert client.get(PREFIX + "/shared-session").status_code == 401


@pytest.mark.parametrize("cookie", [None, "bad", "quoted", "duplicate", "forged", "expired"])
def test_missing_invalid_duplicate_expired_sessions_do_not_gain_authority(shared, cookie):
    app = shared[0]
    with browser(shared) as client:
        workspace = bootstrap(client)
        token = client.cookies.get(COOKIE)
        if cookie == "expired":
            with app.state.workflow.store.read() as conn:
                expiry = conn.execute("SELECT expires_at FROM browser_sessions").fetchone()[0]
            app.state.sessions.clock = lambda: expiry
        supplied = {None: None, "bad": "wrong", "quoted": '"' + token + '"',
                    "duplicate": token + "; " + COOKIE + "=" + token,
                    "forged": secrets.token_urlsafe(32), "expired": token}[cookie]
        client.cookies.clear()
        headers = {} if supplied is None else {"Cookie": COOKIE + "=" + supplied}
        denied = client.get(PREFIX + f"/workspaces/{workspace}", headers=headers)
        assert denied.status_code == 401
        assert "Max-Age=0" in denied.headers["set-cookie"]
        if supplied is not None:
            assert client.get(PREFIX + "/shared-session", headers=headers).status_code == 401
        with app.state.workflow.store.read() as conn:
            assert conn.execute("SELECT count(*) FROM browser_sessions").fetchone()[0] == 1


@pytest.mark.parametrize("attack", ["wrong_proof", "missing_proof", "missing_shared_origin", "foreign_origin", "missing_origin", "cross_site", "same_site", "owner_bearer"])
def test_shared_mutation_boundary_cannot_be_forged_or_upgraded(shared, attack):
    app, _, headers, owner = shared
    with browser(shared) as client:
        bootstrap(client)
        token = client.cookies.get(COOKIE)
    bad = {**headers, "Cookie": COOKIE + "=" + token}
    if attack == "wrong_proof":
        bad[GATEWAY_HEADER] = secrets.token_urlsafe(32)
    elif attack == "missing_proof":
        bad.pop(GATEWAY_HEADER)
    elif attack == "missing_shared_origin":
        bad.pop(ORIGIN_HEADER)
    elif attack == "foreign_origin":
        bad["Origin"] = "https://foreign.example"
    elif attack == "missing_origin":
        bad.pop("Origin")
    elif attack in {"cross_site", "same_site"}:
        bad["Sec-Fetch-Site"] = attack.replace("_", "-")
    else:
        bad["Authorization"] = "Bearer " + owner
    with TestClient(app, base_url=ORIGIN, headers=bad) as client:
        response = client.post(PREFIX + "/workspaces", json={"name": "Must not be created"})
        assert response.status_code == 403, response.json()
    with app.state.workflow.store.read() as conn:
        assert conn.execute("SELECT count(*) FROM workspaces").fetchone()[0] == 1


def test_bootstrap_transaction_rolls_back_and_capacity_preserves_history(shared):
    app = shared[0]
    with app.state.workflow.store.transaction() as conn:
        conn.execute("CREATE TRIGGER refuse_session BEFORE INSERT ON browser_sessions BEGIN SELECT RAISE(ABORT,'synthetic refusal'); END")
    with browser(shared) as client, pytest.raises(sqlite3.IntegrityError):
        bootstrap(client)
    with app.state.workflow.store.read() as conn:
        assert conn.execute("SELECT count(*) FROM memberships").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM workspaces").fetchone()[0] == 0
    with app.state.workflow.store.transaction() as conn:
        conn.execute("DROP TRIGGER refuse_session")
    app.state.sessions.max_sessions = 1
    with browser(shared) as first, browser(shared) as second:
        first_id = bootstrap(first)
        assert second.get(PREFIX + "/shared-session").status_code == 429
        assert first.get(PREFIX + "/shared-session").json()["workspace_id"] == first_id
        assert first.post(PREFIX + "/shared-session/rotate").status_code == 429
        assert first.get(PREFIX + f"/workspaces/{first_id}").status_code == 200


def test_private_gateway_file_admission_and_hot_configuration(shared, tmp_path):
    app, settings, headers, _ = shared
    path = tmp_path / "share-gateway.json"
    original = path.read_bytes()
    path.unlink()
    with browser(shared) as client:
        assert client.get(PREFIX + "/capabilities").json()["shared_access"]["available"] is False
        assert client.get(PREFIX + "/shared-session").status_code == 404
        path.write_bytes(original)
        path.chmod(0o600)
        assert client.get(PREFIX + "/capabilities").json()["shared_access"]["available"] is True
        bootstrap(client)
    path.chmod(0o644)
    assert gateway_digest(str(path)) is None
    path.chmod(0o600)
    linked = tmp_path / "linked.json"
    linked.symlink_to(path)
    assert gateway_digest(str(linked)) is None
    assert gateway_digest(str(tmp_path)) is None
    path.write_text(json.dumps({"version": True, "secret": headers[GATEWAY_HEADER]}))
    assert gateway_digest(str(path)) is None
    path.write_text("x" * 1025)
    assert gateway_digest(str(path)) is None
    local = create_app(replace(settings, shared_gateway_file=None))
    with TestClient(local) as client:
        assert client.get(PREFIX + "/shared-session").status_code == 404


def test_new_sessions_do_not_reset_global_provider_capacity(shared):
    app = shared[0]
    ledger = ProviderLedger(app.state.workflow.store, request_cap=1)
    with browser(shared) as first, browser(shared) as second:
        workspaces = [bootstrap(first), bootstrap(second)]
    with app.state.workflow.store.read() as conn:
        actors = {r["workspace_id"]: r["actor_id"] for r in conn.execute("SELECT * FROM browser_sessions")}
    contexts = []
    for workspace in workspaces:
        actor = actors[workspace]
        operation = app.state.workflow.begin_operation(actor, workspace, "offline-control", "control", {})
        contexts.append({"workspace_id": workspace, "actor_id": actor, "operation_id": operation["id"]})
    metadata = {"reserved_input_tokens": 10, "reserved_output_tokens": 10}
    attempt = ledger.begin_attempt(contexts[0], metadata)
    ledger.finish_attempt(attempt, {"outcome": "unknown_outcome"})
    with pytest.raises(LedgerBudgetExceeded):
        ledger.begin_attempt(contexts[1], metadata)
    with app.state.workflow.store.read() as conn:
        assert conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0] == 1


def test_science_history_exports_and_sources_are_private_between_sessions(shared):
    # Reuse the ordinary API workflow control with an explicitly unavailable
    # adapter. Separate real installed-engine regression remains required.
    from test_api import prepared, ROOT
    app = shared[0]
    with browser(shared) as alice, browser(shared) as bob:
        bootstrap(alice)
        bootstrap(bob)
        workspace, dataset, problem, plan, approval = prepared(alice)
        run = post(alice, f"/plans/{plan['id']}/runs", {"approval_id": approval["id"], "expected_plan_digest": plan["digest"]})
        assert Worker(app.state.workflow, adapter=app.state.adapter, settings=app.state.settings).tick() == 1
        finished = alice.get(PREFIX + f"/runs/{run['id']}").json()
        report = post(alice, f"/runs/{run['id']}/reports", {})
        uploaded = alice.post(PREFIX + f"/workspaces/{workspace}/source-assets?origin=synthetic&retention=retain",
                              content=(ROOT / "fixtures/intake/clean.png").read_bytes(),
                              headers={"Content-Type": "image/png", "Idempotency-Key": "private-image"})
        assert uploaded.status_code == 201, uploaded.json()
        source = uploaded.json()
        paths = [f"/workspaces/{workspace}", f"/workspaces/{workspace}/activity", f"/workspaces/{workspace}/records?kind=dataset",
                 f"/records/{dataset['id']}", f"/records/{problem['id']}", f"/records/{plan['id']}",
                 f"/records/{finished['scenarios'][0]['result_id']}", f"/runs/{run['id']}",
                 f"/reports/{report['id']}/download", f"/records/{source['id']}", f"/source-assets/{source['id']}/content"]
        for path in paths:
            assert bob.get(PREFIX + path).status_code == 404, path
        assert bob.post(PREFIX + f"/runs/{run['id']}/cancel", json={}, headers={"Idempotency-Key": "attack"}).status_code == 404
        assert bob.post(PREFIX + f"/workspaces/{workspace}/datasets", json=dataset["body"], headers={"Idempotency-Key": "attack"}).status_code == 404
        assert alice.get(PREFIX + f"/reports/{report['id']}/download").status_code == 200


def test_native_bytes_and_external_anchors_remain_private_after_restart(shared):
    # This tests storage authorization, not scientific validity. The separate
    # installed-engine regression verifies actual certificates and fresh replay.
    app, settings, headers, _ = shared
    with browser(shared) as alice, browser(shared) as bob:
        workspace = bootstrap(alice)
        bootstrap(bob)
        with app.state.workflow.store.read() as conn:
            actor = conn.execute("SELECT actor_id FROM browser_sessions WHERE workspace_id=?", (workspace,)).fetchone()[0]
        content = b'{"synthetic_storage_authorization_control":true}'
        anchors = {"external_input_identity": "synthetic-storage-control"}
        artifact = ArtifactService(app.state.workflow, settings.artifact_dir).publish(
            actor, workspace, content, media_type="application/json", anchor=anchors, key="private-native-control")
        native = PREFIX + f"/artifacts/{artifact['id']}"
        paths = [native, native + "/anchor", native + "/anchor?download=true", PREFIX + f"/records/{artifact['id']}"]
        assert alice.get(native).content == content
        assert alice.get(native + "/anchor").json()["anchor"] == anchors
        for path in paths:
            assert bob.get(path).status_code == 404
        tokens = [client.cookies.get(COOKIE) for client in (alice, bob)]
    restarted = create_app(settings)
    for index, token in enumerate(tokens):
        with TestClient(restarted, base_url=ORIGIN, headers={**headers, "Cookie": COOKIE + "=" + token}) as client:
            for path in paths:
                assert client.get(path).status_code == (200 if index == 0 else 404)
