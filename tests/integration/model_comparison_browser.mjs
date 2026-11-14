// Actual Chromium -> private same-origin proxy -> API -> numerical subprocess.
// This qualifies the connected transport, not the teammate's unfinished UI.
// BEAN_TEST_PYTHON=/path/to/backend/python PLAYWRIGHT_MODULE=/path/to/playwright \
//   node tests/integration/model_comparison_browser.mjs --results /tmp/comparison-results
import assert from 'node:assert/strict'
import { spawn, execFileSync } from 'node:child_process'
import { once } from 'node:events'
import { randomBytes, createHash } from 'node:crypto'
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { createServer } from 'node:net'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'

const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || 'playwright')
const root = fileURLToPath(new URL('../../', import.meta.url))
const python = process.env.BEAN_TEST_PYTHON || resolve(root, '.venv/bin/python')
const args = process.argv.slice(2)
assert.ok(args.length === 0 || (args.length === 2 && args[0] === '--results'), 'Use only --results <directory>')
const output = args.length ? resolve(args[1]) : await mkdtemp(join(tmpdir(), 'bean-comparison-evidence-'))
await mkdir(output, { recursive: true })
const scratch = await mkdtemp(join(tmpdir(), 'bean-comparison-browser-'))
const gatewaySecret = 'DRBEAN-DUMMY-' + randomBytes(24).toString('base64url').slice(0, 30)
const checks = [], external = [], pageErrors = [], children = []
const check = name => { checks.push(name); console.log(JSON.stringify({ check: name, status: 'passed' })) }
const pause = ms => new Promise(resolve => setTimeout(resolve, ms))
const gatewayFile = join(scratch, 'local-gateway.json'), database = join(scratch, 'bean.sqlite3')
const guardLog = join(scratch, 'egress.jsonl')
const safeEnv = { PATH: process.env.PATH || '/usr/bin:/bin', LANG: 'C.UTF-8', TMPDIR: scratch }
let browser, evidence, failure

async function freePort() {
  const server = createServer()
  await new Promise((yes, no) => { server.once('error', no); server.listen(0, '127.0.0.1', yes) })
  const port = server.address().port
  await new Promise(yes => server.close(yes))
  assert.ok(![8000, 4173, 4174].includes(port), 'Do not use protected application ports')
  return port
}
const apiPort = await freePort()
let webPort = await freePort()
while (webPort === apiPort) webPort = await freePort()
const base = `http://127.0.0.1:${webPort}`
const env = { ...safeEnv, PYTHONDONTWRITEBYTECODE: '1', PYTHONNOUSERSITE: '1',
  PYTHONPATH: join(root, 'evaluation/drbean_eval/guard') + ':' + join(root, 'apps/api'),
  DRBEAN_EGRESS_GUARD_LOG: guardLog, BEAN_AUTH_FILE: join(scratch, 'absent-auth.json'),
  BEAN_DATABASE_PATH: database, BEAN_BLOB_DIR: join(scratch, 'sources'), BEAN_ARTIFACT_DIR: join(scratch, 'artifacts'),
  BEAN_SCIENCE_ADAPTER: 'unavailable', BEAN_AI_MODE: 'placeholder', BEAN_RESEARCH_MODE: 'disabled',
  BEAN_SOURCE_INTAKE_MODE: 'disabled', BEAN_LOCAL_GATEWAY_FILE: gatewayFile, BEAN_LOCAL_BROWSER_ORIGIN: base,
  BEAN_ALLOWED_ORIGINS: base, BEAN_SHARE_GATEWAY_FILE: '', LANGSMITH_TRACING: 'false' }
