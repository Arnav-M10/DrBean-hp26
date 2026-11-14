import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createServer, request } from 'node:http'
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { chmod, mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const proof = `DRBEAN-DUMMY-${'g'.repeat(30)}`
const credential = `DRBEAN-DUMMY-${'c'.repeat(30)}`
const issuedCookie = `bean_local_session=${credential}; HttpOnly; Max-Age=86400; Path=/; SameSite=strict`

async function fixture(t, { configured = true } = {}) {
  const directory = await mkdtemp(join(tmpdir(), 'bean-local-proxy-'))
  const gatewayFile = join(directory, 'local-gateway.json')
  await writeFile(gatewayFile, JSON.stringify({ version: 1, secret: proof }), { mode: 0o600 })
  const calls = [], state = { cookie: undefined, status: 200 }
  const api = createServer((req, res) => {
    let body = ''; req.on('data', chunk => { body += chunk }); req.on('end', () => {
      calls.push({ path: req.url, headers: req.headers, body })
      const headers = { 'Content-Type': 'application/json', 'X-Bean-Local-Gateway': 'DRBEAN-DUMMY-hidden' }
      if (state.cookie !== undefined) headers['Set-Cookie'] = state.cookie
      res.writeHead(state.status, headers)
      res.end('{"mode":"browser_session","authenticated":true,"credentials":"server_managed","workspace_id":"w_private"}')
    })
  })
  await new Promise(resolve => api.listen(0, '127.0.0.1', resolve))
  const child = spawn(process.execPath, [new URL('./serve.mjs', import.meta.url).pathname, '0'], {
    env: { BEAN_WEB_API_PORT: String(api.address().port), ...(configured ? { BEAN_LOCAL_GATEWAY_FILE: gatewayFile } : {}) },
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  t.after(async () => {
    if (child.exitCode === null) { child.kill(); await once(child, 'exit') }
    api.closeAllConnections(); await new Promise(resolve => api.close(resolve))
    await rm(directory, { recursive: true, force: true })
  })
  const port = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Local proxy did not start.')), 5000)
    child.once('error', error => { clearTimeout(timer); reject(error) })
    child.stdout.on('data', bytes => {
      const match = bytes.toString().match(/http:\/\/127\.0\.0\.1:(\d+)/)
      if (match) { clearTimeout(timer); resolve(Number(match[1])) }
    })
  })
  const origin = `http://127.0.0.1:${port}`
  const send = (path, headers = {}, method = 'GET') => new Promise((resolve, reject) => {
    const req = request({ hostname: '127.0.0.1', port, path, method, headers }, res => {
      let text = ''; res.on('data', bytes => { text += bytes }); res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, text }))
    })
    req.on('error', reject); req.end(method === 'POST' ? 'species,height\nbean,4.6' : undefined)
  })
  return { calls, state, send, gatewayFile, directory, origin, api }
}

