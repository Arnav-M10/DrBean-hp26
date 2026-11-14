"""Offline preflight: controlled graph/transport checks, never account discovery.

Run with the pinned backend interpreter. No credentials or environment keys are
read. This proves controlled orchestration only, not Counterdex or live Gemini.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import socket
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))


def preflight() -> dict:
    attempts = []
    original_connect, original_connect_ex = socket.socket.connect, socket.socket.connect_ex

    def deny_connect(*args, **kwargs):
        attempts.append("socket_connection_attempt")
        raise RuntimeError("External dispatch is prohibited in offline preflight")

    socket.socket.connect = deny_connect
    socket.socket.connect_ex = deny_connect
    report = {"offline_preflight_passed": False, "live_qualification": "not_run",
              "evidence_level": "controlled_graph_with_controlled_tools",
              "dispatch_observation_scope": "socket.connect/connect_ex in this preflight process",
              "external_dispatch_attempts": 0, "actual_model_tokens": 0}
    try:
        from langchain_core.language_models.chat_models import BaseChatModel
        from langchain_core.messages import AIMessage, ToolMessage
        from langchain_core.outputs import ChatGeneration, ChatResult
        from pydantic import BaseModel

        from bean_api.coordinator import CoordinatorScope, ScopedCallbacks, run_coordinator
        from bean_api.providers import (
            AttemptContext, GeminiProvider, ProviderConfig, ProviderFailure, package_version,
        )

        class LocalLedger:
            def __init__(self):
                self.attempts = []

            def begin_attempt(self, context, metadata):
                self.attempts.append({"context": context, "metadata": metadata})
                return f"local-{len(self.attempts)}"

            def finish_attempt(self, attempt_id, metadata):
                self.attempts[int(attempt_id.split("-")[-1]) - 1]["result"] = metadata

        class ControlledModel(BaseChatModel):
            model_name: str = "drbean-offline-preflight-v1"
            mode: str = "adaptive"

            @property
            def _llm_type(self):
                return "drbean-controlled"

            def bind_tools(self, tools, **kwargs):
                return self

            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                observed = [json.loads(m.content) for m in messages if isinstance(m, ToolMessage)]
                if not observed:
                    name, args = "execute_approved_scenario", {"scenario_id": "baseline"}
                elif self.mode == "loop":
                    name, args = "read_scoped_evidence", {"evidence_id": observed[0]["id"]}
                elif len(observed) == 1:
                    if observed[0]["scientific_outcome"] == "no_counterexample_found":
                        name, args = "execute_approved_scenario", {"scenario_id": "optional"}
                    else:
                        name, args = "record_allowed_skip", {
                            "scenario_id": "optional", "reason_code": "sufficient_evidence"}
                else:
                    name, args = "return_grounded_explanation", {
                        "fact_ids": [observed[0]["id"]], "next_action": "stop",
                        "text": "This is controlled commentary about a synthetic tool result."}
                message = AIMessage(content="", tool_calls=[{
                    "id": f"local-call-{len(observed)}", "name": name, "args": args, "type": "tool_call"}])
                return ChatResult(generations=[ChatGeneration(message=message)])

            async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
                return self._generate(messages, stop, run_manager, **kwargs)

        config = ProviderConfig(api_key="nonsecret-controlled-dummy", model="drbean-offline-preflight-v1",
                                account_gate_passed=True, account_decision_id="controlled-local-policy")
        context = AttemptContext("local-actor", "local-workspace", "local-operation", "local-consent")
        disabled_ledger = LocalLedger()
        provider = GeminiProvider(config, disabled_ledger)
        try:
            asyncio.run(provider.generate("explanation", "Offline boundary control", BaseModel, context=context))
        except ProviderFailure as exc:
            if exc.code != "provider_dispatch_disabled":
                raise RuntimeError("Unexpected provider boundary result") from None
        else:
            raise RuntimeError("Live provider boundary unexpectedly admitted work")
        if disabled_ledger.attempts:
            raise RuntimeError("Disabled provider reserved an attempt")
        report["provider_boundary"] = "disabled_before_client_or_reservation"
        report["versions"] = {name: package_version(name) for name in ("deepagents", "langchain", "google-genai")}
        report["branches"] = []
        for outcome in ("certified_counterexample", "no_counterexample_found"):
            ledger, executed, skipped = LocalLedger(), [], []

            def execute(scenario_id):
                executed.append(scenario_id)
                return {"id": "fact-" + scenario_id, "problem_id": "local-problem",
                        "scientific_outcome": outcome,
                        "verification": "valid" if outcome == "certified_counterexample" else "not_checked",
                        "expected_binding": "matches", "controlled_tool_result": True}

            def skip(scenario_id, reason):
                skipped.append(scenario_id)
                return {"id": "local-skip"}

            callbacks = ScopedCallbacks(lambda: None, execute, lambda _: None, skip)
            result = asyncio.run(run_coordinator(config, ledger, context,
                CoordinatorScope("local-run", "local-plan", "local-problem", "baseline", ("optional",)),
                callbacks, chat_model=ControlledModel()))
            if result.status != "completed" or not result.explanation:
                raise RuntimeError("Controlled graph did not complete")
            expected = ["baseline", "optional"] if outcome == "no_counterexample_found" else ["baseline"]
            if executed != expected or skipped != ([] if len(expected) == 2 else ["optional"]):
                raise RuntimeError("Controlled graph scenario accounting mismatch")
            observations = result.scenario_observations
            expected_dispositions = ["completed", "completed" if len(expected) == 2 else "skipped"]
            if ([item["scenario_id"] for item in observations] != ["baseline", "optional"]
                    or [item["disposition"] for item in observations] != expected_dispositions
                    or any(item["observation_scope"] != "coordinator_invocation" for item in observations)):
                raise RuntimeError("Controlled graph observations are incomplete")
            report["branches"].append({"controlled_outcome": outcome, "executed": executed,
                "skipped": skipped, "result": asdict(result)})
        retained_fact = {"id": "retained-baseline", "problem_id": "local-problem",
                         "scientific_outcome": "inconclusive", "verification": "not_checked",
                         "expected_binding": "matches", "controlled_tool_result": True}
        failed = asyncio.run(run_coordinator(config, LocalLedger(), context,
            CoordinatorScope("interrupted-run", "local-plan", "local-problem", "baseline", ("optional",)),
            ScopedCallbacks(lambda: None, lambda _: dict(retained_fact), lambda _: dict(retained_fact), lambda *_: None),
            chat_model=ControlledModel(mode="loop")))
        if (failed.status != "failed" or failed.error_code != "agent_model_budget_exhausted"
                or len(failed.evidence) != 1
                or [item["disposition"] for item in failed.scenario_observations] != ["completed", "unresolved"]):
            raise RuntimeError("Interrupted assistance did not preserve scenario observations")
        report["failure_controls"] = [{"expected_failure": "agent_model_budget_exhausted",
                                       "result": asdict(failed)}]
        report["offline_preflight_passed"] = not attempts
    except Exception as exc:
        # Fixed public code only; dependency exceptions may contain source data.
        report["error_code"] = "offline_preflight_failed"
        report["error_type"] = type(exc).__name__
    finally:
        report["external_dispatch_attempts"] = len(attempts)
        socket.socket.connect, socket.socket.connect_ex = original_connect, original_connect_ex
    return report


if __name__ == "__main__":
    output = preflight()
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    raise SystemExit(0 if output["offline_preflight_passed"] else 1)
