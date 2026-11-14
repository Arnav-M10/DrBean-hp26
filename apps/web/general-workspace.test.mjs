// Controlled service results exercise UI authority; no hosted model is called.
import test from 'node:test'
import assert from 'node:assert/strict'
import { GeneralResearchWorkspace, GENERAL_LIMITS, generalCapabilities, validateFileSelection, validateResearchAsset, validateResearchAnalysis } from './general-workspace.mjs'

const text = 'temperature_C,growth_percent\n18,12\n24,29\n'
const capabilities = { general_research: { available: true, media_types: ['text/csv', 'text/plain', 'application/json', 'application/pdf'], max_assets: 5, max_file_bytes: 5242880, max_total_bytes: 10485760, max_pdf_pages: 10, analysis: { available: true, model: 'controlled-model' }, budget: { remaining: { requests: 3, input_tokens: 4568, output_tokens: 4736 } } } }
const workspaceId = 'ws-private'
class Storage {
  values = new Map()
  get length() { return this.values.size }
  key(index) { return [...this.values.keys()][index] }
  getItem(key) { return this.values.get(key) ?? null }
  setItem(key, value) { this.values.set(key, value) }
  removeItem(key) { this.values.delete(key) }
}
const digest = async bytes => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('')
async function fixture(overrides = {}) {
  const file = new File([text], 'plant-growth.csv', { type: 'text/csv' })
  const sha256 = await digest(await file.arrayBuffer())
  const asset = { id: 'source-plant', workspace_id: workspaceId, filename: file.name, sha256, byte_size: file.size, media_type: 'text/csv', provenance: { origin: 'user_supplied' }, pages: [{ page_index: 0, page_number: 1, width: null, height: null, image_sha256: null, text_sha256: sha256, text_preview: text }] }
  const result = { id: 'analysis-plant', workspace_id: workspaceId, body: { summary: 'The supplied table compares growth at two temperatures.', extracted_tables: [{ id: 'growth-table', title: 'Plant growth', columns: ['temperature_C', 'growth_percent'], rows: [['18', '12'], ['24', '29']], citation_ids: ['c1'] }], claims: [{ text: 'The two rows report different growth values.', citation_ids: ['c1'] }], limitations: ['Two rows do not establish a causal effect.'], clarifications: [{ question: 'How many replicates were measured?', citation_ids: [] }], suggested_next_steps: [{ text: 'Record replicate counts and experimental conditions.', citation_ids: ['c1'] }], citations: [{ id: 'c1', asset_id: asset.id, source_sha256: sha256, page_index: 0, quote: '24,29' }], execution_mode: 'controlled', provider_attempt_id: null, verification: { status: 'not_mathematically_verified', supported_adapter: null } } }
  const calls = { uploads: [], analyses: [], assets: [], gets: [] }
  const service = { upload: async (file, key) => { calls.uploads.push({ file, key }); return structuredClone(asset) },
    analyze: async body => { calls.analyses.push(structuredClone(body)); return structuredClone(result) },
    asset: async id => { calls.assets.push(id); return structuredClone(asset) },
    analysis: async id => { calls.gets.push(id); return structuredClone(result) }, ...overrides }
  let sequence = 0
  const storage = new Storage()
  const ui = new GeneralResearchWorkspace({ storage, serviceFactory: () => service, randomId: () => `operation-${++sequence}` })
  const connection = { api: {}, capabilities: structuredClone(capabilities), workspaceId, mode: 'browser_session' }
  await ui.connect(connection)
  return { ui, service, calls, file, asset, result, storage, connection }
}
async function reviewed(f) { await f.ui.upload([f.file]); f.ui.editQuestion('What patterns and limitations are present in this table?'); f.ui.prepareReview(); f.ui.accept(true) }

test('own arbitrary-column CSV stays unchanged and upload grants no AI consent', async () => {
  const f = await fixture(); await f.ui.upload([f.file])
  assert.equal(f.ui.state.assets[0].filename, 'plant-growth.csv')
  assert.equal(f.calls.analyses.length, 0)
  assert.match(f.ui.state.notice, /Nothing has been sent/)
  f.ui.editQuestion('Compare growth, without assuming a concentration model.'); f.ui.prepareReview()
  await f.ui.analyze()
  assert.equal(f.calls.analyses.length, 0)
  f.ui.accept(true); await f.ui.analyze()
  assert.deepEqual(f.ui.state.result.body.extracted_tables[0].columns, ['temperature_C', 'growth_percent'])
  assert.equal(f.ui.state.result.body.verification.status, 'not_mathematically_verified')
  assert.equal(f.calls.analyses[0].consent.include_question, true)
})

