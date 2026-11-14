import { test } from 'node:test'
import assert from 'node:assert/strict'
import { bootstrapSharedSession } from './session.mjs'

const metadata = { mode: 'browser_session', authenticated: true, workspace_id: 'workspace_private', credentials: 'server_managed' }

test('bootstrap reopens a private session using its HttpOnly cookie transport', async () => {
  const calls = []
  const { api, session } = await bootstrapSharedSession(async (url, options) => {
    calls.push({ url, ...options })
    return new Response(JSON.stringify(url.endsWith('/shared-session') ? metadata : { workspaces: [] }))
  })
  assert.deepEqual(session, metadata)
  assert.equal(Object.isFrozen(session), true)
  await api.json('/workspaces')
  assert.equal(calls[0].url, '/api/bean/v1/shared-session')
  for (const call of calls) {
    assert.equal(call.credentials, 'same-origin')
    assert.equal(call.headers.Authorization, undefined)
    assert.equal(call.headers.Cookie, undefined)
    assert.equal(call.cache, 'no-store')
    assert.equal(call.redirect, 'error')
  }
})

test('only absent local session support falls back; refused, expired or unreachable shared sessions remain visible failures', async () => {
  assert.equal(await bootstrapSharedSession(async () => new Response('{}', { status: 404 })), null)
  for (const status of [401, 403, 429, 500, 503]) {
    await assert.rejects(bootstrapSharedSession(async () => new Response('{"code":"session_refused"}', { status })), error => error.kind === 'rejected' && error.status === status)
  }
  await assert.rejects(bootstrapSharedSession(async () => { throw new Error('offline') }), error => error.kind === 'unreachable')
})

test('malformed or old shared-demo metadata cannot create a session client', async () => {
  for (const value of [{ ...metadata, authenticated: false }, { ...metadata, mode: 'shared_demo' }, { ...metadata, workspace_id: '' },
    { ...metadata, credentials: 'bearer' }, { ...metadata, token: 'forbidden' }, {}, null]) {
    await assert.rejects(bootstrapSharedSession(async () => new Response(JSON.stringify(value))), /private browser session/)
  }
})
