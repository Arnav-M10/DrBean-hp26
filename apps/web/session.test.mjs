import { test } from 'node:test'
import assert from 'node:assert/strict'
import { bootstrapSharedSession, readConnection } from './session.mjs'
import { BeanApi } from './api.mjs'

const metadata = { mode: 'browser_session', authenticated: true, workspace_id: 'workspace_private', credentials: 'server_managed' }
const reply = (body, status = 200) => new Response(JSON.stringify(body), { status })
const missing = () => reply({ code: 'browser_session_missing' }, 401)
function options() {
  const values = new Map()
  return { storage: { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) }, locks: null, delay: async () => {} }
}

test('first visit confirms cookie retention before returning a private authenticated transport', async () => {
  const calls = []; let issued = false
  const { api, session } = await bootstrapSharedSession(async (url, request) => {
    calls.push({ url, ...request })
    if (url.endsWith('/shared-session')) { issued = true; return reply(metadata) }
    if (url.endsWith('/current')) return issued ? reply(metadata) : missing()
    return reply([])
  }, options())
  assert.deepEqual(session, metadata)
  assert.equal(Object.isFrozen(session), true)
  await api.json('/workspaces')
  assert.deepEqual(calls.map(c => c.url), ['/shared-session/current', '/shared-session', '/shared-session/current', '/workspaces'].map(p => '/api/bean/v1' + p))
  for (const call of calls) {
    assert.equal(call.method, 'GET')
    assert.equal(call.credentials, 'same-origin')
    assert.equal(call.headers.Authorization, undefined)
    assert.equal(call.headers.Cookie, undefined)
    assert.equal(call.cache, 'no-store')
    assert.equal(call.redirect, 'error')
  }
})

test('reload and second tab recover a valid session without issuance or rotation', async () => {
  const calls = [], config = options()
  const fetcher = async url => { calls.push(url); return reply(metadata) }
  await bootstrapSharedSession(fetcher, config)
  await bootstrapSharedSession(fetcher, config)
  assert.deepEqual(calls, Array(2).fill('/api/bean/v1/shared-session/current'))
})

test('startup retry is bounded and limited to nonissuing reads', async () => {
  const config = options(), calls = [], delays = []
  config.delay = async ms => delays.push(ms)
  await assert.rejects(bootstrapSharedSession(async url => { calls.push(url); return reply({}, 503) }, config), e => e.status === 503)
  assert.deepEqual(delays, [250, 750])
  assert.deepEqual(calls, Array(3).fill('/api/bean/v1/shared-session/current'))
  const api = new BeanApi(null, async () => assert.fail('unsafe request retried'), { mode: 'browser_session' })
  for (const path of ['/shared-session', '/shared-session/rotate', '/runs', '/workspaces/w/research-sessions']) {
    await assert.rejects(readConnection(api, path), /Not a connection read/)
  }
})

test('lost issuance acknowledgement is never automatically replayed; explicit retry only reads retained cookie', async () => {
  const config = options(), calls = []; let issued = false
  const fetcher = async url => {
    calls.push(url)
    if (url.endsWith('/shared-session')) { issued = true; throw new Error('lost response after server issued cookie') }
    return issued ? reply(metadata) : missing()
  }
  await assert.rejects(bootstrapSharedSession(fetcher, config), e => e.code === 'session_uncertain')
  assert.equal((await bootstrapSharedSession(fetcher, config)).session.workspace_id, metadata.workspace_id)
  assert.equal(calls.filter(url => url.endsWith('/shared-session')).length, 1)
})

test('blocked cookies cannot loop issuance on retry or reload', async () => {
  const config = options(), calls = []
  const fetcher = async url => { calls.push(url); return url.endsWith('/current') ? missing() : reply(metadata) }
  await assert.rejects(bootstrapSharedSession(fetcher, config), e => e.code === 'session_cookie_unavailable')
  await assert.rejects(bootstrapSharedSession(fetcher, config), e => e.code === 'session_lost' && e.mayStartNew)
  await assert.rejects(bootstrapSharedSession(async url => fetcher(url), config), e => e.code === 'session_lost')
  assert.equal(calls.filter(url => url.endsWith('/shared-session')).length, 1)
})

