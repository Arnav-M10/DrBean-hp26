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

from bean_api.coordinator import CoordinatorFailure, CoordinatorScope, ScopedCallbacks, run_coordinator
from bean_api.contracts import GroundedExplanation
from bean_api.providers import AttemptContext, ProviderConfig
import test_scientific_http as scientific_http

scientific_client = scientific_http.scientific_client


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
                name, args = "read_scoped_evidence", {"evidence_id": last["id"]}
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
    observations = result.scenario_observations
    assert [item["scenario_id"] for item in observations] == ["baseline", "optional"]
    assert all(item["observation_scope"] == "coordinator_invocation" for item in observations)
    assert observations[0]["disposition"] == "completed"
    assert observations[0]["evidence_id"] == "evidence-baseline"
    if len(expected) == 2:
        assert observations[1]["disposition"] == "completed"
        assert observations[1]["evidence_id"] == "evidence-optional"
    else:
        assert observations[1]["disposition"] == "skipped"
        assert observations[1]["evidence_id"] is None
        assert observations[1]["reason_code"] == "sufficient_evidence"


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
    baseline, optional = result.scenario_observations
    assert baseline["disposition"] == "completed" and baseline["evidence_id"] == "evidence-baseline"
    assert optional["scenario_id"] == "optional" and optional["disposition"] == "unresolved"
    assert optional["evidence_id"] is None and optional["reason_code"] == "agent_model_budget_exhausted"
    terminal = [event for event in result.trace if event["type"] == "invocation_failed"]
    assert terminal[-1]["scenario_observations"] == result.scenario_observations


def test_lower_approved_tool_budget_is_enforced_before_dispatch():
    result, _, harness, _ = run("no_counterexample_found", max_tool_calls=1)
    assert result.error_code == "agent_tool_budget_exhausted"
    assert harness.executed == ["baseline"]


async def observed_invocation(harness, model, scope):
    config = ProviderConfig(api_key="controlled-no-network", model=model.model_name,
                            account_gate_passed=True, account_decision_id="controlled-test-policy")
    return await run_coordinator(config, Ledger(), AttemptContext("actor", "workspace", "op", "consent"),
                                 scope, harness.callbacks(), chat_model=model)


def test_callback_failure_keeps_unobserved_science_unresolved_and_retains_completed_baseline():
    harness = ToolHarness("no_counterexample_found")
    execute = harness.execute

    async def fail_optional(scenario_id):
        if scenario_id == "optional":
            harness.executed.append(scenario_id)
            raise CoordinatorFailure("controlled_callback_failed")
        return await execute(scenario_id)

    harness.execute = fail_optional
    result = asyncio.run(observed_invocation(harness, EvidenceModel(),
        CoordinatorScope("run", "plan", "problem", "baseline", ("optional",))))
    assert result.status == "failed" and result.error_code == "controlled_callback_failed"
    assert [fact["id"] for fact in result.evidence] == ["evidence-baseline"]
    baseline, optional = result.scenario_observations
    assert baseline["disposition"] == "completed" and baseline["evidence_id"] == "evidence-baseline"
    assert optional["disposition"] == "unresolved" and optional["reason_code"] == "controlled_callback_failed"
    assert optional["observation_scope"] == "coordinator_invocation"
    assert harness.skipped == []


def test_wall_timeout_preserves_baseline_and_marks_unobserved_optional_work_unresolved():
    class StalledAfterBaseline(EvidenceModel):
        async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
            if any(isinstance(message, ToolMessage) for message in messages):
                await asyncio.Event().wait()
            return self._generate(messages, stop, run_manager, **kwargs)

    harness = ToolHarness("inconclusive")
    result = asyncio.run(observed_invocation(harness, StalledAfterBaseline(),
        CoordinatorScope("run", "plan", "problem", "baseline", ("optional",), wall_seconds=1)))
    assert result.status == "failed" and result.error_code == "agent_wall_budget_exhausted"
    baseline, optional = result.scenario_observations
    assert baseline["disposition"] == "completed" and baseline["evidence_id"] == "evidence-baseline"
    assert optional["disposition"] == "unresolved" and optional["reason_code"] == "agent_wall_budget_exhausted"
    assert [fact["id"] for fact in result.evidence] == ["evidence-baseline"]
    terminal, = [event for event in result.trace if event["type"] == "invocation_failed"]
    assert terminal["scenario_observations"] == result.scenario_observations
    assert not any(event["type"] == "invocation_cancelled" for event in result.trace)


