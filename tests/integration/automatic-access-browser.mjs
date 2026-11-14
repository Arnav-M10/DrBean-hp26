// Actual launcher, automatic local browser identity, and two isolated HTTPS visitors.
// This is an offline acceptance test: temporary store, no tunnel, no provider calls.
// BEAN_AUTOMATIC_ACCESS_EVIDENCE_DIR=/tmp/bean-access-evidence \
//   PLAYWRIGHT_MODULE=/absolute/path/to/playwright node tests/integration/automatic-access-browser.mjs
import assert from 'node:assert/strict'
import { spawn, execFileSync } from 'node:child_process'
import { randomBytes, createHash } from 'node:crypto'
import { mkdtemp, mkdir, writeFile, readFile, rm } from 'node:fs/promises'
import { createServer as createHttpServer, request as httpRequest } from 'node:http'
import { createServer as createHttpsServer } from 'node:https'
import { createRequire } from 'node:module'
import { createServer as createNetServer, connect } from 'node:net'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createShareGateway } from '../../apps/web/share-gateway.mjs'

const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || 'playwright')
const root = fileURLToPath(new URL('../../', import.meta.url))
const python = process.env.BEAN_TEST_PYTHON || resolve(root, '.venv/bin/python')
const engine = process.env.BEAN_TEST_ENGINE_PYTHON || resolve(root, '.venv-engine/bin/python')
const scratch = await mkdtemp(join(tmpdir(), 'drbean-automatic-access-'))
const output = process.env.BEAN_AUTOMATIC_ACCESS_EVIDENCE_DIR
  ? resolve(process.env.BEAN_AUTOMATIC_ACCESS_EVIDENCE_DIR)
  : await mkdtemp(join(tmpdir(), 'drbean-automatic-access-evidence-'))
const prefix = '/api/bean/v1', origin = 'https://automatic-access-test.trycloudflare.com'
const hostname = new URL(origin).hostname
const ownerToken = 'DRBEAN-DUMMY-' + randomBytes(32).toString('base64url')
const gatewaySecret = 'DRBEAN-DUMMY-' + randomBytes(24).toString('base64url').slice(0, 30)
const checks = [], external = [], pageErrors = [], browserConsole = [], browsers = [], servers = [], sockets = new Set()
const secretValues = [ownerToken, gatewaySecret]
let launched = false, currentPage, deniedProxyConnections = 0
const redact = value => secretValues.reduce((text, secret) => text.split(secret).join('[synthetic private credential]'), String(value))
const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds))
const check = id => { checks.push({ id, passed: true }); console.log(JSON.stringify({ check: id, status: 'passed' })) }

async function listen(server) {
  await new Promise((yes, no) => { server.once('error', no); server.listen(0, '127.0.0.1', yes) })
  const port = server.address().port
  assert.ok(![8000, 4173, 4174].includes(port), 'Tests must not bind the owner app ports')
  return port
}
async function freePort() {
  const reservation = createNetServer(), port = await listen(reservation)
  await new Promise(yes => reservation.close(yes))
  return port
}
const apiPort = await freePort(), webPort = await freePort(), base = `http://127.0.0.1:${webPort}`
const env = { PATH: process.env.PATH || '/opt/homebrew/bin:/usr/bin:/bin', LANG: 'C.UTF-8', DRBEAN_VAR_DIR: scratch,
  BEAN_AUTH_FILE: join(scratch, 'auth.json'), BEAN_DEV_API_PORT: String(apiPort), BEAN_DEV_WEB_PORT: String(webPort),
  BEAN_RESEARCH_MODE: 'controlled', BEAN_AI_MODE: 'placeholder', PYTHONDONTWRITEBYTECODE: '1', LANGSMITH_TRACING: 'false',
  PYTHONPATH: join(root, 'evaluation/drbean_eval/guard') + ':' + join(root, 'apps/api'),
  DRBEAN_EGRESS_GUARD_LOG: join(scratch, 'egress.jsonl') }
