"""Deterministic model-facing snapshots; the durable graph/audit remains untouched.

Completed exchanges may be summarized only after every tool response is present.
The latest exchange, including provider-signed parts and tool-call IDs, is copied
without alteration. Scientific facts retain their existing validated projections.
No model, provider, new authority or request is used to build this view.
"""
from __future__ import annotations

import copy
import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from .coordinator import CoordinatorFailure

VERSION = "research-canonical-context.v1"


def model_messages(messages, state, *, question, reviewed_context):
    calls, pending, facts, reports = {}, set(), {}, []
    prepared = operation = failure = None
    last_ai = None
    current_start = 0
    completed = []
    for index, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            if pending:
                return messages  # Never cut an incomplete provider exchange.
            current_start = index
            completed = []
            prepared = operation = failure = None
        elif isinstance(message, AIMessage):
            if pending or message.invalid_tool_calls:
                return messages
            last_ai = index
            for call in message.tool_calls:
                if call['id'] in calls:
                    return messages
                calls[call['id']] = call
                pending.add(call['id'])
        elif isinstance(message, ToolMessage):
            if message.tool_call_id not in pending:
                return messages
            pending.remove(message.tool_call_id)
            call = calls[message.tool_call_id]
            completed.append(call['name'])
            if message.status == 'error':
                failure = {'tool': call['name'], 'tool_call_id': message.tool_call_id,
                           'arguments': copy.deepcopy(call['args']), 'status': 'error',
                           'content': copy.deepcopy(message.content)}
                continue
            try:
                value = json.loads(message.content)
            except (TypeError, ValueError):
                continue  # Todo acknowledgements are plain text, not facts.
            observed = []
            retained = {'tool_call_id': message.tool_call_id, 'arguments': copy.deepcopy(call['args']),
                        'result': copy.deepcopy(value)}
            if call['name'] == 'prepare_scientific_proposal' and isinstance(value, dict):
                if value.get('available') is False:
                    failure = {'tool': call['name'], **retained}
                elif value.get('proposal_id'):
                    prepared = retained
            elif call['name'] == 'run_scientific_operation' and isinstance(value, dict):
                operation = retained
                # These immutable facts are retained separately in evidence (or
                # the untouched last exchange), so do not repeat their bodies.
                operation['result'].pop('canonical_evidence', None)
            if call['name'] == 'read_research_evidence' and isinstance(value, dict) and value.get('id') == call['args'].get('evidence_id'):
                observed = [value]
            elif call['name'] == 'run_scientific_operation' and isinstance(value, dict) and value.get('state') == 'completed':
                observed = [fact for fact in value.get('canonical_evidence', [])
                            if isinstance(fact, dict) and fact.get('id') in value.get('evidence_ids', [])]
            elif call['name'] == 'publish_research_report' and isinstance(value, dict):
                report = {key: copy.deepcopy(value[key]) for key in ('id', 'evidence_ids', 'agent_commentary', 'commentary_persisted') if key in value}
                if isinstance(report.get('agent_commentary'), dict):
                    # Prior narration stays in the immutable report; the model
                    # needs its proposed next action and the actual facts.
                    report['agent_commentary'].pop('text', None)
                reports.append(report)
            for fact in observed:
                key = fact['id']
                if key in facts and facts[key] != fact:
                    raise CoordinatorFailure('research_evidence_binding_invalid')
                facts[key] = copy.deepcopy(fact)
    if pending:
        return messages
    # Only the current action's last complete exchange remains a provider turn.
    # Older signed messages remain intact in checkpoint storage, never rewritten.
    tail = messages[last_ai:] if last_ai is not None and last_ai > current_start else []
    tail_responses = {message.tool_call_id for message in tail if isinstance(message, ToolMessage)}
    tail_facts = set()
    for message in tail:
        if isinstance(message, ToolMessage) and message.status != 'error':
            try:
                value = json.loads(message.content)
            except (TypeError, ValueError):
                continue
            call = calls.get(message.tool_call_id, {})
            if call.get('name') == 'read_research_evidence' and isinstance(value, dict):
                tail_facts.add(value.get('id'))
            elif call.get('name') == 'run_scientific_operation' and isinstance(value, dict):
                tail_facts.update(fact.get('id') for fact in value.get('canonical_evidence', []) if isinstance(fact, dict))
    snapshot = {'version': VERSION, 'todos': copy.deepcopy(state.get('todos', [])),
                'completed_tools_in_action': completed, 'evidence': [fact for key, fact in facts.items() if key not in tail_facts],
                'latest_report': reports[-1] if reports else None,
                'authority': 'context_only; canonical approval and current backend checks are required'}
    # A model may revise its plan between preparing and running a proposal, or
    # between a rejected/failed operation and its explanation. Keep those exact
    # scoped results after their provider exchange leaves the tail. These are
    # context only: running a proposal still rereads canonical human approval.
    bindings = ('proposal_id', 'proposal_digest', 'review_id', 'review_digest')
    represented_operations = [call['args'] for message in tail if isinstance(message, AIMessage)
                              for call in message.tool_calls if call['name'] == 'run_scientific_operation']
    if operation is not None:
        represented_operations.append(operation['arguments'])
    if (prepared is not None and all(isinstance(prepared['result'].get(key), str) and prepared['result'][key]
                                    for key in bindings)
            and any(all(arguments.get(key) == prepared['result'][key] for key in bindings)
                    for arguments in represented_operations)):
        # The exact prepared binding is already carried by a later operation;
        # its original acknowledgement remains immutable in the audit history.
        prepared = None
    for key, retained in (('latest_prepared_proposal', prepared), ('last_operation', operation),
                          ('latest_tool_failure', failure)):
        if retained is not None and retained['tool_call_id'] not in tail_responses:
            snapshot[key] = retained
    reviewed_context = copy.deepcopy(reviewed_context)
    problem, current = reviewed_context.get('problem'), reviewed_context.get('current_problem')
    if isinstance(problem, dict) and current == {'id': problem.get('id'), 'digest': problem.get('digest'), 'same_as': 'problem'}:
        reviewed_context.pop('current_problem')  # Exact alias; full problem stays.
    content = {'question': question, 'reviewed_context': reviewed_context, 'canonical_snapshot': snapshot}
    return [HumanMessage(content=json.dumps(content, ensure_ascii=False, separators=(',', ':'))), *tail]
