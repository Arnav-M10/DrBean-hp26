import test from 'node:test'
import assert from 'node:assert/strict'
import { ResearchController, designConstraints, researchSnapshot, researchCapacity, researchStopMessage } from './research.mjs'

const snapshot = (changes = {}) => ({ schema_version: 'DB-RESEARCH-1', id: 'research_session_test', workspace_id: 'ws_test', revision: 0,
  objective: 'Does this reviewed range survive?', mode: 'controlled', state: 'ready', children: [], reports: [], pending_review: null, pending_review_digest: null, ...changes })
const storage = () => { const values = new Map(); return { getItem: key => values.get(key), setItem: (key, value) => values.set(key, value) } }
function setup(api) {
  const draft = { question: { goal: 'Does this reviewed range survive?' }, rows: [{ value: '3.0' }] }
  const controller = new ResearchController({ getDraft: () => draft, storage: storage() })
  const connection = { api, identityId: 'private_alice', workspaceId: 'ws_test', capabilities: {}, saveReviewedInputs: async () => ({ problem: { id: 'problem_test', digest: 'a'.repeat(64) } }) }
  return { controller, connection, draft }
}
const empty = { json: async path => path.endsWith('/research-sessions') ? { items: [] } : path.includes('/events?') ? { items: [] } : snapshot() }

test('snapshot refuses foreign workspaces and altered review bindings', () => {
  assert.equal(researchSnapshot(snapshot(), 'ws_test').id, 'research_session_test')
  assert.throws(() => researchSnapshot(snapshot(), 'ws_other'))
  assert.throws(() => researchSnapshot(snapshot({ pending_review: { id: 'plan_test', workspace_id: 'ws_test', digest: 'a'.repeat(64) }, pending_review_digest: 'b'.repeat(64) }), 'ws_test'))
})

test('create, restore and polling are separate from explicit advance', async () => {
  const calls = [], api = { json: async (path, body, key) => { calls.push({ path, body, key }); return body ? snapshot() : path.endsWith('/research-sessions') ? { items: [] } : path.includes('/events?') ? { items: [] } : snapshot() } }
  const { controller: c, connection, draft } = setup(api)
  await c.connect(connection); c.state.dataAccepted = true; c.state.acceptedDraft = JSON.stringify(draft)
  await c.create(); assert.equal(c.state.snapshot.objective, draft.question.goal)
  assert.equal(calls.filter(call => call.body).length, 1)
  assert.ok(!calls.some(call => call.path.endsWith('/advance')))
  await c.refresh(); assert.equal(calls.filter(call => call.body).length, 1)
  await c.advance(); assert.equal(calls.filter(call => call.path.endsWith('/advance')).length, 1)
})

test('uncertain response keeps frozen body and operation identity across reopen', async () => {
  const calls = []; let uncertain = true
  const api = { json: async (path, body, key) => { calls.push({ path, body, key }); if (body && uncertain) throw Object.assign(new Error('Unknown outcome'), { kind: 'uncertain' }); return body ? snapshot() : path.endsWith('/research-sessions') ? { items: [] } : path.includes('/events?') ? { items: [] } : snapshot() } }
  const { controller: c, connection, draft } = setup(api)
  await c.connect(connection); c.state.dataAccepted = true; c.state.acceptedDraft = JSON.stringify(draft); await c.create()
  const pending = structuredClone(c.state.pending); assert.ok(pending.key); draft.question.goal = 'Changed draft after timeout'
  const reopened = new ResearchController({ getDraft: () => draft, storage: c.storage }); await reopened.connect(connection)
  assert.deepEqual(reopened.state.pending, pending); uncertain = false; await reopened.retry()
  assert.equal(calls.at(-1).key, pending.key); assert.deepEqual(calls.at(-1).body, pending.body)
  assert.equal(reopened.state.pending, null)
})

test('late mutation response cannot replace another private identity or workspace', async () => {
  let release; const response = new Promise(resolve => { release = resolve })
  const api = { json: async (path, body) => body ? response : { items: [] } }
  const { controller: c, connection, draft } = setup(api)
  await c.connect(connection); c.state.dataAccepted = true; c.state.acceptedDraft = JSON.stringify(draft)
  const pending = c.create(); await new Promise(resolve => setTimeout(resolve, 0))
  await c.connect({ ...connection, api: empty, identityId: 'private_bob', workspaceId: 'ws_bob' })
  release(snapshot()); await pending
  assert.equal(c.state.snapshot, null); assert.equal(c.connection.identityId, 'private_bob')
})

test('changed draft invalidates data acknowledgement before saving records', async () => {
  const { controller: c, connection, draft } = setup(empty); let saves = 0
  connection.saveReviewedInputs = async () => { saves++; return {} }
  await c.connect(connection); c.state.dataAccepted = true; c.state.acceptedDraft = JSON.stringify(draft); draft.rows[0].value = '7.0'
  await c.create(); assert.equal(saves, 0); assert.match(c.state.error, /Review and accept/)
})

test('a blank personal question uses the same closed claim question as manual review', async () => {
  const requests = []
  const api = { json: async (path, body) => {
    if (!body) return { items: [] }
    requests.push(body)
    return snapshot({ objective: body.objective })
  } }
  const { controller, connection, draft } = setup(api)
  Object.assign(draft.question, { goal: '', targetMin: '0.10', targetMax: '0.17' })
  connection.saveReviewedInputs = async () => ({ problem: { id: 'problem_test', digest: 'a'.repeat(64),
    body: { target: { lower: '1/10', upper: '17/100' } } } })
  await controller.connect(connection)
  controller.state.dataAccepted = true; controller.state.acceptedDraft = JSON.stringify(draft)
  await controller.create()
  assert.equal(requests.length, 1)
  assert.match(requests[0].objective, /outside the closed interval \[1\/10, 17\/100\]/)
})

