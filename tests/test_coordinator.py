"""Actual deepagents graph tests with a controlled model and controlled tools.

These prove framework constraints and evidence-dependent dispatch, not live Gemini
quality or Groundwork science. No network request is made by this module.
"""
import asyncio
import json

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from bean_api.coordinator import CoordinatorScope, ScopedCallbacks, run_coordinator
from bean_api.providers import AttemptContext, ProviderConfig


class Ledger:
    def __init__(self):
        self.attempts = []
    def begin_attempt(self, context, metadata):
        self.attempts.append({"context": context, "metadata": metadata})
        return str(len(self.attempts))
    def finish_attempt(self, attempt_id, metadata):
        self.attempts[int(attempt_id) - 1]["result"] = metadata


class EvidenceModel(BaseChatModel):
    model_name: str = "bean-controlled-evidence-test"
    mode: str = "adapt"
    offered: list[str] = []

    @property
    def _llm_type(self):
        return "bean-controlled"

    def bind_tools(self, tools, **kwargs):
        self.offered = sorted(t.name for t in tools)
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        observed = [m for m in messages if isinstance(m, ToolMessage)]
        if self.mode == "forbidden":
            name, args = "execute", {"command": "cat /etc/passwd"}
        elif self.mode == "optional_first":
            name, args = "execute_approved_scenario", {"scenario_id": "optional"}
        elif not observed:
            name, args = "execute_approved_scenario", {"scenario_id": "baseline"}
        else:
            last = json.loads(observed[-1].content)
            if self.mode == "loop":
                name, args = "read_scoped_evidence", {"evidence_id": "evidence-baseline"}
            elif len(observed) == 1 and last["scientific_outcome"] == "no_counterexample_found":
                name, args = "execute_approved_scenario", {"scenario_id": "optional"}
            else:
                name = "return_grounded_explanation"
                args = {"fact_ids": [last["id"]], "text": "The returned evidence has the stated conditional scope.",
                        "next_action": "stop"}
        msg = AIMessage(content="", tool_calls=[{"id": f"call-{len(observed)}", "name": name, "args": args, "type": "tool_call"}])
        return ChatResult(generations=[ChatGeneration(message=msg)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._generate(messages, stop, run_manager, **kwargs)


class ToolHarness:
    def __init__(self, outcome):
        self.outcome = outcome
        self.executed = []
        self.records = {}
        self.events = []
    def authority(self):
        return None
    async def execute(self, scenario_id):
        self.executed.append(scenario_id)
        record = {"id": "evidence-" + scenario_id, "problem_id": "problem",
                  "scientific_outcome": self.outcome if scenario_id == "baseline" else "inconclusive",
                  "verification": "valid" if self.outcome == "certified_counterexample" else "not_checked",
                  "expected_binding": "matches", "fixture": True}
        self.records[record["id"]] = record
        return record
    def read(self, evidence_id):
        return self.records[evidence_id]
    def skip(self, scenario_id, reason_code):
        return {"id": "skip-" + scenario_id}
    def callbacks(self):
        return ScopedCallbacks(self.authority, self.execute, self.read, self.skip, record_event=self.events.append)


def run(outcome, mode="adapt", **scope_kwargs):
    ledger, harness = Ledger(), ToolHarness(outcome)
    model = EvidenceModel(mode=mode)
    config = ProviderConfig(api_key="controlled-no-network", model=model.model_name,
                            account_gate_passed=True, account_decision_id="controlled-test-policy")
    scope = CoordinatorScope("run", "plan", "problem", "baseline", ("optional",), **scope_kwargs)
    result = asyncio.run(run_coordinator(config, ledger, AttemptContext("actor", "workspace", "op", "consent"),
                                        scope, harness.callbacks(), chat_model=model))
    return result, ledger, harness, model


@pytest.mark.parametrize("outcome,expected", [
    ("certified_counterexample", ["baseline"]),
    ("no_counterexample_found", ["baseline", "optional"]),
])
def test_actual_framework_changes_next_action_using_returned_evidence(outcome, expected):
    result, ledger, harness, model = run(outcome)
    assert result.status == "completed", result.error_code
    assert harness.executed == expected
    assert result.scientific_reservations == len(expected)
    assert result.explanation["scientific_authority"] is False
    assert result.runtime["execution_lane"] == "controlled_model"
    assert result.runtime["live_qualified"] is False
    assert len(ledger.attempts) == len(expected) + 1
    assert all(x["result"]["status"] == "validated" for x in ledger.attempts)
    assert set(model.offered) == {"execute_approved_scenario", "read_scoped_evidence", "record_allowed_skip", "return_grounded_explanation"}
    assert not set(model.offered) & {"execute", "ls", "read_file", "write_file", "task", "web_search"}
    assert harness.events == result.trace


def test_forbidden_model_tool_is_counted_but_never_dispatched():
    result, ledger, harness, _ = run("inconclusive", "forbidden")
    assert result.status == "failed"
    assert result.error_code == "agent_forbidden_tool"
    assert result.tool_calls == 1 and harness.executed == []
    assert ledger.attempts[0]["result"]["status"] == "failed"


def test_baseline_order_is_server_enforced():
    result, _, harness, _ = run("inconclusive", "optional_first")
    assert result.status == "failed"
    assert result.error_code == "baseline_must_execute_first"
    assert harness.executed == []


def test_model_loop_stops_at_four_attempts_without_losing_evidence():
    result, ledger, harness, _ = run("inconclusive", "loop")
    assert result.status == "failed"
    assert result.error_code == "agent_model_budget_exhausted"
    assert len(ledger.attempts) == result.model_turns == 4
    assert len(result.evidence) == 1 and harness.executed == ["baseline"]


def test_lower_approved_tool_budget_is_enforced_before_dispatch():
    result, _, harness, _ = run("no_counterexample_found", max_tool_calls=1)
    assert result.error_code == "agent_tool_budget_exhausted"
    assert harness.executed == ["baseline"]


def test_reviewed_tool_allowlist_is_not_expanded():
    result, _, harness, model = run("inconclusive", permitted_tools=("execute_approved_scenario", "return_grounded_explanation"))
    assert result.status == "completed", result.error_code
    assert set(model.offered) == {"execute_approved_scenario", "return_grounded_explanation"}
    assert harness.executed == ["baseline"]


def test_wrong_problem_evidence_cannot_become_an_explanation():
    harness, ledger = ToolHarness("certified_counterexample"), Ledger()
    original = harness.execute
    async def wrong_problem(scenario_id):
        value = await original(scenario_id)
        value["problem_id"] = "some-other-problem"
        return value
    harness.execute = wrong_problem
    model = EvidenceModel()
    config = ProviderConfig(api_key="controlled", model=model.model_name, account_gate_passed=True, account_decision_id="test")
    result = asyncio.run(run_coordinator(config, ledger, AttemptContext("actor", "workspace", "op", "consent"),
        CoordinatorScope("run", "plan", "problem", "baseline"), harness.callbacks(), chat_model=model))
    assert result.error_code == "agent_evidence_problem_mismatch"
    assert result.explanation is None


def test_explicit_optional_problem_binding_is_preserved():
    harness, ledger = ToolHarness("no_counterexample_found"), Ledger()
    original = harness.execute
    async def distinct_problem(scenario_id):
        value = await original(scenario_id)
        if scenario_id == "optional":
            value["problem_id"] = "reviewed-optional-problem"
        return value
    harness.execute = distinct_problem
    model = EvidenceModel()
    config = ProviderConfig(api_key="controlled", model=model.model_name, account_gate_passed=True, account_decision_id="test")
    result = asyncio.run(run_coordinator(config, ledger, AttemptContext("actor", "workspace", "op", "consent"),
        CoordinatorScope("run", "plan", "problem", "baseline", ("optional",),
                         scenario_problem_ids={"baseline": "problem", "optional": "reviewed-optional-problem"}),
        harness.callbacks(), chat_model=model))
    assert result.status == "completed", result.error_code
    assert harness.executed == ["baseline", "optional"]
    assert result.evidence[1]["problem_id"] == "reviewed-optional-problem"


def test_known_interval_overstatement_and_unsupported_numbers_are_rejected():
    from bean_api.coordinator import _validate_explanation, CoordinatorFailure
    from bean_api.contracts import GroundedExplanation
    facts = {"fact": {"scientific_outcome": "no_counterexample_found", "value": "10/1"}}
    with pytest.raises(CoordinatorFailure, match="unsupported_claim"):
        _validate_explanation(GroundedExplanation(fact_ids=["fact"], text="My interval is proven now.", next_action="stop"), facts)
    with pytest.raises(CoordinatorFailure, match="unsupported_number"):
        _validate_explanation(GroundedExplanation(fact_ids=["fact"], text="The value is 1.", next_action="stop"), facts)
