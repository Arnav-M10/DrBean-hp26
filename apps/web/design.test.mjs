import { test } from 'node:test'
import assert from 'node:assert/strict'
import { designAvailable, designCandidates, designRequest, designExplanation } from './design.mjs'

// Contract doubles only. Actual scientific acceptance is in check-backend.mjs.
const run = { id: 'returned-run' }
function evidence() {
  return { id: 'returned-evidence', body: { run_id: run.id, scenario_id: 'returned-scenario', result: {
    projection_version: 'DB-SC-1-to-groundwork-v1', problem_id: 'returned-problem', problem_digest: 'returned-digest',
    expected_binding: 'matches', verification: 'valid', replay: 'passed',
    candidates: [0, 1].map(i => ({ id: `returned-candidate-${i}`, problem_id: 'returned-problem', problem_digest: 'returned-digest',
      verification: 'valid', checked_horizon: '4/1', parameter_vector: { A: `${10 + i}/1`, ke: '1/10', ka: '2/1' } })),
    artifacts: [{ id: 'returned-native', media_type: 'application/vnd.counterdex.native+json' }],
  } } }
}
const draft = () => ({ candidateIds: ['returned-candidate-1', 'returned-candidate-0'], times: '8.00, 6', allowance: '0.20', horizon: '8',
  allowanceOrigin: 'reviewed_hard_bound', allowanceDescription: 'Reviewed future absolute error bound', allowConstruction: true, allowContinuation: true })

test('native design requires its actual operation and requested tier to be available', () => {
  const capabilities = { contract_version: 'DB-SC-1', policy_version: 'GF-2', science: { available: true, native_design: true, native_design_requested_tiers: ['checked_pair_separation'] } }
  assert.equal(designAvailable(capabilities), true)
  assert.equal(designAvailable({ ...capabilities, science: { ...capabilities.science, native_design: false } }), false)
  assert.equal(designAvailable({ ...capabilities, science: { available: true, baseline_discovery: true } }), false)
})

test('design preserves returned pair identities and approved grid order without mutating evidence', () => {
  const source = evidence(), before = structuredClone(source), request = designRequest(run, source, draft())
  assert.deepEqual(request.feasible_times, ['8/1', '6/1'])
  assert.equal(request.future_hard_allowance, '1/5')
  assert.equal(request.maximum_horizon, '8/1')
  assert.equal(request.scientific_profile, 'counterdex.v1')
  assert.equal(request.requested_tier, 'checked_pair_separation')
  assert.equal(request.historical_run_id, run.id)
  assert.equal(request.scenario_id, source.body.scenario_id)
  assert.deepEqual(request.candidate_vectors, [...source.body.result.candidates].reverse().map(c => c.parameter_vector))
  assert.deepEqual(request.source_artifact_ids, ['returned-native'])
  request.candidate_vectors[0].A = '99/1'
  assert.deepEqual(source, before)
})

test('design cannot use one witness, an unchecked candidate, another run or an invented pair', () => {
  const source = evidence()
  assert.throws(() => designRequest({ id: 'another-run' }, source, draft()), /baseline/)
  assert.throws(() => designRequest(run, source, { ...draft(), candidateIds: ['invented', 'returned-candidate-0'] }), /distinct candidates/)
  assert.throws(() => designRequest(run, source, { ...draft(), candidateIds: ['returned-candidate-0', 'returned-candidate-0'] }), /distinct candidates/)
  source.body.result.candidates[0].verification = 'not_checked'
  assert.equal(designCandidates(source).length, 1)
  assert.throws(() => designRequest(run, source, draft()), /two freshly checked/)
  source.body.result.replay = 'unsupported'
  assert.deepEqual(designCandidates(source), [])
})

test('design rejects equivalent duplicate times and out-of-scope horizons', () => {
  for (const times of ['6, 6.0', '0, 8', '-1, 8', Array.from({ length: 65 }, (_, i) => i + 1).join(',')]) {
    assert.throws(() => designRequest(run, evidence(), { ...draft(), times }))
  }
  assert.throws(() => designRequest(run, evidence(), { ...draft(), horizon: '7' }), /horizon/)
  assert.throws(() => designRequest(run, evidence(), { ...draft(), times: '2,3', horizon: '3' }), /historical/)
})

test('design requires positive declared precision, retained evidence and explicit extension permission', () => {
  assert.throws(() => designRequest(run, evidence(), { ...draft(), allowance: '0' }), /positive/)
  assert.throws(() => designRequest(run, evidence(), { ...draft(), allowanceDescription: ' ' }), /Explain/)
  assert.throws(() => designRequest(run, evidence(), { ...draft(), allowConstruction: false }), /requires permission/)
  const source = evidence(); source.body.result.artifacts = []
  assert.throws(() => designRequest(run, source, draft()), /retained native/)
  assert.equal(designRequest(run, evidence(), { ...draft(), allowanceOrigin: 'hypothetical' }).allowance_origin.kind, 'hypothetical')
})

test('design explanations keep selected-pair checking distinct from numerical guidance and absence claims', () => {
  assert.match(designExplanation({ design_tier: 'numerical_guidance' }), /does not establish checked separation/)
  assert.match(designExplanation({ design_tier: 'no_separation_established' }), /does not rule out a useful time elsewhere/)
  assert.match(designExplanation({ design_tier: 'checked_pair_separation', verification: 'not_checked' }), /not established/)
  assert.match(designExplanation({ design_tier: 'checked_pair_separation', verification: 'valid', replay: 'passed', verification_record: { expected_binding: 'matches' } }), /does not identify the true model/)
})
