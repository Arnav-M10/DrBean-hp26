// Actual browser -> API -> worker -> discovery -> separately approved design -> native replay.
// No candidate fixtures, fake scientific adapter, or model-provider calls.
// PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.mjs \
// BEAN_COUNTERDEX_PYTHON=/absolute/path/to/python3.11 node apps/web/check-backend.mjs
import { spawn } from 'node:child_process'
import { mkdtemp, rm, readFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'node:net'
import { randomBytes, createHash } from 'node:crypto'
import assert from 'node:assert/strict'

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const root = fileURLToPath(new URL('../../', import.meta.url))
const temp = await mkdtemp(join(tmpdir(), 'drbean-web-baseline-'))
const token = randomBytes(40).toString('hex')
const freePort = async () => {
  const server = createServer()
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve) })
  const port = server.address().port
  await new Promise(resolve => server.close(resolve))
  return port
}
const apiPort = await freePort(), webPort = await freePort()
const base = `http://127.0.0.1:${webPort}`
const enginePython = process.env.BEAN_COUNTERDEX_PYTHON || 'python3.11'
const env = { PATH: process.env.PATH, PYTHONPATH: join(root, 'apps/api'),
  BEAN_DATABASE_PATH: join(temp, 'test.sqlite'), BEAN_BLOB_DIR: join(temp, 'sources'),
  BEAN_ARTIFACT_DIR: join(temp, 'artifacts'), BEAN_AUTH_TOKENS_JSON: JSON.stringify({ 'web-test': token }),
  BEAN_SCIENCE_ADAPTER: 'counterdex', BEAN_COUNTERDEX_PYTHON: enginePython, BEAN_WEB_API_PORT: String(apiPort) }
