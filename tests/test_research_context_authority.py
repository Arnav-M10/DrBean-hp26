"""Context compression retains exact tool authority references; no provider calls."""
import copy
import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
import pytest

from bean_api.research_context import model_messages


def exchange(name, arguments, result, call_id, *, status='success'):
    return [AIMessage(content='', tool_calls=[{'name': name, 'args': arguments,
                'id': call_id, 'type': 'tool_call'}],
                additional_kwargs={'gemini_content_parts': [{'thought_signature': 'RFJCRUFO',
                    'function_call': {'name': name, 'args': arguments, 'id': call_id}}]}),
            ToolMessage(content=json.dumps(result) if status == 'success' else result,
                        tool_call_id=call_id, status=status)]


def todo(call_id='intervening-plan'):
    return exchange('write_todos', {'todos': [{'content': 'Review the prepared scope',
        'status': 'in_progress'}]}, {'updated': True}, call_id)


def project(messages):
    result = model_messages(messages, {'todos': [{'content': 'Review the prepared scope',
        'status': 'in_progress'}]}, question='Compare the reviewed range', reviewed_context={})
    return result, json.loads(result[0].content)['canonical_snapshot']


def test_intervening_plan_keeps_exact_prepared_scope_without_granting_approval():
    arguments = {'kind': 'investigation', 'reference_ids': ['reviewed-problem']}
    proposal = {'accepted': False, 'proposal_id': 'prepared-plan', 'proposal_digest': 'exact-input-scope',
                'review_id': 'human-review', 'review_digest': 'exact-reviewed-scope'}
    messages = [HumanMessage(content='Question'), *exchange('prepare_scientific_proposal',
        arguments, proposal, 'prepare')]
    _, immediate = project(messages)
    assert 'latest_prepared_proposal' not in immediate  # Exact response remains in the signed tail.
    messages.extend(todo())
    original = copy.deepcopy(messages)
    view, snapshot = project(messages)
    retained = snapshot['latest_prepared_proposal']
    assert retained == {'tool_call_id': 'prepare', 'arguments': arguments, 'result': proposal}
    assert retained['result']['accepted'] is False
    assert snapshot['authority'] == 'context_only; canonical approval and current backend checks are required'
    assert view[-2] is messages[-2] and view[-1] is messages[-1]
    assert view[-2].additional_kwargs == messages[-2].additional_kwargs
    assert messages == original


@pytest.mark.parametrize('outcome', ['rejected', 'failed', 'cancelled', 'unresolved', 'completed'])
def test_intervening_plan_keeps_operation_status_and_exact_review_binding(outcome):
    arguments = {'proposal_id': 'prepared-plan', 'proposal_digest': 'scope-digest',
                 'review_id': 'human-review', 'review_digest': 'review-digest'}
    result = {'state': outcome, 'job_id': 'original-job', 'proposal_id': 'prepared-plan',
              'error_code': 'bounded_search_inconclusive' if outcome == 'unresolved' else None}
    messages = [HumanMessage(content='Question'), *exchange('run_scientific_operation', arguments, result, 'run')]
    _, immediate = project(messages)
    assert 'last_operation' not in immediate
    messages.extend(todo())
    _, snapshot = project(messages)
    assert snapshot['last_operation'] == {'tool_call_id': 'run', 'arguments': arguments, 'result': result}
    assert snapshot['evidence'] == []


def test_completed_operation_retains_inconclusive_fact_once_without_outcome_upgrade():
    fact = {'id': 'retained-evidence', 'scientific_outcome': 'inconclusive', 'verification': 'valid',
            'native_replay': {'status': 'passed'}}
    result = {'state': 'completed', 'job_id': 'job', 'evidence_ids': [fact['id']], 'canonical_evidence': [fact]}
    messages = [HumanMessage(content='Question'), *exchange('run_scientific_operation',
        {'proposal_id': 'prepared-plan'}, result, 'run'), *todo()]
    original = copy.deepcopy(messages)
    _, snapshot = project(messages)
    assert snapshot['last_operation']['result'] == {key: value for key, value in result.items()
                                                   if key != 'canonical_evidence'}
    assert snapshot['evidence'] == [fact]
    assert snapshot['evidence'][0]['scientific_outcome'] == 'inconclusive'
    assert messages == original