function start(executable, arguments_, environment) {
  const child = spawn(executable, arguments_, { cwd: root, env: environment, stdio: ['ignore', 'pipe', 'pipe'] })
  child.tail = ''
  for (const stream of [child.stdout, child.stderr]) stream.on('data', bytes => { child.tail = (child.tail + bytes.toString()).slice(-16384) })
  child.on('error', error => { child.startError = error })
  children.push(child)
  return child
}
async function ready(url, child) {
  for (let attempt = 0; attempt < 150; attempt++) {
    if (child.startError) throw child.startError
    if (child.exitCode !== null) throw new Error(`Owned test process exited: ${child.tail.replaceAll(gatewaySecret, '[dummy]')}`)
    try { const response = await fetch(url, { signal: AbortSignal.timeout(1000) }); if (response.ok) return } catch { /* bounded startup read */ }
    await pause(100)
  }
  throw new Error(`Owned test service did not become ready: ${child.tail.replaceAll(gatewaySecret, '[dummy]')}`)
}
function counters() {
  const script = `import json,sqlite3,sys
c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True)
tables=['provider_attempts','jobs','approvals','browser_sessions','workspaces','operations']
r={t:c.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in tables}
r['comparison_records']=c.execute("SELECT count(*) FROM entities WHERE kind='model_comparison'").fetchone()[0]
print(json.dumps(r))`
  return JSON.parse(execFileSync(python, ['-c', script, database], { env, encoding: 'utf8' }))
}
async function pageFor(context) {
  const page = await context.newPage()
  page.on('pageerror', error => pageErrors.push(error.message))
  await page.route('**/*', route => {
    const url = route.request().url()
    if (!url.startsWith(base + '/') && !/^(blob|data):/.test(url)) { external.push(url); return route.abort() }
    return route.continue()
  })
  await page.goto(base + '/workspace-preview/', { waitUntil: 'networkidle' })
  const connected = await page.evaluate(async () => {
    const manifest = await (await fetch('./comparison-service.json')).json()
    if (manifest.schema_version !== 'DB-MODEL-COMPARISON-CONNECTION-1' || manifest.available !== true
      || manifest.module !== '/comparison-api.mjs' || manifest.mode !== 'private_session') throw new Error('Trusted manifest unavailable')
    const { connectComparison } = await import('/comparison-api.mjs')
    globalThis.comparison = await connectComparison()
    globalThis.reviewedRequest = await (await fetch('./examples/synthetic.request.json')).json()
    return { workspaceId: comparison.workspaceId, capability: comparison.capabilities }
  })
  assert.equal(connected.capability.provider_calls, 0)
  assert.equal(connected.capability.execution_mode, 'numerical_offline')
  return { page, workspace: connected.workspaceId }
}

