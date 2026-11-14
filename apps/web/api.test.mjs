import { test } from 'node:test'
import assert from 'node:assert/strict'
import { ApiError, BeanApi, MAX_JSON_BYTES, baselineAvailable, baselineExplanation, liveGeminiAvailable } from './api.mjs'
import { datasetBody, problemBody, planRequest, investigationObjective } from './manual.mjs'

test('uncertain mutation retry retains its operation key and token never enters body or URL', async () => {
  const seen = []
  const api = new BeanApi('private-token', async (url, options) => {
    seen.push({ url, ...options })
    if (seen.length === 1) throw new Error('connection lost')
    return new Response('{}')
  })
  await assert.rejects(api.json('/plans/p/approvals', { accepted: true }))
  await api.json('/plans/p/approvals', { accepted: true })
  assert.equal(seen[0].headers['Idempotency-Key'], seen[1].headers['Idempotency-Key'])
  assert.equal(seen[0].headers.Authorization, 'Bearer private-token')
  assert.ok(!seen[0].url.includes('private-token') && !seen[0].body.includes('private-token'))
})
test('mismatched download bytes are rejected', async () => {
  const api = new BeanApi('token', async () => new Response('{}', { headers: { 'X-Artifact-SHA256': 'incorrect' } }))
  await assert.rejects(api.download('/artifacts/e'), /digest mismatch/)
})
test('baseline availability uses the actual operation without awarding global scientific qualification', () => {
  assert.equal(Boolean(baselineAvailable({})), false)
  const configured = { contract_version: 'DB-SC-1', policy_version: 'GF-2', science: { verified_in_environment: false, available: true, baseline_discovery: true } }
  assert.equal(baselineAvailable(configured), true)
  assert.equal(baselineAvailable({ ...configured, science: { ...configured.science, available: false } }), false)
  assert.equal(baselineAvailable({ ...configured, science: { available: true, verified_in_environment: true } }), false)
})
test('manual wire mapping preserves excluded duplicates, original spelling and server identities', () => {
  const draft = { rows: [0, 1, 2, 2].map((t, i) => ({ id: i + 1, time: `${t}.00`, concentration: '1.20', epsilon: '0.1', included: i !== 3 })), sources: [], question: {
    aMin: '1', aMax: '12', keMin: '0.1', keMax: '0.3', kaMin: '0.5', kaMax: '2', targetMin: '0.10', targetMax: '17/100', allowanceOrigin: 'Reviewed hard bound', methods: '', goal: '',
  } }
  const dataset = datasetBody(draft, { experiment: 'exp', timeOrigin: 'Dose at t=0', origin: 'actual' })
  assert.equal(dataset.rows.length, 4)
  assert.equal(dataset.rows[3].included, false)
  assert.equal(dataset.rows[3].time, dataset.rows[2].time)
  assert.equal(dataset.rows[0].original_values.concentration, '1.20')
  const problem = problemBody(draft, { id: 'server-dataset', digest: 'server-digest' })
  assert.equal(problem.dataset_digest, 'server-digest')
  const plan = planRequest({ id: 'server-problem', digest: 'server-problem-digest', body: problem })
  assert.equal(plan.plan.scenarios[0].problem_digest, 'server-problem-digest')
  assert.equal(plan.plan.provider_disclosure.provider, 'none')
  assert.equal(plan.plan.scientific_profile, 'counterdex.v1')
  assert.equal(plan.plan.objective.version, 'research-objective.v1')
  assert.match(plan.plan.objective.question, /\[1\/10, 17\/100\]/)
  assert.match(plan.plan.objective.success_criterion, /No witness found does not prove the claim/)
  assert.equal(investigationObjective({ body: problem }, '  Could this experiment support another ke? ').question, 'Could this experiment support another ke?')
  assert.throws(() => investigationObjective({ body: problem }, 'x'.repeat(2001)), /2,000/)
})

test('native download must match both transport digest and selected evidence reference', async () => {
  const content = new TextEncoder().encode('{"native":true}')
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', content)), b => b.toString(16).padStart(2, '0')).join('')
  const api = new BeanApi('token', async () => new Response(content, { headers: { 'X-Artifact-SHA256': digest } }))
  assert.equal((await api.download('/artifacts/native', { sha256: digest, byte_size: content.length })).digest, digest)
  await assert.rejects(api.download('/artifacts/native', { sha256: '0'.repeat(64) }), /evidence reference/)
  await assert.rejects(api.download('/artifacts/native', { byte_size: content.length + 1 }), /evidence reference/)
})

test('bounded search and failed checking cannot be explained as proof', () => {
  assert.match(baselineExplanation({ scientific_outcome: 'no_counterexample_found' }), /does not prove/)
  assert.match(baselineExplanation({ scientific_outcome: 'numerical_candidate' }), /does not establish/)
  assert.match(baselineExplanation({ scientific_outcome: 'certified_counterexample', verification: 'invalid' }), /Incomplete or unsuccessful checking/)
  assert.match(baselineExplanation({ scientific_outcome: 'certified_counterexample', verification: 'valid', expected_binding: 'matches', replay: 'passed' }), /strictly outside/)
})

