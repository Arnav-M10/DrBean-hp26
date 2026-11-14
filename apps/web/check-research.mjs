// Actual launcher -> browser -> canonical review -> Deep Agents -> real Counterdex.
// Synthetic measurements only; no fixture candidates, injected model or provider calls.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import { createRequire } from 'node:module'
import { createServer } from 'node:net'
import { mkdtemp, mkdir, readFile, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || 'playwright')
const root = fileURLToPath(new URL('../../', import.meta.url))
const scratch = await mkdtemp(join(tmpdir(), 'drbean-agent-browser-'))
const output = resolve(process.env.BEAN_RESEARCH_BROWSER_EVIDENCE_DIR || join(root, 'var/test-evidence/research-browser'))
const python = resolve(root, '.venv/bin/python'), engine = resolve(root, '.venv-engine/bin/python')
async function freePort() {
  const server = createServer()
  await new Promise((yes, no) => { server.once('error', no); server.listen(0, '127.0.0.1', yes) })
  const port = server.address().port
  await new Promise(yes => server.close(yes))
  return port
}
const apiPort = await freePort(), webPort = await freePort(), base = `http://127.0.0.1:${webPort}`
const env = { PATH: process.env.PATH, LANG: 'C.UTF-8', DRBEAN_VAR_DIR: scratch,
  BEAN_AUTH_FILE: join(scratch, 'auth.json'),
  BEAN_DEV_API_PORT: String(apiPort), BEAN_DEV_WEB_PORT: String(webPort), BEAN_RESEARCH_MODE: 'controlled',
  BEAN_AI_MODE: 'placeholder', PYTHONPATH: join(root, 'apps/api') + ':' + join(root, 'evaluation/drbean_eval/guard'),
  DRBEAN_EGRESS_GUARD_LOG: join(scratch, 'egress.jsonl'), LANGSMITH_TRACING: 'false' }
