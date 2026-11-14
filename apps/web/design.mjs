import { parseExact, compareExact } from './exact.mjs'

export function designAvailable(capabilities) {
  return capabilities?.contract_version === 'DB-SC-1' && capabilities?.policy_version === 'GF-2'
    && capabilities.science?.available === true && capabilities.science?.native_design === true
    && capabilities.science?.native_design_requested_tiers?.includes('checked_pair_separation') === true
}

export function designCandidates(evidence) {
  const result = evidence?.body?.result
  if (result?.projection_version !== 'DB-SC-1-to-groundwork-v1' || result.expected_binding !== 'matches'
      || result.replay !== 'passed' || result.verification !== 'valid') return []
  return (result.candidates ?? []).filter(candidate => candidate.verification === 'valid'
    && candidate.problem_id === result.problem_id && candidate.problem_digest === result.problem_digest)
}

export function designRequest(run, evidence, draft) {
  const result = evidence?.body?.result, candidates = designCandidates(evidence)
  if (!run || evidence?.body?.run_id !== run.id || candidates.length < 2) throw new Error('Open a baseline with two freshly checked compatible candidates before preparing a design.')
  const selected = draft.candidateIds.map(id => candidates.find(candidate => candidate.id === id))
  if (selected.length !== 2 || selected.some(candidate => !candidate) || selected[0].id === selected[1].id) throw new Error('Select two distinct candidates from this baseline.')
  const values = draft.times.trim().split(/[\s,]+/).filter(Boolean)
  if (!values.length || values.length > 64) throw new Error('Enter between 1 and 64 feasible elapsed times, separated by commas or spaces.')
  const times = values.map(parseExact)
  if (new Set(times).size !== times.length) throw new Error('Each feasible time must be unique, including equivalent decimal and fraction spellings.')
  if (times.some(time => compareExact(time, '0/1') <= 0)) throw new Error('Feasible elapsed times must be positive.')
  const allowance = parseExact(draft.allowance), horizon = parseExact(draft.horizon)
  if (compareExact(allowance, '0/1') <= 0) throw new Error('Enter a positive future hard allowance.')
  if (compareExact(horizon, '0/1') <= 0 || times.some(time => compareExact(time, horizon) > 0)
      || selected.some(candidate => candidate.checked_horizon && compareExact(candidate.checked_horizon, horizon) > 0)) {
    throw new Error('The maximum horizon must cover the historical observations and every feasible time.')
  }
  const description = draft.allowanceDescription.trim()
  if (!description || description.length > 2000) throw new Error('Explain the future hard allowance in 1–2,000 characters. It is not a standard deviation or confidence interval.')
  if (!['reviewed_hard_bound', 'hypothetical'].includes(draft.allowanceOrigin)) throw new Error('Choose the origin of the future hard allowance.')
  if (draft.allowContinuation && !draft.allowConstruction) throw new Error('Extending the checked horizon requires permission to construct fixed-vector certificates.')
  const sources = (result.artifacts ?? []).filter(artifact => artifact.media_type === 'application/vnd.counterdex.native+json')
  if (sources.length !== 1) throw new Error('This design needs the retained native baseline evidence.')
  return {
    schema_version: 'DB-SC-1', scientific_profile: 'counterdex.v1', requested_tier: 'checked_pair_separation',
    historical_run_id: run.id, scenario_id: evidence.body.scenario_id,
    problem_id: result.problem_id, problem_digest: result.problem_digest,
    candidate_ids: selected.map(candidate => candidate.id), candidate_vectors: selected.map(candidate => ({ ...candidate.parameter_vector })),
    observable: 'concentration', feasible_times: times, future_hard_allowance: allowance,
    allowance_origin: { kind: draft.allowanceOrigin, description }, maximum_horizon: horizon,
    allow_construction: Boolean(draft.allowConstruction), allow_continuation: Boolean(draft.allowContinuation),
    source_artifact_ids: [],
    budget: { wall_seconds: 120, fixed_vector_constructions: 2, pair_verifications: 2, bundle_bytes: 4194304 },
  }
}

export function designExplanation(result) {
  if (result.design_tier === 'checked_pair_separation' && result.verification === 'valid' && result.replay === 'passed'
      && result.verification_record?.expected_binding === 'matches') {
    return 'The selected time has a freshly checked positive separation margin for these two fixed candidates and the reviewed future hard allowance. This distinguishes this pair under the assumptions; it does not identify the true model or rule out every other candidate.'
  }
  if (result.design_tier === 'no_separation_established') return 'No separating time was established for this pair on the reviewed grid at this allowance. This does not rule out a useful time elsewhere or establish that the candidates are identical.'
  if (result.design_tier === 'numerical_guidance') return 'This is numerical guidance only. It does not establish checked separation. Review the per-time states and the reason before choosing a measurement.'
  return 'Checked separation was not established. Inspect the execution state, available per-time evidence and reason; an incomplete calculation is not a scientific conclusion.'
}
