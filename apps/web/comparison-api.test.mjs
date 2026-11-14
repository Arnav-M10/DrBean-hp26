import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { connectComparison, comparisonCanonical } from './comparison-api.mjs'

const request = JSON.parse(await readFile(new URL('../../fixtures/model-comparison/synthetic.request.json', import.meta.url)))
const result = JSON.parse(await readFile(new URL('../../fixtures/model-comparison/synthetic.response.json', import.meta.url)))
const hash = value => createHash('sha256').update(comparisonCanonical(value)).digest('hex')
const metadata = { mode: 'browser_session', authenticated: true, workspace_id: 'workspace_private', credentials: 'server_managed' }
const capability = { available: true, contract_version: 'DB-MODEL-COMPARISON-1', result_contract_version: 'DB-MODEL-COMPARISON-RESULT-1', execution_mode: 'numerical_offline', provider_calls: 0, verification: 'not_performed' }
function record(body = structuredClone(result)) {
  return { id: 'model_comparison_one', workspace_id: metadata.workspace_id, kind: 'model_comparison', body, digest: hash(body), parent_id: null, created_by: 'private_actor', created_at: '2026-11-14T00:00:00Z' }
}
const response = (body, status = 200, headers = {}) => new Response(JSON.stringify(body), { status, headers })
function options() {
  const values = new Map()
  return { storage: { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) }, locks: null, delay: async () => {} }
}
async function fixture(handle, override = capability) {
  const calls = []
  const client = await connectComparison({ sessionOptions: options(), fetcher: async (url, init) => {
    calls.push({ url, ...init })
    if (url.endsWith('/shared-session/current')) return response(metadata)
    if (url.endsWith('/capabilities')) return response({ model_comparison: override })
    return handle(url, init)
  } })
  return { client, calls }
}

test('connected comparison uses only the retained private session and immutable input-bound results', async () => {
  const retained = record()
  const { client, calls } = await fixture((url, init) => response(init.method === 'POST' ? retained : [retained]))
  const submitted = await client.submit(request)
  assert.equal(submitted.id, retained.id)
  assert.equal(Object.isFrozen(submitted.body.request), true)
  assert.equal(Object.isFrozen(submitted.body.fits), true)
  assert.deepEqual(await client.list(), [retained])
  assert.equal(client.workspaceId, metadata.workspace_id)
  assert.deepEqual(calls.map(call => call.url), [
    '/api/bean/v1/shared-session/current', '/api/bean/v1/capabilities',
    '/api/bean/v1/workspaces/workspace_private/model-comparisons',
    '/api/bean/v1/workspaces/workspace_private/model-comparisons',
  ])
  for (const call of calls) {
    assert.equal(call.credentials, 'same-origin')
    assert.equal(call.headers.Authorization, undefined)
    assert.equal(call.headers.Cookie, undefined)
  }
  assert.deepEqual(JSON.parse(calls[2].body), request)
})

test('absent or incompatible numerical capability remains unavailable without a submission', async () => {
  for (const unsupported of [undefined, { ...capability, available: false }, { ...capability, execution_mode: 'live' },
    { ...capability, provider_calls: 1 }, { ...capability, verification: 'checked' }]) {
    await assert.rejects(fixture(() => assert.fail('No numerical operation should start'), unsupported ?? null), error => error.kind === 'not_available')
  }
})

test('approval, request changes and explicit retries keep mutation authority separate', async () => {
  const { client, calls } = await fixture(() => { throw new TypeError('Response lost after possible acceptance') })
  for (const invalid of [{ ...request, approval: 'draft' }, { ...request, review: { ...request.review, reviewed: 1 } }]) {
    await assert.rejects(client.submit(invalid), error => error.kind === 'review_required')
  }
  assert.equal(calls.length, 2)
  await assert.rejects(client.submit(request), error => error.kind === 'uncertain')
  assert.equal(calls.length, 3, 'An uncertain mutation is never automatically resent')
  await assert.rejects(client.submit(request), error => error.kind === 'uncertain')
  const changed = structuredClone(request)
  changed.noise.seed++
  await assert.rejects(client.submit(changed), error => error.kind === 'uncertain')
  assert.equal(calls[2].headers['Idempotency-Key'], calls[3].headers['Idempotency-Key'])
  assert.notEqual(calls[3].headers['Idempotency-Key'], calls[4].headers['Idempotency-Key'])
})

test('workspace, result, input and exact-status substitutions fail the binding checks', async () => {
  const attacks = [
    item => { item.workspace_id = 'other_workspace' },
    item => { item.body.input_digest = '0'.repeat(64) },
    item => { item.digest = '0'.repeat(64) },
    item => { item.body.exact_verification = 'passed'; item.digest = hash(item.body) },
    item => { item.body.request.noise.seed++; item.body.input_digest = hash(item.body.request); item.digest = hash(item.body) },
  ]
  for (const change of attacks) {
    const item = record(); change(item)
    const { client } = await fixture(() => response(item))
    await assert.rejects(client.submit(request), error => error.kind === 'malformed')
  }
  const { client } = await fixture(() => response(record()))
  await assert.rejects(client.get('different_id'), error => error.kind === 'malformed')
  await assert.rejects(client.get('../secrets'), error => error.kind === 'malformed')
})

test('download verifies actual bytes, result identity and reviewed inputs without upgrading outcome', async () => {
  const inconclusive = structuredClone(result)
  inconclusive.status = 'fit_failed'
  inconclusive.decision = 'Neither bounded fit met the declared threshold.'
  const selected = record(inconclusive)
  const packet = { schema_version: 'DB-MODEL-COMPARISON-EXPORT-1', result: selected }
  const encoded = comparisonCanonical(packet)
  const { client } = await fixture(() => new Response(encoded, { headers: { 'X-Artifact-SHA256': createHash('sha256').update(encoded).digest('hex') } }))
  const downloaded = await client.download(selected)
  assert.equal(new TextDecoder().decode(downloaded.bytes), encoded)
  assert.equal(downloaded.record.body.status, 'fit_failed')
  assert.equal(downloaded.record.body.exact_verification, 'not_performed')
  const substituted = record(); substituted.id = 'different_record'
  const bytes = comparisonCanonical({ ...packet, result: substituted })
  const invalid = await fixture(() => new Response(bytes, { headers: { 'X-Artifact-SHA256': createHash('sha256').update(bytes).digest('hex') } }))
  await assert.rejects(invalid.client.download(selected), error => error.kind === 'malformed')
})

test('canonical binding matches the backend fixture and rejects silently coerced values', () => {
  assert.equal(hash(request), result.input_digest)
  for (const invalid of [0.1, -0, -1, Infinity, undefined, '\ud800', { 'β': 'key' }]) {
    assert.throws(() => comparisonCanonical(invalid))
  }
  assert.equal(comparisonCanonical({ text: 'μA 🫘', b: '0.01', a: 3 }), '{"a":3,"b":"0.01","text":"μA 🫘"}')
})