const children = []
const start = (command, args, childEnv = env) => {
  const child = spawn(command, args, { cwd: root, env: childEnv, stdio: ['ignore', 'pipe', 'pipe'] })
  child.output = ''; child.on('error', error => { child.launchError = error })
  for (const stream of [child.stdout, child.stderr]) stream.on('data', chunk => { child.output = (child.output + chunk).slice(-65536) })
  children.push(child); return child
}
const python = process.env.BEAN_TEST_PYTHON || resolve(root, '.venv/bin/python')
const api = async path => {
  const response = await fetch(`${base}/api/bean/v1${path}`, { headers: { Authorization: `Bearer ${token}` } })
  assert.ok(response.ok, `HTTP ${response.status}: ${await response.clone().text()}`)
  return response.json()
}
const waitForExit = child => new Promise((resolve, reject) => {
  if (child.launchError) return reject(child.launchError)
  if (child.exitCode !== null) return resolve(child.exitCode)
  child.once('error', reject); child.once('exit', resolve)
})
let browser
try {
  const server = start(python, ['-m', 'uvicorn', 'bean_api.main:create_app', '--factory', '--host', '127.0.0.1', '--port', String(apiPort)])
  const web = start(process.execPath, ['apps/web/serve.mjs', String(webPort)])
  let capabilities
  for (let i = 0; ; i++) {
    try { capabilities = await api('/capabilities'); break } catch (error) {
      if (i > 100 || server.exitCode !== null || web.exitCode !== null) throw new Error(`${error.message}\n${server.output}\n${web.output}`)
      await new Promise(resolve => setTimeout(resolve, 100))
    }
  }
  assert.equal(capabilities.science.available, true, JSON.stringify(capabilities.science))
  assert.equal(capabilities.science.baseline_discovery, true, JSON.stringify(capabilities.science))
  assert.equal(capabilities.gemini.dispatch_enabled, false)
  start(python, ['-m', 'bean_api.worker'])
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', args: ['--no-sandbox'] })
  const context = await browser.newContext({ acceptDownloads: true })
  const page = await context.newPage(), errors = [], external = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/*', route => {
    const url = route.request().url()
    if (!url.startsWith(base + '/') && !/^(blob|data):/.test(url)) { external.push(url); return route.abort() }
    return route.continue()
  })
  await page.goto(base)
  await page.locator('#connection-panel summary').click()
  await page.fill('#bearer', token)
  await page.getByRole('button', { name: 'Connect', exact: true }).click()
  await page.waitForFunction(() => document.querySelector('#connection-status').textContent.includes('Connected'))
  await page.fill('#workspace-name', 'Browser baseline computation')
  await page.getByRole('button', { name: 'Create workspace', exact: true }).click()
  await page.waitForFunction(() => document.querySelector('#workspace-select').value !== '')
  await page.click('#example')
  await page.getByRole('button', { name: 'Use these rows', exact: true }).click()
  await page.click('#measurements button[type=submit]')
  const fields = { 'experiment-id': 'browser_synthetic', 'time-origin': 'Elapsed hours from synthetic t=0',
    aMin: '0.001', aMax: '30', keMin: '0.015', keMax: '0.35', kaMin: '0.4', kaMax: '8',
    targetMin: '0.10', targetMax: '0.17', allowanceOrigin: 'Team-selected synthetic hard bound of 0.50 mg/L' }
  for (const [id, value] of Object.entries(fields)) await page.fill(`#${id}`, value)
  await page.selectOption('#dataset-origin', 'synthetic')
  await page.click('#question-form button[type=submit]')

  async function prepareApproveAndRun(expectCounterexample = true) {
    await page.getByRole('button', { name: 'Save inputs and prepare plan' }).click()
    await page.waitForSelector('#approve-scope')
    assert.equal(await page.getByRole('button', { name: 'Approve reviewed plan' }).isDisabled(), true)
    assert.equal(await page.getByRole('button', { name: 'Queue approved manual run' }).isDisabled(), true)
    assert.match(await page.locator('#backend-review').textContent(), /No witness found does not prove the claim/)
    await page.check('#approve-scope')
    await page.getByRole('button', { name: 'Approve reviewed plan' }).click()
    await page.getByRole('button', { name: 'Plan approved', exact: true }).waitFor()
    const response = page.waitForResponse(r => /\/plans\/[^/]+\/runs$/.test(r.url()) && r.request().method() === 'POST')
    await page.getByRole('button', { name: 'Queue approved manual run' }).click()
    const run = await (await response).json()
    await page.waitForFunction(id => document.querySelector('#run-id').value === id, run.id)
    await page.waitForFunction(() => {
      const text = document.querySelector('#backend-investigations').textContent
      return /execution: (failed|cancelled|interrupted)/.test(text)
        || (/execution: completed/.test(text) && text.includes('Outcome:'))
    }, null, { timeout: 125000 })
    const finished = await api(`/runs/${run.id}`)
    assert.equal(finished.state, 'completed', JSON.stringify(finished))
    const evidence = await api(`/records/${finished.scenarios[0].result_id}`)
    const result = evidence.body.result
    assert.ok(['certified_counterexample', 'no_counterexample_found', 'numerical_candidate', 'inconclusive'].includes(result.scientific_outcome))
    assert.match(await page.locator('#backend-investigations').textContent(), new RegExp(`Outcome: ${result.scientific_outcome}\\.`))
    assert.equal(result.expected_binding, 'matches')
    if (expectCounterexample) {
      assert.equal(result.scientific_outcome, 'certified_counterexample')
      assert.equal(result.verification, 'valid')
      assert.equal(result.replay, 'passed')
      assert.equal(await page.locator('[aria-label="Computed candidate parameters"] tbody tr').count() >= 1, true)
    }
    return finished
  }
  const run = await prepareApproveAndRun()
  assert.equal(run.state, 'completed')
  const workspace = await page.locator('#workspace-select').inputValue()
  const evidence = await api(`/records/${run.scenarios[0].result_id}`)
  const reference = evidence.body.result.artifacts[0]
  const dataset = (await api(`/workspaces/${workspace}/records?kind=dataset`))[0]
  assert.equal(dataset.body.rows[0].original_values.concentration, '4.80')
  assert.equal(dataset.body.rows[0].concentration, '24/5')
  const plan = await api(`/records/${run.plan_id}`)
  assert.equal(plan.body.scientific_profile, 'counterdex.v1')
  assert.equal(plan.body.objective.version, 'research-objective.v1')

  async function downloadAndReplay(result, name, design = false) {
    const reference = result.artifacts[0]
    const [nativeDownload] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: design ? 'Download native design evidence' : 'Download native scientific evidence', exact: true }).first().click()])
    const nativePath = join(temp, `${name}.native.json`)
    await nativeDownload.saveAs(nativePath)
    const nativeBytes = await readFile(nativePath)
    assert.equal(nativeBytes.length, reference.byte_size)
    assert.equal(createHash('sha256').update(nativeBytes).digest('hex'), reference.sha256)
    const [anchorDownload] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: design ? 'Download design replay anchors' : 'Download replay anchors', exact: true }).first().click()])
    const anchorPath = join(temp, `${name}.anchors.json`)
    await anchorDownload.saveAs(anchorPath)
    const replay = start(enginePython, ['-I', '-m', 'counterdex', 'replay-native', nativePath, '--anchors', anchorPath],
      { PATH: process.env.PATH })
    assert.equal(await waitForExit(replay), 0, replay.output)
    const fresh = JSON.parse(replay.output)
    assert.equal(fresh.integrity, 'passed')
    assert.equal(fresh.expected_binding, 'matches')
    assert.equal(fresh.replay, result.replay)
    if (design) {
      assert.equal(fresh.operation, 'design')
      assert.equal(fresh.fresh_checked.tier, result.design_tier)
      assert.equal(fresh.fresh_checked.selected_time, result.selected_time)
    } else assert.equal(fresh.outcome.scientific_outcome, result.scientific_outcome)
    return fresh
  }
  await downloadAndReplay(evidence.body.result, 'first')

  // Design uses the actual returned pair, its own reviewed assumptions and approval.
  assert.equal(capabilities.science.native_design, true)
  assert.equal(evidence.body.result.candidates.length, 2)
  await page.fill('#design-times', '8, 6')
  await page.fill('#design-allowance', '0.2')
  await page.fill('#design-horizon', '8')
  await page.fill('#design-allowanceDescription', 'Team-reviewed future absolute error bound for this synthetic control')
  await page.check('#design-allowConstruction')
  await page.check('#design-allowContinuation')

  async function prepareDesign() {
    const response = page.waitForResponse(r => /\/runs\/[^/]+\/design-proposals$/.test(r.url()) && r.request().method() === 'POST')
    await page.getByRole('button', { name: 'Prepare measurement design', exact: true }).click()
    const plan = await (await response).json()
    assert.ok(plan.id, JSON.stringify(plan))
    await page.waitForSelector('#approve-design-scope')
    assert.equal(await page.locator('#approve-design').isDisabled(), true)
    assert.equal(await page.locator('#queue-design').isDisabled(), true)
    assert.deepEqual(plan.body.request.candidate_ids, evidence.body.result.candidates.map(c => c.id))
    assert.deepEqual(plan.body.request.candidate_vectors, evidence.body.result.candidates.map(c => c.parameter_vector))
    assert.deepEqual(plan.body.request.feasible_times, ['8/1', '6/1'])
    return plan
  }
  async function approveDesign() {
    await page.check('#approve-design-scope')
    await page.getByRole('button', { name: 'Approve reviewed design', exact: true }).click()
    await page.getByRole('button', { name: 'Design approved', exact: true }).waitFor()
  }
  async function runDesign(expectedTier, name) {
    const response = page.waitForResponse(r => /\/design-plans\/[^/]+\/jobs$/.test(r.url()) && r.request().method() === 'POST')
    await page.getByRole('button', { name: 'Queue approved design', exact: true }).click()
    const started = await (await response).json()
    assert.ok(started.id, JSON.stringify(started))
    await page.waitForFunction(() => /design execution: (completed|failed|cancelled|interrupted)/.test(document.querySelector('#backend-design').textContent), null, { timeout: 125000 })
    const finished = await api(`/design-jobs/${started.id}`)
    assert.equal(finished.state, 'completed', JSON.stringify(finished))
    const suggestion = await api(`/records/${finished.result_id}`)
    assert.equal(suggestion.body.design_tier, expectedTier)
    assert.equal(suggestion.body.verification, 'valid')
    assert.equal(suggestion.body.replay, 'passed')
    assert.equal(await page.locator('[aria-label="Measurement design grid"] tbody tr').count(), 2)
    assert.deepEqual(await page.locator('[aria-label="Measurement design grid"] tbody tr td:first-child').allTextContents(), ['8/1', '6/1'])
    assert.match(await page.locator('#backend-design').textContent(), new RegExp(`Design tier: ${expectedTier}`))
    await downloadAndReplay(suggestion.body, name, true)
    return { finished, suggestion }
  }
  const designPlan = await prepareDesign()
  await approveDesign()
  const positive = await runDesign('checked_pair_separation', 'design-positive')
  assert.equal(positive.finished.plan_id, designPlan.id)
  assert.equal(await page.locator('#queue-design').isDisabled(), true)
  await page.fill('#design-allowance', '10')
  assert.equal(await page.locator('#approve-design-scope').isDisabled(), true)
  assert.equal(await page.locator('#queue-design').isDisabled(), true)
  assert.match(await page.locator('#design-draft-state').textContent(), /Design inputs changed/)
  const noSeparationPlan = await prepareDesign()
  assert.notEqual(noSeparationPlan.id, designPlan.id)
  await approveDesign()
  const noSeparation = await runDesign('no_separation_established', 'design-no-separation')
  assert.match(await page.locator('#backend-design').textContent(), /does not rule out a useful time elsewhere/)
  assert.equal((await api(`/records/${positive.suggestion.id}`)).digest, positive.suggestion.digest)
  await page.fill('#design-job-id', positive.finished.id)
  await page.getByRole('button', { name: 'Open or refresh design', exact: true }).click()
  await page.waitForFunction(() => document.querySelector('#backend-design').textContent.includes('Design tier: checked_pair_separation'))
  assert.equal((await api(`/design-jobs/${noSeparation.finished.id}`)).state, 'completed')

  // A changed observation must create new reviewed identities and actual computation.
  await page.getByRole('link', { name: 'Inputs', exact: true }).click()
  await page.getByRole('textbox', { name: 'Row 1, concentration', exact: true }).fill('4.85')
  await page.getByRole('link', { name: 'Review', exact: true }).click()
  assert.equal(await page.locator('#approve-scope').isDisabled(), true)
  assert.match(await page.locator('#backend-review').textContent(), /Draft changed/)
  const changed = await prepareApproveAndRun(false)
  assert.notEqual(changed.id, run.id)
  const changedEvidence = await api(`/records/${changed.scenarios[0].result_id}`)
  assert.notEqual(changedEvidence.body.result.problem_digest, evidence.body.result.problem_digest)
  assert.notEqual(changedEvidence.body.result.artifacts[0].sha256, reference.sha256)
  assert.equal(await page.locator('#design-job-id').inputValue(), '')
  assert.equal(await page.getByRole('button', { name: 'Download native design evidence', exact: true }).count(), 0)
  await downloadAndReplay(changedEvidence.body.result, 'changed')
  assert.equal((await api(`/records/${evidence.id}`)).digest, evidence.digest)
  assert.deepEqual(await api(`/workspaces/${workspace}/provider-attempts`), [])

  await page.getByRole('link', { name: 'Report', exact: true }).click()
  await page.getByRole('button', { name: 'Create report for selected run' }).click()
  const [reportDownload] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download exact report JSON' }).click()])
  assert.equal(JSON.parse(await readFile(await reportDownload.path(), 'utf8')).body.run.id, changed.id)
  await page.setViewportSize({ width: 390, height: 844 })
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
  assert.deepEqual(errors, [])
  assert.deepEqual(external, [])
  assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0)
  assert.equal((await context.cookies()).length, 0)
  await page.click('#disconnect')
  assert.match(await page.locator('#backend-review').textContent(), /Connect to the local backend/)
  const denied = await fetch(`${base}/api/bean/v1/workspaces`, { headers: { Origin: 'https://external.invalid' } })
  assert.equal(denied.status, 403)
  console.log('Passed: actual browser review/approval/dispatch, real baseline discovery on two reviewed inputs, separately approved positive and no-separation designs from the actual pair, exact native and anchor downloads with installed-engine replay, preserved earlier evidence, reopened design history, zero provider attempts, memory-only credentials, and proxy origin rejection.')
} finally {
  await browser?.close()
  for (const child of children.reverse()) if (child.exitCode === null && !child.launchError) child.kill('SIGTERM')
  await Promise.all(children.map(child => child.launchError ? undefined : waitForExit(child)))
  await rm(temp, { recursive: true, force: true })
}