@pytest.mark.parametrize("stop_during", ["model_after_baseline", "baseline_callback"])
def test_cancellation_reports_observation_scope_without_claiming_scientific_cancellation(stop_during):
    async def exercise():
        entered, never_finishes = asyncio.Event(), asyncio.Event()
        harness = ToolHarness("inconclusive")

        class InterruptedModel(EvidenceModel):
            async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
                if stop_during == "model_after_baseline" and any(isinstance(m, ToolMessage) for m in messages):
                    entered.set()
                    await never_finishes.wait()
                return self._generate(messages, stop, run_manager, **kwargs)

        if stop_during == "baseline_callback":
            async def interrupted_callback(scenario_id):
                harness.executed.append(scenario_id)
                entered.set()
                await never_finishes.wait()
            harness.execute = interrupted_callback
        task = asyncio.create_task(observed_invocation(harness, InterruptedModel(),
            CoordinatorScope("run", "plan", "problem", "baseline", ("optional",))))
        try:
            async with asyncio.timeout(5):
                await entered.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        terminal, = [event for event in harness.events if event["type"] == "invocation_cancelled"]
        assert terminal["termination"] == "controlled_orchestrator_cancelled"
        baseline, optional = terminal["scenario_observations"]
        assert [baseline["scenario_id"], optional["scenario_id"]] == ["baseline", "optional"]
        assert all(item["observation_scope"] == "coordinator_invocation" for item in (baseline, optional))
        assert optional["disposition"] == "unresolved"
        assert optional["reason_code"] == "controlled_orchestrator_cancelled"
        if stop_during == "model_after_baseline":
            assert baseline["disposition"] == "completed" and baseline["evidence_id"] == "evidence-baseline"
            assert "evidence-baseline" in harness.records
        else:
            assert baseline["disposition"] == "unresolved" and baseline["evidence_id"] is None
        assert not any(item["disposition"] in {"failed", "cancelled"} for item in (baseline, optional))
        assert harness.executed == ["baseline"] and harness.skipped == []
    asyncio.run(exercise())


def test_cancellation_survives_a_failed_cancellation_event_sink(monkeypatch):
    import bean_api.coordinator as coordinator
    captured_invocations = []
    make_graph = coordinator._make_graph

    def capture_invocation(invocation, model):
        captured_invocations.append(invocation)
        return make_graph(invocation, model)

    monkeypatch.setattr(coordinator, "_make_graph", capture_invocation)

    async def exercise():
        entered, never_finishes = asyncio.Event(), asyncio.Event()
        harness, sink_attempts, model_calls = ToolHarness("inconclusive"), [], []

        class InterruptedModel(EvidenceModel):
            async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
                model_calls.append(True)
                if any(isinstance(message, ToolMessage) for message in messages):
                    entered.set()
                    await never_finishes.wait()
                return self._generate(messages, stop, run_manager, **kwargs)

        def failing_sink(event):
            harness.events.append(event)
            if event["type"] == "invocation_cancelled":
                sink_attempts.append(True)
                raise RuntimeError("private_source_and_token_must_not_escape")

        callbacks = harness.callbacks()
        callbacks.record_event = failing_sink
        harness.callbacks = lambda: callbacks
        task = asyncio.create_task(observed_invocation(harness, InterruptedModel(),
            CoordinatorScope("run", "plan", "problem", "baseline", ("optional",))))
        try:
            async with asyncio.timeout(5):
                await entered.wait()
            task.cancel("requested_stop")
            with pytest.raises(asyncio.CancelledError) as caught:
                await task
            assert caught.value.args == ("requested_stop",)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        assert sink_attempts == [True] and len(model_calls) == 2
        assert harness.executed == ["baseline"] and harness.skipped == []
        assert "evidence-baseline" in harness.records
        invocation, = captured_invocations
        terminal, = [event for event in invocation.trace if event["type"] == "invocation_cancelled"]
        assert terminal["event_persistence"] == "unconfirmed"
        assert terminal["event_persistence_code"] == "agent_event_sink_failed"
        baseline, optional = terminal["scenario_observations"]
        assert baseline["disposition"] == "completed" and baseline["evidence_id"] == "evidence-baseline"
        assert optional["disposition"] == "unresolved" and optional["reason_code"] == "controlled_orchestrator_cancelled"
        assert "private_source_and_token" not in json.dumps(invocation.trace)
    asyncio.run(exercise())


