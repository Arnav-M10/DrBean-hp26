import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createServer, request } from 'node:http'
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { readFile } from 'node:fs/promises'

test('local proxy disables only session bootstrap and bounds filename metadata without trusting shared cookies or headers', async t => {
  const calls = []
  const api = createServer((req, res) => {
    let body = ''; req.on('data', chunk => { body += chunk }); req.on('end', () => {
      calls.push({ path: req.url, headers: req.headers, body })
      // An API with shared access enabled would refuse the local proxy's
      // untrusted session bootstrap. The proxy must not forward that request.
      res.writeHead(req.url === '/api/bean/v1/shared-session' ? 403 : 200, { 'Content-Type': 'application/json', 'Set-Cookie': 'untrusted=secret', 'X-Bean-Shared-Gateway': 'secret' });
      res.end(req.url === '/api/bean/v1/capabilities' ? '{"shared_access":{"mode":"browser_session","available":true}}' : '{}')
    })
  })
  await new Promise(resolve => api.listen(0, '127.0.0.1', resolve))
  const child = spawn(process.execPath, [new URL('./serve.mjs', import.meta.url).pathname, '0'], {
    env: { ...process.env, BEAN_WEB_API_PORT: String(api.address().port) }, stdio: ['ignore', 'pipe', 'pipe'],
  })
  t.after(async () => { child.kill(); await once(child, 'exit'); await new Promise(resolve => api.close(resolve)) })
  const port = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Local proxy did not start.')), 5000)
    child.once('error', error => { clearTimeout(timer); reject(error) })
    child.stdout.on('data', bytes => {
      const match = bytes.toString().match(/http:\/\/127\.0\.0\.1:(\d+)/)
      if (match) { clearTimeout(timer); resolve(Number(match[1])) }
    })
  })
  const send = (path, headers = {}, method = path.startsWith('/api/') ? 'POST' : 'GET') => new Promise((resolve, reject) => {
    const req = request({ hostname: '127.0.0.1', port, path, method, headers }, res => {
      let text = ''; res.on('data', bytes => { text += bytes }); res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, text }))
    })
    req.on('error', reject); req.end(method === 'POST' ? 'species,height\nbean,4.6' : undefined)
  })
  assert.match((await send('/session.mjs')).text, /bootstrapSharedSession/)
  // Until the UI owner's actual module arrives, the route must stay absent
  // rather than serve a production fallback. The same test checks its exact
  // bytes once that module is integrated.
  let generalSource
  try { generalSource = await readFile(new URL('./general-workspace.mjs', import.meta.url), 'utf8') } catch (error) {
    if (error.code !== 'ENOENT') throw error
  }
  const generalModule = await send('/general-workspace.mjs')
  assert.equal(generalModule.status, generalSource === undefined ? 404 : 200)
  assert.equal(generalModule.text, generalSource ?? '')
  if (generalSource !== undefined) assert.match(generalModule.headers['content-type'], /^text\/javascript/)
  const researchModule = await send('/research.mjs')
  assert.equal(researchModule.status, 200)
  assert.equal(researchModule.text, await readFile(new URL('./research.mjs', import.meta.url), 'utf8'))
  assert.match(researchModule.headers['content-type'], /^text\/javascript/)
  const session = await send('/api/bean/v1/shared-session', { cookie: '__Host-bean_session=forged', 'x-bean-shared-gateway': 'forged' }, 'GET')
  assert.equal(session.status, 404)
  assert.equal(JSON.parse(session.text).code, 'shared_access_unavailable')
  assert.equal(session.headers['cache-control'], 'no-store')
  assert.equal(session.headers['set-cookie'], undefined)
  assert.equal(calls.length, 0)
  const result = await send('/api/bean/v1/workspaces/w/research-assets', { authorization: 'Bearer owner', 'x-source-name': 'plants.csv',
    'content-type': 'text/csv', cookie: '__Host-bean_session=forged', 'x-bean-shared-gateway': 'forged', 'x-bean-shared-origin': 'https://evil.test' })
  assert.equal(result.status, 200)
  assert.equal(result.headers['set-cookie'], undefined)
  assert.equal(result.headers['x-bean-shared-gateway'], undefined)
  assert.equal(calls[0].headers.authorization, 'Bearer owner')
  assert.equal(calls[0].headers['x-source-name'], 'plants.csv')
  assert.equal(calls[0].body, 'species,height\nbean,4.6')
  for (const name of ['cookie', 'x-bean-shared-gateway', 'x-bean-shared-origin']) assert.equal(calls[0].headers[name], undefined)
  for (const name of ['a'.repeat(256), '../private.csv', 'caf\u00e9.csv']) {
    assert.equal((await send('/api/bean/v1/workspaces/w/research-assets', { 'x-source-name': name })).status, 400)
  }
  assert.equal(calls.length, 1)
  const capabilities = await send('/api/bean/v1/capabilities', {}, 'GET')
  assert.equal(capabilities.status, 200)
  assert.equal(JSON.parse(capabilities.text).shared_access.available, true)
  assert.equal(calls.length, 2)
  assert.equal(calls[1].path, '/api/bean/v1/capabilities')
})