test('approval is bound to the exact server review and rejects chat-like consent', async () => {
  const { controller: c, connection } = setup(empty); await c.connect(connection)
  const review = { id: 'plan_test', digest: 'a'.repeat(64), workspace_id: 'ws_test' }
  c.state.snapshot = snapshot({ pending_review: review, pending_review_digest: review.digest, state: 'waiting_review' })
  c.state.reviewAccepted = 'yes'
  await assert.rejects(() => c.decide('approve'), /exact pending/)
})

test('measurement constraints retain exact values and demand their origin', () => {
  assert.equal(designConstraints({}), null)
  assert.throws(() => designConstraints({ times: '6, 8' }), /together/)
  const result = designConstraints({ times: '8, 6', allowance: '0.2', horizon: '10', allowanceReason: 'Reviewed prospective bound' })
  assert.deepEqual(result.feasible_times, ['8/1', '6/1']); assert.equal(result.future_hard_allowance, '1/5')
})

test('general sources retain an untrusted question without forced model inputs or approval', async () => {
  const calls = [], api = { json: async (path, body) => { calls.push({ path, body }); return body ? snapshot({ problem_id: null }) : { items: [] } } }
  const { controller: c, connection } = setup(api)
  c.getSources = () => [{ id: 'research_asset_table' }]; c.getSourceQuestion = () => 'Which model applies to these arbitrary columns?'
  connection.saveReviewedInputs = () => { throw new Error('General files cannot silently create concentration inputs') }
  await c.connect(connection); await c.createFromSources()
  const body = calls.at(-1).body
  assert.equal(body.objective, c.getSourceQuestion()); assert.equal(body.problem_id, undefined); assert.equal(body.accepted, undefined)
  assert.deepEqual(body.source_ids, ['research_asset_table']); assert.equal(calls.filter(call => call.body).length, 1)
})

test('live session saving neither consents nor grants provider allocation', async () => {
  const calls = [], api = { json: async (path, body) => { calls.push({ path, body }); return body ? snapshot({ mode: 'live' }) : { items: [] } } }
  const { controller: c, connection, draft } = setup(api)
  connection.capabilities = { deepagents: { execution_mode: 'live', dispatch_enabled: true }, gemini: { model: 'gemini-2.5-flash-lite' } }
  await c.connect(connection); c.state.dataAccepted = true; c.state.acceptedDraft = JSON.stringify(draft)
  await c.create()
  assert.equal(calls.at(-1).body.mode, 'live')
  assert.equal(calls.filter(call => call.body).length, 1)
  assert.equal(calls.some(call => /consent|allocation|advance/.test(call.path)), false)
})

test('explicit live consent freezes the exact disclosure and never advances or allocates', async () => {
  const calls = [], scope = 'c'.repeat(64), current = snapshot({ mode: 'live', provider_disclosure: { context_digest: scope } })
  const api = { json: async (path, body) => {
    calls.push({ path, body })
    if (body) return { id: 'consent_test', kind: 'research_provider_consent', workspace_id: 'ws_test', body: { research_session_id: current.id, context_digest: scope, model: body.model, accepted: true } }
    return path.endsWith('/research-sessions') ? { items: [] } : current
  } }
  const { controller: c, connection } = setup(api)
  connection.capabilities = { deepagents: { execution_mode: 'live' }, gemini: { model: 'gemini-2.5-flash-lite' } }
  await c.connect(connection); c.state.snapshot = current
  await assert.rejects(() => c.consent(), /disclosure/)
  c.state.providerAccepted = true; await c.consent()
  const mutation = calls.filter(call => call.body)
  assert.equal(mutation.length, 1)
  assert.equal(mutation[0].path, `/research-sessions/${current.id}/provider-consents`)
  assert.deepEqual(mutation[0].body, { model: 'gemini-2.5-flash-lite', expected_context_digest: scope, accepted: true })
  assert.equal(c.state.pending, null)
})


test('live continuation respects token, accounting, action-quota and unknown-outcome projections independently of remaining calls', () => {
  const live = {mode:'live', provider_allocation:{physical_requests:6}, usage:{physical_calls:1}, provider_usage:{accounting_valid:true,remaining:{physical_requests:5,input_tokens:100,output_tokens:100}}}
  assert.equal(researchCapacity(live).blocked,false)
  for (const key of ['physical_requests','input_tokens','output_tokens']) assert.equal(researchCapacity({...live,provider_usage:{...live.provider_usage,remaining:{...live.provider_usage.remaining,[key]:0}}}).blocked,true)
  assert.equal(researchCapacity({...live,provider_usage:{...live.provider_usage,accounting_valid:false}}).blocked,true)
  for (const interaction of [{quota_exhausted:true},{recovery:{required:true,can_reconcile:false}}]) assert.equal(researchCapacity({...live,interaction}).blocked,true)
  assert.equal(researchCapacity({mode:'live',provider_allocation:{physical_requests:0}}).blocked,true)
  assert.equal(researchCapacity({mode:'controlled'}).blocked,false)
})
test('provider stops have readable safe guidance without hiding their separate technical code', () => {
  assert.match(researchStopMessage('provider_rate_limited'),/No automatic retry/)
  assert.match(researchStopMessage('provider_budget_exhausted'),/existing allocation/)
  assert.match(researchStopMessage('research_provider_allocation_exhausted'),/Consent does not grant/)
  assert.match(researchStopMessage('unknown'),/Inspect the saved state/)
})