let browser, browserContext, launched = false, page
const checks = [], external = [], errors = []
const redact = value => String(value)
async function command(executable, args, timeout = 45000) {
  const child = spawn(executable, args, { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] })
  let text = '', timer
  for (const stream of [child.stdout, child.stderr]) stream.on('data', bytes => { text = (text + bytes).slice(-1048576) })
  const result = await new Promise((yes, no) => {
    child.once('error', no); child.once('exit', code => yes(code))
    timer = setTimeout(() => { child.kill('SIGTERM'); no(new Error('Owned launcher command timed out')) }, timeout)
  }).finally(() => clearTimeout(timer))
  assert.equal(result, 0, redact(text))
  return text
}
async function api(path) {
  assert.ok(browserContext || path === '/capabilities', 'Private API evidence requires the actual browser context')
  const response = browserContext ? await browserContext.request.get(`${base}/api/bean/v1${path}`)
    : await fetch(`${base}/api/bean/v1${path}`, { signal: AbortSignal.timeout(15000) })
  const status = browserContext ? response.status() : response.status
  assert.equal(status, 200, status === 200 ? '' : await response.text())
  return response.json()
}
const check = name => checks.push(name)
try {
  await mkdir(output, { recursive: true })
  await command(python, ['-m', 'bean_api.bootstrap'], 10000)
  await command(python, ['scripts/dev/launcher.py', 'start'])
  launched = true
  const capabilities = await api('/capabilities')
  assert.equal(capabilities.deepagents.execution_mode, 'controlled', JSON.stringify(capabilities.deepagents))
  assert.equal(capabilities.deepagents.dispatch_enabled, true, JSON.stringify(capabilities.deepagents))
  assert.equal(capabilities.gemini.dispatch_enabled, false)
  check('actual-launcher-api-worker-and-controlled-policy-ready')
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || chromium.executablePath(), args: ['--no-sandbox'] })
  const context = await browser.newContext({ acceptDownloads: true })
  browserContext = context
  page = await context.newPage()
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/*', route => {
    const url = route.request().url()
    if (!url.startsWith(base + '/') && !/^(blob|data):/.test(url)) { external.push(url); return route.abort() }
    return route.continue()
  })
  await page.goto(base + '#inputs')
  await page.waitForFunction(() => document.querySelector('#workspace-select').value !== '')
  const workspace = await page.locator('#workspace-select').inputValue()
  assert.equal(await page.locator('#bearer').isVisible(), false)
  const connected = await api('/shared-session/current')
  assert.equal(connected.workspace_id, workspace)
  assert.equal(connected.credentials, 'server_managed')
  check('automatic-private-browser-session-without-token-entry')
  // Exercise the ordinary file input, not the optional example button.
  const file = join(scratch, 'reviewed-synthetic-readings.csv')
  await writeFile(file, 'time,concentration,epsilon\n0.25,4.80,0.50\n0.5,7.20,0.50\n1,8.00,0.50\n2,6.80,0.50\n4,5.70,0.50\n')
  await page.locator('#csv-file').setInputFiles(file)
  await page.getByRole('button', { name: 'Use these rows', exact: true }).click()
  await page.getByLabel('Row 1, concentration', { exact: true }).fill('4.81')
  await page.click('#measurements button[type=submit]')
  for (const [id, value] of Object.entries({ 'experiment-id': 'agent-browser-synthetic', 'time-origin': 'Explicit synthetic elapsed hours from t=0',
    aMin: '0.001', aMax: '30', keMin: '0.015', keMax: '0.35', kaMin: '0.4', kaMax: '8', targetMin: '0.10', targetMax: '0.17',
    allowanceOrigin: 'Explicit synthetic hard bound of0.50mg/L, not an SD or instrument claim', goal: 'Does this reviewed target range survive these corrected measurements, and what checked pair measurement could distinguish the computed candidates?' })) await page.fill(`#${id}`, value)
  await page.selectOption('#dataset-origin', 'synthetic')
  await page.click('#question-form button[type=submit]')
  await page.getByRole('link', { name: 'Research with the assistant', exact: true }).click()
  const panel = page.locator('#durable-research')
  await panel.getByText('Feasible next-measurement constraints (optional until design)', { exact: true }).click()
  for (const [name, value] of Object.entries({ times: '8, 6', allowance: '0.2', horizon: '8', allowanceReason: 'Explicit synthetic prospective hard bound; not a claim about an instrument' })) await panel.locator(`[name="${name}"]`).fill(value)
  await panel.getByLabel('I reviewed the exact measurement values, units, time origin, hard allowances, parameter bounds and question assumptions.', { exact: true }).check()
  await panel.getByRole('button', { name: 'Save reviewed inputs and research question', exact: true }).click()
  await panel.getByRole('button', { name: 'Advance research plan', exact: true }).waitFor()
  let session = (await api(`/workspaces/${workspace}/research-sessions`)).items[0]
  assert.equal(session.children.length, 0)
  assert.equal(session.action, null)
  assert.equal(session.reviewed_context.dataset.body.rows[0].concentration, '481/100')
  check('ordinary-file-correction-question-and-human-input-review-bind-exact-inputs')
  await panel.getByRole('button', { name: 'Advance research plan', exact: true }).click()
  await panel.getByRole('heading', { name: 'Review the investigation operation', exact: true }).waitFor({ timeout: 30000 })
  session = await api(`/research-sessions/${session.id}`)
  assert.equal(session.state, 'waiting_review')
  assert.ok(session.plan.body.steps.length)
  assert.equal(session.children.length, 0)
  const approve = panel.getByRole('button', { name: 'Approve exact operation and continue', exact: true })
  assert.equal(await approve.isDisabled(), true)
  check('real-maintained-plan-and-canonical-interrupt-do-not-authorize-a-child')
  await panel.getByLabel('I approve only this frozen scientific scope and its limits.', { exact: true }).check()
  await approve.click()
  await panel.getByRole('button', { name: 'Plan next step for separate review', exact: true }).waitFor({ timeout: 140000 })
  session = await api(`/research-sessions/${session.id}`)
  assert.equal(session.state, 'completed')
  assert.equal(session.children.length, 1)
  assert.equal(session.reports.length, 1)
  await panel.getByRole('button', { name: 'Plan next step for separate review', exact: true }).click()
  await panel.getByRole('heading', { name: 'Review the separate pair-design operation', exact: true }).waitFor({ timeout: 140000 })
  session = await api(`/research-sessions/${session.id}`)
  assert.equal(session.children.length, 1)
  assert.equal(session.children[0].state, 'completed')
  const baseline = await api(`/records/${session.children[0].scenarios[0].result_id}`)
  assert.equal(baseline.body.result.problem_id, session.problem_id)
  assert.equal(baseline.body.result.expected_binding, 'matches')
  const events = (await api(`/research-sessions/${session.id}/events?after=-1`)).items
  assert.ok(events.some(event => event.event_type === 'evidence_observed' && event.reference_ids.includes(baseline.id)))
  assert.deepEqual(session.pending_review.body.request.candidate_ids, baseline.body.result.candidates.map(candidate => candidate.id))
  assert.equal(await approve.isDisabled(), true)
  check('approved-real-baseline-read-by-agent-leads-to-separate-bound-pair-design-review')
  await panel.getByLabel('I approve only this frozen scientific scope and its limits.', { exact: true }).check()
  await approve.click()
  await page.waitForFunction(() => document.querySelector('#durable-research').textContent.includes('State: completed'), null, { timeout: 140000 })
  session = await api(`/research-sessions/${session.id}`)
  assert.equal(session.children.length, 2)
  assert.ok(session.children.every(child => child.state === 'completed'))
  assert.equal(session.reports.length, 2)
  check('separate-design-approval-computes-design-and-accepts-evidence-bound-report')
  const navigate = async name => page.locator('.steps').getByRole('link', { name }).click()
  await navigate(/^Next measurement/)
  const [download] = await Promise.all([page.waitForEvent('download'), page.locator('#research-report').getByRole('button', { name: 'Download research report snapshot', exact: true }).last().click()])
  await download.saveAs(join(output, 'report.json'))
  const report = JSON.parse(await readFile(join(output, 'report.json'), 'utf8')).body
  assert.equal(report.report_profile, 'research-report.v2')
  assert.equal(report.evidence.length, 2)
  assert.equal(report.native_evidence.length, 2)
  const evidence = page.locator('#research-results, #research-next')
  const nativeButtons = evidence.getByRole('button', { name: 'Download native evidence', exact: true })
  const anchorButtons = evidence.getByRole('button', { name: 'Download independent replay anchors', exact: true })
  for (let index = 0; index < report.native_evidence.length; index++) {
    const entry = report.native_evidence[index]
    const record = report.evidence.find(item => item.id === entry.evidence_id)
    await navigate(record.kind === 'suggestion' ? /^Next measurement/ : /^Result/)
    const [native] = await Promise.all([page.waitForEvent('download'), nativeButtons.nth(index).click()])
    const [anchor] = await Promise.all([page.waitForEvent('download'), anchorButtons.nth(index).click()])
    const nativePath = join(output, entry.native_filename), anchorPath = join(output, entry.anchor_filename)
    await native.saveAs(nativePath); await anchor.saveAs(anchorPath)
    assert.equal(createHash('sha256').update(await readFile(nativePath)).digest('hex'), entry.artifact.sha256)
    const replay = JSON.parse(await command(engine, ['-I', '-m', 'counterdex', 'replay-native', nativePath, '--anchors', anchorPath]))
    assert.equal(replay.integrity, 'passed'); assert.equal(replay.expected_binding, 'matches')
    const result = record.body.result || record.body
    assert.equal(replay.replay, result.replay)
    if (record.kind === 'suggestion') assert.equal(replay.fresh_checked.tier, result.design_tier)
    else assert.equal(replay.outcome.scientific_outcome, result.scientific_outcome)
    await writeFile(join(output, `${entry.artifact.id}.replay.json`), JSON.stringify(replay, null, 2))
  }
  check('actual-browser-native-downloads-and-fresh-installed-engine-replay-for-both-operations')
  assert.deepEqual(errors, []); assert.deepEqual(external, [])
  const guard = await readFile(join(scratch, 'egress.jsonl'), 'utf8').catch(() => '')
  assert.doesNotMatch(guard, /"(?:egress_blocked|provider_client_blocked|credential_access)"/)
  const attempts = await api(`/workspaces/${workspace}/provider-attempts`)
  assert.equal((attempts.items || attempts).length, 0)
  check('zero-provider-attempts-and-no-browser-or-api-egress')
  const receipt = { status: 'passed', checks, supported: ['investigation', 'checked_pair_design'],
    omissions: ['observation_ingestion', 'design_amendment', 'restart_qualification', 'live_provider_qualification'],
    provider_calls: 0, scientific_children: 2 }
  await writeFile(join(output, 'receipt.json'), JSON.stringify(receipt, null, 2))
  console.log(JSON.stringify(receipt, null, 2))
} catch (error) {
  if (page) { await page.screenshot({ path: join(output, 'failure.png'), fullPage: true }).catch(() => {}) }
  await writeFile(join(output, 'failure.json'), JSON.stringify({ error: redact(error.message), checks }, null, 2))
  throw error
} finally {
  await browser?.close()
  if (launched) await command(python, ['scripts/dev/launcher.py', 'stop']).catch(error => { console.error(redact(error.message)); process.exitCode = 1 })
  await rm(scratch, { recursive: true, force: true })
}
