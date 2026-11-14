// C (independent): the narrow LangChain demo through the ordinary browser application (DEMO-02, DEMO-06, DEMO-08).
// Launches an isolated API, worker and web server from this checkout on ephemeral ports, then drives the research
// panel with Playwright:
// - the exact pending review shown matches the server's;
// - approval needs the explicit checkbox, and the dispatched child binds the approved review;
// - the native, anchor and report downloads match the authenticated records;
// - a second private browser identity cannot see or read the session.
// Controlled coordinator only. External requests are blocked and counted; no provider credential exists.
// Usage: PLAYWRIGHT_MODULE=/abs/playwright/index.mjs BEAN_COUNTERDEX_PYTHON=/abs/python3.11 \
//        node tests/integration/langchain_demo_browser.mjs
// Exit 0: every check passed. Exit 3: NOT_AVAILABLE (research dispatch disabled). Otherwise: failure.
import { spawn } from 'node:child_process'
import { mkdtemp, readFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'node:net'
import { randomBytes, createHash } from 'node:crypto'
import { createRequire } from 'node:module'
import assert from 'node:assert/strict'

const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || 'playwright')
const root = fileURLToPath(new URL('../../', import.meta.url))
const temp = await mkdtemp(join(tmpdir(), 'drbean-c-demo-browser-'))
const owner = randomBytes(40).toString('hex'), stranger = randomBytes(40).toString('hex')
const freePort = async () => {
  const server = createServer()
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve) })
  const port = server.address().port
  await new Promise(resolve => server.close(resolve))
  return port
}
const apiPort = await freePort(), webPort = await freePort(), base = `http://127.0.0.1:${webPort}`
const env = { PATH: process.env.PATH, PYTHONPATH: join(root, 'apps/api'), BEAN_AI_MODE: 'placeholder',
  BEAN_DATABASE_PATH: join(temp, 'test.sqlite'), BEAN_BLOB_DIR: join(temp, 'sources'), BEAN_ARTIFACT_DIR: join(temp, 'artifacts'),
  BEAN_AUTH_TOKENS_JSON: JSON.stringify({ 'c-demo-owner': owner, 'c-demo-stranger': stranger }),
  BEAN_SCIENCE_ADAPTER: 'counterdex', BEAN_COUNTERDEX_PYTHON: process.env.BEAN_COUNTERDEX_PYTHON || 'python3.11',
  BEAN_WEB_API_PORT: String(apiPort) }