async function command(executable, args, timeout = 60000) {
  const child = spawn(executable, args, { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] })
  let text = '', timer
  for (const stream of [child.stdout, child.stderr]) stream.on('data', bytes => { text = (text + bytes).slice(-1048576) })
  const result = await new Promise((yes, no) => {
    child.once('error', no); child.once('exit', code => yes(code))
    timer = setTimeout(() => { child.kill('SIGTERM'); no(new Error('Owned test command timed out')) }, timeout)
  }).finally(() => clearTimeout(timer))
  assert.equal(result, 0, redact(text))
  return text
}
function store(script, args = []) {
  return JSON.parse(execFileSync(python, ['-c', script, join(scratch, 'bean.sqlite3'), ...args],
    { env, encoding: 'utf8' }))
}
function counters() {
  return store(`import json,sqlite3,sys
c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True)
tables=['browser_sessions','workspaces','memberships','operations','provider_attempts','jobs','scenario_reservations','approvals','research_actions','research_effects','research_attempt_bindings']
r={t:c.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in tables}
r['scientific_reservations']=c.execute('SELECT coalesce(sum(scientific_reservations),0) FROM jobs').fetchone()[0]
print(json.dumps(r))`)
}
function scientificCounters(value) {
  const { browser_sessions, workspaces, memberships, ...scientific } = value
  return scientific
}
async function browserRequest(page, path, { body, headers = {} } = {}) {
  return page.evaluate(async ({ path, body, headers }) => {
    const response = await fetch('/api/bean/v1' + path, { method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin',
      headers: { ...(body === undefined ? {} : { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() }), ...headers },
      body: body === undefined ? undefined : JSON.stringify(body), redirect: 'error', signal: AbortSignal.timeout(15000) })
    const text = await response.text()
    let data; try { data = JSON.parse(text) } catch { data = { bytes: text.length } }
    return { status: response.status, body: data }
  }, { path, body, headers })
}
async function ownApi(page, path) {
  const result = await browserRequest(page, path)
  assert.equal(result.status, 200, JSON.stringify(result.body))
  return result.body
}
async function directOwner(path, body) {
  const response = await fetch(`http://127.0.0.1:${apiPort}${prefix}${path}`, {
    method: body === undefined ? 'GET' : 'POST', headers: { Authorization: `Bearer ${ownerToken}`,
      ...(body === undefined ? {} : { 'Content-Type': 'application/json', 'Idempotency-Key': randomBytes(16).toString('hex') }) },
    body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(10000) })
  assert.ok(response.ok, `Synthetic operator fixture failed: ${response.status}`)
  return response.json()
}
async function trackedPage(context, allowedOrigin) {
  const page = await context.newPage(); currentPage = page
  page.on('pageerror', error => pageErrors.push(error.message))
  page.on('console', message => { if (['warning', 'error'].includes(message.type())) browserConsole.push({ type: message.type(), text: redact(message.text()) }) })
  page.on('dialog', dialog => dialog.accept()) // Only this harness's deliberately discarded local draft.
  await page.route('**/*', route => {
    const url = route.request().url()
    if (!url.startsWith(allowedOrigin + '/') && !/^(blob|data):/.test(url)) { external.push(url); return route.abort() }
    return route.continue()
  })
  return page
}
async function readyPage(page, allowedOrigin) {
  await page.goto(allowedOrigin + '/#inputs', { waitUntil: 'networkidle' })
  await page.waitForFunction(() => Boolean(document.querySelector('#workspace-select')?.value), null, { timeout: 30000 })
  assert.equal(await page.locator('#connect-form').isVisible(), false)
  assert.equal(await page.locator('#bearer').isVisible(), false)
  const session = await ownApi(page, '/shared-session/current')
  assert.equal(session.mode, 'browser_session'); assert.equal(session.credentials, 'server_managed')
  assert.equal(await page.locator('#workspace-select').inputValue(), session.workspace_id)
  return session
}
async function assertHiddenSecrets(page) {
  const visible = await page.evaluate(() => JSON.stringify({ dom: document.documentElement.outerHTML,
    cookies: document.cookie, local: Object.entries(localStorage), session: Object.entries(sessionStorage) }))
  for (const secret of secretValues) assert.equal(visible.includes(secret), false, 'Credentials must remain outside page and web storage')
}
function track(server) {
  servers.push(server)
  server.on('connection', socket => { sockets.add(socket); socket.once('close', () => sockets.delete(socket)) })
  return server
}
async function publicBrowser() {
  const gateway = track(createShareGateway({ originFile: join(scratch, 'share-origin.json'),
    gatewayFile: join(scratch, 'share-gateway.json'), apiPort, webPort }))
  const gatewayPort = await listen(gateway)
  const tlsKey = join(scratch, 'localhost.key'), tlsCert = join(scratch, 'localhost.crt')
  execFileSync('openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', tlsKey, '-out', tlsCert,
    '-subj', `/CN=${hostname}`, '-addext', `subjectAltName=DNS:${hostname}`, '-days', '1'], { env, stdio: 'ignore' })
  const tlsServer = track(createHttpsServer({ key: await readFile(tlsKey), cert: await readFile(tlsCert) }, (request, response) => {
    const upstream = httpRequest({ hostname: '127.0.0.1', port: gatewayPort, method: request.method, path: request.url,
      headers: { ...request.headers, 'x-forwarded-proto': 'https', 'x-forwarded-host': request.headers.host } }, result => {
      response.writeHead(result.statusCode, result.headers); result.pipe(response)
    })
    upstream.on('error', () => { if (!response.headersSent) response.writeHead(502); response.end() })
    request.on('aborted', () => upstream.destroy()); request.pipe(upstream)
  }))
  const tlsPort = await listen(tlsServer)
  const proxy = track(createHttpServer((_request, response) => { deniedProxyConnections++; response.writeHead(403).end() }))
  proxy.on('connect', (request, socket, head) => {
    if (request.url !== `${hostname}:443`) { deniedProxyConnections++; socket.end('HTTP/1.1 403 Forbidden\r\n\r\n'); return }
    const upstream = connect(tlsPort, '127.0.0.1', () => {
      socket.write('HTTP/1.1 200 Connection Established\r\n\r\n'); if (head.length) upstream.write(head)
      socket.pipe(upstream); upstream.pipe(socket)
    })
    sockets.add(upstream); upstream.once('close', () => sockets.delete(upstream))
    upstream.on('error', () => socket.destroy()); socket.on('error', () => upstream.destroy())
    socket.once('close', () => upstream.destroy())
  })
  const proxyPort = await listen(proxy)
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || chromium.executablePath(),
    proxy: { server: `http://127.0.0.1:${proxyPort}` }, args: ['--no-sandbox', '--disable-background-networking', '--disable-quic',
      '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1', '--proxy-bypass-list=<-loopback>'] })
  browsers.push(browser); return browser
}

