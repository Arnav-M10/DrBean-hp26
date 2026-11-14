"""New parent factory + actual provider-free child, through a component adapter.

The local ports adapter invokes existing authenticated scientific API/Worker
operations. Its pending-review view, plan/events and turn admission are test
scaffolding; InMemorySaver is explicitly NOT B's durable research backend. This
does not assert a new research route, restart durability or browser integration.
"""
import asyncio
import base64
from copy import deepcopy
import hashlib
import json
import socket

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

from bean_api.agent_evidence import project_evidence_fact
from bean_api.canonical import canonical_bytes
from bean_api.contracts import PlanBody
from bean_api.coordinator import CoordinatorFailure
from bean_api.main import PREFIX
from bean_api.research_coordinator import PORT_VERSION, TOOLS, ResearchContext, create_research_coordinator
from bean_api.worker import Worker
import test_baseline_workflow as baseline
from test_counterdex_adapter import reviewed_history
import test_scientific_http as scientific_http
from test_scientific_http import post

scientific_client = scientific_http.scientific_client
replay_python = baseline.replay_python
QUESTION = "Do these reviewed measurements support my parameter range, and what should I measure next?"


class NativeParentModel(BaseChatModel):
    """Controlled policy reads returned evidence; no fixture/outcome switch."""

    model_name: str = "bean-controlled-research-native"
    offered: list[str] = []
    questions: list[str] = []
    observed_outcome: str | None = None

    @property
    def _llm_type(self):
        return "bean-controlled-research-native"

    def bind_tools(self, tools, **kwargs):
        self.offered = sorted(tool.name for tool in tools)
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        envelope = json.loads(next(message.content for message in messages if isinstance(message, HumanMessage)))
        self.questions.append(envelope["question"])
        observed = [message for message in messages if isinstance(message, ToolMessage)]
        if not observed:
            tool, args = "write_todos", {"todos": [
                {"content": "Review the proposed investigation before scientific execution", "status": "in_progress"},
                {"content": "Inspect actual evidence before proposing the next measurement", "status": "pending"}]}
        elif observed[-1].name == "write_todos":
            tool, args = "prepare_scientific_proposal", {"kind": "investigation",
                "reference_ids": [envelope["reviewed_context"]["problem_id"]]}
        elif observed[-1].name == "prepare_scientific_proposal":
            proposal = json.loads(observed[-1].content)
            tool, args = "run_scientific_operation", {
                key: proposal[key] for key in ("proposal_id", "proposal_digest", "review_id", "review_digest")}
        else:
            assert observed[-1].name == "run_scientific_operation"
            result = json.loads(observed[-1].content)
            fact = result["evidence"]
            self.observed_outcome = fact["scientific_outcome"]
            checked_pair = (fact["verification"] == "valid" and fact["expected_binding"] == "matches"
                            and fact["replay"] == "passed" and len(fact["candidates"]) == 2
                            and all(row["verification"] == "valid" for row in fact["candidate_results"]))
            next_action = "review_design" if checked_pair and self.observed_outcome == "certified_counterexample" else "stop"
            tool, args = "publish_research_report", {"evidence_ids": [fact["id"]],
                "text": "The evidence has a conditional scope.", "next_action": next_action}
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[{
            "id": f"controlled-{len(observed)}", "name": tool, "args": args, "type": "tool_call"}]))])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._generate(messages, stop, run_manager, **kwargs)


