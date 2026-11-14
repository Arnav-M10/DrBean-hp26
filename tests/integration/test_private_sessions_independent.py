"""C (independent): private browser sessions on the actual application (predicates AUTH-01, AUTH-02, AUTH-03).

Written from the public session interface (cookie name, gateway headers, routes), not from B's tests. Each test
builds its own application on an isolated temporary store with a trusted-gateway file, exactly as the shared
gateway would present requests. No provider, network or launched process is involved.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bean_api.config import Settings
from bean_api.main import PREFIX, create_app
from bean_api.sessions import COOKIE, GATEWAY_HEADER, ORIGIN_HEADER

ROOT = Path(__file__).resolve().parents[2]
ORIGIN = "https://c-independent-probe.trycloudflare.com"
FIXTURE = json.loads((ROOT / "shared/contracts/DB-SC-1/fixtures/synthetic-workflow.json").read_text(encoding="utf-8"))
def _png() -> bytes:
    import io
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (24, 16), (40, 90, 160)).save(buffer, format="PNG")
    return buffer.getvalue()


PNG = _png()


def build(tmp_path, **settings):
    proof, owner = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    gateway = tmp_path / "share-gateway.json"
    gateway.write_text(json.dumps({"version": 1, "secret": proof}), encoding="utf-8")
    gateway.chmod(0o600)
    app = create_app(Settings(database_path=str(tmp_path / "app.sqlite3"), blob_dir=str(tmp_path / "sources"),
                              artifact_dir=str(tmp_path / "artifacts"), auth_file=str(tmp_path / "unused.json"),
                              auth_tokens={"owner": owner}, science_adapter="unavailable",
                              shared_gateway_file=str(gateway), **settings))
    headers = {GATEWAY_HEADER: proof, ORIGIN_HEADER: ORIGIN, "Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"}
    return app, headers, owner


def visitor(app, headers) -> TestClient:
    return TestClient(app, base_url=ORIGIN, headers=headers)


def bootstrap(client) -> str:
    response = client.get(PREFIX + "/shared-session")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "browser_session" and body["authenticated"] is True and COOKIE not in json.dumps(body)
    return body["workspace_id"]


def private_work(client, workspace) -> dict:
    """Ordinary scientific inputs and a retained source, created through public routes only."""
    def post(path, body, key):
        response = client.post(PREFIX + path, json=body, headers={"Idempotency-Key": key})
        assert response.status_code == 201, response.text
        return response.json()
    dataset = post(f"/workspaces/{workspace}/datasets", FIXTURE["dataset"], "c-dataset")
    problem = post(f"/workspaces/{workspace}/problems", {**FIXTURE["problem"], "dataset_id": dataset["id"],
                                                         "dataset_digest": dataset["digest"]}, "c-problem")
    source = client.post(PREFIX + f"/workspaces/{workspace}/source-assets?origin=synthetic&retention=retain",
                         content=PNG, headers={"Content-Type": "image/png", "Idempotency-Key": "c-source"})
    assert source.status_code == 201, source.text
    return {"dataset": dataset["id"], "problem": problem["id"], "source": source.json()["id"]}


def test_two_private_contexts_cannot_read_or_write_each_others_work(tmp_path):
    """AUTH-01: every cross-context read and write is refused as not found and changes nothing."""
    app, headers, _ = build(tmp_path)
    with visitor(app, headers) as alice, visitor(app, headers) as bob:
        mine, theirs = bootstrap(alice), bootstrap(bob)
        assert mine != theirs
        work = private_work(alice, mine)
        before = {kind: len(alice.get(PREFIX + f"/workspaces/{mine}/records", params={"kind": kind}).json())
                  for kind in ("dataset", "problem", "source_asset")}
        reads = [f"/workspaces/{mine}", f"/workspaces/{mine}/records?kind=dataset", f"/records/{work['dataset']}",
                 f"/records/{work['problem']}", f"/source-assets/{work['source']}",
                 f"/source-assets/{work['source']}/content", f"/workspaces/{mine}/provider-attempts",
                 f"/workspaces/{mine}/provider-budget", f"/workspaces/{mine}/activity"]
        for path in reads:
            response = bob.get(PREFIX + path)
            assert response.status_code == 404, (path, response.status_code)
        writes = [(f"/workspaces/{mine}/datasets", FIXTURE["dataset"]),
                  (f"/workspaces/{mine}/problems", {**FIXTURE["problem"], "dataset_id": work["dataset"],
                                                    "dataset_digest": "0" * 64})]
        for path, body in writes:
            response = bob.post(PREFIX + path, json=body, headers={"Idempotency-Key": "bob-write"})
            assert response.status_code == 404, (path, response.status_code)
        upload = bob.post(PREFIX + f"/workspaces/{mine}/source-assets?origin=synthetic&retention=retain",
                          content=PNG, headers={"Content-Type": "image/png", "Idempotency-Key": "bob-upload"})
        assert upload.status_code == 404
        assert [w["id"] for w in bob.get(PREFIX + "/workspaces").json()] == [theirs]
        after = {kind: len(alice.get(PREFIX + f"/workspaces/{mine}/records", params={"kind": kind}).json())
                 for kind in ("dataset", "problem", "source_asset")}
        assert after == before


def test_no_owner_fallback_and_forged_or_missing_sessions_are_refused(tmp_path):
    """AUTH-02: no cookie, a forged cookie, a malformed cookie or an owner bearer on the gateway lane never
    reaches the owner's or another visitor's data; a new visitor gets a new private workspace."""
    app, headers, owner = build(tmp_path)
    with TestClient(app, headers={"Authorization": "Bearer " + owner}) as local:
        response = local.post(PREFIX + "/workspaces", json={"name": "Owner research"})
        assert response.status_code == 201
        owner_workspace = response.json()["id"]
    with visitor(app, headers) as alice:
        mine = bootstrap(alice)
    anonymous = TestClient(app, base_url=ORIGIN, headers=headers)
    assert anonymous.get(PREFIX + "/workspaces").status_code == 401
    forged = TestClient(app, base_url=ORIGIN, headers={**headers, "Cookie": f"{COOKIE}={secrets.token_urlsafe(32)}"})
    assert forged.get(PREFIX + "/workspaces").status_code == 401
    malformed = TestClient(app, base_url=ORIGIN, headers={**headers, "Cookie": f"{COOKIE}=not-a-token"})
    assert malformed.get(PREFIX + "/workspaces").status_code == 401
    bearer = TestClient(app, base_url=ORIGIN, headers={**headers, "Authorization": "Bearer " + owner})
    response = bearer.get(PREFIX + "/workspaces")
    assert response.status_code == 403 and owner_workspace not in response.text
    with TestClient(app, headers={"Authorization": "Bearer " + owner}) as local:
        assert local.get(PREFIX + f"/workspaces/{mine}").status_code == 404
    with visitor(app, headers) as newcomer:
        fresh = bootstrap(newcomer)
        assert fresh not in {mine, owner_workspace}
        assert [w["id"] for w in newcomer.get(PREFIX + "/workspaces").json()] == [fresh]


def test_rotation_keeps_identity_and_expiry_refuses_without_erasing_work(tmp_path):
    """AUTH-03: rotation keeps the identity and its work; the old token stops working; after expiry access is
    refused, the retained records still exist, and a new anonymous identity cannot reach them by ID."""
    app, headers, _ = build(tmp_path)
    with visitor(app, headers) as alice:
        mine = bootstrap(alice)
        work = private_work(alice, mine)
        old_token = alice.cookies.get(COOKIE)
        rotated = alice.post(PREFIX + "/shared-session/rotate")
        assert rotated.status_code == 200 and rotated.json()["workspace_id"] == mine
        assert alice.cookies.get(COOKIE) != old_token
        assert alice.get(PREFIX + f"/records/{work['dataset']}").status_code == 200
        stale = TestClient(app, base_url=ORIGIN, headers={**headers, "Cookie": f"{COOKIE}={old_token}"})
        assert stale.get(PREFIX + f"/records/{work['dataset']}").status_code == 401
        clock = app.state.sessions.clock
        app.state.sessions.clock = lambda: clock() + app.state.sessions.ttl_seconds + 1
        expired = alice.get(PREFIX + f"/records/{work['dataset']}")
        assert expired.status_code == 401
    with sqlite3.connect(tmp_path / "app.sqlite3") as conn:
        retained = conn.execute("SELECT count(*) FROM entities WHERE workspace_id=?", (mine,)).fetchone()[0]
    assert retained >= 3                                          # dataset, problem and source are kept
    app.state.sessions.clock = clock
    with visitor(app, headers) as successor:
        other = bootstrap(successor)
        assert other != mine
        for record in work.values():
            assert successor.get(PREFIX + f"/records/{record}").status_code == 404


@pytest.mark.xfail(strict=True, reason="F-SESSION-CAPACITY-EXHAUSTION (B): anonymous bootstraps consume permanent "
                                       "issuance capacity, including revoked and expired sessions")
def test_anonymous_bootstraps_cannot_permanently_lock_out_new_visitors(tmp_path):
    """Availability probe: once every issued session is logged out or expired, a new visitor can still start a
    private workspace. Capacity is reduced to 3 here only to make the probe fast; the default is 4096."""
    app, headers, _ = build(tmp_path, browser_session_capacity=3)
    for _ in range(3):
        with visitor(app, headers) as anyone:
            bootstrap(anyone)
            assert anyone.post(PREFIX + "/shared-session/logout").status_code == 200
    with visitor(app, headers) as newcomer:
        assert newcomer.get(PREFIX + "/shared-session").status_code == 200
