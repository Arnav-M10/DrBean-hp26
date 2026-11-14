"""Actual native science through restricted deepagents, with a local controlled model.

Only measurements and model decisions are synthetic. Candidates and native evidence
are computed through the ordinary adapter; no provider network dispatch is allowed.
"""
import json
import socket

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from bean_api.main import PREFIX
from bean_api.providers import ProviderConfig
from bean_api.worker import Worker
import test_scientific_http as scientific_http
import test_baseline_workflow as baseline
from test_scientific_http import post
from test_counterdex_adapter import reviewed_history

scientific_client = scientific_http.scientific_client
replay_python = baseline.replay_python

OBJECTIVE = {"question": "Does the checked baseline justify the reviewed optional comparison?",
             "success_criterion": "Account for each approved scenario using its actual evidence."}


@pytest.fixture(autouse=True)
def deny_external_dispatch(scientific_client, monkeypatch):
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    attempted = []
    def reject(self, address):
        attempted.append(address)
        raise AssertionError("Controlled acceptance must not dispatch any network request")
    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket.socket, "connect_ex", reject)
    yield
    assert attempted == []


class NativeDecisionModel(BaseChatModel):
    """Explicit controlled test decisions, never a hosted model implementation."""
    model_name: str = "bean-controlled-native-acceptance"
    mode: str = "adapt"
    offered: list[str] = []

    @property
    def _llm_type(self):
        return "bean-controlled-native"

    def bind_tools(self, tools, **kwargs):
        self.offered = sorted(tool.name for tool in tools)
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        observed = [json.loads(message.content) for message in messages if isinstance(message, ToolMessage)]
        if not observed:
            tool, args = "execute_approved_scenario", {"scenario_id": "baseline"}
        elif len(observed) == 1:
            # The integrated coordinator now requires optional disposition
            # before explaining. Exercise bad narration only after that valid
            # prerequisite, rather than masking it with incomplete accounting.
            if self.mode == "force_optional" or observed[0]["scientific_outcome"] != "certified_counterexample":
                tool, args = "execute_approved_scenario", {"scenario_id": "optional"}
            else:
                tool, args = "record_allowed_skip", {"scenario_id": "optional", "reason_code": "sufficient_evidence"}
        else:
            text = "The returned evidence has the stated conditional scope."
            if self.mode == "bad_narration":
                text = "This proves the interval and identifies the true parameter."
            tool, args = "return_grounded_explanation", {
                "fact_ids": [observed[0]["id"]], "text": text, "next_action": "stop"}
        message = AIMessage(content="", tool_calls=[{
            "id": f"call-{len(observed)}", "name": tool, "args": args, "type": "tool_call"}])
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._generate(messages, stop, run_manager, **kwargs)