async function scientificLoop(page, otherPage, workspace) {
  const api = path => ownApi(page, path)
  const panel = page.locator('#durable-research')
  // Ordinary uploaded file and explicit reviewed correction, not injected candidates.
  const file = join(scratch, 'reviewed-synthetic-readings.csv')
  await writeFile(file, 'time,concentration,epsilon\n0.25,4.80,0.50\n0.5,7.20,0.50\n1,8.00,0.50\n2,6.80,0.50\n4,5.70,0.50\n')
  await page.locator('#csv-file').setInputFiles(file)
  await page.getByRole('button', { name: 'Use these rows', exact: true }).click()
  await page.getByLabel('Row 1, concentration', { exact: true }).fill('4.81')
  await page.click('#measurements button[type=submit]')
  for (const [id, value] of Object.entries({ 'experiment-id': 'automatic-access-synthetic', 'time-origin': 'Explicit synthetic elapsed hours from t=0',
    aMin: '0.001', aMax: '30', keMin: '0.015', keMax: '0.35', kaMin: '0.4', kaMax: '8', targetMin: '0.10', targetMax: '0.17',
    allowanceOrigin: 'Explicit synthetic hard bound of 0.50 mg/L, not an SD or instrument claim',
    goal: 'Does this reviewed target range survive these corrected measurements, and what checked pair measurement distinguishes the computed candidates?' })) await page.fill(`#${id}`, value)
  await page.selectOption('#dataset-origin', 'synthetic')
  await page.click('#question-form button[type=submit]')
  await page.getByRole('link', { name: 'Research with the assistant', exact: true }).click()
  await panel.getByText('Feasible next-measurement constraints (optional until design)', { exact: true }).click()
  for (const [name, value] of Object.entries({ times: '8, 6', allowance: '0.2', horizon: '8',
    allowanceReason: 'Explicit synthetic prospective hard bound; not a claim about an instrument' })) await panel.locator(`[name="${name}"]`).fill(value)
  await panel.getByLabel('I reviewed the exact measurement values, units, time origin, hard allowances, parameter bounds and question assumptions.', { exact: true }).check()
  await panel.getByRole('button', { name: 'Save reviewed inputs and research question', exact: true }).click()
  await panel.getByRole('button', { name: 'Advance research plan', exact: true }).waitFor()
  let session = (await api(`/workspaces/${workspace}/research-sessions`)).items[0]
  assert.equal(session.children.length, 0); assert.equal(session.action, null)
  assert.equal(session.reviewed_context.dataset.body.rows[0].concentration, '481/100')
  await panel.getByRole('button', { name: 'Advance research plan', exact: true }).click()
  await panel.getByRole('heading', { name: 'Review the investigation operation', exact: true }).waitFor({ timeout: 30000 })
  session = await api(`/research-sessions/${session.id}`)
  assert.equal(session.state, 'waiting_review'); assert.ok(session.plan.body.steps.length); assert.equal(session.children.length, 0)
  const approve = panel.getByRole('button', { name: 'Approve exact operation and continue', exact: true })
  assert.equal(await approve.isDisabled(), true)
  for (const path of [`/research-sessions/${session.id}`, `/research-sessions/${session.id}/events`, `/records/${session.pending_review.id}`]) {
    assert.equal((await browserRequest(otherPage, path)).status, 404)
  }
  const forbiddenDecision = { expected_revision: session.revision, pending_review_id: session.pending_review.id,
    expected_review_digest: session.pending_review.digest, decision: 'approve', accepted: true }
  assert.equal((await browserRequest(otherPage, `/research-sessions/${session.id}/decisions`, { body: forbiddenDecision })).status, 404)
  check('automatic-session-exact-input-review-and-cross-visitor-approval-denial')
  await panel.getByLabel('I approve only this frozen scientific scope and its limits.', { exact: true }).check()
  await approve.click()
  await panel.getByRole('button', { name: 'Plan next step for separate review', exact: true }).waitFor({ timeout: 140000 })
  session = await api(`/research-sessions/${session.id}`)
  assert.equal(session.state, 'completed'); assert.equal(session.children.length, 1); assert.equal(session.reports.length, 1)
  await panel.getByRole('button', { name: 'Plan next step for separate review', exact: true }).click()
  await panel.getByRole('heading', { name: 'Review the separate pair-design operation', exact: true }).waitFor({ timeout: 140000 })
  session = await api(`/research-sessions/${session.id}`)
  assert.equal(session.children.length, 1)
  const baseline = await api(`/records/${session.children[0].scenarios[0].result_id}`)
  assert.equal(baseline.body.result.problem_id, session.problem_id)
  assert.equal(baseline.body.result.expected_binding, 'matches')
  assert.equal(baseline.body.result.scientific_outcome, 'certified_counterexample')
  assert.equal(baseline.body.result.verification, 'valid')
  assert.equal(baseline.body.result.candidates.length, 2)
  const events = (await api(`/research-sessions/${session.id}/events?after=-1`)).items
  assert.ok(events.some(event => event.event_type === 'evidence_observed' && event.reference_ids.includes(baseline.id)))
  assert.deepEqual(session.pending_review.body.request.candidate_ids, baseline.body.result.candidates.map(candidate => candidate.id))
  assert.equal(await approve.isDisabled(), true)
  await panel.getByLabel('I approve only this frozen scientific scope and its limits.', { exact: true }).check()
  await approve.click()
  await page.waitForFunction(() => document.querySelector('#durable-research').textContent.includes('State: completed'), null, { timeout: 140000 })
  session = await api(`/research-sessions/${session.id}`)
  assert.equal(session.children.length, 2); assert.ok(session.children.every(child => child.state === 'completed'))
  assert.equal(session.reports.length, 2)
  for (const child of session.children) assert.equal((await browserRequest(otherPage, `/approvals/${child.approval_id}`)).status, 404)
  check('cookie-authorized-real-baseline-and-separately-approved-pair-design')
  const navigate = async (name, keyboard = false) => {
    const link = page.locator('.steps').getByRole('link', { name })
    const hash = await link.getAttribute('href'), previous = await page.evaluate(() => location.hash)
    if (keyboard) { await link.focus(); await page.keyboard.press('Enter') }
    else await link.click()
    await page.waitForFunction(({ hash, changed }) => location.hash === hash
      && !document.getElementById(hash.slice(1)).hidden
      && (!changed || document.activeElement?.id === `${hash.slice(1)}-title`), { hash, changed: previous !== hash })
  }
  await navigate(/^Next measurement/)
  const [download] = await Promise.all([page.waitForEvent('download'), page.locator('#research-report').getByRole('button', { name: 'Download research report snapshot', exact: true }).last().click()])
  await download.saveAs(join(output, 'report.json'))
  const downloaded = JSON.parse(await readFile(join(output, 'report.json'), 'utf8')), report = downloaded.body
  assert.equal(report.report_profile, 'research-report.v2'); assert.equal(report.evidence.length, 2); assert.equal(report.native_evidence.length, 2)
  assert.equal((await browserRequest(otherPage, `/records/${downloaded.id}`)).status, 404)
  assert.equal((await browserRequest(otherPage, `/reports/${downloaded.id}/download`)).status, 404)
  for (let index = 0; index < report.native_evidence.length; index++) {
    const entry = report.native_evidence[index]
    const evidence = report.evidence.find(item => item.id === entry.evidence_id)
    await navigate(evidence.kind === 'suggestion' ? /^Next measurement/ : /^Result/)
    const destination = page.locator(evidence.kind === 'suggestion' ? '#research-next' : '#research-results')
    const card = destination.locator('section.callout').filter({ hasText: entry.artifact.id })
    assert.equal(await card.count(), 1, `One visible evidence card must bind artifact ${entry.artifact.id}`)
    for (const path of [`/artifacts/${entry.artifact.id}`, `/artifacts/${entry.artifact.id}/anchor`]) assert.equal((await browserRequest(otherPage, path)).status, 404)
    const [native] = await Promise.all([page.waitForEvent('download'), card.getByRole('button', { name: 'Download evidence file', exact: true }).click()])
    const [anchor] = await Promise.all([page.waitForEvent('download'), card.getByRole('button', { name: 'Download replay anchors', exact: true }).click()])
    const nativePath = join(output, entry.native_filename), anchorPath = join(output, entry.anchor_filename)
    await native.saveAs(nativePath); await anchor.saveAs(anchorPath)
    assert.equal(createHash('sha256').update(await readFile(nativePath)).digest('hex'), entry.artifact.sha256)
    const replay = JSON.parse(await command(engine, ['-I', '-m', 'counterdex', 'replay-native', nativePath, '--anchors', anchorPath]))
    assert.equal(replay.integrity, 'passed'); assert.equal(replay.expected_binding, 'matches')
    const result = evidence.body.result || evidence.body
    assert.equal(replay.replay, result.replay)
    if (evidence.kind === 'suggestion') {
      assert.equal(result.design_tier, 'checked_pair_separation')
      assert.equal(replay.fresh_checked.tier, result.design_tier)
    }
    else assert.equal(replay.outcome.scientific_outcome, result.scientific_outcome)
    await writeFile(join(output, `${entry.artifact.id}.replay.json`), JSON.stringify(replay, null, 2))
  }
  await page.evaluate(() => scrollTo(0, 0))
  await page.screenshot({ path: join(output, 'scientific-loop.png'), fullPage: true })
  check('native-browser-downloads-private-anchors-and-fresh-cpython311-replay')
  const beforeVisualReview = counters(), layouts = []
  for (const viewport of [{ name: 'desktop', width: 1280, height: 900 }, { name: 'phone', width: 390, height: 844 }]) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    for (const [name, label] of [['start', /^Start/], ['result', /^Result/], ['next', /^Next measurement/]]) {
      await navigate(label, true)
      if (name === 'start') {
        const resume = page.locator('#resume-list')
        const saved = resume.locator('.resume-item').filter({ hasText: session.objective.slice(0, 160) })
        assert.equal(await saved.count(), 1, 'The current research session must appear exactly once in saved work')
        assert.equal(await saved.locator('strong').innerText(), session.objective.slice(0, 160))
        assert.equal(await saved.getByText('Research plan, completed', { exact: true }).count(), 1)
        assert.doesNotMatch(await resume.innerText(), /No saved checks/)
      }
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
      await page.evaluate(() => scrollTo(0, 0))
      const layout = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth,
        focused: document.activeElement?.id, current: document.querySelector('.steps [aria-current="step"]')?.getAttribute('href') }))
      assert.ok(layout.document <= layout.viewport + 1, `${viewport.name} ${name} must not overflow horizontally: ${JSON.stringify(layout)}`)
      assert.equal(layout.focused, `${name}-title`)
      assert.equal(layout.current, `#${name}`)
      layouts.push({ page: name, device: viewport.name, ...layout })
      await page.screenshot({ path: join(output, `${name}-${viewport.name}.png`), fullPage: true })
    }
  }
  assert.deepEqual(counters(), beforeVisualReview)
  await writeFile(join(output, 'layout-review.json'), JSON.stringify(layouts, null, 2))
  check('desktop-and-phone-keyboard-navigation-preserve-layout-focus-and-operation-ledgers')
}

