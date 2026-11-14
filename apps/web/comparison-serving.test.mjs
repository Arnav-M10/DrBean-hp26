import { test } from 'node:test'
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { readFile, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { createServer, request } from 'node:http'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createShareGateway } from './share-gateway.mjs'

const listen = server => new Promise(resolve => server.listen(0, '127.0.0.1', () => resolve(server.address().port)))
const close = server => new Promise(resolve => { server.closeAllConnections(); server.close(resolve) })
function send(port, path, headers = {}, method = 'GET') {
  return new Promise((resolve, reject) => {
    const req = request({ hostname: '127.0.0.1', port, path, headers, method }, res => {
      let text = ''; res.on('data', part => { text += part }); res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, text }))
    })
    req.on('error', reject); req.end()
  })
}
async function server(t) {
  const child = spawn(process.execPath, [new URL('./serve.mjs', import.meta.url).pathname, '0'], { env: {}, stdio: ['ignore', 'pipe', 'pipe'] })
  t.after(async () => { if (child.exitCode === null) { child.kill(); await once(child, 'exit') } })
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Preview server failed to start')), 5000)
    child.once('error', error => { clearTimeout(timer); reject(error) })
    child.stdout.on('data', part => {
      const match = part.toString().match(/http:\/\/127\.0\.0\.1:(\d+)/)
      if (match) { clearTimeout(timer); resolve(Number(match[1])) }
    })
  })
}

test('trusted server exposes a fixed preview and connector route set, never arbitrary repository files', async t => {
  const port = await server(t)
  const mappings = [
    ['/workspace-preview/', '../../workspace-preview/index.html'],
    ['/workspace-preview/comparison.html', '../../workspace-preview/comparison.html'],
    ['/workspace-preview/research-ui.mjs', '../../workspace-preview/research-ui.mjs'],
    ['/workspace-preview/research-view.mjs', '../../workspace-preview/research-view.mjs'],
    ['/research-api.mjs', 'research-api.mjs'],
    ['/workspace-preview/index.html', '../../workspace-preview/index.html'],
    ['/workspace-preview/comparison.mjs', '../../workspace-preview/comparison.mjs'],
    ['/workspace-preview/comparison-core.mjs', '../../workspace-preview/comparison-core.mjs'],
    ['/workspace-preview/comparison-view.mjs', '../../workspace-preview/comparison-view.mjs'],
    ['/workspace-preview/comparison.css', '../../workspace-preview/comparison.css'],
    ['/workspace-preview/saved-example.html', '../../workspace-preview/saved-example.html'],
    ['/workspace-preview/app.mjs', '../../workspace-preview/app.mjs'],
    ['/workspace-preview/styles.css', '../../workspace-preview/styles.css'],
    ['/workspace-preview/reference.json', '../../workspace-preview/reference.json'],
    ['/workspace-preview/examples/synthetic.request.json', '../../fixtures/model-comparison/synthetic.request.json'],
    ['/comparison-api.mjs', 'comparison-api.mjs'],
  ]
  for (const [path, file] of mappings) {
    const actual = await send(port, path)
    assert.equal(actual.status, 200, path)
    assert.equal(actual.text, await readFile(new URL(file, import.meta.url), 'utf8'))
    assert.equal(actual.headers['cache-control'], 'no-store')
    assert.equal(actual.headers['access-control-allow-origin'], undefined)
    const head = await send(port, path, {}, 'HEAD')
    assert.equal(head.status, 200); assert.equal(head.text, '')
  }
  const manifest = await send(port, '/workspace-preview/comparison-service.json')
  assert.deepEqual(JSON.parse(manifest.text), {
    schema_version: 'DB-MODEL-COMPARISON-CONNECTION-1', available: true, mode: 'private_session', module: '/comparison-api.mjs',
    request_schema: 'DB-MODEL-COMPARISON-1', result_schema: 'DB-MODEL-COMPARISON-RESULT-1',
  })
  assert.equal((await send(port, '/workspace-preview/comparison-service.json', {}, 'POST')).status, 405)
  const researchManifest = await send(port, '/workspace-preview/research-service.json')
  assert.deepEqual(JSON.parse(researchManifest.text), {schema_version:'DB-RESEARCH-CONNECTION-1',available:true,mode:'private_session',module:'/research-api.mjs'})
  assert.equal((await send(port, '/workspace-preview/research-service.json', {}, 'POST')).status, 405)
  for (const path of ['/workspace-preview/README.md', '/workspace-preview/../apps/api/bean_api/main.py',
    '/workspace-preview/%2e%2e/apps/api/bean_api/main.py', '/workspace-preview/.env', '/comparison-api.test.mjs', '/research-api.test.mjs', '/workspace-preview/tests/failure_worker.py', '/workspace-preview/check-research.mjs', '/fixtures/model-comparison/synthetic.request.json']) {
    assert.equal((await send(port, path)).status, 404, path)
  }
  assert.equal((await send(port, '/api/bean/v1/shared-session')).status, 503, 'Manifest alone cannot bypass absent private-access configuration')
})

test('shared entry navigation admits the preview document, but not its manifest, modules or API cross-site', async t => {
  const webPort = await server(t), directory = await mkdtemp(join(tmpdir(), 'bean-comparison-gateway-'))
  const origin = 'https://comparison-test.trycloudflare.com'
  const originFile = join(directory, 'origin.json'), gatewayFile = join(directory, 'gateway.json')
  await writeFile(originFile, JSON.stringify({ origin }))
  await writeFile(gatewayFile, JSON.stringify({ version: 1, secret: `DRBEAN-DUMMY-${'g'.repeat(30)}` }), { mode: 0o600 })
  const calls = []
  const api = createServer((req, res) => { calls.push(req.url); res.writeHead(401).end('{}') })
  const apiPort = await listen(api)
  const gateway = createShareGateway({ originFile, gatewayFile, webPort, apiPort }), port = await listen(gateway)
  t.after(async () => { await close(gateway); await close(api); await rm(directory, { recursive: true, force: true }) })
  const headers = { host: new URL(origin).host, 'x-forwarded-proto': 'https', 'sec-fetch-site': 'cross-site', 'sec-fetch-mode': 'navigate', 'sec-fetch-dest': 'document' }
  for (const path of ['/workspace-preview/', '/workspace-preview/index.html']) assert.equal((await send(port, path, headers)).status, 200)
  for (const path of ['/workspace-preview/app.mjs', '/workspace-preview/comparison-service.json', '/workspace-preview/research-service.json', '/comparison-api.mjs', '/research-api.mjs', '/api/bean/v1/shared-session']) assert.equal((await send(port, path, headers)).status, 403)
  assert.equal(calls.length, 0)
  const sameOrigin = { ...headers, 'sec-fetch-site': 'same-origin', 'sec-fetch-mode': 'cors', 'sec-fetch-dest': 'empty' }
  assert.equal((await send(port, '/workspace-preview/comparison-service.json', sameOrigin)).status, 200)
  assert.equal((await send(port, '/api/bean/v1/workspaces/private/model-comparisons', sameOrigin)).status, 401)
  assert.equal(calls.length, 1)
})