def test_event_callback_and_caller_cannot_mutate_retained_scenario_observations():
    from bean_api.coordinator import _Invocation
    harness = ToolHarness("inconclusive")
    inv = _Invocation(ProviderConfig(), Ledger(), AttemptContext("actor", "workspace", "op", "consent"),
        CoordinatorScope("run", "plan", "problem", "baseline", ("optional",)), harness.callbacks())
    observations = inv.scenario_observations("controlled_stop")
    asyncio.run(inv.event({"type": "invocation_failed", "scenario_observations": observations}))
    observations[0]["disposition"] = "completed"
    harness.events[0]["scenario_observations"][1]["disposition"] = "skipped"
    assert all(item["disposition"] == "unresolved" for item in inv.trace[0]["scenario_observations"])
    assert all(item["reason_code"] == "controlled_stop" for item in inv.trace[0]["scenario_observations"])


def test_separately_approved_design_has_one_completed_callback_observation():
    class DesignModel(EvidenceModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            observed = [message for message in messages if isinstance(message, ToolMessage)]
            if not observed:
                name, args = "execute_approved_design", {}
            else:
                name, args = "return_grounded_explanation", {
                    "fact_ids": ["design-evidence"], "text": "The returned design remains numerical guidance.", "next_action": "stop"}
            message = AIMessage(content="", tool_calls=[{
                "id": f"design-call-{len(observed)}", "name": name, "args": args, "type": "tool_call"}])
            return ChatResult(generations=[ChatGeneration(message=message)])

    harness = ToolHarness("inconclusive")
    callbacks = harness.callbacks()
    callbacks.execute_design = lambda: {"id": "design-evidence", "problem_id": "problem", "design_tier": "numerical_guidance"}
    harness.callbacks = lambda: callbacks
    result = asyncio.run(observed_invocation(harness, DesignModel(),
        CoordinatorScope("run", "plan", "problem", "baseline", kind="design", max_scientific_reservations=1, wall_seconds=120)))
    assert result.status == "completed", result.error_code
    observation, = result.scenario_observations
    assert observation["scenario_id"] == "baseline" and observation["disposition"] == "completed"
    assert observation["evidence_id"] == "design-evidence" and observation["reason_code"] is None
    assert result.scientific_reservations == 1 and harness.executed == []


def test_reviewed_tool_allowlist_is_not_expanded():
    result, _, harness, model = run("inconclusive", optional_scenario_ids=(),
                                  permitted_tools=("execute_approved_scenario", "return_grounded_explanation"))
    assert result.status == "completed", result.error_code
    assert set(model.offered) == {"execute_approved_scenario", "return_grounded_explanation"}
    assert harness.executed == ["baseline"]


def test_design_tool_is_omitted_when_its_actual_callback_is_absent():
    from bean_api.coordinator import _Invocation, _make_graph

    ledger, harness, model = Ledger(), ToolHarness("inconclusive"), EvidenceModel()
    config = ProviderConfig(api_key="controlled", model=model.model_name,
                            account_gate_passed=True, account_decision_id="test")
    scope = CoordinatorScope("run", "plan", "problem", "baseline", kind="design",
                             max_scientific_reservations=1, wall_seconds=120)
    inv = _Invocation(config, ledger, AttemptContext("actor", "workspace", "op", "consent"),
                      scope, harness.callbacks())
    _, runtime = _make_graph(inv, model)
    assert set(runtime["tool_inventory"]) == {"read_scoped_evidence", "return_grounded_explanation"}
    assert ledger.attempts == [] and harness.executed == []


def test_explicit_missing_design_tool_is_rejected_before_model_or_ledger_work():
    from bean_api.coordinator import CoordinatorFailure

    ledger, harness, model = Ledger(), ToolHarness("inconclusive"), EvidenceModel()
    config = ProviderConfig(api_key="controlled", model=model.model_name,
                            account_gate_passed=True, account_decision_id="test")
    scope = CoordinatorScope("run", "plan", "problem", "baseline", kind="design",
        max_scientific_reservations=1, wall_seconds=120,
        permitted_tools=("execute_approved_design", "return_grounded_explanation"))
    with pytest.raises(CoordinatorFailure, match="agent_tool_not_implemented"):
        asyncio.run(run_coordinator(config, ledger, AttemptContext("actor", "workspace", "op", "consent"),
                                   scope, harness.callbacks(), chat_model=model))
    assert model.offered == [] and ledger.attempts == [] and harness.events == []


def test_actual_controlled_design_callback_is_offered_and_executed_within_design_scope():
    class DesignModel(EvidenceModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            if not any(isinstance(message, ToolMessage) for message in messages):
                message = AIMessage(content="", tool_calls=[{"id": "design-call", "name": "execute_approved_design",
                    "args": {}, "type": "tool_call"}])
                return ChatResult(generations=[ChatGeneration(message=message)])
            return super()._generate(messages, stop, run_manager, **kwargs)

    ledger, harness, model, designs = Ledger(), ToolHarness("inconclusive"), DesignModel(), []
    def execute_design():
        designs.append("approved-design")
        return {"id": "design-evidence", "problem_id": "problem", "design_tier": "no_separation_established",
                "verification": "not_checked", "expected_binding": "matches"}
    callbacks = harness.callbacks()
    callbacks.execute_design = execute_design
    config = ProviderConfig(api_key="controlled", model=model.model_name,
                            account_gate_passed=True, account_decision_id="test")
    scope = CoordinatorScope("run", "plan", "problem", "baseline", kind="design",
                             max_scientific_reservations=1, wall_seconds=120)
    result = asyncio.run(run_coordinator(config, ledger, AttemptContext("actor", "workspace", "op", "consent"),
                                        scope, callbacks, chat_model=model))
    assert result.status == "completed", result.error_code
    assert set(result.runtime["tool_inventory"]) == {
        "read_scoped_evidence", "return_grounded_explanation", "execute_approved_design"}
    assert designs == ["approved-design"] and harness.executed == []
    assert result.scientific_reservations == 1
    assert result.explanation["fact_ids"] == ["design-evidence"]
    assert len(ledger.attempts) == result.model_turns == 2


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


@pytest.mark.parametrize("metadata", [
    {"id": "evidence-999"}, {"candidate_ids": ["candidate-999"]},
    {"scientific_problem_digest": "999"}, {"sha256": "999"},
    {"reason_code": "result-999", "notes": "The source mentions 999."},
    {"schema_version": "999", "999": "A field name is not a quantity."},
])
def test_identifier_digest_version_and_free_prose_cannot_authorize_a_scientific_number(metadata):
    from bean_api.coordinator import CoordinatorFailure, _validate_explanation

    facts = {"cited": {"problem_id": "problem", **metadata}}
    with pytest.raises(CoordinatorFailure, match="explanation_unsupported_number"):
        _validate_explanation(GroundedExplanation(fact_ids=["cited"],
            text="The future hard allowance is 999.", next_action="stop"), facts)


def test_uncited_scientific_fact_cannot_authorize_a_number():
    from bean_api.coordinator import CoordinatorFailure, _validate_explanation

    facts = {"cited": {"selected_time": "8/1"}, "uncited": {"future_hard_allowance": "999/1"}}
    with pytest.raises(CoordinatorFailure, match="explanation_unsupported_number"):
        _validate_explanation(GroundedExplanation(fact_ids=["cited"],
            text="The future hard allowance is 999.", next_action="stop"), facts)
    with pytest.raises(CoordinatorFailure, match="explanation_unknown_fact"):
        _validate_explanation(GroundedExplanation(fact_ids=["missing"],
            text="Review the result.", next_action="stop"), facts)


@pytest.mark.parametrize("text", [
    "This is globally optimal experimental design.", "All alternative parameter values have been eliminated.",
    "All outside candidates are excluded.", "The true model has been found.", "The interval is proven.",
    "The search proves your interval.", "No counterexample found proves the interval.",
    "The reference curve is truth.", "This proves truth.",
])
def test_unconditional_scientific_overclaims_are_rejected(text):
    from bean_api.coordinator import CoordinatorFailure, _validate_explanation

    with pytest.raises(CoordinatorFailure, match="explanation_unsupported_claim"):
        _validate_explanation(GroundedExplanation(fact_ids=["cited"], text=text, next_action="stop"),
                              {"cited": {"scientific_outcome": "no_counterexample_found"}})


@pytest.mark.parametrize("text", [
    "The interval is not proven.", "The search does not prove the interval.",
    "Compatibility does not identify the true model.", "The true model remains unknown.",
    "This result does not establish global optimality.",
    "No claim that all alternatives are eliminated is supported.",
])
def test_scoped_scientific_caveats_are_preserved(text):
    from bean_api.coordinator import _validate_explanation

    _validate_explanation(GroundedExplanation(fact_ids=["cited"], text=text, next_action="stop"),
                          {"cited": {"scientific_outcome": "no_counterexample_found"}})


@pytest.mark.parametrize("text", [
    "The prospective hard allowance is 0.2.", "The prospective hard allowance is 2/10.",
    "The prospective hard allowance is 2e-1.", "The prospective hard allowance is 0.2mg/L.",
])
def test_cited_scientific_quantities_accept_exact_equivalent_spellings(text):
    from bean_api.coordinator import _validate_explanation

    _validate_explanation(GroundedExplanation(fact_ids=["cited"], text=text, next_action="stop"),
                          {"cited": {"future_hard_allowance": "1/5"}})


def test_numeric_policy_uses_ranges_parameter_vectors_selected_options_and_search_counters():
    from bean_api.ai_prompts import commentary_rejection

    facts = [{"target": {"lower": "1/10", "upper": "17/100"},
              "candidates": [{"id": "candidate-999", "parameter_vector": {"ke": "3/25"}}],
              "selected_option": {"time": "8/1", "exact_margin": "1/5"},
              "baseline_search": {"evaluated_count": 3, "settings": {"ka_points": 7}, "reason": "999"}}]
    assert commentary_rejection("The interval is [0.10, 0.17]; the candidate rate is 0.12.", facts) is None
    assert commentary_rejection("At elapsed time 8h, the margin is 0.2mg/L.", facts) is None
    assert commentary_rejection("The search evaluated 3 assignments using 7 rate grid points.", facts) is None
    assert commentary_rejection("The margin is 999mg/L.", facts) == "unsupported_numeric_claim"
    assert commentary_rejection("The selected time is 999h.", facts) == "unsupported_numeric_claim"
    assert commentary_rejection("The selected time is 999.", facts) == "unsupported_numeric_claim"
    # IDs are still opaque to numeric checking. Arbitrary identity assertions
    # now fail the complete-statement policy instead of becoming narration.
    assert commentary_rejection("Opaque evidence a123b and candidate-999 retain their original IDs.", facts) == "unsupported_claim"


@pytest.mark.parametrize("facts, reason", [
    ([], "unsupported_numeric_claim"),
    ([{"ke": "37/500"}], "unsupported_claim"),
])
def test_numeric_failure_precedence_preserves_overclaim_rejection(facts, reason):
    from bean_api.ai_prompts import commentary_rejection
    assert commentary_rejection("The true parameter is ke = 0.074 per hour.", facts) == reason


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
    assert result.error_code == "scenario_accounting_incomplete"
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


@pytest.mark.parametrize("change", ["scientific_outcome", "omitted_replay_transcript"])
def test_scoped_read_cannot_rewrite_facts_under_an_existing_evidence_identity(change):
    harness, ledger = ToolHarness("inconclusive"), Ledger()
    original = harness.read
    execute = harness.execute

    async def replay_fact(scenario_id):
        value = await execute(scenario_id)
        value["native_replay"] = {"replay": "passed", "integrity": "passed",
            "candidate_results": [{"candidate_id": "fixed", "rows": [{"observation_id": "r1", "value": "1/1"}]}]}
        return value

    def changed_fact(evidence_id):
        value = original(evidence_id)
        if change == "scientific_outcome":
            return {**value, "scientific_outcome": "certified_counterexample"}
        return {**value, "native_replay": {**value["native_replay"], "candidate_results": []}}

    harness.execute = replay_fact
    harness.read = changed_fact
    model = EvidenceModel(mode="loop")
    config = ProviderConfig(api_key="controlled", model=model.model_name,
                            account_gate_passed=True, account_decision_id="test")
    result = asyncio.run(run_coordinator(config, ledger, AttemptContext("actor", "workspace", "op", "consent"),
        CoordinatorScope("run", "plan", "problem", "baseline"), harness.callbacks(), chat_model=model))
    assert result.error_code == "agent_evidence_changed"
    assert result.evidence[0]["scientific_outcome"] == "inconclusive"
    assert result.explanation is None


def _approved_real_agent_run(client, model, *, optional=False, provider_turns=4):
    """Create actual inputs, approval and a queued run through ordinary HTTP."""
    from bean_api.contracts import PlanBody
    from bean_api.worker import Worker
    from test_counterdex_adapter import reviewed_history
    from test_scientific_http import post

    history = reviewed_history()
    workspace = post(client, "/workspaces", {"name": "Controlled agent real-science acceptance"}, "workspace")["id"]
    dataset = post(client, f"/workspaces/{workspace}/datasets", history["dataset"]["body"], "dataset")
    problem = post(client, f"/workspaces/{workspace}/problems", {
        **history["problem"]["body"], "dataset_id": dataset["id"], "dataset_digest": dataset["digest"]}, "problem")
    disclosure = {"provider": "gemini", "model": model.model_name,
                  "source_asset_ids": [], "context_fields": ["problem", "dataset"]}
    consent = post(client, f"/workspaces/{workspace}/provider-consents", {
        **disclosure, "problem_id": problem["id"], "accepted": True}, "controlled-consent")
    scenarios = [{"id": "baseline", "kind": "baseline", "label": "Real bounded discovery",
                  "problem_id": problem["id"], "problem_digest": problem["digest"]}]
    if optional:
        scenarios.append({"id": "optional", "kind": "optional", "label": "Separately listed optional comparison",
                          "problem_id": problem["id"], "problem_digest": problem["digest"],
                          "purpose": "An explicitly reviewed repeat comparison after checked baseline evidence.",
                          "eligible_baseline_outcomes": ["certified_counterexample"]})
    body = PlanBody(problem_id=problem["id"], problem_digest=problem["digest"], dataset_id=dataset["id"],
        scientific_profile="counterdex.v1", objective={
            "question": "Which checked outside witness remains compatible with the reviewed synthetic data?",
            "success_criterion": "Retain real native evidence with controlled commentary and zero provider dispatch."},
        scenarios=scenarios, budget={"provider_turns": provider_turns},
        provider_disclosure={**disclosure, "permission_id": consent["id"]}).model_dump(mode="json")
    plan = post(client, f"/workspaces/{workspace}/plans", {
        "expected_current_revision_id": problem["id"], "plan": body}, "plan")
    approval = post(client, f"/plans/{plan['id']}/approvals", {
        "expected_current_revision_id": problem["id"], "expected_plan_digest": plan["digest"],
        "accepted": True}, "approval")
    run = post(client, f"/plans/{plan['id']}/runs", {
        "approval_id": approval["id"], "expected_plan_digest": plan["digest"]}, "run")
    config = ProviderConfig(api_key="nonsecret-controlled-placeholder", model=model.model_name,
                            account_gate_passed=True, account_decision_id="controlled-local-test-policy")
    worker = Worker(client.app.state.workflow, settings=client.app.state.settings,
                    adapter=client.app.state.adapter, provider_config=config, controlled_model=model)
    return workspace, dataset, problem, plan, approval, run, worker


def test_controlled_graph_runs_http_approved_counterdex_and_replays_bound_native_bytes(scientific_client):
    """Controlled orchestration with real science, never live Gemini reasoning."""
    import base64
    import hashlib

    from bean_api.main import PREFIX
    from test_scientific_http import post

    client = scientific_client
    workspace, dataset, problem, plan, approval, run, worker = _approved_real_agent_run(client, EvidenceModel())
    assert worker.tick() == 1
    finished = client.get(PREFIX + f"/runs/{run['id']}").json()
    assert finished["state"] == "completed", finished
    assert len(finished["scenarios"]) == finished["scientific_reservations"] == 1
    scenario = finished["scenarios"][0]
    assert scenario["scenario_id"] == "baseline" and scenario["state"] == "completed"
    evidence_record = client.get(PREFIX + f"/records/{scenario['result_id']}").json()
    assert evidence_record["body"]["run_id"] == run["id"]
    evidence = evidence_record["body"]["result"]
    assert evidence["problem_id"] == problem["id"] and evidence["problem_digest"] == problem["digest"]
    assert evidence["scientific_outcome"] == "certified_counterexample"
    assert evidence["verification"] == "valid" and evidence["expected_binding"] == "matches"
    assert evidence["baseline_search"]["attempted_count"] > 0
    summary = client.get(PREFIX + f"/records/{finished['result_id']}").json()["body"]
    assert summary["explanation"]["authorship"] == "controlled_commentary"
    assert summary["explanation"]["fact_ids"] == [evidence_record["id"]]
    assert summary["runtime"]["active_mode"] == "controlled_offline"
    assert summary["external_provider_calls"] == summary["actual_model_tokens"] == 0
    assert summary["model_turns"] == finished["provider_turns"] == 2

    reference, = evidence["artifacts"]
    downloaded = client.get(PREFIX + f"/artifacts/{reference['id']}")
    assert downloaded.status_code == 200
    assert hashlib.sha256(downloaded.content).hexdigest() == reference["sha256"]
    anchors = client.get(PREFIX + f"/artifacts/{reference['id']}/anchor?download=true").json()
    assert anchors["run_id"] == run["id"] and anchors["scenario_id"] == "baseline"
    assert anchors["dataset_digest"] == dataset["digest"] and anchors["problem_digest"] == problem["digest"]
    assert anchors["projection_digest"] == evidence["scientific_problem_digest"]
    packet = downloaded.json()
    native = json.loads(base64.b64decode(packet["scientific"]["bytes_base64"], validate=True))
    assert native["operation"] == "bounded_discovery"
    assert native["workflow"]["plan_id"] == plan["id"]
    assert native["workflow"]["approval_id"] == approval["id"]
    assert native["workflow"]["execution_id"] == run["id"]
    fresh = client.app.state.adapter.replay_native(downloaded.content, expected=anchors)
    assert fresh["replay"] == fresh["integrity"] == "passed", fresh
    assert fresh["expected_binding"] == "matches" and fresh["verification"] == "valid"
    assert fresh["search_replayed"] is False
    assert {row["candidate_id"] for row in fresh["candidate_results"]} == {row["id"] for row in evidence["candidates"]}
    wrong = client.app.state.adapter.replay_native(downloaded.content, expected={**anchors, "run_id": "another_run"})
    assert wrong["worker_error"] == "wrong_scenario_binding"
    response = post(client, f"/workspaces/{workspace}/assistant-turns", {
        "operation": "explain", "client_operation_id": "explain-real-evidence",
        "expected_conversation_revision": 0, "text": "Explain the selected checked result and its limits.",
        "problem_id": problem["id"], "run_id": run["id"]}, "explain-real-evidence")["body"]
    assert response["author"] == "server" and response["model_commentary"] is None
    assert response["provider_attempt_id"] is None and response["execution_approved"] is False
    assert response["code"] == "provider_consent_required"
    facts = {fact["field"]: fact["value"] for fact in response["facts"] if fact["record_id"] == evidence_record["id"]}
    assert facts["scientific_outcome"] == "certified_counterexample"
    assert facts["baseline_search"]["attempted_count"] > 0
    assert facts["scientific_problem_digest"] == evidence["scientific_problem_digest"]
    assert any(fact["record_id"] == dataset["id"] and fact["field"] == "origin" and fact["value"] == "synthetic"
               for fact in response["facts"])
    assert any("strictly outside the reviewed interval" in text for text in response["critical_statements"])
    assert any("synthetic examples" in text for text in response["critical_statements"])
    assert client.get(PREFIX + f"/workspaces/{workspace}/provider-attempts").json() == []
    assert worker.tick() == 0


def test_real_baseline_survives_exhausted_assistance_with_optional_work_unresolved(scientific_client):
    """Budget failure preserves real discovery/checking and its portable evidence."""
    import hashlib

    from bean_api.main import PREFIX
    from test_scientific_http import post

    client = scientific_client
    workspace, dataset, problem, plan, approval, run, worker = _approved_real_agent_run(
        client, EvidenceModel(mode="loop"), optional=True, provider_turns=2)
    assert worker.tick() == 1
    finished = client.get(PREFIX + f"/runs/{run['id']}").json()
    assert finished["state"] == "failed" and finished["error_code"] == "agent_model_budget_exhausted", finished
    assert finished["provider_turns"] == 2 and finished["scientific_reservations"] == 1
    scenario, = finished["scenarios"]
    assert scenario["scenario_id"] == "baseline" and scenario["state"] == "completed"
    evidence_record = client.get(PREFIX + f"/records/{scenario['result_id']}").json()
    evidence = evidence_record["body"]["result"]
    assert evidence_record["body"]["run_id"] == run["id"]
    assert evidence["scientific_outcome"] == "certified_counterexample"
    assert evidence["verification"] == "valid" and evidence["expected_binding"] == "matches"
    assert evidence["replay"] == "passed" and evidence["baseline_search"]["attempted_count"] > 0
    summary = client.get(PREFIX + f"/records/{finished['result_id']}").json()["body"]
    assert summary["status"] == "failed" and summary["explanation"] is None
    baseline, optional = summary["scenario_observations"]
    assert baseline == {"scenario_id": "baseline", "observation_scope": "coordinator_invocation",
                        "disposition": "completed", "evidence_id": evidence_record["id"], "reason_code": None}
    assert optional == {"scenario_id": "optional", "observation_scope": "coordinator_invocation",
                        "disposition": "unresolved", "evidence_id": None, "reason_code": "agent_model_budget_exhausted"}
    assert len(summary["evidence"]) == 1 and summary["evidence"][0]["id"] == evidence_record["id"]
    reference, = evidence["artifacts"]
    downloaded = client.get(PREFIX + f"/artifacts/{reference['id']}")
    assert downloaded.status_code == 200
    assert hashlib.sha256(downloaded.content).hexdigest() == reference["sha256"]
    anchors = client.get(PREFIX + f"/artifacts/{reference['id']}/anchor?download=true").json()
    assert anchors["run_id"] == run["id"] and anchors["scenario_id"] == "baseline"
    assert anchors["dataset_digest"] == dataset["digest"] and anchors["problem_digest"] == problem["digest"]
    replay = client.app.state.adapter.replay_native(downloaded.content, expected=anchors)
    assert replay["integrity"] == replay["replay"] == "passed", replay
    assert replay["verification"] == "valid" and replay["expected_binding"] == "matches"
    assert replay["search_replayed"] is False
    assert {row["candidate_id"] for row in replay["candidate_results"]} == {row["id"] for row in evidence["candidates"]}
    assert post(client, f"/plans/{plan['id']}/runs", {
        "approval_id": approval["id"], "expected_plan_digest": plan["digest"]}, "retry-failed-assistance")["id"] == run["id"]
    assert worker.tick() == 0
    assert client.get(PREFIX + f"/runs/{run['id']}").json() == finished
    assert client.get(PREFIX + f"/records/{evidence_record['id']}").json() == evidence_record
    assert client.get(PREFIX + f"/artifacts/{reference['id']}").content == downloaded.content
    assert len(client.get(PREFIX + f"/workspaces/{workspace}/records?kind=evidence").json()) == 1
    assert len(client.get(PREFIX + f"/workspaces/{workspace}/records?kind=controlled_attempt").json()) == 2
    assert client.get(PREFIX + f"/workspaces/{workspace}/provider-attempts").json() == []