test('a lost mutation response is reported as uncertain, a lost read as unreachable, a refusal as rejected', async () => {
  const lost = new BeanApi('t', async () => { throw new Error('socket closed') })
  await assert.rejects(lost.json('/plans/p/approvals', { accepted: true }), e => e instanceof ApiError && e.kind === 'uncertain' && /cannot create a second one/.test(e.message))
  await assert.rejects(lost.json('/runs/r'), e => e.kind === 'unreachable' && /Nothing was changed/.test(e.message))
  const refused = new BeanApi('t', async () => new Response(JSON.stringify({ code: 'stale_revision', message: 'Review again.', field_paths: ['plan.problem_id'], current_revision_id: 'p2', request_id: 'req' }), { status: 409 }))
  await assert.rejects(refused.json('/x', {}), e => e.kind === 'rejected' && e.code === 'stale_revision' && e.status === 409 && e.fieldPaths[0] === 'plan.problem_id' && e.currentRevisionId === 'p2')
})
test('a different request body gets a different operation key', async () => {
  const keys = []
  const api = new BeanApi('t', async (url, options) => { keys.push(options.headers['Idempotency-Key']); return new Response('{}') })
  await api.json('/plans/p/runs', { approval_id: 'a' }); await api.json('/plans/p/runs', { approval_id: 'b' }); await api.json('/plans/p/runs', { approval_id: 'a' })
  assert.notEqual(keys[0], keys[1]); assert.equal(keys[0], keys[2])
})
test('oversized and malformed responses are refused, not parsed', async () => {
  const declared = new BeanApi('t', async () => new Response('{}', { headers: { 'Content-Length': String(MAX_JSON_BYTES + 1) } }))
  await assert.rejects(declared.json('/x'), e => e.kind === 'too_large')
  const streamed = new BeanApi('t', async () => new Response(new Uint8Array(MAX_JSON_BYTES + 5)))
  await assert.rejects(streamed.json('/x'), e => e.kind === 'too_large')
  const garbage = new BeanApi('t', async () => new Response('<html>'))
  await assert.rejects(garbage.json('/x'), e => e.kind === 'malformed')
})


test('follow-up explanation preserves pair scope and refuses unchecked conclusions', () => {
  const result = { native_replay: { operation: 'recheck' }, verification: 'valid', expected_binding: 'matches', replay: 'passed', scientific_outcome: 'inconclusive' }
  assert.match(baselineExplanation(result), /rechecked the two previously selected candidates/)
  assert.match(baselineExplanation(result), /does not establish global model inconsistency/)
  for (const changed of [{ verification: 'invalid' }, { expected_binding: 'mismatch' }, { replay: 'unavailable' }]) {
    assert.match(baselineExplanation({ ...result, ...changed }), /incomplete or its evidence does not match/)
  }
})

test('source upload preserves bytes and retains the operation identity after a lost response', async () => {
  const seen = [], bytes = new Uint8Array([137, 80, 78, 71])
  const api = new BeanApi('private-token', async (url, options) => {
    seen.push({ url, ...options })
    if (seen.length === 1) throw new Error('lost response')
    return new Response('{"id":"source_test"}')
  })
  const file = { type: 'image/png', size: bytes.length, arrayBuffer: async () => bytes.buffer }
  await assert.rejects(api.uploadSource('workspace', file, 'synthetic'), error => error.kind === 'uncertain')
  assert.equal((await api.uploadSource('workspace', file, 'synthetic')).id, 'source_test')
  assert.equal(seen[0].headers['Idempotency-Key'], seen[1].headers['Idempotency-Key'])
  assert.equal(seen[0].headers['Content-Type'], 'image/png')
  assert.deepEqual(new Uint8Array(seen[0].body), bytes)
  await assert.rejects(api.uploadSource('workspace', { ...file, type: 'application/pdf' }, 'synthetic'), /PNG or JPEG/)
})

test('live controls require explicit dispatch, live provenance and a disclosed model', () => {
  const available = { gemini: { dispatch_enabled: true, execution_mode: 'live', model: 'gemini-test' } }
  assert.equal(liveGeminiAvailable(available), true)
  for (const patch of [{ dispatch_enabled: false }, { dispatch_enabled: undefined }, { execution_mode: 'controlled' }, { execution_mode: 'disabled' }, { model: null }, { model: '' }]) {
    assert.equal(liveGeminiAvailable({ gemini: { ...available.gemini, ...patch } }), false)
  }
  assert.equal(liveGeminiAvailable({}), false)
})

test('assistant operation identity matches its request body and survives a lost response without automatic retries', async () => {
  const seen = [], api = new BeanApi('token', async (url, options) => {
    seen.push({ url, ...options })
    if (seen.length === 1) throw new Error('lost answer')
    return new Response('{}')
  })
  const body = { client_operation_id: 'assistant_one', expected_conversation_revision: 0, text: 'Explain the selected evidence.' }
  await assert.rejects(api.assistantTurn('workspace', body), error => error.kind === 'uncertain')
  assert.equal(seen.length, 1)
  await api.assistantTurn('workspace', body)
  for (const call of seen) assert.equal(call.headers['Idempotency-Key'], JSON.parse(call.body).client_operation_id)
  assert.equal(seen[0].body, seen[1].body)
  assert.equal(seen[0].url, '/api/bean/v1/workspaces/workspace/assistant-turns')
  await assert.rejects(api.assistantTurn('workspace', { ...body, client_operation_id: '' }), /operation identity/)
  assert.equal(seen.length, 2)
})