def prepare_controlled_run(client, *, wide=False, mode="adapt"):
    workspace = post(client, "/workspaces", {"name": "Controlled agent with actual native science"}, "workspace")["id"]
    # Reviewed synthetic inputs only; reviewed_history supplies no candidates.
    # Two exact replicates keep the same scientific constraints while making
    # genuine full replay facts larger than the coordinator's 12 KB fact cap.
    inputs = reviewed_history()
    data = inputs["dataset"]["body"]
    data["rows"] += [{**row, "id": "replicate-" + row["id"]} for row in data["rows"][:2]]
    dataset = post(client, f"/workspaces/{workspace}/datasets", data, "dataset")
    problem_body = inputs["problem"]["body"]
    optional_problem = post(client, f"/workspaces/{workspace}/problems", {
        **problem_body, "dataset_id": dataset["id"], "dataset_digest": dataset["digest"],
        "target": {"lower": "1/10", "upper": "11/100"}}, "optional-problem")
    target = problem_body["domain"]["ke"] if wide else problem_body["target"]
    problem = post(client, f"/workspaces/{workspace}/problems", {
        **problem_body, "dataset_id": dataset["id"], "dataset_digest": dataset["digest"], "target": target}, "problem")
    model = NativeDecisionModel(mode=mode)
    consent = post(client, f"/workspaces/{workspace}/provider-consents", {
        "provider": "gemini", "model": model.model_name, "source_asset_ids": [],
        "context_fields": ["problem", "dataset"], "problem_id": problem["id"], "accepted": True}, "consent")
    shared = {"problem_id": problem["id"], "problem_digest": problem["digest"]}
    plan = post(client, f"/workspaces/{workspace}/plans", {
        "expected_current_revision_id": problem["id"], "plan": {
            **shared, "dataset_id": dataset["id"], "scientific_profile": "counterdex.v1", "objective": OBJECTIVE,
            "scenarios": [{**shared, "id": "baseline", "kind": "baseline", "label": "Computed baseline"},
                          {"problem_id": optional_problem["id"], "problem_digest": optional_problem["digest"],
                           "id": "optional", "kind": "optional", "label": "Reviewed narrower range",
                           "purpose": "Compare the separately reviewed narrower range when baseline found no outside witness.",
                           "eligible_baseline_outcomes": ["no_counterexample_found", "inconclusive"]}],
            "provider_disclosure": {"provider": "gemini", "model": model.model_name, "source_asset_ids": [],
                "context_fields": ["problem", "dataset"], "permission_id": consent["id"]}}}, "plan")
    approval = post(client, f"/plans/{plan['id']}/approvals", {
        "expected_current_revision_id": problem["id"], "expected_plan_digest": plan["digest"], "accepted": True}, "approval")
    start = {"approval_id": approval["id"], "expected_plan_digest": plan["digest"]}
    run = post(client, f"/plans/{plan['id']}/runs", start, "start")
    config = ProviderConfig(api_key="synthetic-no-network", model=model.model_name,
        account_gate_passed=True, account_decision_id="controlled-native-test-only", max_input_tokens=64_000)
    worker = Worker(client.app.state.workflow, settings=client.app.state.settings,
                    provider_config=config, controlled_model=model)
    assert worker.tick() == 1
    finished = client.get(PREFIX + f"/runs/{run['id']}").json()
    assert post(client, f"/plans/{plan['id']}/runs", start, "retry")["id"] == run["id"]
    assert worker.tick() == 0
    return workspace, dataset, problem, plan, finished, model


def evidence_for(client, run, scenario_id="baseline"):
    scenario = next(item for item in run["scenarios"] if item["scenario_id"] == scenario_id)
    assert scenario["state"] == "completed", scenario
    return client.get(PREFIX + f"/records/{scenario['result_id']}").json()


def verify_download(client, run, record, replay_python, tmp_path):
    result = record["body"]["result"]
    assert result["verification"] == "valid" and result["replay"] == "passed"
    assert result["baseline_search"]["attempted_count"] > 0
    assert result["candidates"]
    artifact = result["artifacts"][0]
    response = client.get(PREFIX + f"/artifacts/{artifact['id']}")
    assert response.status_code == 200
    anchors = client.get(PREFIX + f"/artifacts/{artifact['id']}/anchor?download=true").json()
    assert anchors["run_id"] == run["id"] and anchors["problem_digest"] == result["problem_digest"]
    process, fresh = baseline.replay_cli(replay_python, tmp_path, response.content, anchors)
    assert process.returncode == 0, fresh
    assert fresh["integrity"] == fresh["replay"] == "passed"
    assert fresh["verification"] == "valid" and fresh["expected_binding"] == "matches"
    assert fresh["search_replayed"] is False
    assert fresh["outcome"]["scientific_outcome"] == result["scientific_outcome"]


