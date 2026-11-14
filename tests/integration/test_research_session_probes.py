"""C (independent): coordinator predicates probed through the DB-RESEARCH-1 routes of the actual application.

Frozen predicates: evaluation/coordinator/predicates.v1.json (LOOP-01, LOOP-08, AUTH-01, AUTH-04, AUTH-06).
Until B registers the research-session routes in create_app(), every probe reports NOT_AVAILABLE (xfail), never a
pass. Only HTTP status codes, published DTO fields and side-effect counts read from the store are relied on, so
the probes do not depend on undeclared response details.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bean_api.config import Settings
from bean_api.main import PREFIX, create_app

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "shared/contracts/DB-SC-1/fixtures/synthetic-workflow.json").read_text(encoding="utf-8"))
ALICE, BOB = "a" * 40, "b" * 40
SEGMENT = r"\{[^}/]+\}"
REQUIRED = {
    "create": ("post", rf"{PREFIX}/workspaces/{SEGMENT}/research-sessions"),
    "read": ("get", rf"{PREFIX}/research-sessions/{SEGMENT}"),
    "advance": ("post", rf"{PREFIX}/research-sessions/{SEGMENT}/advance"),
    "decisions": ("post", rf"{PREFIX}/research-sessions/{SEGMENT}/decisions"),
    "reconcile": ("post", rf"{PREFIX}/research-sessions/{SEGMENT}/reconcile"),
    "cancel": ("post", rf"{PREFIX}/research-sessions/{SEGMENT}/cancel"),
    "events": ("get", rf"{PREFIX}/research-sessions/{SEGMENT}/events"),
}


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("BEAN_AI_MODE", "placeholder")
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    application = create_app(Settings(database_path=str(tmp_path / "db.sqlite3"), blob_dir=str(tmp_path / "sources"),
                                      artifact_dir=str(tmp_path / "artifacts"), auth_file=str(tmp_path / "none.json"),
                                      auth_tokens={"alice": ALICE, "bob": BOB}, science_adapter="unavailable"))
    application.state.c_database = tmp_path / "db.sqlite3"
    return application


def registered(application) -> dict[str, str]:
    paths = application.openapi()["paths"]
    found = {}
    for name, (method, pattern) in REQUIRED.items():
        for path, operations in paths.items():
            if method in operations and re.fullmatch(pattern, path):
                found[name] = path
    return found


def require_routes(application) -> dict[str, str]:
    found = registered(application)
    missing = sorted(set(REQUIRED) - set(found))
    if missing:
        pytest.xfail(f"NOT_AVAILABLE: DB-RESEARCH-1 routes not registered in the actual app: {', '.join(missing)}")
    return found


def counts(application) -> dict[str, int]:
    with sqlite3.connect(application.state.c_database) as conn:
        def count(sql):
            try:
                return conn.execute(sql).fetchone()[0]
            except sqlite3.OperationalError:
                return 0
        return {"provider_attempts": count("SELECT count(*) FROM provider_attempts"),
                "jobs": count("SELECT count(*) FROM jobs"),
                "approvals": count("SELECT count(*) FROM approvals"),
                "controlled_attempts": count("SELECT count(*) FROM entities WHERE kind='controlled_attempt'"),
                # DB-RESEARCH-1 tables (an absent table counts 0): a queued action precedes any model turn, effects
                # bind scientific children and attempt bindings record model admissions.
                "research_actions": count("SELECT count(*) FROM research_actions"),
                "research_effects": count("SELECT count(*) FROM research_effects"),
                "research_attempt_bindings": count("SELECT count(*) FROM research_attempt_bindings")}


def client(application, token) -> TestClient:
    result = TestClient(application)
    result.headers["Authorization"] = "Bearer " + token
    return result


def session_for(application, user) -> tuple[str, str, dict]:
    """Ordinary inputs through public routes, then one research session (controlled mode)."""
    workspace = user.post(PREFIX + "/workspaces", json={"name": "C probe"}).json()["id"]
    dataset = user.post(PREFIX + f"/workspaces/{workspace}/datasets", json=FIXTURE["dataset"],
                        headers={"Idempotency-Key": "c-ds"}).json()
    problem = user.post(PREFIX + f"/workspaces/{workspace}/problems",
                        json={**FIXTURE["problem"], "dataset_id": dataset["id"], "dataset_digest": dataset["digest"]},
                        headers={"Idempotency-Key": "c-pr"}).json()
    body = {"schema_version": "DB-RESEARCH-1", "objective": "Is the elimination-rate claim supported by these readings?",
            "problem_id": problem["id"], "expected_problem_digest": problem["digest"], "mode": "controlled"}
    path = registered(application)["create"].replace(re.search(SEGMENT, registered(application)["create"]).group(0),
                                                    workspace)
    response = user.post(path, json=body, headers={"Idempotency-Key": "c-session"})
    assert response.status_code in (200, 201), response.text
    record = response.json()
    session = record.get("research_session_id") or record.get("id")
    assert isinstance(session, str) and session, record
    return workspace, session, record


def route(found: dict[str, str], name: str, session: str) -> str:
    return re.sub(SEGMENT, session, found[name], count=1)


def test_db_research_routes_are_registered_in_the_actual_app(app):
    """Gate 1 availability: the routes exist in create_app() itself, not only in a fixture."""
    require_routes(app)


def test_creating_and_reading_a_research_session_dispatches_nothing(app):
    """LOOP-01 and LOOP-08: creating, reading and polling preserve the question and cause no model or science work."""
    found = require_routes(app)
    alice = client(app, ALICE)
    before = counts(app)
    _, session, record = session_for(app, alice)
    for _ in range(3):
        snapshot = alice.get(route(found, "read", session))
        assert snapshot.status_code == 200
        assert alice.get(route(found, "events", session), params={"after": 0}).status_code == 200
    assert "Is the elimination-rate claim supported by these readings?" in json.dumps(snapshot.json())
    assert "thread" not in json.dumps(snapshot.json()).lower()                       # AUTH-06: thread stays private
    assert counts(app) == before


def test_another_identity_cannot_reach_a_research_session(app):
    """AUTH-01: every read and write on a foreign research session is refused as not found."""
    found = require_routes(app)
    alice, bob = client(app, ALICE), client(app, BOB)
    _, session, _ = session_for(app, alice)
    before = counts(app)
    assert bob.get(route(found, "read", session)).status_code == 404
    assert bob.get(route(found, "events", session), params={"after": 0}).status_code == 404
    for name, body in (("advance", {"expected_revision": 0}),
                       ("decisions", {"expected_revision": 0, "pending_review_id": "review_x", "decision": "approve",
                                      "expected_review_digest": "0" * 64, "accepted": True}),
                       ("reconcile", {"expected_revision": 0, "acknowledged_unknown_outcome": True}),
                       ("cancel", {})):
        response = bob.post(route(found, name, session), json=body, headers={"Idempotency-Key": f"bob-{name}"})
        assert response.status_code == 404, (name, response.status_code)
    assert counts(app) == before


@pytest.mark.parametrize("body", [
    {"expected_revision": 0, "pending_review_id": "review_forged", "expected_review_digest": "0" * 64,
     "decision": "approve", "accepted": True},
    {"expected_revision": 0, "pending_review_id": "review_x", "expected_review_digest": "0" * 64,
     "decision": "approve", "accepted": True, "command": {"resume": {"approved": True}}},
    {"expected_revision": 0, "pending_review_id": "review_x", "expected_review_digest": "0" * 64,
     "decision": "approve", "accepted": True, "actor_id": "owner"},
    {"expected_revision": 0, "pending_review_id": "review_x", "expected_review_digest": "0" * 64,
     "decision": "approve", "accepted": False},
])
def test_decisions_refuse_forged_reviews_raw_commands_and_actor_selection(app, body):
    """AUTH-04 and AUTH-06: only a canonical decision on a real pending review can authorize execution."""
    found = require_routes(app)
    alice = client(app, ALICE)
    _, session, _ = session_for(app, alice)
    before = counts(app)
    response = alice.post(route(found, "decisions", session), json=body, headers={"Idempotency-Key": "c-decision"})
    assert 400 <= response.status_code < 500, response.status_code
    assert counts(app) == before


def test_advance_while_research_dispatch_is_disabled_is_refused_honestly(app):
    """Honest failure state (Gate 4) and LOOP-08: while capabilities report research dispatch disabled, an explicit
    advance is refused with the published unavailable reason and queues no action, child or model admission."""
    found = require_routes(app)
    alice = client(app, ALICE)
    research = alice.get(PREFIX + "/capabilities").json().get("deepagents") or {}
    if research.get("dispatch_enabled") is not False:
        pytest.skip("research dispatch is enabled or unreported in this build; the loop probes cover advance")
    _, session, record = session_for(app, alice)
    before = counts(app)
    response = alice.post(route(found, "advance", session), json={"expected_revision": record.get("revision", 0)},
                          headers={"Idempotency-Key": "c-advance"})
    assert response.status_code == 503, response.text
    assert research.get("unavailable_reason") and research["unavailable_reason"] in response.text, response.text
    assert counts(app) == before
