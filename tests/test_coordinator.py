"""Actual deepagents graph tests with a controlled model and controlled tools.

These prove framework constraints and evidence-dependent dispatch, not live Gemini
quality or Groundwork science. No network request is made by this module.
"""
import asyncio
import json

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
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
        envelope = json.loads(next(m.content for m in messages if isinstance(m, HumanMessage)))
        optional = envelope["optional_scenario_ids"]
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
            elif len(observed) == 1 and optional and last["scientific_outcome"] == "no_counterexample_found":
                name, args = "execute_approved_scenario", {"scenario_id": "optional"}
            elif len(observed) == 1 and optional and self.mode != "omit_optional":
                name, args = "record_allowed_skip", {"scenario_id": "optional", "reason_code": "sufficient_evidence"}
            else:
                name = "return_grounded_explanation"
                last_fact = next(json.loads(m.content) for m in reversed(observed) if "id" in json.loads(m.content))
                args = {"fact_ids": [last_fact["id"]], "text": "The returned evidence has the stated conditional scope.",
                        "next_action": "stop"}
        msg = AIMessage(content="", tool_calls=[{"id": f"call-{len(observed)}", "name": name, "args": args, "type": "tool_call"}])
        if self.mode == "synthetic_usage":
            msg.usage_metadata = {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110}
        return ChatResult(generations=[ChatGeneration(message=msg)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._generate(messages, stop, run_manager, **kwargs)


class ToolHarness:
    def __init__(self, outcome):
        self.outcome = outcome
        self.executed = []
        self.skipped = []
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
        self.skipped.append((scenario_id, reason_code))
        return {"id": "skip-" + scenario_id}
    def callbacks(self):
        return ScopedCallbacks(self.authority, self.execute, self.read, self.skip, record_event=self.events.append)


def run(outcome, mode="adapt", *, optional_scenario_ids=("optional",), **scope_kwargs):
    ledger, harness = Ledger(), ToolHarness(outcome)
    model = EvidenceModel(mode=mode)
    config = ProviderConfig(api_key="controlled-no-network", model=model.model_name,
                            account_gate_passed=True, account_decision_id="controlled-test-policy")
    scope = CoordinatorScope("run", "plan", "problem", "baseline", optional_scenario_ids, **scope_kwargs)
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
    assert len(ledger.attempts) == 3
    assert harness.skipped == ([("optional", "sufficient_evidence")] if len(expected) == 1 else [])
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
    result, _, harness, model = run("inconclusive", optional_scenario_ids=(),
                                  permitted_tools=("execute_approved_scenario", "return_grounded_explanation"))
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


@pytest.mark.parametrize("module", [None, "langchain_google_genai.chat_models", "langchain_openai.chat_models", "langchain_anthropic.chat_models"])
def test_offline_gate_rejects_absent_and_inherited_hosted_models_before_graph_or_ledger(monkeypatch, module):
    from bean_api.coordinator import CoordinatorFailure
    import bean_api.coordinator as coordinator
    import builtins

    model = None
    if module:
        hosted = type("HostedModel", (), {"__module__": module})
        # The subclass appears local, but inherits the hosted transport.
        model = type("LocalSubclass", (hosted,), {"__module__": __name__})()
    def forbidden_graph(*args):
        pytest.fail("offline rejection must precede graph or client construction")
    real_import = builtins.__import__
    def deny_hosted_import(name, *args, **kwargs):
        if name.startswith(("langchain_google_genai", "langchain_openai", "langchain_anthropic")):
            pytest.fail("offline rejection must precede hosted SDK import")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(coordinator, "_make_graph", forbidden_graph)
    monkeypatch.setattr(builtins, "__import__", deny_hosted_import)
    ledger, harness = Ledger(), ToolHarness("inconclusive")
    config = ProviderConfig(api_key="synthetic-nonempty", model="configured-intended-model",
                            account_gate_passed=True, account_decision_id="synthetic-account")
    with pytest.raises(CoordinatorFailure, match="provider_dispatch_disabled"):
        asyncio.run(run_coordinator(config, ledger, AttemptContext("actor", "workspace", "op", "consent"),
            CoordinatorScope("run", "plan", "problem", "baseline"), harness.callbacks(), chat_model=model))
    assert ledger.attempts == [] and harness.executed == []


def test_controlled_provenance_never_claims_gemini_authorship_or_provider_billing():
    result, ledger, _, _ = run("no_counterexample_found", "synthetic_usage")
    assert result.status == "completed", result.error_code
    assert result.explanation["authorship"] == "controlled_commentary"
    assert result.runtime["active_mode"] == "controlled_offline"
    assert result.runtime["provider_adapter"] == "controlled_local_model"
    assert result.runtime["live_qualification"] == "not_run"
    assert result.runtime["external_provider_calls"] == result.runtime["actual_model_tokens"] == 0
    assert "api_surface" not in result.runtime
    for attempt in ledger.attempts:
        assert attempt["metadata"]["provider"] == "controlled_local"
        assert attempt["metadata"]["provider_request_id"] is None
        assert "reserved_input_tokens" not in attempt["metadata"]
        assert attempt["result"]["usage"] is None
        assert attempt["result"]["actual_model_tokens"] == 0
    requests = [item for item in result.trace if item["type"] == "model_request"]
    assert all(item["local_attempt_id"] and item["provider_request_id"] is None for item in requests)


def test_agent_cannot_finish_by_silently_omitting_reviewed_optional_work():
    result, _, harness, _ = run("certified_counterexample", "omit_optional")
    assert result.status == "failed"
    assert result.error_code == "agent_scenario_accounting_incomplete"
    assert result.explanation is None
    assert harness.executed == ["baseline"] and harness.skipped == []
    assert [fact["id"] for fact in result.evidence] == ["evidence-baseline"]


def test_caller_mutation_cannot_widen_the_reviewed_problem_mapping():
    harness, ledger = ToolHarness("no_counterexample_found"), Ledger()
    scope = CoordinatorScope("run", "plan", "problem", "baseline", ("optional",),
        scenario_problem_ids={"baseline": "problem", "optional": "reviewed-optional-problem"})
    original = harness.execute
    async def mutated_callback(scenario_id):
        scope.scenario_problem_ids["optional"] = "unreviewed-problem"
        value = await original(scenario_id)
        if scenario_id == "optional":
            value["problem_id"] = "unreviewed-problem"
        return value
    harness.execute = mutated_callback
    model = EvidenceModel()
    config = ProviderConfig(api_key="controlled", model=model.model_name,
                            account_gate_passed=True, account_decision_id="test")
    result = asyncio.run(run_coordinator(config, ledger, AttemptContext("actor", "workspace", "op", "consent"),
        scope, harness.callbacks(), chat_model=model))
    assert result.error_code == "agent_evidence_problem_mismatch"
    assert result.explanation is None
    assert [fact["problem_id"] for fact in result.evidence] == ["problem"]


def test_caller_mutation_cannot_replace_the_reviewed_objective():
    harness, ledger, seen_contexts = ToolHarness("inconclusive"), Ledger(), []
    scope = CoordinatorScope("run", "plan", "problem", "baseline",
                             context={"objective": {"question": "reviewed question"}})
    class CapturingModel(EvidenceModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            envelope = json.loads(next(m.content for m in messages if isinstance(m, HumanMessage)))
            seen_contexts.append(envelope["approved_context"])
            return super()._generate(messages, stop, run_manager, **kwargs)
    def mutate_original_context(event):
        scope.context["objective"]["question"] = "unreviewed question"
    callbacks = harness.callbacks()
    callbacks.record_event = mutate_original_context
    model = CapturingModel()
    config = ProviderConfig(api_key="controlled", model=model.model_name,
                            account_gate_passed=True, account_decision_id="test")
    result = asyncio.run(run_coordinator(config, ledger, AttemptContext("actor", "workspace", "op", "consent"),
        scope, callbacks, chat_model=model))
    assert result.status == "completed", result.error_code
    assert scope.context["objective"]["question"] == "unreviewed question"
    assert all(value["objective"]["question"] == "reviewed question" for value in seen_contexts)


def test_later_callback_mutation_cannot_rewrite_retained_baseline_evidence():
    harness, ledger = ToolHarness("no_counterexample_found"), Ledger()
    original = harness.execute
    async def mutate_old_evidence(scenario_id):
        if scenario_id == "optional":
            harness.records["evidence-baseline"]["scientific_outcome"] = "certified_counterexample"
        return await original(scenario_id)
    harness.execute = mutate_old_evidence
    model = EvidenceModel()
    config = ProviderConfig(api_key="controlled", model=model.model_name,
                            account_gate_passed=True, account_decision_id="test")
    result = asyncio.run(run_coordinator(config, ledger, AttemptContext("actor", "workspace", "op", "consent"),
        CoordinatorScope("run", "plan", "problem", "baseline", ("optional",)), harness.callbacks(), chat_model=model))
    assert result.status == "completed", result.error_code
    assert harness.records["evidence-baseline"]["scientific_outcome"] == "certified_counterexample"
    baseline = next(fact for fact in result.evidence if fact["id"] == "evidence-baseline")
    assert baseline["scientific_outcome"] == "no_counterexample_found"


def test_scoped_read_cannot_substitute_a_different_evidence_identity():
    harness, ledger = ToolHarness("inconclusive"), Ledger()
    original = harness.read
    def wrong_identity(evidence_id):
        return {**original(evidence_id), "id": "unrequested-evidence"}
    harness.read = wrong_identity
    model = EvidenceModel(mode="loop")
    config = ProviderConfig(api_key="controlled", model=model.model_name,
                            account_gate_passed=True, account_decision_id="test")
    result = asyncio.run(run_coordinator(config, ledger, AttemptContext("actor", "workspace", "op", "consent"),
        CoordinatorScope("run", "plan", "problem", "baseline"), harness.callbacks(), chat_model=model))
    assert result.error_code == "agent_evidence_identity_mismatch"
    assert [fact["id"] for fact in result.evidence] == ["evidence-baseline"]


def test_scoped_read_cannot_rewrite_facts_under_an_existing_evidence_identity():
    harness, ledger = ToolHarness("inconclusive"), Ledger()
    original = harness.read

    def changed_fact(evidence_id):
        return {**original(evidence_id), "scientific_outcome": "certified_counterexample"}

    harness.read = changed_fact
    model = EvidenceModel(mode="loop")
    config = ProviderConfig(api_key="controlled", model=model.model_name,
                            account_gate_passed=True, account_decision_id="test")
    result = asyncio.run(run_coordinator(config, ledger, AttemptContext("actor", "workspace", "op", "consent"),
        CoordinatorScope("run", "plan", "problem", "baseline"), harness.callbacks(), chat_model=model))
    assert result.error_code == "agent_evidence_changed"
    assert result.evidence[0]["scientific_outcome"] == "inconclusive"
    assert result.explanation is None
