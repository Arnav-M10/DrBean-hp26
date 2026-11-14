import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createServer, request } from 'node:http'
import { chmod, mkdtemp, writeFile, rm, symlink } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createShareGateway, shareOrigin } from './share-gateway.mjs'

const origin = 'https://bean-test-study.trycloudflare.com'
const secret = 'g'.repeat(43), session = 's'.repeat(43), cookie = `__Host-bean_session=${session}`
const secureCookie = `${cookie}; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=3600`
const listen = server => new Promise(resolve => server.listen(0, '127.0.0.1', () => resolve(server.address().port)))
const close = server => new Promise(resolve => server.close(resolve))
function send(port, { path = '/api/bean/v1/workspaces', method = 'GET', headers = {}, body } = {}) {
  return new Promise((resolve, reject) => {
    const req = request({ hostname: '127.0.0.1', port, path, method, headers: {
      host: new URL(origin).host, 'x-forwarded-proto': 'https', ...headers,
    } }, res => {
      let text = ''; res.on('data', chunk => { text += chunk }); res.on('end', () => resolve({ status: res.statusCode, text, headers: res.headers }))
    })
    req.on('error', reject); req.end(body)
  })
}

async function fixture(t, apiHandler = (req, res) => res.end('{}'), webHandler = (req, res) => res.end('static')) {
  const directory = await mkdtemp(join(tmpdir(), 'bean-share-')), originFile = join(directory, 'origin.json'), gatewayFile = join(directory, 'gateway.json')
  await writeFile(originFile, JSON.stringify({ origin }))
  await writeFile(gatewayFile, JSON.stringify({ version: 1, secret }), { mode: 0o600 })
  const calls = [], statics = []
  const record = (target, handler) => (req, res) => {
    let body = ''; req.on('data', chunk => { body += chunk }); req.on('end', () => {
      target.push({ headers: req.headers, method: req.method, path: req.url, body }); handler(req, res)
    })
  }
  const api = createServer(record(calls, apiHandler)), web = createServer(record(statics, webHandler))
  const apiPort = await listen(api), webPort = await listen(web)
  const gateway = createShareGateway({ originFile, gatewayFile, apiPort, webPort }), port = await listen(gateway)
  t.after(async () => { await close(gateway); await close(api); await close(web); await rm(directory, { recursive: true, force: true }) })
  return { directory, originFile, gatewayFile, port, apiPort, webPort, calls, statics }
}

test('sharing accepts one explicit HTTPS tunnel origin, never credentials or a wildcard', () => {
  assert.equal(shareOrigin(origin).origin, origin)
  for (const value of ['http://bean.trycloudflare.com', 'https://*.trycloudflare.com', 'https://bean.trycloudflare.com/path',
    'https://user:secret' + '@bean.trycloudflare.com', 'https://bean.trycloudflare.com.evil.test', 'https://127.0.0.1', origin + ':443']) {
    assert.throws(() => shareOrigin(value))
  }
})

test('shared API uses a private gateway credential and browser cookie, never browser owner credentials', async t => {
  const f = await fixture(t, (req, res) => {
    res.writeHead(200, { 'Content-Type': 'application/json', 'Set-Cookie': secureCookie,
      'X-Bean-Shared-Gateway': secret, Authorization: 'Bearer owner', Location: 'https://evil.test' })
    res.end(JSON.stringify({ mode: 'browser_session', authenticated: true, workspace_id: 'workspace_private', credentials: 'server_managed' }))
  })
  const result = await send(f.port, { method: 'POST', headers: { origin, 'sec-fetch-site': 'same-origin', authorization: 'Bearer owner-token',
    cookie: `unrelated=hidden; ${cookie}`, 'x-bean-shared-gateway': 'forged', 'x-bean-shared-origin': 'https://evil.test', 'x-owner-id': 'owner',
    'x-forwarded-host': new URL(origin).host, 'content-type': 'text/csv', 'x-source-name': 'plant-growth.csv', 'idempotency-key': 'operation_one' }, body: 'species,height\nbean,4' })
  assert.equal(result.status, 200)
  assert.deepEqual(result.headers['set-cookie'], [secureCookie])
  assert.equal(result.headers['cache-control'], 'no-store')
  assert.equal(result.headers['referrer-policy'], 'no-referrer')
  for (const name of ['authorization', 'x-bean-shared-gateway', 'location']) assert.equal(result.headers[name], undefined)
  assert.equal(result.text.includes(secret), false)
  const call = f.calls[0]
  assert.equal(call.headers.host, `127.0.0.1:${f.apiPort}`)
  assert.equal(call.headers.origin, origin)
  assert.equal(call.headers['x-bean-shared-gateway'], secret)
  assert.equal(call.headers['x-bean-shared-origin'], origin)
  assert.equal(call.headers.cookie, cookie)
  assert.equal(call.headers['idempotency-key'], 'operation_one')
  assert.equal(call.headers['x-source-name'], 'plant-growth.csv')
  for (const name of ['authorization', 'x-owner-id', 'x-forwarded-host', 'x-forwarded-proto', 'sec-fetch-site']) assert.equal(call.headers[name], undefined)
  assert.equal(call.body, 'species,height\nbean,4')
  assert.equal(f.statics.length, 0)
})