@pytest.mark.parametrize('changed_binding', [False, True])
def test_prepared_binding_is_deduplicated_only_when_operation_carries_every_exact_identifier(changed_binding):
    binding = {'proposal_id': 'prepared-plan', 'proposal_digest': 'scope-digest',
               'review_id': 'human-review', 'review_digest': 'review-digest'}
    operation_binding = {**binding, 'review_digest': 'different-review'} if changed_binding else dict(binding)
    messages = [HumanMessage(content='Question'), *exchange('prepare_scientific_proposal',
        {'kind': 'investigation', 'reference_ids': ['problem']}, {'accepted': False, **binding}, 'prepare'),
        *exchange('run_scientific_operation', operation_binding, {'state': 'rejected'}, 'run')]
    _, immediate = project(messages)
    assert ('latest_prepared_proposal' in immediate) is changed_binding
    assert 'last_operation' not in immediate  # The untouched tail carries it.
    messages.extend(todo())
    _, later = project(messages)
    assert ('latest_prepared_proposal' in later) is changed_binding
    assert later['last_operation']['arguments'] == operation_binding


def test_failed_tool_and_unavailable_design_do_not_disappear_after_plan_revision():
    arguments = {'kind': 'design', 'reference_ids': ['baseline-evidence']}
    unavailable = {'accepted': False, 'available': False, 'kind': 'design',
                   'reason': 'Reviewed feasible times and hard allowance are required.'}
    messages = [HumanMessage(content='Question'), *exchange('prepare_scientific_proposal',
        arguments, unavailable, 'prepare'), *todo()]
    _, snapshot = project(messages)
    assert 'latest_prepared_proposal' not in snapshot
    assert snapshot['latest_tool_failure']['result'] == unavailable
    assert snapshot['latest_tool_failure']['arguments'] == arguments
    messages.extend(exchange('prepare_scientific_proposal', arguments, 'Canonical review is unavailable.',
                             'failed-prepare', status='error'))
    _, immediate = project(messages)
    assert 'latest_tool_failure' not in immediate
    messages.extend(todo('later-plan'))
    _, snapshot = project(messages)
    assert snapshot['latest_tool_failure'] == {'tool': 'prepare_scientific_proposal',
        'tool_call_id': 'failed-prepare', 'arguments': arguments, 'status': 'error',
        'content': 'Canonical review is unavailable.'}


def test_explicit_new_action_does_not_promote_older_operation_or_proposal_to_current_scope():
    fact = {'id': 'retained-evidence', 'scientific_outcome': 'inconclusive'}
    messages = [HumanMessage(content='Original question'),
        *exchange('prepare_scientific_proposal', {'kind': 'investigation', 'reference_ids': ['problem']},
                  {'accepted': False, 'proposal_id': 'old-proposal'}, 'prepare'),
        *exchange('run_scientific_operation', {'proposal_id': 'old-proposal'},
                  {'state': 'completed', 'evidence_ids': [fact['id']], 'canonical_evidence': [fact]}, 'run'),
        *exchange('prepare_scientific_proposal', {'kind': 'design', 'reference_ids': [fact['id']]},
                  {'accepted': False, 'available': False, 'reason': 'Missing feasible times'}, 'missing'),
        HumanMessage(content='Explicitly advanced question')]
    _, snapshot = project(messages)
    assert not {'latest_prepared_proposal', 'last_operation', 'latest_tool_failure'} & snapshot.keys()
    assert snapshot['evidence'] == [fact]
    assert snapshot['completed_tools_in_action'] == []


def test_incomplete_exchange_is_never_compacted_or_rebound():
    messages = [HumanMessage(content='Question'), *todo()]
    messages.pop()  # No tool response yet: preserve exact call and signature.
    result = model_messages(messages, {}, question='Question', reviewed_context={})
    assert result is messages
