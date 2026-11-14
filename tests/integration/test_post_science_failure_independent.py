"""C (independent): SCI-08. A model failure after a completed scientific child keeps that child's evidence and its
native downloads, and replay neither upgrades the recorded outcome nor certifies any narration.

Frozen predicate SCI-08 (evaluation/coordinator/predicates.v1.json). The application runs in process with the
actual Counterdex adapter and the ordinary Worker. A C-authored controlled chat model requests the approved baseline,
then fails the way an unavailable provider would; it never constructs a client. The run is controlled
model plus actual science (lane controlled_science). There is no provider key, only a labelled dummy value. The
session egress guard is active. The inputs are C's own hero packet, and a variant widens the claim to the whole
admitted ke domain so the search can only end without an outside witness.
"""
from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from drbean_support import REPO, launcher, load_packet
from drbean_eval import native
from drbean_eval import science_flow as sf

pytestmark = [pytest.mark.real_science]

HERO = load_packet("hero-v2")
ALICE = "c" * 40
DUMMY_KEY = "DRBEAN-DUMMY-c-post-science-failure"


class FailsAfterScience(BaseChatModel):
    """Requests the approved baseline once, then fails like an unavailable provider. Test-only, no client."""

    model_name: str = "c-controlled-post-science-failure"
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "c-controlled-post-science-failure"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls += 1
        if not any(isinstance(message, ToolMessage) for message in messages):
            call = {"id": "c-call-0", "name": "execute_approved_scenario", "args": {"scenario_id": "baseline"},
                    "type": "tool_call"}
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[call]))])
        raise RuntimeError("controlled provider unavailable after the scientific child (C test double)")

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._generate(messages, stop, run_manager, **kwargs)


@pytest.fixture
def science():
    try:
        return launcher.science_python()
    except launcher.StackError as error:
        pytest.fail(f"the controlled_science lane needs the qualified CPython 3.11 engine interpreter: {error}")


@pytest.fixture
def app(tmp_path, science, monkeypatch):
    from bean_api.config import Settings
    from bean_api.main import create_app
    monkeypatch.setenv("BEAN_AI_MODE", "placeholder")
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(database_path=str(tmp_path / "db.sqlite3"), blob_dir=str(tmp_path / "sources"),
                        artifact_dir=str(tmp_path / "artifacts"), auth_file=str(tmp_path / "none.json"),
                        counterdex_python=science, auth_tokens={"alice": ALICE})
    with TestClient(create_app(settings)) as client:
        client.headers["Authorization"] = "Bearer " + ALICE
        yield client


def post(client, path, body, key):
    from bean_api.main import PREFIX
    response = client.post(PREFIX + path, json=body, headers={"Idempotency-Key": key})
    assert response.status_code in (200, 201, 202), (path, response.status_code, response.text)
    return response.json()


def get(client, path):
    from bean_api.main import PREFIX
    response = client.get(PREFIX + path)
    assert response.status_code == 200, (path, response.status_code, response.text)
    return response


