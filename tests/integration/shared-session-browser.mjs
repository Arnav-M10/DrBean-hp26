// Real HTTPS browser -> real gateway -> actual FastAPI session authority.
// No tunnel, owner store, provider credentials, model call, or fixed app port.
// npm ci --prefix tests/integration --ignore-scripts --no-audit --no-fund
// node tests/integration/node_modules/playwright/cli.js install chromium
// node tests/integration/shared-session-browser.mjs
import assert from 'node:assert/strict'
import { spawn, execFileSync } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { mkdtemp, writeFile, readFile, rm, access } from 'node:fs/promises'
import { createServer as createHttpServer, request as httpRequest } from 'node:http'
import { createServer as createHttpsServer } from 'node:https'
import { createRequire } from 'node:module'
import { createServer as createNetServer, connect } from 'node:net'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createShareGateway } from '../../apps/web/share-gateway.mjs'

let chromium
try {
  ({ chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || 'playwright'))
} catch {
  console.log(JSON.stringify({ status: 'unrun', reason: 'Install the pinned tests/integration Playwright dependencies.' }))
  process.exit(3)
}
const root = fileURLToPath(new URL('../../', import.meta.url))
const python = process.env.BEAN_TEST_PYTHON || resolve(root, '.venv/bin/python')
const origin = 'https://private-test.trycloudflare.com', hostname = new URL(origin).hostname
const cookieName = '__Host-bean_session', prefix = '/api/bean/v1'
const temp = await mkdtemp(join(tmpdir(), 'drbean-private-browser-'))
const ownerToken = randomBytes(32).toString('base64url'), gatewaySecret = randomBytes(32).toString('base64url')
const children = [], servers = [], sockets = new Set(), checks = [], externalRequests = [], pageErrors = []
const networkGuardFile = join(temp, 'blocked-network-attempts')
const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds))
const check = (id, fn) => { fn(); checks.push({ id, passed: true }) }
const redact = text => String(text).split(ownerToken).join('[synthetic owner credential]').split(gatewaySecret).join('[synthetic gateway credential]')
let browser, apiChild

function track(server) {
  servers.push(server)
  server.on('connection', socket => { sockets.add(socket); socket.once('close', () => sockets.delete(socket)) })
  return server
}
async function listen(server) {
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve) })
  const port = server.address().port
  assert.ok(![8000, 4173, 4174].includes(port), 'Tests must not use the owner app ports')
  return port
}
async function freePort() {
  const reservation = createNetServer(), port = await listen(reservation)
  await new Promise(resolve => reservation.close(resolve))
  return port
}
function start(command, args, env) {
  const child = spawn(command, args, { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] })
  child.output = ''; child.launchError = null
  child.on('error', error => { child.launchError = error })
  child.done = new Promise(resolve => { child.once('exit', resolve); child.once('error', resolve) })
  for (const stream of [child.stdout, child.stderr]) stream.on('data', chunk => { child.output = (child.output + chunk).slice(-16384) })
  children.push(child)
  return child
}
async function stop(child) {
  if (!child || child.exitCode !== null || child.signalCode !== null || child.launchError) return
  child.kill('SIGTERM')
  let timer
  await Promise.race([child.done, new Promise(resolve => { timer = setTimeout(resolve, 5000) })])
  clearTimeout(timer)
  if (child.exitCode === null && child.signalCode === null) { child.kill('SIGKILL'); await child.done }
}
async function ready(url, child) {
  for (let i = 0; i < 100; i++) {
    if (child.launchError || child.exitCode !== null) throw new Error(`Isolated server exited: ${redact(child.output || child.launchError)}`)
    try { const response = await fetch(url, { signal: AbortSignal.timeout(1000) }); if (response.ok) return response } catch { /* startup only */ }
    await sleep(100)
  }
  throw new Error(`Isolated server did not become ready: ${redact(child.output)}`)
}
async function jsonRequest(base, path, { body, headers = {} } = {}) {
  const response = await fetch(base + prefix + path, { method: body === undefined ? 'GET' : 'POST',
    headers: { ...(body === undefined ? {} : { 'Content-Type': 'application/json' }), ...headers },
    body: body === undefined ? undefined : JSON.stringify(body), redirect: 'error', signal: AbortSignal.timeout(5000) })
  return { status: response.status, body: await response.json() }
}
async function browserRequest(page, path, { body, headers = {} } = {}) {
  return page.evaluate(async ({ path, body, headers }) => {
    const response = await fetch('/api/bean/v1' + path, { method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin',
      headers: { ...(body === undefined ? {} : { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() }), ...headers },
      body: body === undefined ? undefined : JSON.stringify(body), redirect: 'error', signal: AbortSignal.timeout(10000) })
    return { status: response.status, body: await response.json() }
  }, { path, body, headers })
}
async function bootstrap(page) {
  return page.evaluate(async () => {
    const { bootstrapSharedSession } = await import('/session.mjs')
    const binding = await bootstrapSharedSession()
    window.testSessionApi = binding.api
    return binding.session
  })
}
async function newPage(context) {
  const page = await context.newPage()
  page.on('pageerror', error => pageErrors.push(error.message))
  await page.route('**/*', route => {
    const url = route.request().url()
    if (!url.startsWith(origin + '/') && !/^(blob|data):/.test(url)) { externalRequests.push(url); return route.abort() }
    return route.continue()
  })
  const response = await page.goto(origin, { waitUntil: 'networkidle' })
  assert.equal(response.status(), 200)
  assert.ok(await page.locator('#connection-panel').count(), 'The real static app must be served')
  return page
}
const dataset = label => ({ schema_version: 'DB-SC-1', experiment_id: label, time_origin: 'Synthetic browser isolation fixture',
  rows: [{ id: 'row_one', time: '0/1', concentration: '1/1', hard_allowance: '1/10', included: true }],
  change_reason: 'Explicit synthetic fixture, never provider analysis', origin: 'synthetic' })