try {
  await writeFile(gatewayFile, JSON.stringify({ version: 1, secret: gatewaySecret }), { mode: 0o600 })
  const api = start(python, ['-m', 'uvicorn', 'bean_api.main:create_app', '--factory', '--host', '127.0.0.1',
    '--port', String(apiPort), '--no-access-log', '--no-proxy-headers'], env)
  await ready(`http://127.0.0.1:${apiPort}/healthz`, api)
  const web = start(process.execPath, ['apps/web/serve.mjs', String(webPort)],
    { ...safeEnv, BEAN_LOCAL_GATEWAY_FILE: gatewayFile, BEAN_WEB_API_PORT: String(apiPort) })
  await ready(base + '/workspace-preview/comparison-service.json', web)
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || chromium.executablePath(), env: safeEnv,
    args: ['--no-sandbox', '--disable-background-networking', '--disable-quic', '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1'] })
  const first = await pageFor(await browser.newContext())
  const second = await pageFor(await browser.newContext())
  assert.notEqual(first.workspace, second.workspace)
  const before = counters()
  assert.equal(before.browser_sessions, 2)
  assert.equal(before.workspaces, 2)
  assert.equal(before.comparison_records, 0)
  check('two actual Chromium contexts receive distinct private workspaces before computation')

  const computed = await first.page.evaluate(async () => {
    globalThis.original = await comparison.submit(reviewedRequest)
    globalThis.repeated = await comparison.submit(reviewedRequest)
    const reopened = await comparison.get(original.id)
    const history = await comparison.list()
    const downloaded = await comparison.download(original)
    return { original, repeated, reopened, history,
      exported: JSON.parse(new TextDecoder().decode(downloaded.bytes)), downloadDigest: downloaded.digest,
      downloadText: new TextDecoder().decode(downloaded.bytes) }
  })
  assert.equal(computed.original.body.status, 'completed')
  assert.equal(computed.original.body.exact_verification, 'not_performed')
  assert.equal(computed.original.body.fits.length, 2)
  assert.deepEqual(computed.repeated, computed.original)
  assert.deepEqual(computed.reopened, computed.original)
  assert.deepEqual(computed.history, [computed.original])
  assert.deepEqual(computed.exported.result, computed.original)
  assert.equal(createHash('sha256').update(computed.downloadText).digest('hex'), computed.downloadDigest)
  assert.equal(counters().comparison_records, 1)
  assert.equal(counters().operations, 1)
  check('actual numerical computation persists once and repeat get list download preserve the same result')

  const changed = await first.page.evaluate(async () => {
    const request = structuredClone(reviewedRequest)
    request.review.description = 'Explicitly reviewed second synthetic case: doubled current observations.'
    for (const row of request.observations) row.current_A = String(Number(row.current_A) * 2)
    return comparison.submit(request)
  })
  assert.equal(changed.body.status, 'completed')
  assert.notEqual(changed.body.input_digest, computed.original.body.input_digest)
  assert.notDeepEqual(changed.body.fits, computed.original.body.fits)
  for (let index = 0; index < 2; index++) {
    const ratio = Number(changed.body.fits[index].parameters.density_m3) / Number(computed.original.body.fits[index].parameters.density_m3)
    assert.ok(Math.abs(ratio - 2) < 1e-10, 'Doubled observations must change the fitted density, not only a label')
  }
  assert.deepEqual(await first.page.evaluate(id => comparison.get(id), computed.original.id), computed.original)
  check('changed reviewed measurements produce a distinct computed fit while preserving original evidence')

  const denied = await second.page.evaluate(async ({ workspace, id, request }) => {
    const base = `/api/bean/v1/workspaces/${workspace}/model-comparisons`
    const responses = []
    for (const path of [base, `${base}/${id}`, `${base}/${id}/download`]) responses.push((await fetch(path, { credentials: 'same-origin' })).status)
    responses.push((await fetch(base, { method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify(request) })).status)
    return { responses, ownHistory: await comparison.list() }
  }, { workspace: first.workspace, id: computed.original.id, request: computed.original.body.request })
  assert.deepEqual(denied.responses, [404, 404, 404, 404])
  assert.deepEqual(denied.ownHistory, [])
  check('second browser cannot read download list or submit into the first private workspace')

  const unsupported = await first.page.evaluate(async () => {
    const request = structuredClone(reviewedRequest)
    request.instrument = null
    const record = await comparison.submit(request)
    const downloaded = await comparison.download(record)
    return { record, export: JSON.parse(new TextDecoder().decode(downloaded.bytes)) }
  })
  assert.equal(unsupported.record.body.status, 'unsupported')
  assert.equal(unsupported.record.body.exact_verification, 'not_performed')
  assert.deepEqual(unsupported.record.body.fits, [])
  assert.deepEqual(unsupported.export.result, unsupported.record)
  check('missing response assumptions remain unsupported after persistence and verified download')

  await first.page.reload({ waitUntil: 'networkidle' })
  const reopened = await first.page.evaluate(async id => {
    const { connectComparison } = await import('/comparison-api.mjs')
    const connection = await connectComparison()
    return { workspace: connection.workspaceId, record: await connection.get(id) }
  }, computed.original.id)
  assert.equal(reopened.workspace, first.workspace)
  assert.deepEqual(reopened.record, computed.original)
  const visible = await first.page.evaluate(() => JSON.stringify({ cookie: document.cookie, local: Object.entries(localStorage), session: Object.entries(sessionStorage), document: document.documentElement.outerHTML }))
  assert.equal(visible.includes(gatewaySecret), false)
  assert.equal(visible.includes('bean_local_session='), false)
  check('page reload reuses the private cookie and retained result without exposing the session credential')

  const after = counters()
  assert.equal(after.comparison_records, 3)
  assert.equal(after.operations, 3)
  assert.equal(after.browser_sessions, 2)
  assert.equal(after.workspaces, 2)
  for (const key of ['provider_attempts', 'jobs', 'approvals']) assert.equal(after[key], 0)
  const guard = (await readFile(guardLog, 'utf8')).trim().split('\n').filter(Boolean).map(line => JSON.parse(line))
  assert.ok(guard.some(event => event.kind === 'guard_installed'))
  assert.deepEqual(guard.filter(event => ['egress_blocked', 'provider_client_blocked', 'credential_read'].includes(event.kind)), [])
  assert.ok(guard.filter(event => event.kind === 'guard_installed').every(event => event.credential_names_present.length === 0))
  assert.deepEqual(external, [])
  assert.deepEqual(pageErrors, [])
  check('zero provider attempts jobs approvals external page requests or guarded API egress attempts')
  evidence = { status: 'passed', lane: 'actual_private_browser_transport_actual_numerical_service', checks,
    git_head: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, env: safeEnv, encoding: 'utf8' }).trim(),
    tracked_worktree_changes: execFileSync('git', ['diff', '--name-only'], { cwd: root, env: safeEnv, encoding: 'utf8' }).trim().split('\n').filter(Boolean),
    input_digest: computed.original.body.input_digest, source_digest: computed.original.body.source_digest,
    numerical_backend: computed.original.body.numerical_backend, original_result: computed.original.id,
    changed_input_digest: changed.body.input_digest, download_sha256: computed.downloadDigest, counters: after,
    exact_verification: 'not_performed', ui_acceptance: 'not_run_transport_only', provider_calls: 0,
    egress_guard_scope: 'API and evidence-query Python processes; compute child uses production credential-free environment',
    external_page_requests: 0, page_errors: 0 }
  await writeFile(join(output, 'original-export.json'), computed.downloadText)
} catch (error) {
  failure = error
  evidence = { status: 'failed', checks, reason: String(error.stack || error).replaceAll(gatewaySecret, '[dummy]'),
    ui_acceptance: 'not_run_transport_only' }
} finally {
  await browser?.close()
  for (const child of children.reverse()) {
    if (child.exitCode === null && child.pid) { child.kill('SIGTERM'); await once(child, 'exit') }
  }
  await writeFile(join(output, 'evidence.json'), JSON.stringify(evidence, null, 2) + '\n')
  await rm(scratch, { recursive: true, force: true })
}
console.log(JSON.stringify({ status: evidence.status, checks: checks.length, results: output }))
if (failure) throw failure