def run_with_failing_model(client, *, widen: bool):
    from bean_api.providers import ProviderConfig
    from bean_api.worker import Worker
    model = FailsAfterScience()
    workspace = post(client, "/workspaces", {"name": "C post-science failure"}, "ws")["id"]
    dataset = post(client, f"/workspaces/{workspace}/datasets", HERO["dataset"], "dataset")
    problem_body = {**HERO["problem"], "dataset_id": dataset["id"], "dataset_digest": dataset["digest"]}
    if widen:
        parameter = HERO["problem"]["target"]["parameter"]
        domain = HERO["problem"]["domain"][parameter]
        problem_body["target"] = {**HERO["problem"]["target"], "lower": domain["lower"], "upper": domain["upper"]}
    problem = post(client, f"/workspaces/{workspace}/problems", problem_body, "problem")
    consent = post(client, f"/workspaces/{workspace}/provider-consents", {
        "provider": "gemini", "model": model.model_name, "source_asset_ids": [], "context_fields": ["problem", "dataset"],
        "problem_id": problem["id"], "accepted": True}, "consent")
    shared = {"problem_id": problem["id"], "problem_digest": problem["digest"]}
    plan = post(client, f"/workspaces/{workspace}/plans", {"expected_current_revision_id": problem["id"], "plan": {
        **shared, "dataset_id": dataset["id"], "schema_version": "DB-SC-1", "scientific_profile": sf.SCIENTIFIC_PROFILE,
        "objective": sf.OBJECTIVE, "scenarios": [{**shared, "id": "baseline", "kind": "baseline",
                                                  "label": "Reviewed baseline"}],
        "provider_disclosure": {"provider": "gemini", "model": model.model_name, "source_asset_ids": [],
                                "context_fields": ["problem", "dataset"], "permission_id": consent["id"]}}}, "plan")
    approval = post(client, f"/plans/{plan['id']}/approvals", {"expected_current_revision_id": problem["id"],
                    "expected_plan_digest": plan["digest"], "accepted": True}, "approval")
    run = post(client, f"/plans/{plan['id']}/runs", {"approval_id": approval["id"],
               "expected_plan_digest": plan["digest"]}, "run")
    config = ProviderConfig(api_key=DUMMY_KEY, model=model.model_name, account_gate_passed=True,
                            account_decision_id="c-controlled-post-science-failure-test-only", max_input_tokens=64_000)
    worker = Worker(client.app.state.workflow, settings=client.app.state.settings, provider_config=config,
                    controlled_model=model)
    assert worker.tick() == 1
    return workspace, get(client, f"/runs/{run['id']}").json(), model


@pytest.mark.parametrize("widen, outcome", [(False, "certified_counterexample"), (True, "no_counterexample_found")],
                         ids=["outside_witness", "no_candidate_found"])
def test_model_failure_after_science_keeps_evidence_downloads_and_the_recorded_outcome(app, science, tmp_path,
                                                                                         widen, outcome):
    workspace, run, model = run_with_failing_model(app, widen=widen)
    # The run fails honestly after the child: a failure code, never a scientific outcome or a completed explanation.
    assert run["state"] == "failed" and run.get("error_code"), run
    assert model.calls == 2  # one decision, then the failure; no hidden retry
    child = next(item for item in run["scenarios"] if item["scenario_id"] == "baseline")
    assert child["state"] == "completed" and child.get("result_id"), child
    first = get(app, f"/records/{child['result_id']}").json()
    result = first["body"]["result"]
    assert result["scientific_outcome"] == outcome and result["verification"] == "valid"
    assert not sf._overclaims(run) and not sf._overclaims(result)
    # Native bytes and the separately authenticated anchor are still served and still bind.
    artifact = result["artifacts"][0]
    data = get(app, f"/artifacts/{artifact['id']}").content
    assert hashlib.sha256(data).hexdigest() == artifact["sha256"] and len(data) == artifact["byte_size"]
    anchor = get(app, f"/artifacts/{artifact['id']}/anchor?download=true").json()
    assert anchor.get("run_id") == run["id"]
    replayed = native.replay(science, str(REPO / "packages" / "groundwork_adapter"), data, {},
                             application_anchor=anchor)
    report = replayed.get("report") or {}
    assert replayed["status"] == "passed" and report.get("integrity") == "passed", replayed
    assert report.get("expected_binding") == "matches"
    # Replay re-runs the same checker: it reproduces the recorded outcome and cannot upgrade it.
    assert (report.get("outcome") or {}).get("scientific_outcome") == outcome, report.get("outcome")
    # The evidence record is unchanged by the failure and by being read again.
    again = get(app, f"/records/{child['result_id']}").json()
    assert json.dumps(again, sort_keys=True) == json.dumps(first, sort_keys=True)
    # A controlled test double is not a physical provider request.
    assert get(app, f"/workspaces/{workspace}/provider-attempts").json() == []