class NativeSciencePorts:
    """Component glue only; canonical plan/approval/job/evidence are real records."""

    version = PORT_VERSION

    def __init__(self, client, workspace, dataset, problem):
        self.client, self.workspace, self.dataset, self.problem = client, workspace, dataset, problem
        self.plan = self.approval = self.run = self.record = self.report = None
        self.events, self.plans, self.turns, self.commentaries = [], [], [], []
        self.admitted_tools = []

    def check_authority(self):
        response = self.client.get(PREFIX + f"/workspaces/{self.workspace}")
        assert response.status_code == 200

    def admit_model_turn(self, action_id, turn):
        self.turns.append((action_id, turn))  # Test observation, not a durable allocation service.

    def admit_tool(self, name):
        # Test-local logical admission observation, not B's canonical budget.
        assert name in TOOLS and len(self.admitted_tools) < 6
        self.admitted_tools.append(name)

    def record_plan(self, todos, plan_digest, evidence=None):
        assert plan_digest == hashlib.sha256(canonical_bytes(todos)).hexdigest()
        self.plans.append(deepcopy(todos))

    def prepare_proposal(self, kind, reference_ids):
        assert kind == "investigation" and reference_ids == [self.problem["id"]]
        body = PlanBody(problem_id=self.problem["id"], problem_digest=self.problem["digest"],
            dataset_id=self.dataset["id"], scientific_profile="counterdex.v1",
            objective={"question": QUESTION, "success_criterion": "Preserve the checked outcome and its limitations."},
            scenarios=[{"id": "baseline", "kind": "baseline", "label": "Actual bounded investigation",
                        "problem_id": self.problem["id"], "problem_digest": self.problem["digest"]}]).model_dump(mode="json")
        self.plan = post(self.client, f"/workspaces/{self.workspace}/plans", {
            "expected_current_revision_id": self.problem["id"], "plan": body}, "component-parent-plan")
        return {**self.read_review(self.plan["id"]), "accepted": False}

    def read_review(self, proposal_id):
        assert self.plan is not None and proposal_id == self.plan["id"]
        retained = self.client.get(PREFIX + f"/records/{proposal_id}").json()
        assert retained == self.plan
        # The current product has canonical plan approvals, but no durable
        # parent pending-review DTO. This explicitly test-local view maps to it.
        return {"proposal_id": proposal_id, "proposal_digest": retained["digest"],
                "review_id": "component-review-" + proposal_id, "review_digest": retained["digest"],
                "decision": "approved" if self.approval else "pending"}

    def approve_as_human(self):
        # Only the test driver calls this authenticated endpoint; it is not a graph tool.
        self.approval = post(self.client, f"/plans/{self.plan['id']}/approvals", {
            "expected_current_revision_id": self.problem["id"],
            "expected_plan_digest": self.plan["digest"], "accepted": True}, "component-human-approval")
        assert self.approval["plan_id"] == self.plan["id"]
        assert self.approval["plan_digest"] == self.plan["digest"]

    async def execute_or_reconcile(self, proposal_id, proposal_digest, review_id, review_digest, max_scientific_calls):
        assert max_scientific_calls == 1 and self.approval is not None
        assert (proposal_id, proposal_digest) == (self.plan["id"], self.plan["digest"])
        assert (review_id, review_digest) == ("component-review-" + proposal_id, self.plan["digest"])
        run = post(self.client, f"/plans/{proposal_id}/runs", {
            "approval_id": self.approval["id"], "expected_plan_digest": proposal_digest}, "component-child-operation")
        worker = Worker(self.client.app.state.workflow, settings=self.client.app.state.settings)
        # The ordinary synchronous worker owns its event loop. Keep that real
        # execution outside the parent graph's loop rather than mocking it.
        assert await asyncio.to_thread(worker.tick) == (0 if self.run else 1)
        self.run = self.client.get(PREFIX + f"/runs/{run['id']}").json()
        assert self.run["state"] == "completed" and self.run["scientific_reservations"] == 1
        assert self.run["provider_turns"] == 0
        self.record = self.client.get(PREFIX + f"/records/{self.run['scenarios'][0]['result_id']}").json()
        return {"proposal_id": proposal_id, "job_id": self.run["id"], "state": "completed",
                "evidence": project_evidence_fact(self.record)}

    def read_evidence(self, evidence_id):
        assert self.record is not None and evidence_id == self.record["id"]
        record = self.client.get(PREFIX + f"/records/{evidence_id}").json()
        assert record == self.record
        return project_evidence_fact(record)

    def clarify(self, fields, question):
        raise AssertionError("These reviewed supported inputs need no clarification")

    def publish_report(self, evidence_ids, commentary):
        assert evidence_ids == [self.record["id"]]
        self.report = post(self.client, f"/runs/{self.run['id']}/reports", None, "component-report")
        self.commentaries.append(deepcopy(commentary))  # No claim of new commentary persistence.
        return {"id": self.report["id"], "report_digest": self.report["digest"],
                "evidence_ids": evidence_ids, "commentary": commentary}

    def record_event(self, event):
        self.events.append(deepcopy(event))