test('session bootstrap reaches the API and ordinary requests without a cookie do not inherit access', async t => {
  const f = await fixture(t, (req, res) => {
    if (req.url === '/api/bean/v1/shared-session') {
      res.writeHead(200, { 'Set-Cookie': secureCookie }); res.end('{"mode":"browser_session"}')
    } else { res.writeHead(req.headers.cookie === cookie ? 200 : 401); res.end('{}') }
  })
  assert.equal((await send(f.port)).status, 401)
  const bootstrap = await send(f.port, { path: '/api/bean/v1/shared-session' })
  assert.equal(bootstrap.status, 200)
  assert.deepEqual(bootstrap.headers['set-cookie'], [secureCookie])
  assert.equal((await send(f.port, { headers: { cookie } })).status, 200)
  assert.equal((await send(f.port, { headers: { cookie: `__Host-bean_session=${'e'.repeat(43)}` } })).status, 401)
  assert.equal(f.calls[0].headers.authorization, undefined)
})

test('foreign or forged origins, hosts and HTTPS metadata are refused before the API', async t => {
  const f = await fixture(t)
  for (const headers of [{ host: 'evil.test' }, { origin: 'https://evil.test' }, { origin: 'null' }, { 'x-forwarded-proto': 'http' },
    { 'x-forwarded-proto': '' }, { 'x-forwarded-proto': 'https,http' }, { 'x-forwarded-host': 'evil.test' },
    { 'sec-fetch-site': 'cross-site' }, { 'sec-fetch-site': 'same-site' }, { 'sec-fetch-site': 'unknown' }]) {
    assert.equal((await send(f.port, { headers })).status, 403)
  }
  assert.equal((await send(f.port, { method: 'POST' })).status, 403)
  assert.equal((await send(f.port, { method: 'POST', headers: { origin, 'sec-fetch-site': 'none' } })).status, 403)
  assert.equal((await send(f.port, { method: 'DELETE' })).status, 405)
  assert.equal((await send(f.port, { path: '//evil.test/api/bean/v1/workspaces' })).status, 405)
  assert.equal(f.calls.length, 0)
})

test('following an external link admits only the entry document, never cross-site API calls or subresources', async t => {
  const f = await fixture(t)
  const navigation = { 'sec-fetch-site': 'cross-site', 'sec-fetch-mode': 'navigate', 'sec-fetch-dest': 'document', 'sec-fetch-user': '?1' }
  assert.equal((await send(f.port, { path: '/', headers: navigation })).status, 200)
  assert.equal((await send(f.port, { path: '/index.html', method: 'HEAD', headers: navigation })).status, 200)
  assert.equal((await send(f.port, { path: '/', headers: { ...navigation, 'sec-fetch-site': 'same-site' } })).status, 200)
  assert.equal((await send(f.port, { path: '/study/', headers: navigation })).status, 200)
  assert.equal((await send(f.port, { path: '/study/app', headers: navigation })).status, 200)
  assert.equal(f.statics.length, 5)
  assert.equal(f.calls.length, 0)
  for (const path of ['/api/bean/v1/shared-session', '/api/bean/v1/workspaces', '/session.mjs', '/styles.css', '/study/app.mjs', '/study/styles.css']) {
    assert.equal((await send(f.port, { path, headers: navigation })).status, 403)
  }
  assert.equal((await send(f.port, { path: '/', headers: { ...navigation, 'sec-fetch-mode': 'no-cors', 'sec-fetch-dest': 'image' } })).status, 403)
  assert.equal((await send(f.port, { path: '/', method: 'POST', headers: { ...navigation, origin } })).status, 403)
  for (const headers of [{ host: 'evil.test' }, { 'x-forwarded-proto': 'http' }, { origin: 'https://evil.test' }, { 'sec-fetch-site': 'unknown' }]) {
    assert.equal((await send(f.port, { path: '/', headers: { ...navigation, ...headers } })).status, 403)
  }
  assert.equal(f.statics.length, 5)
  assert.equal(f.calls.length, 0)
})