test('local session proxy retains real module routes and injects only its own private boundary', async t => {
  const { calls, state, send, origin } = await fixture(t)
  for (const name of ['session', 'research', 'general-workspace', 'motion']) {
    let source
    try { source = await readFile(new URL(`./${name}.mjs`, import.meta.url), 'utf8') } catch (error) { if (error.code !== 'ENOENT') throw error }
    const result = await send(`/${name}.mjs`)
    assert.equal(result.status, source === undefined ? 404 : 200)
    assert.equal(result.text, source ?? '')
    if (source !== undefined) assert.match(result.headers['content-type'], /^text\/javascript/)
  }
  state.cookie = issuedCookie
  const session = await send('/api/bean/v1/shared-session', {
    authorization: 'Bearer ' + proof, cookie: `__Host-bean_session=${credential}; unrelated=private`,
    'x-bean-shared-gateway': 'forged', 'x-bean-shared-origin': 'https://evil.test',
    'x-bean-local-gateway': 'forged', 'x-bean-local-origin': 'http://evil.test',
    'x-forwarded-for': 'evil', 'x-forwarded-host': 'evil', 'x-forwarded-proto': 'https', forwarded: 'host=evil',
  })
  assert.equal(session.status, 200)
  assert.deepEqual(session.headers['set-cookie'], [issuedCookie])
  assert.equal(session.headers['cache-control'], 'no-store')
  assert.equal(session.headers['x-bean-local-gateway'], undefined)
  assert.equal(calls[0].headers['x-bean-local-gateway'], proof)
  assert.equal(calls[0].headers['x-bean-local-origin'], origin)
  for (const key of ['authorization', 'cookie', 'x-bean-shared-gateway', 'x-bean-shared-origin', 'x-forwarded-for', 'x-forwarded-host', 'x-forwarded-proto', 'forwarded']) assert.equal(calls[0].headers[key], undefined, key)
  state.cookie = undefined
  const result = await send('/api/bean/v1/workspaces/w/research-assets', {
    origin, authorization: 'Bearer ' + proof, 'x-source-name': 'plants.csv', 'content-type': 'text/csv',
    cookie: `unrelated=private; bean_local_session=${credential}; __Host-bean_session=${proof}`, 'sec-fetch-site': 'same-origin',
  }, 'POST')
  assert.equal(result.status, 200)
  assert.equal(calls[1].headers.authorization, undefined)
  assert.equal(calls[1].headers.cookie, `bean_local_session=${credential}`)
  assert.equal(calls[1].headers.origin, origin)
  assert.equal(calls[1].headers['x-source-name'], 'plants.csv')
  assert.equal(calls[1].body, 'species,height\nbean,4.6')
  assert.equal((await send('/api/bean/v1/shared-session/current')).status, 200)
  assert.equal(calls[2].path, '/api/bean/v1/shared-session/current')
})

test('local boundary rejects cross-origin, ambiguous and malformed requests before any API action', async t => {
  const { calls, send, origin } = await fixture(t)
  for (const headers of [{ host: 'evil.test' }, { origin: 'https://evil.test' }, { 'sec-fetch-site': 'cross-site' }, { 'sec-fetch-site': 'same-site' }, { origin: [origin, origin] }]) {
    assert.equal((await send('/api/bean/v1/shared-session', headers)).status, 403)
  }
  assert.equal((await send('/api/bean/v1/shared-session/rotate', {}, 'POST')).status, 403)
  assert.equal((await send('/api/bean/v1/shared-session/rotate', { origin, 'sec-fetch-site': 'none' }, 'POST')).status, 403)
  for (const cookie of ['bean_local_session=forged', `bean_local_session=${credential}; bean_local_session=${credential}`]) {
    const result = await send('/api/bean/v1/shared-session', { cookie })
    assert.equal(result.status, 401)
    assert.equal(JSON.parse(result.text).code, 'invalid_browser_session')
    assert.match(result.headers['set-cookie'][0], /^bean_local_session=""; Max-Age=0; Path=\/; HttpOnly; SameSite=Strict$/)
  }
  for (const name of ['a'.repeat(256), '../private.csv', 'caf\u00e9.csv']) assert.equal((await send('/api/bean/v1/workspaces/w/research-assets', { origin, 'x-source-name': name }, 'POST')).status, 400)
  assert.equal((await send('/api/bean/v1/workspaces/w/research-assets', { origin, 'idempotency-key': 'a'.repeat(129) }, 'POST')).status, 400)
  assert.equal(calls.length, 0)
})

test('only correctly scoped local HttpOnly cookies cross the proxy, including revocation', async t => {
  const { state, send } = await fixture(t)
  for (const cookie of [
    `__Host-bean_session=${credential}; Secure; HttpOnly; Max-Age=60; Path=/; SameSite=Strict`,
    issuedCookie.replace('; HttpOnly', ''), issuedCookie.replace('Path=/', 'Path=/api'),
    issuedCookie.replace('SameSite=strict', 'SameSite=None'), `${issuedCookie}; Domain=127.0.0.1`,
    `${issuedCookie}; Secure`, `${issuedCookie}; HttpOnly`, issuedCookie.replace('86400', '86401'),
    [issuedCookie, 'unrelated=private'],
  ]) {
    state.cookie = cookie
    const result = await send('/api/bean/v1/shared-session')
    assert.equal(result.status, 502)
    assert.equal(result.headers['set-cookie'], undefined)
  }
  state.status = 401
  state.cookie = 'bean_local_session=""; expires=Thu, 01 Jan 1970 00:00:00 GMT; HttpOnly; Max-Age=0; Path=/; SameSite=strict'
  const expired = await send('/api/bean/v1/shared-session/current')
  assert.equal(expired.status, 401)
  assert.deepEqual(expired.headers['set-cookie'], [state.cookie])
})