try {
  await writeFile(join(temp, 'auth.json'), JSON.stringify({ owner: ownerToken }), { mode: 0o600 })
  await writeFile(join(temp, 'share-gateway.json'), JSON.stringify({ version: 1, secret: gatewaySecret }), { mode: 0o600 })
  await writeFile(join(temp, 'share-origin.json'), JSON.stringify({ origin }), { mode: 0o600 })
  // Process-level defense: this API may accept local HTTP connections but cannot
  // establish any outbound socket or resolve an external hostname, even on a bug.
  await writeFile(join(temp, 'sitecustomize.py'), `import os, socket\nfrom pathlib import Path\ndef refuse(*args, **kwargs):\n Path(os.environ['BEAN_TEST_NETWORK_GUARD']).write_text('blocked outbound attempt\\n')\n raise RuntimeError('Outbound networking is forbidden in the private browser test')\nsocket.socket.connect = refuse\nsocket.socket.connect_ex = refuse\noriginal = socket.getaddrinfo\ndef local_only(host, *args, **kwargs):\n if host not in (None, '127.0.0.1', '::1', b'127.0.0.1', b'::1'):\n  return refuse()\n return original(host, *args, **kwargs)\nsocket.getaddrinfo = local_only\n`, { mode: 0o600 })
  const apiPort = await freePort(), webPort = await freePort()
  const apiBase = `http://127.0.0.1:${apiPort}`
  const apiEnv = { PATH: process.env.PATH || '/usr/bin:/bin', PYTHONPATH: `${temp}:${join(root, 'apps/api')}`,
    PYTHONDONTWRITEBYTECODE: '1', BEAN_AI_MODE: 'placeholder', BEAN_SCIENCE_ADAPTER: 'unavailable', BEAN_GENERAL_ANALYSIS_MODE: 'controlled_demo',
    BEAN_DATABASE_PATH: join(temp, 'browser.sqlite3'), BEAN_BLOB_DIR: join(temp, 'sources'),
    BEAN_AUTH_FILE: join(temp, 'auth.json'), BEAN_ARTIFACT_DIR: join(temp, 'artifacts'),
    BEAN_SHARE_GATEWAY_FILE: join(temp, 'share-gateway.json'), BEAN_TEST_NETWORK_GUARD: networkGuardFile }
  execFileSync(python, ['-c', "import socket; assert socket.socket.connect.__module__ == 'sitecustomize'; assert socket.getaddrinfo.__module__ == 'sitecustomize'"],
    { env: apiEnv, stdio: 'pipe' })
  const startApi = () => start(python, ['-m', 'uvicorn', 'bean_api.main:create_app', '--factory', '--host', '127.0.0.1',
    '--port', String(apiPort), '--no-access-log'], apiEnv)
  apiChild = startApi()
  await ready(apiBase + '/healthz', apiChild)
  const capabilities = await jsonRequest(apiBase, '/capabilities')
  check('actual-api-placeholder-and-sessions-ready', () => {
    assert.equal(capabilities.status, 200)
    assert.equal(capabilities.body.gemini.dispatch_enabled, false)
    assert.equal(capabilities.body.shared_access.available, true)
    assert.equal(capabilities.body.shared_access.mode, 'browser_session')
  })
  const webChild = start(process.execPath, ['apps/web/serve.mjs', String(webPort)],
    { PATH: process.env.PATH || '/usr/bin:/bin', BEAN_WEB_API_PORT: String(apiPort) })
  await ready(`http://127.0.0.1:${webPort}/`, webChild)
  const ownerHeaders = { Authorization: `Bearer ${ownerToken}` }
  const owner = await jsonRequest(apiBase, '/workspaces', { body: { name: 'Synthetic private owner work' }, headers: ownerHeaders })
  assert.equal(owner.status, 201)
  const ownerRecord = await jsonRequest(apiBase, `/workspaces/${owner.body.id}/datasets`, {
    body: dataset('owner_fixture'), headers: { ...ownerHeaders, 'Idempotency-Key': 'owner_browser_fixture' } })
  assert.equal(ownerRecord.status, 201)

  const gateway = track(createShareGateway({ originFile: join(temp, 'share-origin.json'), gatewayFile: join(temp, 'share-gateway.json'), apiPort, webPort }))
  const gatewayPort = await listen(gateway)
  const tlsKey = join(temp, 'localhost.key'), tlsCert = join(temp, 'localhost.crt')
  execFileSync('openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', tlsKey, '-out', tlsCert,
    '-subj', `/CN=${hostname}`, '-addext', `subjectAltName=DNS:${hostname}`, '-days', '1'],
  { env: { PATH: process.env.PATH || '/usr/bin:/bin' }, stdio: 'ignore' })
  const tlsServer = track(createHttpsServer({ key: await readFile(tlsKey), cert: await readFile(tlsCert) }, (request, response) => {
    const upstream = httpRequest({ hostname: '127.0.0.1', port: gatewayPort, method: request.method, path: request.url,
      headers: { ...request.headers, 'x-forwarded-proto': 'https', 'x-forwarded-host': request.headers.host } }, result => {
      response.writeHead(result.statusCode, result.headers); result.pipe(response)
    })
    upstream.on('error', () => { if (!response.headersSent) response.writeHead(502); response.end() })
    request.on('aborted', () => upstream.destroy()); request.pipe(upstream)
  }))
  const tlsPort = await listen(tlsServer)
  // The only CONNECT target is a synthetic canonical HTTPS host, mapped directly
  // to our own ephemeral TLS socket. This proxy cannot reach the internet.
  let deniedProxyConnections = 0
  const proxy = track(createHttpServer((_request, response) => { deniedProxyConnections++; response.writeHead(403).end() }))
  proxy.on('connect', (request, socket, head) => {
    if (request.url !== `${hostname}:443`) { deniedProxyConnections++; socket.end('HTTP/1.1 403 Forbidden\r\n\r\n'); return }
    const upstream = connect(tlsPort, '127.0.0.1', () => {
      socket.write('HTTP/1.1 200 Connection Established\r\n\r\n')
      if (head.length) upstream.write(head)
      socket.pipe(upstream); upstream.pipe(socket)
    })
    sockets.add(upstream); upstream.once('close', () => sockets.delete(upstream))
    upstream.on('error', () => socket.destroy()); socket.on('error', () => upstream.destroy())
    socket.once('close', () => upstream.destroy())
  })
  const proxyPort = await listen(proxy)
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || chromium.executablePath(),
    proxy: { server: `http://127.0.0.1:${proxyPort}` }, args: ['--no-sandbox', '--disable-background-networking', '--disable-quic',
      '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1', '--proxy-bypass-list=<-loopback>'] })
  const alice = await browser.newContext({ ignoreHTTPSErrors: true }), bob = await browser.newContext({ ignoreHTTPSErrors: true })
  const pageA = await newPage(alice), pageB = await newPage(bob)
  const sessionA = await bootstrap(pageA), sessionB = await bootstrap(pageB)
  check('two-real-browser-contexts-get-distinct-private-workspaces', () => {
    assert.notEqual(sessionA.workspace_id, sessionB.workspace_id)
    assert.notEqual(sessionA.workspace_id, owner.body.id)
    assert.deepEqual(Object.keys(sessionA).sort(), ['authenticated', 'credentials', 'mode', 'workspace_id'])
    assert.equal(sessionA.credentials, 'server_managed')
  })
  const cookiesA = await alice.cookies(origin), cookiesB = await bob.cookies(origin)
  const secretA = cookiesA.find(item => item.name === cookieName), secretB = cookiesB.find(item => item.name === cookieName)
  check('browser-enforces-secure-httponly-host-cookie', () => {
    assert.ok(secretA && secretB)
    assert.notEqual(secretA.value, secretB.value)
    assert.equal(secretA.secure, true); assert.equal(secretA.httpOnly, true); assert.equal(secretA.sameSite, 'Strict')
    assert.equal(secretA.domain, hostname); assert.equal(secretA.path, '/')
    assert.ok(secretA.expires > Date.now() / 1000 && secretA.expires <= Date.now() / 1000 + 86401)
  })
  assert.equal(await pageA.evaluate(() => document.cookie.includes('__Host-bean_session')), false)
  for (const page of [pageA, pageB]) {
    const browserVisible = await page.evaluate(() => JSON.stringify({
      dom: document.documentElement.outerHTML, cookies: document.cookie,
      local: Object.entries(localStorage), session: Object.entries(sessionStorage),
    }))
    for (const secret of [secretA.value, secretB.value, ownerToken, gatewaySecret]) assert.equal(browserVisible.includes(secret), false)
  }
  checks.push({ id: 'session-and-server-secrets-absent-from-dom-and-browser-storage', passed: true })
  for (const [page, session] of [[pageA, sessionA], [pageB, sessionB]]) {
    const own = await page.evaluate(() => window.testSessionApi.json('/workspaces'))
    assert.deepEqual(own.map(item => item.id), [session.workspace_id])
  }
  checks.push({ id: 'separate-workspace-lists-exclude-other-browser-and-owner', passed: true })
  const recordA = await pageA.evaluate(async ({ workspace, body }) => window.testSessionApi.json(`/workspaces/${workspace}/datasets`, body),
    { workspace: sessionA.workspace_id, body: dataset('alice_fixture') })
  for (const [page, forbiddenWorkspace, forbiddenRecord] of [
    [pageB, sessionA.workspace_id, recordA.id], [pageA, sessionB.workspace_id, null],
    [pageA, owner.body.id, ownerRecord.body.id], [pageB, owner.body.id, ownerRecord.body.id],
  ]) {
    assert.equal((await browserRequest(page, `/workspaces/${forbiddenWorkspace}`)).status, 404)
    assert.equal((await browserRequest(page, `/workspaces/${forbiddenWorkspace}/records?kind=dataset`)).status, 404)
    assert.equal((await browserRequest(page, `/workspaces/${forbiddenWorkspace}/datasets`, { body: dataset('forbidden_fixture') })).status, 404)
    if (forbiddenRecord) assert.equal((await browserRequest(page, `/records/${forbiddenRecord}`)).status, 404)
  }
  checks.push({ id: 'cross-browser-and-owner-reads-and-mutations-denied', passed: true })
  const forgedHeaders = { Authorization: `Bearer ${ownerToken}`, 'X-Owner-Id': 'owner',
    'X-Bean-Shared-Gateway': 'f'.repeat(43), 'X-Bean-Shared-Origin': origin }
  const forgedList = await browserRequest(pageA, '/workspaces', { headers: forgedHeaders })
  assert.equal(forgedList.status, 200)
  assert.deepEqual(forgedList.body.map(item => item.id), [sessionA.workspace_id])
  assert.equal((await browserRequest(pageA, `/workspaces/${owner.body.id}`, { headers: forgedHeaders })).status, 404)
  assert.equal((await browserRequest(pageA, `/workspaces/${owner.body.id}/datasets`, { body: dataset('upgrade_attack'), headers: forgedHeaders })).status, 404)
  checks.push({ id: 'browser-owner-bearer-and-forged-boundary-cannot-upgrade-session', passed: true })

  // Real retained-file producer, actual citation validation and ordinary UI.
  // Only the model response is an explicitly labelled local controlled preview.
  await pageA.evaluate(() => { location.hash = 'research' })
  await pageA.locator('#research-files').setInputFiles(join(root, 'tests/integration/fixtures/general/penguins-excerpt.csv'))
  await pageA.locator('#general-assets article').first().waitFor()
  const admitted = await browserRequest(pageA, `/workspaces/${sessionA.workspace_id}/research-assets`)
  assert.equal(admitted.status, 200); assert.equal(admitted.body.length, 1)
  const source = admitted.body[0]
  assert.equal(source.sha256, execFileSync(python, ['-c', 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())',
    join(root, 'tests/integration/fixtures/general/penguins-excerpt.csv')], { env: { PATH: process.env.PATH }, encoding: 'utf8' }).trim())
  assert.equal((await browserRequest(pageB, `/research-assets/${source.id}`)).status, 404)
  assert.equal((await browserRequest(pageB, `/research-assets/${source.id}/content`)).status, 404)
  checks.push({ id: 'real-file-ui-retains-exact-bytes-and-private-source-binding', passed: true })
  const originalQuestion = 'Which penguin measurements and missing values should I review before comparing groups?'
  await pageA.locator('#research-question').fill(originalQuestion)
  await pageA.locator('#general-review-button').click()
  await pageA.locator('#general-consent').waitFor()
  assert.match(await pageA.locator('[data-general-review]').innerText(), /Controlled local preview/)
  await pageA.locator('#general-consent').check()
  let dropAnalysisAcknowledgement = true
  await pageA.route('**/research-analyses', async route => {
    if (route.request().method() === 'POST' && dropAnalysisAcknowledgement) {
      dropAnalysisAcknowledgement = false
      const response = await route.fetch()
      assert.equal(response.status(), 201)
      return route.abort('failed')
    }
    return route.continue()
  })
  await pageA.locator('#general-analyze').click()
  await pageA.locator('#general-pending').waitFor()
  const completedAnalysis = await browserRequest(pageA, `/workspaces/${sessionA.workspace_id}/research-analyses`)
  assert.equal(completedAnalysis.body.length, 1, 'The actual backend completed before its acknowledgement was dropped')
  await pageA.locator('#research-question').fill('A changed question must not relabel the saved result.')
  await pageA.reload({ waitUntil: 'networkidle' })
  await pageA.locator('#general-pending details').first().locator('summary').first().click()
  await pageA.getByRole('button', { name: 'Retry this same reviewed request', exact: true }).click()
  await pageA.locator('#general-result').waitFor()
  assert.match(await pageA.locator('#general-result').innerText(), /Controlled test response/)
  assert.ok((await pageA.locator('#general-result').innerText()).includes(originalQuestion))
  assert.equal((await browserRequest(pageA, `/workspaces/${sessionA.workspace_id}/research-analyses`)).body.length, 1)
  assert.equal((await browserRequest(pageB, `/research-analyses/${completedAnalysis.body[0].id}`)).status, 404)
  checks.push({ id: 'actual-analysis-lost-ack-reload-retry-reuses-result-and-original-question', passed: true })
  await pageA.locator('#general-result .citation-link').first().click()
  await pageA.locator('#general-citation-panel').waitFor()
  assert.ok((await pageA.locator('#general-citation-panel').innerText()).includes(source.filename))
  checks.push({ id: 'actual-producer-citation-opens-retained-source-evidence', passed: true })

  const sourceQuestion = 'Which scientific model and metadata would be needed for these penguin measurements?'
  await pageA.locator('#research-question').fill(sourceQuestion)
  // The research plan lives on the Investigate step; changing the hash never reloads state.
  await pageA.evaluate(() => { location.hash = 'investigations' })
  await pageA.getByRole('button', { name: 'Save selected files and research question', exact: true }).click()
  await pageA.locator('#durable-research h4').filter({ hasText: sourceQuestion }).waitFor()
  const savedResearch = await browserRequest(pageA, `/workspaces/${sessionA.workspace_id}/research-sessions`)
  assert.equal(savedResearch.body.items.length, 1)
  const researchId = savedResearch.body.items[0].id
  assert.equal(savedResearch.body.items[0].objective, sourceQuestion)
  assert.equal(savedResearch.body.items[0].problem_id, null, 'Arbitrary biological data must not become concentration inputs')
  assert.deepEqual(savedResearch.body.items[0].sources, [{ id: source.id, sha256: source.sha256 }])
  assert.equal(savedResearch.body.items[0].action, null, 'Saving files/question does not advance or compute')
  assert.equal((await browserRequest(pageB, `/research-sessions/${researchId}`)).status, 404)
  assert.equal((await browserRequest(pageB, `/research-sessions/${researchId}/events`)).status, 404)
  checks.push({ id: 'ordinary-research-ui-retains-untrusted-files-question-without-forced-scientific-model', passed: true })

  await pageA.reload({ waitUntil: 'networkidle' })
  assert.equal((await bootstrap(pageA)).workspace_id, sessionA.workspace_id)
  assert.equal((await browserRequest(pageA, `/records/${recordA.id}`)).body.id, recordA.id)
  assert.equal((await browserRequest(pageA, `/research-sessions/${researchId}`)).body.objective, sourceQuestion)
  await pageB.close()
  const reopenedB = await newPage(bob)
  assert.equal((await bootstrap(reopenedB)).workspace_id, sessionB.workspace_id)
  checks.push({ id: 'reload-and-new-tab-reopen-retain-private-session', passed: true })
  await stop(apiChild)
  apiChild = startApi()
  await ready(apiBase + '/healthz', apiChild)
  assert.equal((await bootstrap(pageA)).workspace_id, sessionA.workspace_id)
  assert.equal((await bootstrap(reopenedB)).workspace_id, sessionB.workspace_id)
  assert.equal((await browserRequest(pageA, `/records/${recordA.id}`)).body.id, recordA.id)
  assert.equal((await browserRequest(reopenedB, `/records/${recordA.id}`)).status, 404)
  checks.push({ id: 'actual-api-restart-preserves-session-authority-and-records', passed: true })

  const rotated = await browserRequest(pageA, '/shared-session/rotate', { body: {} })
  assert.equal(rotated.status, 200); assert.equal(rotated.body.workspace_id, sessionA.workspace_id)
  assert.notEqual((await alice.cookies(origin)).find(item => item.name === cookieName).value, secretA.value)
  const replay = await browser.newContext({ ignoreHTTPSErrors: true })
  await replay.addCookies([secretA])
  const replayPage = await newPage(replay)
  assert.equal((await browserRequest(replayPage, `/workspaces/${sessionA.workspace_id}`)).status, 401)
  await replay.close()
  checks.push({ id: 'rotated-cookie-replay-does-not-reopen-private-work', passed: true })
  assert.deepEqual((await jsonRequest(apiBase, '/workspaces', { headers: ownerHeaders })).body.map(item => item.id), [owner.body.id])
  assert.equal((await jsonRequest(apiBase, `/records/${ownerRecord.body.id}`, { headers: ownerHeaders })).status, 200)
  checks.push({ id: 'local-owner-access-and-records-remain-intact', passed: true })
  assert.deepEqual((await browserRequest(pageA, `/workspaces/${sessionA.workspace_id}/provider-attempts`)).body, [])
  assert.deepEqual(pageErrors, [])
  assert.deepEqual(externalRequests, [])
  await stop(apiChild)
  const evidence = JSON.parse(execFileSync(python, ['-c',
    "import json,sqlite3,sys; c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True); print(json.dumps({'provider_attempts':c.execute('SELECT count(*) FROM provider_attempts').fetchone()[0],'sessions':c.execute('SELECT count(*) FROM browser_sessions').fetchone()[0]}))",
    join(temp, 'browser.sqlite3')], { env: { PATH: process.env.PATH || '/usr/bin:/bin' }, encoding: 'utf8' }))
  assert.equal(evidence.provider_attempts, 0)
  let outboundAttempt = false
  try { await access(networkGuardFile); outboundAttempt = true } catch { /* absent means no attempted outbound socket */ }
  assert.equal(outboundAttempt, false)
  checks.push({ id: 'zero-provider-attempts-and-no-outbound-api-or-browser-request', passed: true })
  console.log(JSON.stringify({ status: 'passed', total: checks.length, checks, provider_attempts: 0,
    api_outbound_attempts: 0, external_page_requests: 0, denied_browser_background_connections: deniedProxyConnections,
    scope: 'Actual isolated HTTPS browser/session components; no public tunnel or live Gemini qualification.' }, null, 2))
} catch (error) {
  console.error(JSON.stringify({ status: 'failed', completed_checks: checks, error: redact(error.stack || error) }, null, 2))
  process.exitCode = 1
} finally {
  await browser?.close().catch(() => {})
  for (const socket of sockets) socket.destroy()
  for (const server of servers.reverse()) {
    server.closeAllConnections?.()
    if (server.listening) await new Promise(resolve => server.close(resolve))
  }
  for (const child of children.reverse()) await stop(child)
  await rm(temp, { recursive: true, force: true })
}