@pytest.mark.parametrize("wide,expected,next_action", [
    (False, "certified_counterexample", "review_design"),
    (True, "no_counterexample_found", "stop"),
])
def test_new_parent_factory_uses_approved_real_science_then_selects_evidence_bound_action(
        scientific_client, replay_python, tmp_path, monkeypatch, wide, expected, next_action):
    client = scientific_client
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    attempts = []

    def reject_network(self, address):
        attempts.append(address)
        raise AssertionError("No model/provider or external network calls are admitted")

    monkeypatch.setattr(socket.socket, "connect", reject_network)
    monkeypatch.setattr(socket.socket, "connect_ex", reject_network)
    workspace = post(client, "/workspaces", {"name": "New parent component, real science"}, "workspace")["id"]
    inputs = reviewed_history()
    dataset = post(client, f"/workspaces/{workspace}/datasets", inputs["dataset"]["body"], "dataset")
    problem_body = inputs["problem"]["body"]
    target = problem_body["domain"]["ke"] if wide else problem_body["target"]
    problem = post(client, f"/workspaces/{workspace}/problems", {
        **problem_body, "dataset_id": dataset["id"], "dataset_digest": dataset["digest"], "target": target}, "problem")
    ports = NativeSciencePorts(client, workspace, dataset, problem)
    model, checkpointer = NativeParentModel(), InMemorySaver()
    context = ResearchContext(workspace_id=workspace, research_session_id="component-session",
        action_id="component-action", thread_id="component-thread", input_digest=problem["digest"],
        question=QUESTION, reviewed_context={"problem_id": problem["id"], "dataset_id": dataset["id"],
            "target": problem["body"]["target"], "feasible_times": ["6/1", "8/1"], "future_allowance": "1/5"},
        max_scientific_calls=1)

    async def investigate():
        coordinator = create_research_coordinator(context=context, ports=ports,
            model_factory=lambda: model, checkpointer=checkpointer)
        pending = await coordinator.start()
        assert pending["awaiting_review"] and len(pending["interrupts"]) == 1
        assert ports.plan["body"]["objective"]["question"] == QUESTION
        assert ports.plan["body"]["provider_disclosure"]["provider"] == "none"
        assert ports.approval is ports.run is ports.record is None
        assert Worker(client.app.state.workflow, settings=client.app.state.settings).tick() == 0
        with pytest.raises(CoordinatorFailure, match="research_canonical_approval_required"):
            await coordinator.resume()
        assert ports.run is None and len(ports.turns) == 2
        assert pending["interrupts"][0]["tool_call_id"] == "controlled-1"
        assert ports.admitted_tools == ["write_todos", "prepare_scientific_proposal"]
        # Rebuilding a facade with the same in-memory state is not process restart.
        reopened = create_research_coordinator(context=context, ports=ports,
            model_factory=lambda: model, checkpointer=checkpointer)
        saved = await reopened.snapshot()
        assert saved["awaiting_review"] and saved["todos"] == ports.plans[0]
        assert saved["model_turns"] == 2 and len(model.questions) == 2
        ports.approve_as_human()
        finished = await reopened.resume()
        assert not finished["awaiting_review"]
        state = await reopened.snapshot()
        assert state["model_turns"] == state["tool_calls"] == 4
        assert state["planning_status_authority"] == "agent_proposal"
        assert state["runtime"]["application_integration_qualified"] is False
        assert state["runtime"]["live_qualification"] == "not_run"

    asyncio.run(investigate())
    assert model.offered == sorted(TOOLS) and model.questions == [QUESTION] * 4
    assert model.observed_outcome == expected
    assert ports.record["body"]["result"]["scientific_outcome"] == expected
    assert ports.commentaries[0]["next_action"] == next_action
    assert ports.commentaries[0]["scientific_authority"] is False
    assert ports.commentaries[0]["authorship"] == "controlled_commentary"
    assert ports.report["body"]["plan"]["body"]["objective"]["question"] == QUESTION
    assert [record["id"] for record in ports.report["body"]["evidence"]] == [ports.record["id"]]
    assert [turn for _, turn in ports.turns] == [1, 2, 3, 4]
    assert ports.admitted_tools == ["write_todos", "prepare_scientific_proposal",
                                    "run_scientific_operation", "publish_research_report"]
    assert len(ports.admitted_tools) <= 6
    child = asyncio.run(ports.execute_or_reconcile(ports.plan["id"], ports.plan["digest"],
        "component-review-" + ports.plan["id"], ports.plan["digest"], 1))
    assert child["job_id"] == ports.run["id"] and ports.run["scientific_reservations"] == 1
    result = ports.record["body"]["result"]
    assert result["baseline_search"]["attempted_count"] > 0
    reference = result["artifacts"][0]
    download = client.get(PREFIX + f"/artifacts/{reference['id']}")
    anchors = client.get(PREFIX + f"/artifacts/{reference['id']}/anchor?download=true").json()
    assert download.status_code == 200 and hashlib.sha256(download.content).hexdigest() == reference["sha256"]
    assert set(anchors) == {"artifact_sha256", "dataset_digest", "problem_digest", "projection_digest",
                            "app_request_digest", "design_digest", "scenario_id", "run_id"}
    assert anchors["artifact_sha256"] == reference["sha256"]
    assert anchors["run_id"] == ports.run["id"] and anchors["problem_digest"] == problem["digest"]
    assert anchors["dataset_digest"] == dataset["digest"]
    assert anchors["projection_digest"] == result["scientific_problem_digest"]
    assert anchors["scenario_id"] == "baseline" and anchors["app_request_digest"] is anchors["design_digest"] is None
    packet = download.json()
    native = json.loads(base64.b64decode(packet["scientific"]["bytes_base64"], validate=True))
    assert packet["operation"] == "investigate" and native["operation"] == "bounded_discovery"
    assert native["workflow"]["plan_id"] == ports.plan["id"]
    assert native["workflow"]["approval_id"] == ports.approval["id"]
    assert native["workflow"]["execution_id"] == ports.run["id"]
    process, replay = baseline.replay_cli(replay_python, tmp_path, download.content, anchors)
    assert process.returncode == 0, replay
    assert replay["replay"] == replay["integrity"] == "passed" and replay["expected_binding"] == "matches"
    assert replay["verification"] == "valid" and replay["search_replayed"] is False
    assert replay["outcome"]["scientific_outcome"] == expected
    assert client.get(PREFIX + f"/workspaces/{workspace}/provider-attempts").json() == []
    assert attempts == []