test('private local configuration is checked on every request and is never served', async t => {
  const { calls, send, gatewayFile, directory } = await fixture(t)
  assert.equal((await send('/local-gateway.json')).status, 404)
  assert.equal((await send('/api/bean/v1/shared-session')).status, 200)
  await chmod(gatewayFile, 0o644)
  assert.equal((await send('/api/bean/v1/shared-session')).status, 503)
  await chmod(gatewayFile, 0o600)
  await writeFile(gatewayFile, '{}')
  assert.equal((await send('/api/bean/v1/shared-session')).status, 503)
  await rm(gatewayFile)
  const target = join(directory, 'private.json')
  await writeFile(target, JSON.stringify({ version: 1, secret: proof }), { mode: 0o600 })
  await symlink(target, gatewayFile)
  assert.equal((await send('/api/bean/v1/shared-session')).status, 503)
  assert.equal(calls.length, 1)
})

test('missing private configuration fails closed without forwarding bearer credentials', async t => {
  const { calls, send } = await fixture(t, { configured: false })
  const result = await send('/api/bean/v1/shared-session', { authorization: 'Bearer ' + proof })
  assert.equal(result.status, 503)
  assert.equal(calls.length, 0)
  assert.equal(result.headers['set-cookie'], undefined)
})

test('the study page serves only its own files, by type, and nothing outside its folder', async t => {
  const { calls, send } = await fixture(t)
  const redirect = await send('/study')
  assert.equal(redirect.status, 308)
  assert.equal(redirect.headers.location, '/study/')
  // /study/ is the front page; /study/app is the study itself.
  const page = await send('/study/')
  assert.equal(page.status, 200)
  assert.match(page.headers['content-type'], /^text\/html/)
  assert.equal(page.headers['x-content-type-options'], 'nosniff')
  assert.match(page.text, /<title>/)
  assert.match(page.text, /src="home\.mjs"/)
  for (const path of ['/study/app', '/study/app.html']) {
    const app = await send(path)
    assert.equal(app.status, 200, path)
    assert.match(app.headers['content-type'], /^text\/html/, path)
    assert.match(app.text, /src="app\.mjs"/, path)
  }
  for (const [path, type] of [['/study/app.mjs', /^text\/javascript/], ['/study/styles.css', /^text\/css/],
    ['/study/home.mjs', /^text\/javascript/], ['/study/home-data.mjs', /^text\/javascript/], ['/study/home.css', /^text\/css/],
    ['/study/vendor/katex/katex.min.js', /^text\/javascript/], ['/study/fonts/atkinson-next-latin.woff2', /^font\/woff2$/]]) {
    const response = await send(path)
    assert.equal(response.status, 200, path)
    assert.match(response.headers['content-type'], type, path)
  }
  const head = await send('/study/index.html', {}, 'HEAD')
  assert.equal(head.status, 200)
  assert.equal(head.text, '')
  for (const path of ['/study/../serve.mjs', '/study/..%2fserve.mjs', '/study/%2e%2e/serve.mjs', '/study/vendor/../../serve.mjs',
    '/study/.hidden.mjs', '/study/fonts/.x.woff2', '/study/fixtures/provenance.json', '/study/fixtures/x.html', '/study/study.test.mjs',
    '/study/vendor/katex/LICENSE', '/study/fonts/SOURCE.txt', '/study/nothing-here.mjs', '/study/app.mjs/', '/study//app.mjs', '/study/a\\b.mjs',
    '/study/app/', '/study/home', '/study/index']) {
    assert.equal((await send(path)).status, 404, path)
  }
  assert.equal((await send('/study/app.mjs', {}, 'POST')).status, 405)
  assert.equal(calls.length, 0)
})