test('edited question or source selection invalidates reviewed consent and creates a new operation', async () => {
  const f = await fixture(); await reviewed(f)
  const original = f.ui.state.review
  assert.ok(Object.isFrozen(original.consent))
  f.ui.editQuestion('A different research question')
  assert.equal(f.ui.state.review, null); assert.equal(f.ui.state.accepted, false)
  await f.ui.analyze(); assert.equal(f.calls.analyses.length, 0)
  f.ui.prepareReview(); assert.notEqual(f.ui.state.review.client_operation_id, original.client_operation_id)
  f.ui.removeAsset(f.asset.id); assert.equal(f.ui.state.review, null)
})

test('uncertain mutation retries preserve original key/body after draft edits and reload', async () => {
  let fail = true
  const f = await fixture()
  const original = f.service.analyze
  f.service.analyze = async body => { if (fail) { f.calls.analyses.push(structuredClone(body)); throw Object.assign(new Error('Response was lost'), { kind: 'uncertain' }) }; return original(body) }
  await reviewed(f); const body = f.ui.state.review
  await f.ui.analyze(); assert.equal(f.ui.state.pending[0].status, 'uncertain')
  f.ui.editQuestion('A new question must not replace the uncertain request.'); f.ui.prepareReview()
  assert.notEqual(f.ui.state.review.client_operation_id, body.client_operation_id)
  const reopened = new GeneralResearchWorkspace({ storage: f.storage, serviceFactory: () => f.service })
  await reopened.connect(f.connection)
  assert.equal(f.calls.analyses.length, 1, 'reload retrieves metadata and never invokes analysis')
  fail = false; await reopened.analyze(reopened.state.pending[0].body)
  assert.deepEqual(f.calls.analyses[0], f.calls.analyses[1])
  assert.equal(reopened.state.pending.length, 0)
  assert.equal(reopened.state.resultQuestion, body.question)
})

test('saved result reopens by GET without another provider mutation', async () => {
  const f = await fixture(); await reviewed(f); await f.ui.analyze()
  const reopened = new GeneralResearchWorkspace({ storage: f.storage, serviceFactory: () => f.service })
  await reopened.connect(f.connection); await reopened.reopen(reopened.state.history[0])
  assert.equal(f.calls.analyses.length, 1); assert.deepEqual(f.calls.gets, ['analysis-plant'])
  assert.match(reopened.state.notice, /No new model call/)
})

test('failed later analysis preserves completed evidence and exposes refusal', async () => {
  const f = await fixture(); await reviewed(f); await f.ui.analyze()
  const saved = f.ui.state.result
  f.ui.editQuestion('What else?'); f.ui.prepareReview(); f.ui.accept(true)
  f.service.analyze = async () => { throw Object.assign(new Error('Application budget exhausted'), { kind: 'rejected', status: 429 }) }
  await f.ui.analyze()
  assert.deepEqual(f.ui.state.result, saved); assert.match(f.ui.state.error, /budget exhausted/)
})

test('shared demo cannot enable private upload or reuse saved session state', async () => {
  const f = await fixture(); await reviewed(f)
  await f.ui.connect({ ...f.connection, mode: 'shared_demo' })
  await f.ui.upload([f.file]); assert.equal(f.calls.uploads.length, 1)
  assert.equal(f.ui.service, null); assert.equal(f.ui.state.assets.length, 0)
})

test('new private workspace drops old draft and never applies a late upload', async () => {
  const f = await fixture()
  let release
  f.service.upload = () => new Promise(resolve => { release = () => resolve(f.asset) })
  const task = f.ui.upload([f.file])
  while (!release) await new Promise(resolve => setTimeout(resolve, 0))
  await f.ui.connect({ ...f.connection, workspaceId: 'ws-other-private' })
  release(); await task
  assert.equal(f.ui.state.assets.length, 0); assert.equal(f.ui.state.result, null)
})

test('budget preflight and unavailable analysis do not call a provider', async () => {
  for (const state of ['unavailable', 'no_requests', 'no_input', 'no_output']) {
    const f = await fixture()
    const caps = structuredClone(capabilities)
    if (state === 'unavailable') caps.general_research.analysis.available = false
    else caps.general_research.budget.remaining[state === 'no_requests' ? 'requests' : state === 'no_input' ? 'input_tokens' : 'output_tokens'] = 0
    await f.ui.connect({ ...f.connection, capabilities: caps }); await f.ui.upload([f.file]); f.ui.editQuestion('A valid question'); f.ui.prepareReview()
    assert.equal(f.ui.state.review, null); assert.ok(f.ui.state.error); assert.equal(f.calls.analyses.length, 0)
  }
})

