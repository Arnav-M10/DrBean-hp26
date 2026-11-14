import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createServer, request } from 'node:http'
import { mkdtemp, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createShareGateway, shareOrigin } from './share-gateway.mjs'

const origin = 'https://bean-test-study.trycloudflare.com'
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

test('sharing accepts one explicit HTTPS tunnel origin, never a URL with credentials or a wildcard', () => {
  assert.equal(shareOrigin(origin).origin, origin)
  for (const value of ['http://bean.trycloudflare.com', 'https://*.trycloudflare.com', 'https://bean.trycloudflare.com/path',
    'https://user:secret' + '@bean.trycloudflare.com', 'https://bean.trycloudflare.com.evil.test', 'https://127.0.0.1', origin + ':443']) {
    assert.throws(() => shareOrigin(value))
  }
})

test('shared gateway fails closed and preserves bearer authentication while rewriting only the approved origin', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'bean-share-')), file = join(directory, 'origin.json'), calls = []
  const upstream = createServer((req, res) => {
    let body = ''; req.on('data', chunk => { body += chunk }); req.on('end', () => {
      calls.push({ headers: req.headers, method: req.method, path: req.url, body })
      res.writeHead(req.headers.authorization ? 200 : 401, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ authenticated: Boolean(req.headers.authorization) }))
    })
  })
  const upstreamPort = await listen(upstream), gateway = createShareGateway({ originFile: file, webPort: upstreamPort })
  const port = await listen(gateway)
  try {
    assert.equal((await send(port)).status, 503)
    await writeFile(file, JSON.stringify({ origin }))
    for (const headers of [{ host: 'evil.test' }, { origin: 'https://evil.test' }, { 'x-forwarded-proto': 'http' },
      { 'x-forwarded-proto': '' }, { 'sec-fetch-site': 'cross-site' }]) {
      assert.equal((await send(port, { headers })).status, 403)
    }
    assert.equal(calls.length, 0)
    assert.equal((await send(port)).status, 401)
    const result = await send(port, { method: 'POST', headers: { origin, authorization: 'Bearer test-token',
      cookie: 'unrelated=secret', 'x-forwarded-host': 'evil.test', 'content-type': 'application/json', 'idempotency-key': 'operation_one' }, body: '{"name":"Shared test"}' })
    assert.equal(result.status, 200)
    assert.equal(result.headers['cache-control'], 'no-store')
    assert.equal(result.headers['referrer-policy'], 'no-referrer')
    const call = calls.at(-1)
    assert.equal(call.headers.host, `127.0.0.1:${upstreamPort}`)
    assert.equal(call.headers.origin, `http://127.0.0.1:${upstreamPort}`)
    assert.equal(call.headers.authorization, 'Bearer test-token')
    assert.equal(call.headers['idempotency-key'], 'operation_one')
    assert.equal(call.headers.cookie, undefined)
    assert.equal(call.headers['x-forwarded-host'], undefined)
    assert.equal(call.body, '{"name":"Shared test"}')
    await writeFile(file, '{invalid')
    assert.equal((await send(port)).status, 503)
  } finally {
    await close(gateway); await close(upstream); await rm(directory, { recursive: true, force: true })
  }
})