try {
  await mkdir(output, { recursive: true })
  await writeFile(join(scratch, 'auth.json'), JSON.stringify({ owner: ownerToken }), { mode: 0o600 })
  await writeFile(join(scratch, 'share-gateway.json'), JSON.stringify({ version: 1, secret: gatewaySecret }), { mode: 0o600 })
  await writeFile(join(scratch, 'share-origin.json'), JSON.stringify({ origin }), { mode: 0o600 })
  const runtime = JSON.parse(await command(engine, ['-I', '-c', `import counterdex,hashlib,importlib.metadata,json,pathlib,sys,tomllib
assert sys.version_info[:2] == (3,11), 'Counterdex acceptance requires CPython 3.11'
installed=pathlib.Path(counterdex.__file__).parent
source=pathlib.Path(sys.argv[1])
def digests(path):
 return {str(p.relative_to(path)):hashlib.sha256(p.read_bytes()).hexdigest() for p in path.rglob('*.py')}
assert digests(installed)==digests(source/'counterdex'), 'Installed Counterdex differs from this candidate source'
version=tomllib.loads((source/'pyproject.toml').read_text())['project']['version']
assert importlib.metadata.version('counterdex')==version
print(json.dumps({'python':sys.version.split()[0],'counterdex':version,'source_matches':True}))`, join(root, 'packages/groundwork_adapter')]))
  check('qualified-cpython311-and-installed-counterdex-match-actual-candidate-source')
  await command(python, ['scripts/dev/launcher.py', 'start']); launched = true
  const capabilities = await directOwner('/capabilities')
  assert.equal(capabilities.gemini.dispatch_enabled, false)
  assert.equal(capabilities.deepagents.execution_mode, 'controlled'); assert.equal(capabilities.deepagents.dispatch_enabled, true)
  const untouched = counters()
  assert.ok(Object.values(scientificCounters(untouched)).every(value => value === 0))
  const localBrowser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || chromium.executablePath(), args: ['--no-sandbox', '--disable-background-networking'] })
  browsers.push(localBrowser)
  // Inspect the server's first paint with application JavaScript disabled: even
  // opening the native disclosure before bootstrap must never expose token entry.
  const firstPaintContext = await localBrowser.newContext({ javaScriptEnabled: false })
  const firstPaint = await trackedPage(firstPaintContext, base)
  await firstPaint.goto(base, { waitUntil: 'networkidle' })
  const connectionPanel = firstPaint.locator('#connection-panel')
  if (await connectionPanel.count() && await connectionPanel.getAttribute('open') === null) {
    await connectionPanel.locator('summary').click()
  }
  assert.equal(await firstPaint.locator('#connect-form').isVisible(), false)
  assert.equal(await firstPaint.locator('#bearer').isVisible(), false)
  if (await connectionPanel.count()) assert.doesNotMatch(await connectionPanel.innerText(), /Paste the researcher access token/)
  assert.deepEqual(counters(), untouched)
  await firstPaint.screenshot({ path: join(output, 'first-paint-no-token-entry.png'), fullPage: true })
  await firstPaint.close(); await firstPaintContext.close()
  check('server-first-paint-never-exposes-token-entry-before-application-javascript')
  const localContext = await localBrowser.newContext({ acceptDownloads: true })
  const local = await trackedPage(localContext, base), localSecond = await trackedPage(localContext, base)
  const [localSession, simultaneousLocalSession] = await Promise.all([readyPage(local, base), readyPage(localSecond, base)])
  assert.equal(localSession.workspace_id, simultaneousLocalSession.workspace_id)
  const localCookie = (await localContext.cookies(base)).find(cookie => cookie.name === 'bean_local_session')
  assert.ok(localCookie); assert.equal(localCookie.httpOnly, true); assert.equal(localCookie.secure, false); assert.equal(localCookie.sameSite, 'Strict')
  secretValues.push(localCookie.value)
  await local.getByLabel('Row 1, concentration', { exact: true }).fill('4.81')
  assert.equal(await local.getByLabel('Row 1, concentration', { exact: true }).inputValue(), '4.81')
  check('fresh-local-launcher-opens-editable-study-without-token-entry')
  await local.reload({ waitUntil: 'networkidle' })
  await local.waitForFunction(workspace => document.querySelector('#workspace-select')?.value === workspace, localSession.workspace_id)
  assert.equal((await readyPage(localSecond, base)).workspace_id, localSession.workspace_id)
  assert.equal(counters().browser_sessions, 1)
  await assertHiddenSecrets(local)
  check('local-http-cookie-reload-and-second-tab-preserve-one-private-workspace')

  const publicClient = await publicBrowser()
  const alice = await publicClient.newContext({ ignoreHTTPSErrors: true, acceptDownloads: true })
  const bob = await publicClient.newContext({ ignoreHTTPSErrors: true, acceptDownloads: true })
  const pageA = await trackedPage(alice, origin), pageB = await trackedPage(bob, origin)
  const sessionA = await readyPage(pageA, origin), sessionB = await readyPage(pageB, origin)
  const budgetBefore = await ownApi(pageA, `/workspaces/${sessionA.workspace_id}/provider-budget`)
  assert.notEqual(sessionA.workspace_id, sessionB.workspace_id); assert.notEqual(sessionA.workspace_id, localSession.workspace_id)
  for (const context of [alice, bob]) {
    const cookie = (await context.cookies(origin)).find(item => item.name === '__Host-bean_session')
    assert.ok(cookie); assert.equal(cookie.secure, true); assert.equal(cookie.httpOnly, true); assert.equal(cookie.sameSite, 'Strict')
    assert.equal(cookie.domain, hostname); assert.equal(cookie.path, '/'); secretValues.push(cookie.value)
  }
  await pageA.reload({ waitUntil: 'networkidle' })
  const secondA = await trackedPage(alice, origin)
  assert.equal((await readyPage(secondA, origin)).workspace_id, sessionA.workspace_id)
  for (let round = 0; round < 3; round++) {
    for (const [page, session] of [[local, localSession], [pageA, sessionA], [pageB, sessionB]]) {
      assert.deepEqual((await ownApi(page, '/workspaces')).map(item => item.id), [session.workspace_id])
      await ownApi(page, `/workspaces/${session.workspace_id}/research-sessions`)
      await ownApi(page, `/workspaces/${session.workspace_id}/provider-attempts`)
      await page.evaluate(() => { location.hash = location.hash === '#inputs' ? 'investigations' : 'inputs' })
    }
  }
  assert.equal(counters().browser_sessions, 3)
  assert.deepEqual(scientificCounters(counters()), scientificCounters(untouched))
  assert.deepEqual(await ownApi(pageA, `/workspaces/${sessionA.workspace_id}/provider-budget`), budgetBefore)
  await assertHiddenSecrets(pageA); await assertHiddenSecrets(pageB)
  check('two-https-visitors-private-continuity-and-zero-provider-or-science-bootstrap-poll-navigation')

  // Interrupt only this test's bootstrap GET, leaving the real services and stored identity intact.
  currentPage = localSecond
  let failedBootstraps = 0
  await localSecond.route('**/shared-session/current', route => { failedBootstraps++; return route.fulfill({ status: 503,
    contentType: 'application/json', body: JSON.stringify({ error: { code: 'temporarily_unavailable', message: 'Synthetic temporary startup delay' } }) }) })
  const beforeRecovery = counters()
  await localSecond.reload({ waitUntil: 'networkidle' })
  await localSecond.locator('#connection-retry').waitFor({ state: 'visible', timeout: 15000 })
  assert.ok(failedBootstraps >= 1 && failedBootstraps <= 3)
  await sleep(1200)
  const settledRequests = failedBootstraps
  await sleep(1200)
  assert.equal(failedBootstraps, settledRequests, 'Failed bootstrap must stop retrying at its bounded limit')
  assert.deepEqual(counters(), beforeRecovery)
  assert.equal(await localSecond.locator('#bearer').isVisible(), false)
  await localSecond.evaluate(() => scrollTo(0, 0))
  await localSecond.screenshot({ path: join(output, 'recoverable-startup-delay.png'), fullPage: true })
  await localSecond.unroute('**/shared-session/current')
  await localSecond.locator('#connection-retry').click()
  await localSecond.waitForFunction(workspace => document.querySelector('#workspace-select')?.value === workspace, localSession.workspace_id)
  assert.deepEqual(counters(), beforeRecovery)
  check('bounded-visible-bootstrap-recovery-preserves-identity-and-all-operation-ledgers')

  // Real server stop/start, scoped to the test's own launcher metadata and ports.
  await command(python, ['scripts/dev/launcher.py', 'stop']); launched = false
  assert.equal((await browserRequest(pageA, '/shared-session/current')).status, 503,
    'Stopping the actual launcher must invalidate its published shared origin')
  await command(python, ['scripts/dev/launcher.py', 'start']); launched = true
  // The launcher deliberately removes its publication on stop. Re-establish
  // only this harness's existing loopback TLS mapping, never a public tunnel.
  await writeFile(join(scratch, 'share-origin.json'), JSON.stringify({ origin }), { mode: 0o600 })
  for (const [page, session] of [[local, localSession], [pageA, sessionA], [pageB, sessionB]]) {
    assert.equal((await ownApi(page, '/shared-session/current')).workspace_id, session.workspace_id)
  }
  assert.deepEqual(counters(), beforeRecovery)
  assert.deepEqual(await ownApi(pageA, `/workspaces/${sessionA.workspace_id}/provider-budget`), budgetBefore)
  check('actual-launcher-restart-preserves-identities-without-quota-or-operation-reset')

  const uncertainContext = await publicClient.newContext({ ignoreHTTPSErrors: true })
  const uncertain = await trackedPage(uncertainContext, origin)
  let issuedButLost = 0
  await uncertain.route('**/shared-session', async route => {
    issuedButLost++
    const response = await route.fetch()
    assert.equal(response.status(), 200)
    return route.abort('failed') // The real issuance completed; only its browser acknowledgement is lost.
  })
  const beforeLost = counters()
  await uncertain.goto(origin, { waitUntil: 'networkidle' })
  await uncertain.locator('#connection-retry').waitFor({ state: 'visible', timeout: 15000 })
  await sleep(1200)
  assert.equal(issuedButLost, 1)
  assert.equal(counters().browser_sessions, beforeLost.browser_sessions + 1)
  assert.deepEqual(scientificCounters(counters()), scientificCounters(beforeLost))
  await uncertain.unroute('**/shared-session')
  await Promise.all([
    uncertain.waitForResponse(response => new URL(response.url()).pathname === prefix + '/shared-session/current'),
    uncertain.locator('#connection-retry').click(),
  ])
  await uncertain.waitForFunction(() => Boolean(document.querySelector('#workspace-select')?.value)
    || (document.querySelector('#connection-start-new') && !document.querySelector('#connection-start-new').hidden))
  await uncertain.reload({ waitUntil: 'networkidle' })
  assert.equal(counters().browser_sessions, beforeLost.browser_sessions + 1,
    'Checking an uncertain acknowledgement must never issue a replacement identity')
  await uncertain.close(); await uncertainContext.close()
  check('lost-issuance-acknowledgement-never-auto-reissues-or-floods-identities')

  // Emulate a browser refusing the server's cookie, using only this fresh context.
  const blockedCookieContext = await publicClient.newContext({ ignoreHTTPSErrors: true })
  const blockedCookiePage = await trackedPage(blockedCookieContext, origin)
  let blockedCookieIssuances = 0
  await blockedCookiePage.route('**/shared-session', async route => {
    blockedCookieIssuances++
    const response = await route.fetch()
    assert.equal(response.status(), 200)
    await blockedCookieContext.clearCookies()
    const headers = Object.fromEntries(Object.entries(response.headers()).filter(([name]) => name.toLowerCase() !== 'set-cookie'))
    return route.fulfill({ status: response.status(), headers, body: await response.body() })
  })
  const beforeBlockedCookies = counters()
  await blockedCookiePage.goto(origin, { waitUntil: 'networkidle' })
  await blockedCookiePage.locator('#connection-start-new').waitFor({ state: 'visible', timeout: 15000 })
  assert.equal(blockedCookieIssuances, 1)
  assert.equal((await blockedCookieContext.cookies(origin)).some(cookie => cookie.name === '__Host-bean_session'), false)
  assert.equal(await blockedCookiePage.locator('#workspace-select').inputValue(), '')
  await Promise.all([
    blockedCookiePage.waitForResponse(response => new URL(response.url()).pathname === prefix + '/shared-session/current'),
    blockedCookiePage.locator('#connection-retry').click(),
  ])
  await blockedCookiePage.locator('#connection-start-new').waitFor({ state: 'visible' })
  await blockedCookiePage.reload({ waitUntil: 'networkidle' })
  await blockedCookiePage.locator('#connection-start-new').waitFor({ state: 'visible' })
  assert.equal(blockedCookieIssuances, 1)
  const afterBlockedCookies = counters()
  assert.equal(afterBlockedCookies.browser_sessions, beforeBlockedCookies.browser_sessions + 1)
  assert.deepEqual(scientificCounters(afterBlockedCookies), scientificCounters(beforeBlockedCookies))
  await blockedCookiePage.close(); await blockedCookieContext.close(); currentPage = local
  check('blocked-cookie-has-one-issuance-and-no-new-identities-on-retry-or-reload')

  const owner = await directOwner('/workspaces', { name: 'Synthetic operator-only fixture' })
  const forgedHeaders = { Authorization: `Bearer ${ownerToken}`, 'X-Owner-Id': 'owner',
    'X-Bean-Shared-Gateway': 'DRBEAN-DUMMY-forged', 'X-Bean-Shared-Origin': origin }
  for (const [page, session, forbidden] of [[pageA, sessionA, sessionB], [pageB, sessionB, sessionA], [local, localSession, sessionA]]) {
    assert.deepEqual((await browserRequest(page, '/workspaces', { headers: forgedHeaders })).body.map(item => item.id), [session.workspace_id])
    for (const workspace of [forbidden.workspace_id, owner.id]) {
      assert.equal((await browserRequest(page, `/workspaces/${workspace}`)).status, 404)
      assert.equal((await browserRequest(page, `/workspaces/${workspace}/datasets`, { body: {
        schema_version: 'DB-SC-1', experiment_id: 'forbidden_fixture', time_origin: 'Synthetic elapsed time',
        rows: [{ id: 'row_one', time: '0/1', concentration: '1/1', hard_allowance: '1/10', included: true }],
        change_reason: 'Synthetic cross-visitor refusal', origin: 'synthetic' }, headers: forgedHeaders })).status, 404)
    }
  }
  check('public-and-local-proxies-reject-owner-bearer-escalation-and-private-record-mutation')
  const bobSavedInput = await browserRequest(pageB, `/workspaces/${sessionB.workspace_id}/datasets`, { body: {
    schema_version: 'DB-SC-1', experiment_id: 'bob_retained_input', time_origin: 'Synthetic elapsed time',
    rows: [{ id: 'row_one', time: '1/1', concentration: '1/1', hard_allowance: '1/10', included: true }],
    change_reason: 'Retained private input; saving does not authorize a scientific operation', origin: 'synthetic' } })
  assert.equal(bobSavedInput.status, 201)
  assert.equal((await browserRequest(pageA, `/records/${bobSavedInput.body.id}`)).status, 404)
  const bobObjective = 'Retain this private question without authorizing any operation.'
  const bobResearch = await browserRequest(pageB, `/workspaces/${sessionB.workspace_id}/research-sessions`, {
    body: { objective: bobObjective, mode: 'controlled' } })
  assert.equal(bobResearch.status, 200)
  assert.equal(bobResearch.body.action, null); assert.equal(bobResearch.body.children.length, 0)
  assert.equal((await browserRequest(pageA, `/research-sessions/${bobResearch.body.id}`)).status, 404)
  await pageB.reload({ waitUntil: 'networkidle' })
  await pageB.locator('.steps').getByRole('link', { name: /^Investigate/ }).click()
  await pageB.locator('#durable-research').getByRole('button', { name: `Reopen: ${bobObjective}`, exact: true }).click()
  await pageB.locator('#durable-research').getByRole('button', { name: 'Refresh saved state', exact: true }).waitFor()
  await pageA.evaluate(() => { location.hash = 'research' })
  await pageA.locator('#research-files').setInputFiles(join(root, 'tests/integration/fixtures/general/penguins-excerpt.csv'))
  await pageA.locator('#general-assets article').first().waitFor()
  const source = (await ownApi(pageA, `/workspaces/${sessionA.workspace_id}/research-assets`))[0]
  assert.equal((await browserRequest(pageB, `/research-assets/${source.id}`)).status, 404)
  assert.equal((await browserRequest(pageB, `/research-assets/${source.id}/content`)).status, 404)
  check('actual-uploaded-source-bytes-and-identifiers-remain-private')
  await pageA.evaluate(() => { location.hash = 'inputs' }); currentPage = pageA
  await scientificLoop(pageA, pageB, sessionA.workspace_id)

  // Rotation and expiry operate on this test's synthetic sessions only.
  const oldCookie = (await alice.cookies(origin)).find(item => item.name === '__Host-bean_session')
  const rotated = await browserRequest(pageA, '/shared-session/rotate', { body: {} })
  assert.equal(rotated.status, 200); assert.equal(rotated.body.workspace_id, sessionA.workspace_id)
  const newCookie = (await alice.cookies(origin)).find(item => item.name === '__Host-bean_session')
  assert.notEqual(newCookie.value, oldCookie.value); secretValues.push(newCookie.value)
  const replayContext = await publicClient.newContext({ ignoreHTTPSErrors: true })
  await replayContext.addCookies([oldCookie])
  const stale = await trackedPage(replayContext, origin), beforeStale = counters()
  await stale.goto(origin, { waitUntil: 'networkidle' })
  await stale.locator('#connection-start-new').waitFor({ state: 'visible', timeout: 15000 })
  assert.equal((await browserRequest(stale, `/workspaces/${sessionA.workspace_id}`)).status, 401)
  assert.deepEqual(counters(), beforeStale)
  assert.equal(await stale.locator('#workspace-select').inputValue(), '')
  assert.equal((await ownApi(pageA, '/shared-session')).workspace_id, sessionA.workspace_id)
  check('valid-rotation-preserves-identity-and-revoked-cookie-cannot-reopen-history')
  currentPage = pageB
  store(`import json,sqlite3,sys,time
c=sqlite3.connect(sys.argv[1]); c.execute('UPDATE browser_sessions SET expires_at=created_at+1 WHERE workspace_id=?',(sys.argv[2],)); c.commit()
assert c.execute('SELECT max(expires_at) FROM browser_sessions WHERE workspace_id=?',(sys.argv[2],)).fetchone()[0] < time.time()
print(json.dumps(True))`, [sessionB.workspace_id])
  const beforeExpired = counters()
  // An already-open child controller must notify the shared connection UI on
  // expiry; its failed read must not dispatch science or replace the identity.
  await pageB.locator('#durable-research').getByRole('button', { name: 'Refresh saved state', exact: true }).click()
  await pageB.waitForFunction(() => document.querySelector('#connection-pill')?.textContent === 'Connection needs attention')
  await pageB.locator('#connection-retry').waitFor({ state: 'visible' })
  assert.doesNotMatch(await pageB.locator('#connection-status').innerText(), /^Ready/)
  assert.deepEqual(counters(), beforeExpired)
  check('in-tab-expired-child-controller-read-revokes-ready-status-without-retry-or-new-identity')
  await pageB.reload({ waitUntil: 'networkidle' })
  await pageB.locator('#connection-start-new').waitFor({ state: 'visible', timeout: 15000 })
  assert.equal((await browserRequest(pageB, `/workspaces/${sessionB.workspace_id}`)).status, 401)
  assert.deepEqual(counters(), beforeExpired)
  assert.equal(await pageB.locator('#workspace-select').inputValue(), '')
  check('expired-browser-cookie-fails-closed-without-silent-replacement-or-resume')
  const retainedOldWorkspace = store(`import json,sqlite3,sys
c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True)
print(json.dumps({'workspace':c.execute('SELECT id,name,created_at FROM workspaces WHERE id=?',(sys.argv[2],)).fetchone(),
 'membership':c.execute('SELECT workspace_id,actor_id FROM memberships WHERE workspace_id=? ORDER BY actor_id',(sys.argv[2],)).fetchall(),
 'entities':c.execute('SELECT id,digest,body FROM entities WHERE workspace_id=? ORDER BY id',(sys.argv[2],)).fetchall()}))`, [sessionB.workspace_id])
  assert.ok(retainedOldWorkspace.workspace)
  assert.ok(retainedOldWorkspace.entities.some(([id]) => id === bobSavedInput.body.id))
  assert.ok(retainedOldWorkspace.entities.some(([id]) => id === bobResearch.body.id))
  await pageB.locator('#connection-start-new').click()
  await pageB.waitForFunction(oldWorkspace => {
    const value = document.querySelector('#workspace-select')?.value
    return Boolean(value) && value !== oldWorkspace
  }, sessionB.workspace_id)
  const replacement = await ownApi(pageB, '/shared-session/current')
  assert.notEqual(replacement.workspace_id, sessionB.workspace_id)
  const afterReplacement = counters()
  assert.equal(afterReplacement.browser_sessions, beforeExpired.browser_sessions + 1)
  assert.equal(afterReplacement.workspaces, beforeExpired.workspaces + 1)
  assert.equal(afterReplacement.memberships, beforeExpired.memberships + 1)
  assert.deepEqual(scientificCounters(afterReplacement), scientificCounters(beforeExpired))
  assert.deepEqual((await ownApi(pageB, '/workspaces')).map(workspace => workspace.id), [replacement.workspace_id])
  assert.equal((await browserRequest(pageB, `/workspaces/${sessionB.workspace_id}`)).status, 404)
  assert.equal((await browserRequest(pageB, `/records/${bobSavedInput.body.id}`)).status, 404)
  assert.equal((await browserRequest(pageB, `/research-sessions/${bobResearch.body.id}`)).status, 404)
  assert.equal((await browserRequest(pageB, `/workspaces/${sessionA.workspace_id}`)).status, 404)
  assert.deepEqual(store(`import json,sqlite3,sys
c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True)
print(json.dumps({'workspace':c.execute('SELECT id,name,created_at FROM workspaces WHERE id=?',(sys.argv[2],)).fetchone(),
 'membership':c.execute('SELECT workspace_id,actor_id FROM memberships WHERE workspace_id=? ORDER BY actor_id',(sys.argv[2],)).fetchall(),
 'entities':c.execute('SELECT id,digest,body FROM entities WHERE workspace_id=? ORDER BY id',(sys.argv[2],)).fetchall()}))`, [sessionB.workspace_id]), retainedOldWorkspace)
  assert.deepEqual(await ownApi(pageB, `/workspaces/${replacement.workspace_id}/provider-budget`), budgetBefore)
  check('explicit-expired-session-replacement-creates-one-private-workspace-without-transferring-history-or-resetting-ledgers')
  await assertHiddenSecrets(pageA); await assertHiddenSecrets(local)
  assert.deepEqual(external, []); assert.deepEqual(pageErrors, [])
  assert.equal(counters().provider_attempts, 0)
  const guard = await readFile(join(scratch, 'egress.jsonl'), 'utf8').catch(() => '')
  assert.doesNotMatch(guard, /"(?:egress_blocked|provider_client_blocked|credential_access)"/)
  check('zero-provider-attempts-no-browser-egress-and-no-client-javascript-errors')
  const receipt = { status: 'passed', candidate_sha: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(),
    working_tree_status: execFileSync('git', ['status', '--short'], { cwd: root, encoding: 'utf8' }).trim(),
    checks, runtime, provider_calls: 0, scientific_children: 2, denied_browser_background_connections: deniedProxyConnections,
    scope: 'Actual local launcher and isolated HTTPS gateway browser acceptance; no public tunnel or live provider qualification.', output }
  await writeFile(join(output, 'receipt.json'), JSON.stringify(receipt, null, 2)); console.log(JSON.stringify(receipt, null, 2))
} catch (error) {
  await currentPage?.evaluate(() => scrollTo(0, 0)).catch(() => {})
  await currentPage?.screenshot({ path: join(output, 'failure.png'), fullPage: true }).catch(() => {})
  const renderedErrors = await currentPage?.locator('.errors').allTextContents().catch(() => [])
  const failure = { status: 'failed', checks, error: redact(error.stack || error), renderedErrors, output }
  await writeFile(join(output, 'failure.json'), JSON.stringify(failure, null, 2)); console.error(JSON.stringify(failure, null, 2)); process.exitCode = 1
} finally {
  await writeFile(join(output, 'browser-console.json'), JSON.stringify({ pageErrors, messages: browserConsole }, null, 2)).catch(() => {})
  for (const browser of browsers.reverse()) await browser.close().catch(() => {})
  for (const socket of sockets) socket.destroy()
  for (const server of servers.reverse()) { server.closeAllConnections?.(); if (server.listening) await new Promise(yes => server.close(yes)) }
  if (launched) await command(python, ['scripts/dev/launcher.py', 'stop']).catch(error => { console.error(redact(error.message)); process.exitCode = 1 })
  await rm(scratch, { recursive: true, force: true })
}
