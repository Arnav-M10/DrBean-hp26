// Real HTTP/browser workflow check. No Gemini or substitute scientific adapter.
// PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.mjs node apps/web/check-backend.mjs
import { spawn } from 'node:child_process'
import { mkdtemp, rm, readFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { randomBytes } from 'node:crypto'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
// require() honours NODE_PATH and CommonJS builds; PLAYWRIGHT_MODULE may name an explicit entry file.
const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || 'playwright')
const root = new URL('../../', import.meta.url).pathname
const temp = await mkdtemp(join(tmpdir(), 'drbean-web-'))
const token = randomBytes(40).toString('hex')
// Placeholder AI: provider credentials in the caller's shell never reach the launched backend.
const inherited = Object.fromEntries(Object.entries(process.env).filter(([name]) => !/^(GEMINI_|GOOGLE_|BEAN_GEMINI_|LANGSMITH_|LANGCHAIN_|ANTHROPIC_|OPENAI_|DATABASE_URL$)/.test(name)))
const env = { ...inherited, BEAN_AI_MODE: 'placeholder', BEAN_DATABASE_PATH: join(temp, 'test.sqlite'), BEAN_BLOB_DIR: join(temp, 'sources'), BEAN_AUTH_TOKENS_JSON: JSON.stringify({ 'web-test': token }) }
const children = []
const start = (command, args) => { const child = spawn(command, args, { cwd: root, env, stdio: 'ignore' }); children.push(child); return child }
const python = process.env.BEAN_TEST_PYTHON || resolve(root, '.venv/bin/python')
const api = async (path, body) => {
  const response = await fetch(`http://127.0.0.1:4173/api/bean/v1${path}`, { method: body ? 'POST' : 'GET',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', 'Idempotency-Key': randomBytes(16).toString('hex') }, body: body ? JSON.stringify(body) : undefined })
  assert.ok(response.ok, `HTTP ${response.status}: ${await response.clone().text()}`); return response.json()
}
let browser
try {
  start(python, ['-m', 'uvicorn', 'bean_api.main:create_app', '--factory', '--host', '127.0.0.1', '--port', '8000'])
  start(process.execPath, ['apps/web/serve.mjs'])
  for (let i = 0; ; i++) {
    try { await api('/capabilities'); break } catch (e) { if (i > 60) throw e; await new Promise(r => setTimeout(r, 100)) }
  }
  start(python, ['-m', 'bean_api.worker'])
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || chromium.executablePath(), args: ['--no-sandbox'] })
  const context = await browser.newContext({ acceptDownloads: true })
  const page = await context.newPage(), errors = []
  page.on('pageerror', e => errors.push(e.message))
  await page.goto('http://127.0.0.1:4173')
  await page.locator('#connection-panel summary').click()
  await page.fill('#bearer', token); await page.getByRole('button', { name: 'Connect', exact: true }).click()
  await page.waitForFunction(() => document.querySelector('#connection-status').textContent.includes('Connected'), null, { timeout: 5000 }).catch(async e => { console.log({ errors, error: await page.locator('#backend-error').textContent() }); throw e })
  await page.fill('#workspace-name', 'Browser API check'); await page.getByRole('button', { name: 'Create workspace', exact: true }).click()
  await page.waitForFunction(() => document.querySelector('#workspace-select').value !== '')
  await page.click('#example'); await page.getByRole('button', { name: 'Use these rows', exact: true }).click()
  await page.click('#measurements button[type=submit]')
  const fields = { 'experiment-id': 'browser_test', 'time-origin': 'Elapsed hours after synthetic dose', aMin: '0.001', aMax: '30', keMin: '0.015', keMax: '0.35', kaMin: '0.4', kaMax: '8', targetMin: '0.10', targetMax: '0.17', allowanceOrigin: 'Team-chosen synthetic hard bound' }
  for (const [id, value] of Object.entries(fields)) await page.fill(`#${id}`, value)
  await page.selectOption('#dataset-origin', 'synthetic'); await page.click('#question-form button[type=submit]')
  await page.getByRole('button', { name: 'Save inputs and prepare plan' }).click()
  await page.waitForSelector('#approve-scope')
  assert.equal(await page.getByRole('button', { name: 'Approve reviewed plan' }).isDisabled(), true)
  assert.equal(await page.getByRole('button', { name: 'Queue approved manual run' }).isDisabled(), true)
  await page.check('#approve-scope'); const receipt = page.waitForResponse(r => r.url().endsWith('/approvals')); await page.getByRole('button', { name: 'Approve reviewed plan' }).click()
  const approval = await (await receipt).json()
  await page.getByRole('button', { name: 'Plan approved', exact: true }).waitFor()
  const workspace = await page.locator('#workspace-select').inputValue()
  const [plan] = await api(`/workspaces/${workspace}/records?kind=plan`)
  const [dataset] = await api(`/workspaces/${workspace}/records?kind=dataset`)
  assert.equal(dataset.body.rows[0].original_values.time, '0.25')
  assert.equal(dataset.body.rows[0].time, '1/4')
  // Exercise backend lifecycle with its honest unsupported adapter. UI cannot dispatch this.
  const queued = await api(`/plans/${plan.id}/runs`, { approval_id: approval.id, expected_plan_digest: plan.digest })
  let run
  for (let i = 0; ; i++) {
    run = await api(`/runs/${queued.id}`)
    if (run.state === 'completed') break
    if (i > 150) throw new Error(`Worker did not finish: ${run.state}`)
    await new Promise(r => setTimeout(r, 100))
  }
  await page.getByRole('link', { name: 'Investigations', exact: true }).click()
  await page.fill('#run-id', run.id); await page.getByRole('button', { name: 'Open or refresh run' }).click()
  await page.getByText('Outcome: unsupported.', { exact: false }).waitFor()
  const [evidenceDownload] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download exact evidence record' }).click()])
  const evidence = JSON.parse(await readFile(await evidenceDownload.path(), 'utf8'))
  assert.equal(evidence.body.result.verification, 'unsupported')
  await page.getByRole('link', { name: 'Report', exact: true }).click()
  await page.getByRole('button', { name: 'Create report for selected run' }).click()
  await page.getByRole('button', { name: 'Download exact report JSON' }).waitFor()
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download exact report JSON' }).click()])
  const report = JSON.parse(await readFile(await download.path(), 'utf8'))
  assert.equal(report.body.run.id, run.id)
  assert.equal(report.body.replay, 'unsupported')
  await page.getByRole('link', { name: 'Question', exact: true }).click(); await page.fill('#keMax', '0.31')
  await page.getByRole('link', { name: 'Review', exact: true }).click()
  assert.equal(await page.locator('#approve-scope').isDisabled(), true)
  assert.ok((await page.locator('#backend-review').textContent()).includes('Draft changed'))
  await page.setViewportSize({ width: 390, height: 844 })
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
  assert.deepEqual(errors, [])
  assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0)
  assert.equal((await context.cookies()).length, 0)
  await page.click('#disconnect')
  assert.ok((await page.locator('#backend-review').textContent()).includes('Connect to the local backend'))
  const denied = await fetch('http://127.0.0.1:4173/api/bean/v1/workspaces', { headers: { Origin: 'https://external.invalid' } })
  assert.equal(denied.status, 403)
  console.log('Passed: real API plan/approval, explicit unsupported worker lifecycle, run retrieval, evidence/report bytes, stale draft, narrow layout, memory-only credentials, proxy origin rejection. No real scientific scenario or provider call qualified.')
} finally {
  await browser?.close()
  for (const child of children.reverse()) child.kill('SIGTERM')
  await Promise.all(children.map(child => new Promise(r => child.exitCode !== null ? r() : child.once('exit', r))))
  await rm(temp, { recursive: true, force: true })
}
