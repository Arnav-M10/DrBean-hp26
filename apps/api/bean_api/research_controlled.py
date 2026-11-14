"""Offline test policy for the ordinary Deep Agents investigation path.

This is a deterministic test fixture, not live AI or evidence of provider
understanding. It selects real graph tools from their actual returned records;
it never computes, supplies or fabricates a scientific result. Reconstructed
instances derive progress from checkpointed messages, not process-local turns.
"""
from __future__ import annotations

import json
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from .coordinator import CoordinatorFailure

CONTROLLED_POLICY_VERSION = "research-controlled.v1"


def _object(content: Any) -> dict[str, Any]:
    try:
        value = json.loads(content) if isinstance(content, str) else content
    except (TypeError, ValueError):
        raise CoordinatorFailure("controlled_research_observation_invalid") from None
    if not isinstance(value, dict):
        raise CoordinatorFailure("controlled_research_observation_invalid")
    return value


def _observations(messages: list) -> list[tuple[str, dict, Any]]:
    calls, observed = {}, []
    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                calls[call["id"]] = call
        elif isinstance(message, ToolMessage):
            call = calls.get(message.tool_call_id)
            if call is None or message.status == "error":
                raise CoordinatorFailure("controlled_research_observation_invalid")
            # write_todos returns a human-readable acknowledgement. Every other
            # tool returns a typed record; never infer a result from its prose.
            body = None if call["name"] == "write_todos" else _object(message.content)
            observed.append((call["name"], call["args"], body))
    return observed


def _next_step(fact: dict) -> tuple[str, str, str]:
    candidates = fact.get("candidates") or []
    checked_pair = (len(candidates) == 2 and all(
        isinstance(c, dict) and c.get("verification") == "valid" and c.get("parameter_vector")
        for c in candidates) and candidates[0]["id"] != candidates[1]["id"]
        and candidates[0]["parameter_vector"] != candidates[1]["parameter_vector"])
    if (fact.get("scientific_outcome") == "certified_counterexample"
            and fact.get("verification") == "valid" and fact.get("expected_binding") == "matches"
            and fact.get("replay") == "passed" and checked_pair):
        return ("review_design", "Review feasible times and allowance for a separately approved pair design",
                "The evidence has a conditional scope. Compatibility does not identify the true model.")
    if fact.get("scientific_outcome") == "no_counterexample_found":
        return ("clarify", "Review assumptions and the bounded search scope before proposing further work",
                "The search does not prove the interval. The true model remains unknown.")
    return ("clarify", "Review the unresolved scientific result and missing design prerequisites",
            "The evidence has a conditional scope. No claim that all alternatives are eliminated is supported.")


class ControlledResearchModel(BaseChatModel):
    """Explicit local fixture; has no provider, key, transport or dataset-name rules."""

    model_name: str = "drbean-offline-research-fixture-v1"

    @property
    def _llm_type(self) -> str:
        return "drbean-controlled-research"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model_name": self.model_name, "policy_version": CONTROLLED_POLICY_VERSION,
                "execution_mode": "offline_test_fixture"}

    def bind_tools(self, tools, **kwargs):
        # The graph separately checks the exact effective inventory. This
        # adapter adds no tools, fallback model or hidden request.
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        starts = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
        if not starts:
            raise CoordinatorFailure("controlled_research_context_missing")
        current = messages[starts[-1]:]
        context = _object(current[0].content).get("reviewed_context")
        if not isinstance(context, dict):
            raise CoordinatorFailure("controlled_research_context_missing")
        observed = _observations(current)
        name, args = self._choose(context, observed)
        # Unique across the retained thread, including new admitted actions.
        sequence = sum(len(m.tool_calls) for m in messages if isinstance(m, AIMessage))
        message = AIMessage(content="", tool_calls=[{"name": name, "args": args,
            "id": f"controlled-research-{sequence}", "type": "tool_call"}])
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    def _choose(self, context: dict, observed: list[tuple[str, dict, Any]]) -> tuple[str, dict]:
        problem = context.get("current_problem") or context.get("problem")
        if not isinstance(problem, dict) or not problem.get("id"):
            return "request_clarification", {"fields": ["reviewed_problem"], "question":
                "Review the supported model, measurements, time origin, hard allowances, parameter domain "
                "and closed claim interval before scientific execution. Uploaded prose alone is insufficient."}
        if not observed:
            return "write_todos", {"todos": [
                {"content": "Investigate the reviewed measurements after canonical approval", "status": "in_progress"},
                {"content": "Read actual scientific evidence and choose a useful next step", "status": "pending"}]}
        name, args, body = observed[-1]
        if name == "write_todos":
            facts = [value for tool, _, value in observed if tool == "read_research_evidence"]
            if facts:
                action, _, text = _next_step(facts[-1])
                return "publish_research_report", {"evidence_ids": [f["id"] for f in facts],
                    "text": text, "next_action": action}
            return "prepare_scientific_proposal", {"kind": "investigation", "reference_ids": [problem["id"]]}
        if name == "prepare_scientific_proposal":
            if body.get("available") is False:
                return "request_clarification", {"fields": ["reviewed_inputs"],
                    "question": "The backend could not prepare this scope. Review the required assumptions and inputs."}
            keys = ("proposal_id", "proposal_digest", "review_id", "review_digest")
            if body.get("accepted") is not False or not all(isinstance(body.get(k), str) and body[k] for k in keys):
                raise CoordinatorFailure("controlled_research_proposal_invalid")
            return "run_scientific_operation", {key: body[key] for key in keys}
        if name == "run_scientific_operation":
            if body.get("state") != "completed" or not body.get("evidence_ids"):
                return "request_clarification", {"fields": ["scientific_scope"],
                    "question": "This operation was rejected or produced no completed evidence. Review its disposition before new work."}
            return "read_research_evidence", {"evidence_id": body["evidence_ids"][0]}
        if name == "read_research_evidence":
            if body.get("id") != args.get("evidence_id"):
                raise CoordinatorFailure("controlled_research_evidence_invalid")
            child = next(value for tool, _, value in reversed(observed) if tool == "run_scientific_operation")
            read = {value["id"] for tool, _, value in observed if tool == "read_research_evidence"}
            remaining = [ref for ref in child["evidence_ids"] if ref not in read]
            if remaining:
                return "read_research_evidence", {"evidence_id": remaining[0]}
            _, title, _ = _next_step(body)
            previous = next(arguments["todos"] for tool, arguments, _ in reversed(observed) if tool == "write_todos")
            return "write_todos", {"todos": [
                *[{"content": todo["content"], "status": "completed"} for todo in previous],
                {"content": title, "status": "pending"}]}
        raise CoordinatorFailure("controlled_research_unexpected_continuation")


def build_controlled_research_model() -> ControlledResearchModel:
    """B's zero-argument production factory for the explicitly offline test lane."""
    return ControlledResearchModel()
