import test from 'node:test'
import assert from 'node:assert/strict'
import { ResearchController, designConstraints, researchSnapshot } from './research.mjs'

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
