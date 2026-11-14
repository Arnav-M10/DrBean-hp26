"""Local HTTP private sessions through real API authorization, entirely offline."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import socket

from fastapi.testclient import TestClient
import pytest

from bean_api.artifacts import ArtifactService
from bean_api.config import Settings
from bean_api.main import PREFIX, create_app
from bean_api.sessions import COOKIE, GATEWAY_HEADER, LOCAL_COOKIE, LOCAL_GATEWAY_HEADER, LOCAL_ORIGIN_HEADER, ORIGIN_HEADER
from bean_api.worker import Worker
from test_browser_sessions import bootstrap, post

LOCAL_ORIGIN = "http://127.0.0.1:19173"
SHARED_ORIGIN = "https://private-test.trycloudflare.com"
LOCAL_PROOF = "DRBEAN-DUMMY-local-".ljust(43, "x")
SHARED_PROOF = "DRBEAN-DUMMY-shared-".ljust(43, "x")
OWNER = "DRBEAN-DUMMY-owner-" + "x" * 32


@pytest.fixture
def local_access(tmp_path, monkeypatch):
    monkeypatch.setenv("BEAN_AI_MODE", "placeholder")
    monkeypatch.setattr(socket.socket, "connect", lambda *args: (_ for _ in ()).throw(AssertionError("No external dispatch")))
    paths = {}
    for lane, proof in (("local", LOCAL_PROOF), ("shared", SHARED_PROOF)):
        path = tmp_path / (lane + "-gateway.json")
        path.write_text(json.dumps({"version": 1, "secret": proof}))
        path.chmod(0o600)
        paths[lane] = str(path)
    settings = Settings(database_path=str(tmp_path / "app.sqlite3"), blob_dir=str(tmp_path / "sources"),
                        artifact_dir=str(tmp_path / "artifacts"), auth_file=str(tmp_path / "unused-auth.json"),
                        auth_tokens={"owner": OWNER}, science_adapter="unavailable",
                        shared_gateway_file=paths["shared"], local_gateway_file=paths["local"],
                        local_browser_origin=LOCAL_ORIGIN)
    return create_app(settings), settings


def browser(local_access, *, shared=False, headers=None, peer="127.0.0.1"):
    origin = SHARED_ORIGIN if shared else LOCAL_ORIGIN
    trusted = ({GATEWAY_HEADER: SHARED_PROOF, ORIGIN_HEADER: origin} if shared else
               {LOCAL_GATEWAY_HEADER: LOCAL_PROOF, LOCAL_ORIGIN_HEADER: origin})
    return TestClient(local_access[0], base_url=origin, client=(peer, 49152),
                      headers={**trusted, "Origin": origin, "Sec-Fetch-Site": "same-origin", **(headers or {})})


@pytest.mark.parametrize("shared", [False, True])
def test_current_is_nonissuing_and_cookie_confirmation_reuses_identity(local_access, shared):
    app, settings = local_access
    cookie_name = COOKIE if shared else LOCAL_COOKIE
    with browser(local_access, shared=shared) as client:
        for _ in range(4):
            missing = client.get(PREFIX + "/shared-session/current")
            assert missing.status_code == 401 and missing.json()["code"] == "browser_session_missing"
            assert "set-cookie" not in missing.headers
        with app.state.workflow.store.read() as conn:
            assert conn.execute("SELECT count(*) FROM browser_sessions").fetchone()[0] == 0
        issued = client.get(PREFIX + "/shared-session")
        assert issued.status_code == 200
        cookie = issued.headers["set-cookie"]
        assert cookie.startswith(cookie_name + "=")
        for attribute in ("HttpOnly", "SameSite=strict", "Path=/", "Max-Age="):
            assert attribute in cookie
        assert ("Secure" in cookie) is shared
        assert "Domain=" not in cookie
        session = issued.json()
        token = client.cookies.get(cookie_name)
        for _ in range(3):
            current = client.get(PREFIX + "/shared-session/current")
            assert current.json() == session and "set-cookie" not in current.headers
            assert {value.strip() for value in current.headers["cache-control"].split(",")} == {"no-store"}
            assert client.get(PREFIX + "/workspaces").json()[0]["id"] == session["workspace_id"]
            assert client.get(PREFIX + "/shared-session").json() == session
    reopened = (create_app(settings), settings)
    def reopen(_):
        with browser(reopened, shared=shared, headers={"Cookie": cookie_name + "=" + token}) as tab:
            assert tab.get(PREFIX + "/shared-session/current").json() == session
            assert tab.get(PREFIX + "/shared-session").json() == session
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(reopen, range(8)))
    with app.state.workflow.store.read() as conn:
        assert conn.execute("SELECT count(*) FROM browser_sessions").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM workspaces").fetchone()[0] == 1
        for table in ("provider_attempts", "jobs", "operations", "research_sessions"):
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


@pytest.mark.parametrize("attack", ["wrong_proof", "shared_proof", "missing_proof", "missing_context", "foreign_context",
                                    "different_port", "foreign_origin", "missing_origin", "same_site", "cross_site",
                                    "owner_bearer", "mixed_lane", "duplicate_proof", "duplicate_origin", "duplicate_fetch_site", "remote_peer"])
def test_local_boundary_requires_exact_server_context_and_same_origin(local_access, attack):
    app = local_access[0]
    with browser(local_access) as client:
        bootstrap(client)
        token = client.cookies.get(LOCAL_COOKIE)
    headers = {LOCAL_GATEWAY_HEADER: LOCAL_PROOF, LOCAL_ORIGIN_HEADER: LOCAL_ORIGIN,
               "Origin": LOCAL_ORIGIN, "Sec-Fetch-Site": "same-origin", "Cookie": LOCAL_COOKIE + "=" + token}
    if attack == "wrong_proof":
        headers[LOCAL_GATEWAY_HEADER] = "x" * 43
    elif attack == "shared_proof":
        headers[LOCAL_GATEWAY_HEADER] = SHARED_PROOF
    elif attack == "missing_proof":
        headers.pop(LOCAL_GATEWAY_HEADER)
    elif attack == "missing_context":
        headers.pop(LOCAL_ORIGIN_HEADER)
    elif attack == "foreign_context":
        headers[LOCAL_ORIGIN_HEADER] = "http://evil.example:19173"
    elif attack == "different_port":
        headers[LOCAL_ORIGIN_HEADER] = "http://127.0.0.1:19174"
    elif attack == "foreign_origin":
        headers["Origin"] = "https://evil.example"
    elif attack == "missing_origin":
        headers.pop("Origin")
    elif attack in {"same_site", "cross_site"}:
        headers["Sec-Fetch-Site"] = attack.replace("_", "-")
    elif attack == "owner_bearer":
        headers["Authorization"] = "Bearer " + OWNER
    elif attack == "mixed_lane":
        headers[GATEWAY_HEADER], headers[ORIGIN_HEADER] = SHARED_PROOF, SHARED_ORIGIN
    # Forwarded headers never make a remote API peer into the trusted local hop.
    headers["X-Forwarded-For"], headers["X-Forwarded-Proto"] = "127.0.0.1", "https"
    pairs = list(headers.items())
    if attack == "duplicate_proof":
        pairs.append((LOCAL_GATEWAY_HEADER, LOCAL_PROOF))
    elif attack == "duplicate_origin":
        pairs.append(("Origin", LOCAL_ORIGIN))
    elif attack == "duplicate_fetch_site":
        pairs.append(("Sec-Fetch-Site", "cross-site"))
    peer = "192.0.2.8" if attack == "remote_peer" else "127.0.0.1"
    with TestClient(app, base_url=LOCAL_ORIGIN, client=(peer, 49152)) as client:
        response = client.post(PREFIX + "/workspaces", json={"name": "Forbidden"}, headers=pairs)
        assert response.status_code == 403, response.json()
        assert "set-cookie" not in response.headers
    with app.state.workflow.store.read() as conn:
        assert conn.execute("SELECT count(*) FROM workspaces").fetchone()[0] == 1


def test_local_lane_is_explicit_and_secure_cookie_cannot_select_it(local_access):
    app, settings = local_access
    disabled = create_app(replace(settings, local_gateway_file=None, local_browser_origin=None))
    with browser((disabled, settings)) as client:
        assert client.get(PREFIX + "/shared-session").status_code == 404
    with browser(local_access) as client:
        bootstrap(client)
        token = client.cookies.get(LOCAL_COOKIE)
        for cookie in (COOKIE + "=" + token, LOCAL_COOKIE + "=" + token + "; " + LOCAL_COOKIE + "=" + token):
            response = client.get(PREFIX + "/shared-session/current", headers={"Cookie": cookie})
            assert response.status_code == 401 and response.json()["code"] == "invalid_browser_session"
            assert response.headers["set-cookie"].startswith(LOCAL_COOKIE + "=")
            assert "Secure" not in response.headers["set-cookie"]
    with TestClient(app, base_url=LOCAL_ORIGIN, headers={"Authorization": "Bearer " + OWNER,
                                                      "Cookie": LOCAL_COOKIE + "=" + token}) as direct:
        assert direct.get(PREFIX + "/workspaces").status_code == 403


def test_local_expiry_rotation_capacity_and_history(local_access):
    app = local_access[0]
    app.state.sessions.max_sessions = 1
    with browser(local_access) as client:
        workspace = bootstrap(client)
        old = client.cookies.get(LOCAL_COOKIE)
        with app.state.workflow.store.read() as conn:
            original = dict(conn.execute("SELECT * FROM browser_sessions").fetchone())
        rotated = client.post(PREFIX + "/shared-session/rotate")
        assert rotated.status_code == 200 and rotated.json()["workspace_id"] == workspace
        replacement = client.cookies.get(LOCAL_COOKIE)
        assert replacement != old
        denied = client.get(PREFIX + "/shared-session/current", headers={"Cookie": LOCAL_COOKIE + "=" + old})
        assert denied.status_code == 401 and denied.json()["code"] == "invalid_browser_session"
        app.state.sessions.clock = lambda: original["expires_at"]
        for _ in range(3):
            denied = client.get(PREFIX + "/shared-session", headers={"Cookie": LOCAL_COOKIE + "=" + replacement})
            assert denied.status_code == 401
        with app.state.workflow.store.read() as conn:
            assert conn.execute("SELECT count(*) FROM browser_sessions").fetchone()[0] == 2
            assert conn.execute("SELECT count(*) FROM workspaces").fetchone()[0] == 1
        # New issuance is an explicit separate action after the rejected cookie;
        # expired credentials free capacity while all history stays retained.
        client.cookies.clear()
        fresh = bootstrap(client)
        assert fresh != workspace
        assert client.get(PREFIX + "/workspaces/" + workspace).status_code == 404
        assert client.post(PREFIX + "/shared-session/logout").status_code == 200
        with app.state.workflow.store.read() as conn:
            assert conn.execute("SELECT count(*) FROM browser_sessions").fetchone()[0] == 3
            assert conn.execute("SELECT count(*) FROM workspaces").fetchone()[0] == 2
            assert conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0] == 0


def test_local_visitors_cannot_substitute_scientific_or_file_ids(local_access):
    from test_api import prepared
    from general_research_support import SOIL_CSV
    app, settings = local_access
    with browser(local_access) as alice, browser(local_access) as bob, browser(local_access, shared=True) as public:
        first, second, third = bootstrap(alice), bootstrap(bob), bootstrap(public)
        assert len({first, second, third}) == 3
        workspace, dataset, problem, plan, approval = prepared(alice)
        run = post(alice, f"/plans/{plan['id']}/runs", {"approval_id": approval["id"], "expected_plan_digest": plan["digest"]})
        assert Worker(app.state.workflow, adapter=app.state.adapter, settings=settings).tick() == 1
        report = post(alice, f"/runs/{run['id']}/reports", {})
        upload = alice.post(PREFIX + f"/workspaces/{workspace}/research-assets", content=SOIL_CSV,
                            headers={"Content-Type": "text/csv", "X-Source-Name": "control.csv", "Idempotency-Key": "local-upload"})
        assert upload.status_code == 201, upload.json()
        asset = upload.json()
        with app.state.workflow.store.read() as conn:
            actor = conn.execute("SELECT actor_id FROM browser_sessions WHERE workspace_id=?", (first,)).fetchone()[0]
        artifact = ArtifactService(app.state.workflow, settings.artifact_dir).publish(
            actor, workspace, b'{"storage_control":true}', media_type="application/json",
            anchor={"external_input_identity": "storage-control"}, key="local-native")
        paths = [f"/workspaces/{workspace}", f"/records/{dataset['id']}", f"/records/{problem['id']}",
                 f"/records/{plan['id']}", f"/runs/{run['id']}",
                 f"/reports/{report['id']}/download", f"/artifacts/{artifact['id']}", f"/artifacts/{artifact['id']}/anchor",
                 f"/research-assets/{asset['id']}", f"/research-assets/{asset['id']}/content"]
        for path in paths:
            assert alice.get(PREFIX + path).status_code == 200, path
            for intruder in (bob, public):
                assert intruder.get(PREFIX + path).status_code == 404, path
                assert intruder.get(PREFIX + path, headers={"Authorization": "Bearer " + OWNER}).status_code == 403
        for intruder in (bob, public):
            assert intruder.post(PREFIX + f"/runs/{run['id']}/cancel", json={}, headers={"Idempotency-Key": "foreign-cancel"}).status_code == 404
            assert intruder.post(PREFIX + f"/plans/{plan['id']}/runs", json={
                "approval_id": approval["id"], "expected_plan_digest": plan["digest"]},
                headers={"Idempotency-Key": "foreign-run"}).status_code == 404
            assert intruder.post(PREFIX + f"/plans/{plan['id']}/approvals", json={
                "expected_plan_digest": plan["digest"], "expected_current_revision_id": problem["id"], "accepted": True},
                headers={"Idempotency-Key": "foreign-approval"}).status_code == 404


@pytest.mark.parametrize("origin", ["http://example.com:19173", "https://127.0.0.1:19173", "http://127.0.0.1:65536",
                                    "http://127.0.0.1:19173/path", "http://user@127.0.0.1:19173", None])
def test_local_config_cannot_expand_the_http_boundary(local_access, origin):
    with pytest.raises(ValueError, match="explicit loopback HTTP origin"):
        create_app(replace(local_access[1], local_browser_origin=origin))
