"""Owner 4: paper routes through the real application. Skips until Owner 2 registers them
(docs/proposals/owner2-paper-routes.patch). Zero provider dispatch is enforced by socket denial."""
from __future__ import annotations

import hashlib
from pathlib import Path
import socket

import pytest

pytest.importorskip("pypdf", reason="pypdf is not installed; Owner 2 pins it")
pytest.importorskip("pypdfium2", reason="pypdfium2 is not installed; Owner 2 pins it")

from fastapi.testclient import TestClient  # noqa: E402

from bean_api.config import Settings  # noqa: E402
from bean_api.main import PREFIX, create_app  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "papers"


@pytest.fixture
def client(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Paper routes must not open network connections")
    settings = Settings(database_path=str(tmp_path / "db.sqlite"), blob_dir=str(tmp_path / "sources"),
                        artifact_dir=str(tmp_path / "artifacts"), auth_tokens={"alice": "a" * 40, "bob": "b" * 40},
                        science_adapter="unavailable")
    app = create_app(settings)
    if not any(getattr(route, "path", "") == PREFIX + "/workspaces/{workspace_id}/papers" for route in app.routes):
        pytest.skip("paper routes are not registered yet (Owner 2: docs/proposals/owner2-paper-routes.patch)")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    with TestClient(app) as test_client:
        yield test_client


def headers(who="a", key=None, mime=None):
    result = {"Authorization": "Bearer " + who * 40}
    if key:
        result["Idempotency-Key"] = key
    if mime:
        result["Content-Type"] = mime
    return result


def workspace(client, who="a"):
    return client.post(PREFIX + "/workspaces", json={"name": "Papers"}, headers=headers(who, "ws")).json()["id"]


def upload(client, scope, name="synthetic-native.pdf", key="up", who="a", raw=None):
    raw = raw if raw is not None else (FIXTURES / name).read_bytes()
    return client.post(PREFIX + f"/workspaces/{scope}/papers?origin=synthetic&retention=retain&filename={name}",
                       content=raw, headers=headers(who, key, "application/pdf"))


def test_capabilities_advertise_paper_limits_and_no_model_extraction(client):
    caps = client.get(PREFIX + "/capabilities").json()["paper_intake"]
    assert (caps["max_bytes"], caps["max_pages"], caps["max_pages_per_batch"]) == (20 * 1024 * 1024, 50, 8)
    assert caps["available"] is True and caps["model_extraction"].startswith("unavailable")


def test_upload_pages_preview_selection_and_citation(client):
    scope = workspace(client)
    response = upload(client, scope, "statistical-trap.pdf")
    assert response.status_code == 201, response.text
    paper = response.json()
    assert upload(client, scope, "statistical-trap.pdf").json() == paper  # retry: same identity
    assert client.get(PREFIX + f"/workspaces/{scope}/papers", headers=headers()).json() == [paper]
    content = client.get(PREFIX + f"/papers/{paper['id']}/content", headers=headers())
    assert hashlib.sha256(content.content).hexdigest() == paper["body"]["sha256"] == content.headers["x-artifact-sha256"]
    text = client.get(PREFIX + f"/papers/{paper['id']}/pages/2/text", headers=headers()).json()
    assert "SEM, not SD" in text["text"] and text["printed_label"] == "2"
    preview = client.get(PREFIX + f"/papers/{paper['id']}/pages/1/preview", headers=headers())
    assert preview.headers["content-type"] == "image/png" and hashlib.sha256(preview.content).hexdigest() == preview.headers["x-artifact-sha256"]
    selection = client.post(PREFIX + f"/papers/{paper['id']}/page-selections", json={"pages": [2]}, headers=headers(key="sel")).json()
    assert selection["body"]["mapping"][0]["physical_page"] == 2
    subset = client.get(PREFIX + f"/paper-page-selections/{selection['id']}/content", headers=headers())
    assert hashlib.sha256(subset.content).hexdigest() == selection["body"]["subset_sha256"]
    check = client.post(PREFIX + f"/papers/{paper['id']}/citation-checks", json={"page": 1, "excerpt": "SEM, not SD"}, headers=headers()).json()
    assert check["quotation"]["status"] == "wrong_page"
    assert client.get(PREFIX + f"/workspaces/{scope}/provider-attempts", headers=headers()).json() == []


def test_refusals_use_the_standard_error_body(client):
    scope = workspace(client)
    for raw, code in ((b"\x89PNG\r\n\x1a\n0000", "media_type_mismatch"), (b"%PDF-1.7\n\x00bad", "malformed_pdf")):
        response = upload(client, scope, raw=raw, key=code)
        assert response.status_code == 422 and response.json()["code"] == code and response.json()["request_id"]
    too_big = upload(client, scope, raw=b"%PDF-1.7\n" + b"0" * (20 * 1024 * 1024), key="big")
    assert too_big.status_code == 413
    assert client.get(PREFIX + f"/workspaces/{scope}/papers", headers=headers()).json() == []


def test_other_workspaces_cannot_reach_any_paper_route(client):
    scope = workspace(client)
    paper = upload(client, scope).json()
    selection = client.post(PREFIX + f"/papers/{paper['id']}/page-selections", json={"pages": [1]}, headers=headers(key="s")).json()
    for path in (f"/papers/{paper['id']}", f"/papers/{paper['id']}/content", f"/papers/{paper['id']}/pages/1/text",
                 f"/papers/{paper['id']}/pages/1/preview", f"/paper-page-selections/{selection['id']}/content"):
        assert client.get(PREFIX + path, headers=headers("b")).status_code == 404, path
    assert client.post(PREFIX + f"/papers/{paper['id']}/page-selections", json={"pages": [1]}, headers=headers("b", "x")).status_code == 404