test('expired or cleared identity requires explicit new-workspace action and preserves the previous marker until then', async () => {
  const config = options(); let active = true, expired = false, issuance = 0
  const fetcher = async url => {
    if (url.endsWith('/shared-session')) { issuance++; active = true; return reply({ ...metadata, workspace_id: 'new_private' }) }
    if (expired) { expired = false; active = false; return reply({ code: 'invalid_browser_session' }, 401) }
    return active ? reply({ ...metadata, workspace_id: issuance ? 'new_private' : metadata.workspace_id }) : missing()
  }
  await bootstrapSharedSession(fetcher, config)
  expired = true
  await assert.rejects(bootstrapSharedSession(fetcher, config), e => e.code === 'session_expired')
  await assert.rejects(bootstrapSharedSession(fetcher, config), e => e.code === 'session_lost')
  assert.equal(issuance, 0)
  assert.equal((await bootstrapSharedSession(fetcher, { ...config, startNew: true })).session.workspace_id, 'new_private')
  assert.equal(issuance, 1)
})

test('concurrent bootstrap callers share one operation and use the cross-tab lock', async () => {
  const config = options(), locks = []; let calls = 0
  config.locks = { request: async (name, fn) => { locks.push(name); return fn() } }
  const fetcher = async () => { calls++; return reply(metadata) }
  const one = bootstrapSharedSession(fetcher, config), two = bootstrapSharedSession(fetcher, config)
  assert.equal(one, two)
  await Promise.all([one, two])
  assert.equal(calls, 1)
  assert.deepEqual(locks, ['dr-bean-private-session'])
})

test('malformed metadata and absent support fail closed without bearer fallback or issuance', async () => {
  for (const value of [{ ...metadata, authenticated: false }, { ...metadata, mode: 'shared_demo' }, { ...metadata, workspace_id: '' },
    { ...metadata, credentials: 'bearer' }, { ...metadata, token: 'forbidden' }, {}, null]) {
    await assert.rejects(bootstrapSharedSession(async () => reply(value), options()), /private browser session/)
  }
  for (const status of [403, 404, 429, 500]) {
    let calls = 0
    await assert.rejects(bootstrapSharedSession(async () => { calls++; return reply({}, status) }, options()), e => e.status === status)
    assert.equal(calls, 1)
  }
})

test('known capacity refusal does not force a new identity on the next user retry', async () => {
  const config = options(); let attempts = 0, issued = false
  const fetcher = async url => {
    if (url.endsWith('/current')) return issued ? reply(metadata) : missing()
    attempts++
    if (attempts === 1) return reply({ code: 'browser_session_capacity' }, 429)
    issued = true; return reply(metadata)
  }
  await assert.rejects(bootstrapSharedSession(fetcher, config), e => e.status === 429)
  assert.equal((await bootstrapSharedSession(fetcher, config)).session.workspace_id, metadata.workspace_id)
  assert.equal(attempts, 2)
})

test('confirmation cannot silently accept a substituted workspace', async () => {
  let currentReads = 0
  await assert.rejects(bootstrapSharedSession(async url => {
    if (url.endsWith('/current')) return currentReads++ ? reply({ ...metadata, workspace_id: 'other_private' }) : missing()
    return reply(metadata)
  }, options()), e => e.code === 'session_changed')
})

test('readable but unwritable storage fails before issuance, including repeat visits', async () => {
  let issued = 0
  for (let visit = 0; visit < 2; visit++) {
    const config = options()
    config.storage = { getItem: () => null, setItem: () => { throw new Error('QuotaExceededError') } }
    const fetcher = async url => { if (url.endsWith('/shared-session')) { issued++; return reply(metadata) } return missing() }
    await assert.rejects(bootstrapSharedSession(fetcher, config), e => e.code === 'session_storage_unavailable')
    await assert.rejects(bootstrapSharedSession(fetcher, config), e => e.code === 'session_storage_unavailable')
  }
  assert.equal(issued, 0)
})

test('a retained valid cookie still reopens when site storage is unavailable', async () => {
  const config = options()
  config.storage = { getItem: () => { throw new Error('SecurityError') }, setItem: () => { throw new Error('SecurityError') } }
  const { session } = await bootstrapSharedSession(async () => reply(metadata), config)
  assert.equal(session.workspace_id, metadata.workspace_id)
})