const python = process.env.BEAN_TEST_PYTHON || join(root, '.venv/bin/python')
const children = []
const start = (command, args) => {
  const child = spawn(command, args, { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] })
  child.output = ''
  for (const stream of [child.stdout, child.stderr]) stream.on('data', chunk => { child.output = (child.output + chunk).slice(-32768) })
  children.push(child); return child
}
const api = async (path, token = owner, expectOk = true) => {
  const response = await fetch(`${base}/api/bean/v1${path}`, { headers: { Authorization: `Bearer ${token}` } })
  if (expectOk) assert.ok(response.ok, `HTTP ${response.status} ${path}: ${(await response.clone().text()).slice(0, 300)}`)
  return response
}
const json = async (path, token) => (await api(path, token)).json()
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex')
const results = {}
const check = (id, condition, detail) => { results[id] = { passed: Boolean(condition), detail }; assert.ok(condition, `${id}: ${detail}`) }
let browser, exitCode = 0
try {
  const server = start(python, ['-m', 'uvicorn', 'bean_api.main:create_app', '--factory', '--host', '127.0.0.1', '--port', String(apiPort)])
  start(process.execPath, ['apps/web/serve.mjs', String(webPort)])
  let capabilities
  for (let i = 0; ; i++) {
    try { capabilities = await json('/capabilities'); break } catch (error) {
      if (i > 150 || server.exitCode !== null) throw new Error(`${error.message}\n${server.output}`)
      await new Promise(resolve => setTimeout(resolve, 100))
    }
  }
  const research = capabilities.deepagents || {}
  if (research.dispatch_enabled !== true || research.execution_mode !== 'controlled') {
    console.log(JSON.stringify({ status: 'NOT_AVAILABLE', reason: research.unavailable_reason || 'research dispatch disabled' }))
    exitCode = 3
  } else {
    start(python, ['-m', 'bean_api.worker'])
    browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || chromium.executablePath(), args: ['--no-sandbox'] })
    const external = []
    const open = async token => {
      const context = await browser.newContext({ acceptDownloads: true })
      const page = await context.newPage()
      await page.route('**/*', route => {
        const url = route.request().url()
        if (!url.startsWith(base + '/') && !/^(blob|data):/.test(url)) { external.push(url); return route.abort() }
        return route.continue()
      })
      await page.goto(base + '#inputs')
      await page.locator('#connection-panel summary').click()
      await page.fill('#bearer', token)
      await page.getByRole('button', { name: 'Connect', exact: true }).click()
      await page.waitForFunction(() => document.querySelector('#connection-status').textContent.includes('Connected'))
      return { context, page }
    }
    const { page } = await open(owner)
    await page.fill('#workspace-name', 'C narrow LangChain demo')
    await page.getByRole('button', { name: 'Create workspace', exact: true }).click()
    await page.waitForFunction(() => document.querySelector('#workspace-select').value !== '')
    const workspace = await page.locator('#workspace-select').inputValue()
    await page.click('#example')
    await page.getByRole('button', { name: 'Use these rows', exact: true }).click()
    await page.click('#measurements button[type=submit]')
    const fields = { 'experiment-id': 'c_demo_synthetic', 'time-origin': 'Elapsed hours from synthetic t=0',
      aMin: '0.001', aMax: '30', keMin: '0.015', keMax: '0.35', kaMin: '0.4', kaMax: '8',
      targetMin: '0.10', targetMax: '0.17', allowanceOrigin: 'Team-selected synthetic hard bound of 0.50 mg/L' }
    for (const [id, value] of Object.entries(fields)) await page.fill(`#${id}`, value)
    await page.selectOption('#dataset-origin', 'synthetic')
    await page.fill('#goal', 'Do these reviewed measurements admit a compatible ke outside the claimed range?')
    await page.click('#question-form button[type=submit]')
    await page.goto(base + '#research')
    const panel = page.locator('#durable-research')
    await panel.getByText('Save reviewed inputs and research question', { exact: true }).waitFor()
    await panel.getByLabel('I reviewed the exact measurement values, units, time origin, hard allowances, parameter bounds and question assumptions.').check()
    await panel.getByRole('button', { name: 'Save reviewed inputs and research question', exact: true }).click()
    await panel.getByRole('button', { name: 'Advance research plan', exact: true }).waitFor()
    const sessions = (await json(`/workspaces/${workspace}/research-sessions`)).items
    check('browser_session_saved_without_work', sessions.length === 1 && sessions[0].children.length === 0
      && sessions[0].usage.logical_turns === 0, `${sessions.length} session(s); usage ${JSON.stringify(sessions[0]?.usage)}`)
    const session = sessions[0].id
    await panel.getByRole('button', { name: 'Advance research plan', exact: true }).click()
    await panel.getByText(/Exact review: /).waitFor({ timeout: 120000 })
    const shown = (await panel.getByText(/Exact review: /).textContent()).match(/Exact review: (\S+) · digest ([0-9a-f]{64})/)
    let snapshot = await json(`/research-sessions/${session}`)
    check('browser_shows_the_exact_pending_review', shown && shown[1] === snapshot.pending_review.id
      && shown[2] === snapshot.pending_review_digest && snapshot.children.length === 0,
      `ui ${shown && shown.slice(1)}; server ${snapshot.pending_review?.id} ${snapshot.pending_review_digest}; children ${snapshot.children.length}`)
    // Without the explicit checkbox the approve control is either disabled or refuses; either way nothing changes.
    const approve = panel.getByRole('button', { name: 'Approve exact operation and continue', exact: true })
    const disabledBeforeCheckbox = await approve.isDisabled()
    if (!disabledBeforeCheckbox) { await approve.click(); await page.waitForTimeout(500) }
    const unapproved = await json(`/research-sessions/${session}`)
    check('approval_requires_the_explicit_checkbox', unapproved.state === 'waiting_review' && unapproved.children.length === 0
      && unapproved.revision === snapshot.revision,
      `approve ${disabledBeforeCheckbox ? 'disabled' : 'enabled but refused'} before the checkbox; state ${unapproved.state}, children ${unapproved.children.length}`)
    await panel.getByLabel('I approve only this frozen scientific scope and its limits.').check()
    await panel.getByRole('button', { name: 'Approve exact operation and continue', exact: true }).click()
    for (let i = 0; i < 300; i++) {
      snapshot = await json(`/research-sessions/${session}`)
      if (!['queued', 'running', 'waiting_child', 'waiting_review'].includes(snapshot.state) || (snapshot.state === 'waiting_review' && snapshot.children.length)) break
      await new Promise(resolve => setTimeout(resolve, 500))
    }
    const child = snapshot.children[0] || {}
    check('browser_approval_dispatched_exactly_the_reviewed_plan', snapshot.children.length === 1 && child.plan_id === shown[1]
      && child.state === 'completed', `state ${snapshot.state}; children ${JSON.stringify(snapshot.children.map(c => [c.plan_id, c.state]))}`)
    const run = await json(`/runs/${child.id}`)
    const evidence = await json(`/records/${run.scenarios[0].result_id}`)
    const artifact = evidence.body.result.artifacts[0]
    await page.getByRole('button', { name: 'Refresh saved state', exact: true }).first().click()
    await panel.getByRole('button', { name: 'Download native evidence', exact: true }).first().waitFor({ timeout: 60000 })
    const download = async name => {
      const pending = page.waitForEvent('download')
      await panel.getByRole('button', { name, exact: true }).first().click()
      return readFile(await (await pending).path())
    }
    const native = await download('Download native evidence')
    check('browser_native_download_matches_the_authenticated_artifact', sha256(native) === artifact.sha256
      && native.length === artifact.byte_size, `sha ${sha256(native).slice(0, 16)} vs ${artifact.sha256.slice(0, 16)}; ${native.length} vs ${artifact.byte_size} bytes`)
    const anchor = JSON.parse(await download('Download independent replay anchors'))
    check('browser_anchor_binds_the_run', anchor.run_id === child.id, `anchor run ${anchor.run_id}, child ${child.id}`)
    await panel.getByRole('button', { name: 'Download research report snapshot', exact: true }).first().waitFor({ timeout: 60000 })
    const report = (await download('Download research report snapshot')).toString('utf8')
    check('browser_report_binds_question_and_evidence', report.includes(evidence.id) && report.includes(snapshot.objective),
      `report ${report.length} bytes; evidence bound ${report.includes(evidence.id)}; question kept ${report.includes(snapshot.objective)}`)
    const { page: other } = await open(stranger)
    const options = await other.locator('#workspace-select option').allTextContents()
    const strangerView = await Promise.all([`/research-sessions/${session}`, `/records/${evidence.id}`, `/artifacts/${artifact.id}`]
      .map(async path => (await api(path, stranger, false)).status))
    check('second_private_identity_cannot_see_or_read_the_research', !options.some(text => text.includes('C narrow LangChain demo'))
      && strangerView.every(status => status === 404), `stranger sees ${options.length} workspace option(s); statuses ${strangerView}`)
    const text = await page.locator('body').innerText()
    check('no_credentials_or_external_requests', !text.includes(owner) && !text.includes(stranger) && !text.includes('DRBEAN-DUMMY')
      && external.length === 0, `external requests ${external.length}`)
    const attempts = await json(`/workspaces/${workspace}/provider-attempts`)
    const items = Array.isArray(attempts) ? attempts : (attempts.items || [])
    check('controlled_run_made_no_provider_attempt', items.length === 0 && snapshot.mode === 'controlled'
      && snapshot.usage.physical_calls === 0, `${items.length} attempt(s); mode ${snapshot.mode}`)
    console.log(JSON.stringify({ status: 'passed', session, child: child.id, evidence: evidence.id, results }, null, 1))
  }
} catch (error) {
  let visible = ''
  try { visible = browser ? (await (browser.contexts()[0]?.pages()[0]?.locator('#durable-research').innerText() ?? '')).slice(0, 1500) : '' } catch { /* diagnostics only */ }
  console.log(JSON.stringify({ status: 'failed', error: error.message.split('\n')[0], panel: visible, results }, null, 1))
  exitCode = 1
} finally {
  if (browser) await browser.close()
  for (const child of children) child.kill('SIGTERM')
}
process.exit(exitCode)
