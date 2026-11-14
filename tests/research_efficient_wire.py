"""Substituted-SDK policy for context/accounting tests; never production Gemini.

Consumes actual canonical snapshots/tool results. It does not compute science or
predict a dataset's answer. This fixture demonstrates one admissible turn shape,
not how a live model will reason or how verbose it will be.
"""
import json

from google.genai import types

from bean_api.research_controlled import _next_step


def efficient_calls(contents, sequence):
    context = json.loads(contents[0].parts[0].text)
    reviewed, snapshot = context['reviewed_context'], context['canonical_snapshot']
    completed = snapshot['completed_tools_in_action']
    results = {part.function_response.name: part.function_response.response['output']
               for content in contents for part in content.parts if part.function_response is not None}
    problem = reviewed.get('current_problem') or reviewed.get('problem')
    plan = snapshot['todos']

    def call(name, args):
        return {'name': name, 'args': args, 'id': f'offline-efficient-{sequence}-{name}', 'type': 'tool_call'}

    if not problem:
        return [call('request_clarification', {'fields': ['reviewed_problem'], 'question': 'Review the supported model, measurements, allowances and claim before investigation.'})]
    if not completed:
        report = snapshot['latest_report']
        if report:
            action = report.get('agent_commentary', {}).get('next_action')
            if action != 'review_design':
                return [call('request_clarification', {'fields': ['new_observation'] if action == 'review_observation' else ['scientific_scope'],
                    'question': 'Separately review the next reading or scientific assumptions before further work.'})]
            if not reviewed.get('design_constraints'):
                return [call('request_clarification', {'fields': ['design_constraints'], 'question': 'Review feasible times, horizon and allowance before pair design.'})]
            proposed = [{**todo, 'status': 'in_progress' if todo['status'] != 'completed' else 'completed'} for todo in plan]
            prepare = {'kind': 'design', 'reference_ids': report['evidence_ids'][:1]}
        else:
            proposed = [{'content': 'Investigate reviewed data after approval', 'status': 'in_progress'},
                        {'content': 'Read evidence; choose next action', 'status': 'pending'}]
            prepare = {'kind': 'investigation', 'reference_ids': [problem['id']]}
        return [call('write_todos', {'todos': proposed}), call('prepare_scientific_proposal', prepare)]
    if 'prepare_scientific_proposal' in results:
        proposal = results['prepare_scientific_proposal']
        return [call('run_scientific_operation', {key: proposal[key] for key in ('proposal_id','proposal_digest','review_id','review_digest')})]
    if 'run_scientific_operation' in results:
        child = results['run_scientific_operation']
        facts = child.get('canonical_evidence', [])
        if child.get('state') != 'completed' or not facts:
            return [call('request_clarification', {'fields': ['scientific_scope'], 'question': 'Review the incomplete scientific result.'})]
        action, title, text = _next_step(facts[-1])
        evidence_ids = list(dict.fromkeys([fact['id'] for fact in snapshot['evidence'] + facts]))
        return [call('write_todos', {'todos': [*[{**todo, 'status':'completed'} for todo in plan], {'content':title,'status':'pending'}]}),
                call('publish_research_report', {'evidence_ids': evidence_ids, 'text':text,'next_action':action})]
    raise AssertionError('Unexpected fixture continuation; do not fabricate a scientific result')


def efficient_response(calls, model):
    return types.GenerateContentResponse(candidates=[types.Candidate(
        content=types.Content(role='model', parts=[types.Part(function_call=types.FunctionCall(
            name=call['name'], args=call['args'], id=call['id']), thought_signature=b'DRBEAN-DUMMY-signature') for call in calls]), finish_reason='STOP')],
        usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=20, candidates_token_count=6, total_token_count=26),
        model_version=model)