test('malformed source bindings, PDFs over ten pages, and inconsistent page numbering refuse admission', async () => {
  const f = await fixture()
  assert.throws(() => validateResearchAsset({ ...f.asset, sha256: '0'.repeat(64) }, { sha256: f.asset.sha256 }), /match/)
  assert.throws(() => validateResearchAsset({ ...f.asset, pages: [{ ...f.asset.pages[0], page_index: 1 }] }), /page identities/)
  assert.throws(() => validateResearchAsset({ ...f.asset, pages: Array(11).fill(f.asset.pages[0]) }), /page list/)
})

test('citation source/page/bbox and fake mathematical badge are rejected', async () => {
  const f = await fixture()
  for (const mutate of [r => { r.body.citations[0].source_sha256 = '0'.repeat(64) }, r => { r.body.citations[0].page_index = 1 },
    r => { r.body.claims[0].citation_ids = ['missing'] }, r => { r.body.citations[0].bbox = [0, 0, 100, 100]; r.body.citations[0].bbox_space = 'pixels' },
    r => { r.body.verification.status = 'verified' }]) {
    const bad = structuredClone(f.result); mutate(bad)
    assert.throws(() => validateResearchAnalysis(bad, [f.asset], workspaceId))
  }
})

test('selection checks counts, server-advertised formats and size without reading oversized bytes', () => {
  const limits = generalCapabilities(capabilities)
  assert.throws(() => validateFileSelection([], [{ name: 'huge.csv', type: 'text/csv', size: GENERAL_LIMITS.fileBytes + 1 }], limits), /5 MiB/)
  assert.throws(() => validateFileSelection([], Array(6).fill({ name: 'a.txt', type: 'text/plain', size: 1 }), limits), /1 and 5/)
  assert.throws(() => validateFileSelection([], [{ name: 'macro.xlsm', type: 'application/vnd.ms-excel', size: 1 }], limits), /not supported/)
  assert.throws(() => validateFileSelection([{ byte_size: GENERAL_LIMITS.totalBytes - 1 }], [{ name: 'a.txt', type: 'text/plain', size: 2 }], limits), /combined limit/)
})

test('uncertain uploads keep exact key and bytes across retry and reload reselection, including empty MIME', async () => {
  const f = await fixture()
  const keys = [], bodies = []
  let fail = true
  f.service.upload = async (file, key) => {
    keys.push(key); bodies.push({ type: file.type, name: file.name, bytes: Buffer.from(await file.arrayBuffer()) })
    if (fail) throw Object.assign(new Error('Lost upload acknowledgement'), { kind: 'uncertain' })
    return f.asset
  }
  const file = new File([text], f.file.name, { type: '' })
  await f.ui.upload([file]); assert.equal(f.ui.state.pendingUploads.length, 1)
  const restored = new GeneralResearchWorkspace({ storage: f.storage, serviceFactory: () => f.service })
  await restored.connect(f.connection)
  assert.equal(keys.length, 1, 'reload never retries an upload')
  fail = false; await restored.upload([file])
  assert.equal(keys[0], keys[1]); assert.deepEqual(bodies[0], bodies[1])
  assert.equal(bodies[1].type, 'text/csv'); assert.equal(restored.state.assets.length, 1)
})

test('restore immediately clears old UI, locks edits, and keeps same-identity workspace pending history', async () => {
  const f = await fixture(); await reviewed(f)
  f.service.analyze = async () => { throw new Error('Unknown outcome') }
  await f.ui.analyze()
  const original = f.ui.state.pending[0].body
  await f.ui.connect({ ...f.connection, workspaceId: 'ws-second' })
  let release
  f.service.asset = () => new Promise(resolve => { release = () => resolve(f.asset) })
  const emissions = []
  f.ui.changed = state => emissions.push({ busy: state.busy, assets: state.assets.length, question: state.question })
  const restoration = f.ui.connect(f.connection)
  assert.deepEqual(emissions[0], { busy: true, assets: 0, question: '' })
  f.ui.editQuestion('This edit must be disabled during restoration')
  release(); await restoration
  assert.equal(f.ui.state.pending[0].body.client_operation_id, original.client_operation_id)
  assert.notEqual(f.ui.state.question, 'This edit must be disabled during restoration')
})

test('reopen rejects a same-workspace wrong result or wrong metadata identity without replacing evidence', async () => {
  const f = await fixture(); await reviewed(f); await f.ui.analyze()
  const original = f.ui.state.result
  f.service.analysis = async () => ({ ...f.result, id: 'wrong-analysis' })
  await f.ui.reopen(f.ui.state.history[0])
  assert.match(f.ui.state.error, /selected saved result/); assert.deepEqual(f.ui.state.result, original)
  f.service.asset = async () => ({ ...f.asset, id: 'wrong-source' })
  await f.ui.reopen(f.ui.state.history[0])
  assert.match(f.ui.state.error, /selected bytes or workspace/); assert.deepEqual(f.ui.state.result, original)
})
