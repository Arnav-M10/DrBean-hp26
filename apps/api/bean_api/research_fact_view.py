"""Model-only evidence views. Full records remain the publication authority.

Omit storage/codec labels and verified duplicate copies, never scientific values,
candidate vectors, scope, uncertainty or a disagreeing check. Artifact hashes and
canonical evidence identity remain available; downloads retain the full packet.
"""
from __future__ import annotations

import copy


def live_fact(fact):
    if fact.get('fact_projection') not in {'agent-evidence.v1', 'agent-design-evidence.v1'}:
        return fact
    view = copy.deepcopy(fact)
    for key in ('workspace_id', 'fact_projection_version', 'projection_version', 'fact_view', 'source_fact_digest'):
        view.pop(key, None)
    artifacts = view.get('artifacts')
    if not isinstance(artifacts, list) or not all(isinstance(item, dict) for item in artifacts):
        return fact
    for artifact in artifacts:
        for key in ('byte_size', 'media_type'):
            artifact.pop(key, None)
    record = view.get('verification_record')
    if len(artifacts) == 1 and isinstance(record, dict):
        equal = {'artifact_id': artifacts[0].get('id'), 'artifact_sha256': artifacts[0].get('sha256'),
                 'verification': view.get('verification'), 'expected_binding': view.get('expected_binding'),
                 'expected_problem_digest': view.get('problem_digest'), 'observed_problem_digest': view.get('problem_digest'),
                 'expected_scientific_problem_digest': view.get('scientific_problem_digest'),
                 'observed_scientific_problem_digest': view.get('scientific_problem_digest')}
        for key, value in equal.items():
            if value is not None and record.get(key) == value:
                record.pop(key, None)
    replay = view.get('native_replay')
    if isinstance(replay, dict):
        # The remaining axes are explicitly distinct. Equal copies inherit the
        # named root fields, rather than turning replay into scientific proof.
        inherited = []
        for key in ('replay', 'verification', 'expected_binding', 'dataset_origin'):
            if key in replay and key in view and replay[key] == view[key]:
                inherited.append(key)
                del replay[key]
        if inherited:
            replay['same_as_fact'] = inherited
        replay.pop('packet_profile', None)  # Serialization metadata, not science.
        anchors = replay.get('anchors')
        equal = {'problem_digest': view.get('problem_digest'), 'projection_digest': view.get('scientific_problem_digest'),
                 'design_digest': view.get('scientific_design_digest'), 'run_id': view.get('run_id'),
                 'scenario_id': view.get('scenario_id')}
        if len(artifacts) == 1:
            equal['artifact_sha256'] = artifacts[0].get('sha256')
        for key, value in equal.items():
            if isinstance(anchors, dict) and value is not None and anchors.get(key) == value:
                anchors.pop(key, None)
        if (view.get('native_suggestion_digest') is not None
                and replay.get('suggestion_digest') == view['native_suggestion_digest']):
            replay.pop('suggestion_digest', None)
        outcome = replay.get('outcome')
        candidates = view.get('candidates', [])
        if (isinstance(outcome, dict) and isinstance(candidates, list) and candidates
                and all(isinstance(candidate, dict) and 'id' in candidate for candidate in candidates)):
            equal = {'scientific_outcome': view.get('scientific_outcome'), 'reason_code': view.get('reason_code')}
            if all('verification' in c for c in candidates):
                equal['compatible_candidate_ids'] = [c['id'] for c in candidates if c['verification'] == 'valid']
            if all(type(c.get('is_counterexample')) is bool for c in candidates):
                equal['counterexample_ids'] = [c['id'] for c in candidates if c['is_counterexample']]
            inherited = []
            for key, value in equal.items():
                if value is not None and outcome.get(key) == value:
                    outcome.pop(key, None)
                    inherited.append(key)
            if inherited:
                outcome['same_as_fact_and_candidates'] = inherited
    return view