@pytest.mark.parametrize("wide,expected,optional_state,reservations", [
    (False, "certified_counterexample", "skipped", 1),
    (True, "no_counterexample_found", "completed", 2),
])
def test_controlled_graph_adapts_to_actual_native_evidence(scientific_client, replay_python, tmp_path,
                                                         wide, expected, optional_state, reservations):
    client = scientific_client
    workspace, _, _, plan, run, model = prepare_controlled_run(client, wide=wide)
    assert run["state"] == "completed", run
    assert plan["body"]["objective"] == {"version": "research-objective.v1", **OBJECTIVE}
    baseline_record = evidence_for(client, run)
    assert baseline_record["body"]["result"]["scientific_outcome"] == expected
    assert len(json.dumps({"id": baseline_record["id"], **baseline_record["body"]["result"]}).encode()) > 12_000
    verify_download(client, run, baseline_record, replay_python, tmp_path)
    optional = next(item for item in run["scenarios"] if item["scenario_id"] == "optional")
    assert optional["state"] == optional_state
    if optional_state == "completed":
        optional_record = evidence_for(client, run, "optional")
        assert optional_record["id"] != baseline_record["id"]
        assert optional_record["body"]["result"]["problem_id"] == plan["body"]["scenarios"][1]["problem_id"]
        assert optional_record["body"]["result"]["problem_id"] != baseline_record["body"]["result"]["problem_id"]
        assert optional_record["body"]["result"]["scientific_outcome"] == "certified_counterexample"
        verify_download(client, run, optional_record, replay_python, tmp_path)
    assert run["scientific_reservations"] == reservations
    assert run["provider_turns"] == run["tool_calls"] == 3
    workflow = client.app.state.workflow
    attempts = workflow.list_records("alice", workspace, "controlled_attempt")
    outcomes = workflow.list_records("alice", workspace, "controlled_outcome")
    assert len(attempts) == len(outcomes) == 3
    assert all(item["body"]["external_provider_calls"] == item["body"]["actual_model_tokens"] == 0 for item in attempts + outcomes)
    assert client.get(PREFIX + f"/workspaces/{workspace}/provider-attempts").json() == []
    summary = client.get(PREFIX + f"/records/{run['result_id']}").json()["body"]
    assert summary["execution_lane"] == "controlled_placeholder" and summary["external_provider_calls"] == 0
    assert summary["runtime"]["execution_lane"] == "controlled_model" and summary["runtime"]["live_qualified"] is False
    assert summary["explanation"]["fact_ids"] == [baseline_record["id"]]
    assert summary["explanation"]["scientific_authority"] is False
    assert summary["evidence"]
    for fact in summary["evidence"]:
        assert len(json.dumps(fact).encode()) <= 12_000
        assert "native_replay" not in fact
        assert fact["id"] in {item["result_id"] for item in run["scenarios"]}
    events = workflow.list_records("alice", workspace, "agent_event")
    requested = [item["body"]["tool"] for item in events if item["body"]["type"] == "tool_request"]
    assert requested == ["execute_approved_scenario", "execute_approved_scenario" if wide else "record_allowed_skip",
                         "return_grounded_explanation"]
    assert model.offered == ["execute_approved_scenario", "read_scoped_evidence", "record_allowed_skip",
                             "return_grounded_explanation"]


@pytest.mark.parametrize("mode,error", [("bad_narration", "explanation_unsupported_claim"),
                                       ("force_optional", "scenario_condition_ineligible")])
def test_bad_controlled_actions_preserve_completed_native_evidence(scientific_client, replay_python, tmp_path, mode, error):
    client = scientific_client
    workspace, _, _, _, run, _ = prepare_controlled_run(client, mode=mode)
    assert run["state"] == "failed" and run["error_code"] == error, run
    record = evidence_for(client, run)
    assert record["body"]["result"]["scientific_outcome"] == "certified_counterexample"
    verify_download(client, run, record, replay_python, tmp_path)
    assert run["scientific_reservations"] == 1
    assert all(item["scenario_id"] != "optional" or item["state"] != "completed" for item in run["scenarios"])
    assert client.get(PREFIX + f"/workspaces/{workspace}/provider-attempts").json() == []