test('malformed or duplicate session cookies are refused; unrelated cookies are stripped', async t => {
  const f = await fixture(t)
  for (const value of ['__Host-bean_session=short', `${cookie}; ${cookie}`, '__Host-bean_session', '__Host-bean_session="' + session + '"']) {
    const result = await send(f.port, { headers: { cookie: value } })
    assert.equal(result.status, 401)
    assert.deepEqual(result.headers['set-cookie'], ['__Host-bean_session=""; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Strict'])
  }
  assert.equal(f.calls.length, 0)
  assert.equal((await send(f.port, { headers: { cookie: 'owner=anything; other=secret' } })).status, 200)
  assert.equal(f.calls[0].headers.cookie, undefined)
})

test('only an owner-only regular gateway file is trusted and failures do not reveal credentials', async t => {
  const f = await fixture(t)
  await chmod(f.gatewayFile, 0o644)
  assert.equal((await send(f.port)).status, 503)
  await chmod(f.gatewayFile, 0o600)
  await writeFile(f.gatewayFile, JSON.stringify({ token: secret }))
  assert.equal((await send(f.port)).status, 503)
  await rm(f.gatewayFile)
  const target = join(f.directory, 'private.json')
  await writeFile(target, JSON.stringify({ version: 1, secret }), { mode: 0o600 })
  await symlink(target, f.gatewayFile)
  const result = await send(f.port)
  assert.equal(result.status, 503)
  assert.equal(result.text.includes(secret), false)
  assert.equal(f.calls.length, 0)
  await writeFile(f.originFile, '{invalid')
  assert.equal((await send(f.port)).status, 503)
})

test('upstream cookies require the exact secure session scope', async t => {
  let returned = secureCookie
  const f = await fixture(t, (req, res) => { res.writeHead(200, { 'Set-Cookie': returned }); res.end('{}') })
  for (const value of [secureCookie.replace('; Secure', ''), secureCookie.replace('; HttpOnly', ''),
    secureCookie.replace('SameSite=Strict', 'SameSite=Lax'), secureCookie + '; Domain=trycloudflare.com',
    secureCookie.replace('Path=/', 'Path=/api'), 'other=secret; Path=/; Secure; HttpOnly; SameSite=Strict',
    [secureCookie, 'other=secret'], secureCookie + '; Secure', secureCookie.replace(session, 'short'),
    secureCookie.replace('; Max-Age=3600', ''), secureCookie.replace('Max-Age=3600', 'Max-Age=86401')]) {
    returned = value
    const result = await send(f.port)
    assert.equal(result.status, 502)
    assert.equal(result.headers['set-cookie'], undefined)
  }
  returned = '__Host-bean_session=; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=0'
  assert.deepEqual((await send(f.port)).headers['set-cookie'], [returned])
  returned = '__Host-bean_session=""; HttpOnly; Max-Age=0; Path=/; SameSite=strict; Secure'
  assert.deepEqual((await send(f.port)).headers['set-cookie'], [returned])
})

test('static requests have no credentials and raw filename metadata stays bounded', async t => {
  const f = await fixture(t, undefined, (req, res) => { res.writeHead(200, { 'Set-Cookie': secureCookie }); res.end('static') })
  const result = await send(f.port, { path: '/session.mjs', headers: { authorization: 'Bearer owner', cookie, 'x-bean-shared-gateway': secret } })
  assert.equal(result.text, 'static')
  assert.equal(result.headers['set-cookie'], undefined)
  assert.equal(f.calls.length, 0)
  for (const name of ['authorization', 'cookie', 'x-bean-shared-gateway', 'x-bean-shared-origin']) assert.equal(f.statics[0].headers[name], undefined)
  for (const value of ['a'.repeat(256), '../private.csv', 'folder\\private.csv', 'caf\u00e9.csv']) {
    assert.equal((await send(f.port, { method: 'POST', headers: { origin, 'x-source-name': value } })).status, 400)
  }
  assert.equal(f.calls.length, 0)
})
