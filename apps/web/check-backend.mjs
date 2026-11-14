// Actual browser -> API -> worker -> discovery -> separately approved design -> native replay.
// No candidate fixtures, fake scientific adapter, or model-provider calls.
// PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.mjs \
// BEAN_COUNTERDEX_PYTHON=/absolute/path/to/python3.11 node apps/web/check-backend.mjs
import { spawn } from 'node:child_process'
import { mkdtemp, rm, readFile, mkdir, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'node:net'
import { randomBytes, createHash } from 'node:crypto'
import assert from 'node:assert/strict'

import { createRequire } from 'node:module'
// require() honours NODE_PATH and CommonJS builds; PLAYWRIGHT_MODULE may name an explicit entry file.
const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || 'playwright')
const root = fileURLToPath(new URL('../../', import.meta.url))
const temp = await mkdtemp(join(tmpdir(), 'drbean-web-baseline-'))
const token = `DRBEAN-DUMMY-${randomBytes(20).toString('hex')}`
const localGatewayFile = join(temp, 'local-gateway.json')
await writeFile(localGatewayFile, JSON.stringify({ version: 1, secret: `DRBEAN-DUMMY-${randomBytes(15).toString('hex')}` }), { mode: 0o600 })
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
  BEAN_SOURCE_INTAKE_MODE: 'controlled', BEAN_CONTROLLED_SOURCE_MANIFEST: join(root, 'scripts/ai/fixtures/source-previews.v1.json'),
  BEAN_SCIENCE_ADAPTER: 'counterdex', BEAN_COUNTERDEX_PYTHON: enginePython, BEAN_WEB_API_PORT: String(apiPort),
  BEAN_LOCAL_GATEWAY_FILE: localGatewayFile, BEAN_LOCAL_BROWSER_ORIGIN: base, BEAN_AI_MODE: 'placeholder' }
const children = []
const start = (command, args, childEnv = env) => {
  const child = spawn(command, args, { cwd: root, env: childEnv, stdio: ['ignore', 'pipe', 'pipe'] })
  child.output = ''; child.on('error', error => { child.launchError = error })
  for (const stream of [child.stdout, child.stderr]) stream.on('data', chunk => { child.output = (child.output + chunk).slice(-65536) })
  children.push(child); return child
}
const python = process.env.BEAN_TEST_PYTHON || resolve(root, '.venv/bin/python')
let browserContext
const api = async path => {
  assert.ok(browserContext || path === '/capabilities', 'Private API evidence requires the actual browser context')
  const response = browserContext ? await browserContext.request.get(`${base}/api/bean/v1${path}`)
    : await fetch(`${base}/api/bean/v1${path}`)
  const ok = browserContext ? response.ok() : response.ok, status = browserContext ? response.status() : response.status
  assert.ok(ok, `HTTP ${status}: ${ok ? '' : await response.text()}`)
  return response.json()
}
const waitForExit = child => new Promise((resolve, reject) => {
  if (child.launchError) return reject(child.launchError)
  if (child.exitCode !== null) return resolve(child.exitCode)
  child.once('error', reject); child.once('exit', resolve)
})
let browser, activePage, lastApiResponse
try {
  const server = start(python, ['-m', 'uvicorn', 'bean_api.main:create_app', '--factory', '--host', '127.0.0.1', '--port', String(apiPort), '--no-proxy-headers'])
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
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || chromium.executablePath(), args: ['--no-sandbox'] })
  const context = await browser.newContext({ acceptDownloads: true })
  browserContext = context
  const page = await context.newPage(), errors = [], external = []
  activePage = page
  page.on('response', async response => {
    if (!response.url().startsWith(base + '/api/bean/v1/')) return
    try { lastApiResponse = { url: response.url(), status: response.status(), body: Number(response.headers()['content-length']) > 32768 ? '[bounded response omitted]' : (await response.text()).slice(0, 32768) } } catch { /* diagnostics only */ }
  })
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/*', route => {
    const url = route.request().url()
    if (!url.startsWith(base + '/') && !/^(blob|data):/.test(url)) { external.push(url); return route.abort() }
    return route.continue()
  })
  // This lane explicitly exercises the supported scientific workflow.
  await page.goto(base + '#inputs')
  // Pages are hash routes; changing the hash never reloads in-memory state.
  const go = async hash => { await page.evaluate(target => { location.hash = target }, hash); await page.waitForSelector(`#${hash}:not([hidden])`) }
  const openSourcePanel = () => page.locator('#source-path').evaluate(panel => { panel.open = true })
  await page.waitForFunction(() => document.querySelector('#workspace-select').value !== '')
  assert.equal(await page.locator('#bearer').isVisible(), false)
  const connected = await api('/shared-session/current')
  assert.equal(connected.workspace_id, await page.locator('#workspace-select').inputValue())
  assert.equal(connected.credentials, 'server_managed')
  await page.click('#example')
  await page.getByRole('button', { name: 'Use these rows', exact: true }).click()
  await page.click('#measurements button[type=submit]')
  const fields = { 'experiment-id': 'browser_synthetic', 'time-origin': 'Elapsed hours from synthetic t=0',
    aMin: '0.001', aMax: '30', keMin: '0.015', keMax: '0.35', kaMin: '0.4', kaMax: '8',
    targetMin: '0.10', targetMax: '0.17', allowanceOrigin: 'Team-selected synthetic hard bound of 0.50 mg/L' }
  for (const [id, value] of Object.entries(fields)) await page.fill(`#${id}`, value)
  await page.selectOption('#dataset-origin', 'synthetic')
  await page.click('#question-form button[type=submit]')

  async function prepareApproveAndRun(expectCounterexample = true, prepared = false) {
    if (!prepared) await page.getByRole('button', { name: 'Save inputs and prepare plan' }).click()
    await page.waitForSelector('#approve-scope')
    assert.equal(await page.getByRole('button', { name: 'Approve reviewed plan' }).isDisabled(), true)
    assert.equal(await page.getByRole('button', { name: 'Queue approved manual run' }).isDisabled(), true)
    assert.match(await page.locator('#backend-review').textContent(), /No witness found does not prove the claim/)
    await page.check('#approve-scope')
    await page.getByRole('button', { name: 'Approve reviewed plan' }).click()
    await page.getByRole('button', { name: 'Plan approved', exact: true }).waitFor()
    const previousRunId = await page.locator('#run-id').inputValue()
    const response = page.waitForResponse(r => /\/plans\/[^/]+\/runs$/.test(r.url()) && r.request().method() === 'POST')
    await page.getByRole('button', { name: 'Queue approved manual run' }).click()
    assert.equal((await response).status(), 202)
    await page.waitForFunction(previous => {
      const id = document.querySelector('#run-id').value
      return id && id !== previous
    }, previousRunId)
    const run = await api(`/runs/${await page.locator('#run-id').inputValue()}`)
    await page.waitForFunction(() => {
      const text = document.querySelector('#backend-investigations').textContent
      return /execution: (failed|cancelled|interrupted)/.test(text)
        || (/execution: completed/.test(text) && document.querySelector('#backend-results').textContent.includes('Outcome:'))
    }, null, { timeout: 125000 })
    const finished = await api(`/runs/${run.id}`)
    assert.equal(finished.state, 'completed', JSON.stringify(finished))
    const evidence = await api(`/records/${finished.scenarios[0].result_id}`)
    const result = evidence.body.result
    assert.ok(['certified_counterexample', 'no_counterexample_found', 'numerical_candidate', 'inconclusive'].includes(result.scientific_outcome))
    assert.match(await page.locator('#backend-results').textContent(), new RegExp(`Outcome: ${result.scientific_outcome}\\.`))
    assert.equal(result.expected_binding, 'matches')
    if (expectCounterexample) {
      assert.equal(result.scientific_outcome, 'certified_counterexample')
      assert.equal(result.verification, 'valid')
      assert.equal(result.replay, 'passed')
      assert.equal(await page.locator('[aria-label="Computed candidate parameters"] tbody tr').count() >= 1, true)
    }
    return finished
  }
  const workspace = await page.locator('#workspace-select').inputValue()
  // Source proposal is an explicitly controlled intake fixture; science runs normally.
  await openSourcePanel()
  await page.locator('#source-image-file').setInputFiles(join(root, 'fixtures/intake/clean.png'))
  await page.selectOption('#source-origin', 'synthetic')
  await page.getByRole('button', { name: 'Upload source for inspection', exact: true }).click()
  await page.waitForFunction(() => /Retained source /.test(document.querySelector('#source-review').textContent) || !document.querySelector('#backend-error').hidden)
  assert.equal(await page.locator('#backend-error').isVisible(), false, await page.locator('#backend-error').textContent())
  const sourceId = (await page.locator('#source-review').textContent()).match(/Retained source (source_[a-zA-Z0-9_]+)/)[1]
  await page.getByRole('button', { name: 'Prepare controlled source proposal', exact: true }).click()
  await page.getByText('Controlled example; not Gemini transcription.', { exact: true }).waitFor()
  await page.getByLabel('rows[0].hard_allowance Reviewed value', { exact: true }).fill('0.500')
  await page.getByLabel('rows[0].hard_allowance value origin', { exact: true }).selectOption('corrected_transcription')
  await page.getByLabel('rows[0].hard_allowance Correction or assumption reason', { exact: true }).fill('Reviewed source uses a synthetic hard allowance of 0.50 mg/L')
  await page.getByRole('button', { name: 'Accept reviewed source values', exact: true }).click()
  await page.getByRole('button', { name: 'Use reviewed values in measurement draft', exact: true }).click()
  await page.click('#measurements button[type=submit]')
  await page.waitForFunction(() => location.hash === '#question'
    && !document.querySelector('#question').hidden && document.activeElement?.id === 'question-title')
  await page.click('#question-form button[type=submit]')
  // Hash navigation rebuilds the source controls, then focuses the heading.
  // Its textarea can already be visible while that navigation is pending.
  await page.waitForFunction(() => location.hash === '#review'
    && !document.querySelector('#review').hidden && document.activeElement?.id === 'review-title')
  const assumptionExplanation = 'Reviewed synthetic example measurements, units, domain and claim entered explicitly for this browser test'
  const assumptionField = page.getByLabel('Explanation for the remaining manually reviewed inputs and assumptions', { exact: true })
  await assumptionField.fill(assumptionExplanation)
  assert.equal(await assumptionField.inputValue(), assumptionExplanation)
  await page.getByRole('button', { name: 'Preview source-bound inputs', exact: true }).click()
  await page.waitForFunction(() => Array.from(document.querySelectorAll('button')).some(button => button.textContent === 'Accept preview and prepare investigation plan' && !button.disabled) || !document.querySelector('#backend-error').hidden)
  assert.equal(await page.locator('#backend-error').isVisible(), false, await page.locator('#backend-error').textContent())
  await page.getByRole('link', { name: 'Question', exact: true }).click()
  await page.fill('#goal', 'Changed after source preview')
  await page.getByRole('link', { name: 'Review', exact: true }).click()
  await page.getByRole('button', { name: 'Accept preview and prepare investigation plan', exact: true }).click()
  await page.waitForFunction(() => !document.querySelector('#backend-error').hidden)
  assert.match(await page.locator('#backend-error').textContent(), /Revise the source-bound input preview/)
  await page.getByRole('button', { name: 'Revise source-bound input preview', exact: true }).click()
  await page.getByRole('button', { name: 'Preview source-bound inputs', exact: true }).click()
  await page.getByRole('button', { name: 'Accept preview and prepare investigation plan', exact: true }).click()
  const run = await prepareApproveAndRun(true, true)
  assert.equal(run.state, 'completed')
  const evidence = await api(`/records/${run.scenarios[0].result_id}`)
  const reference = evidence.body.result.artifacts[0]
  const dataset = (await api(`/workspaces/${workspace}/records?kind=dataset`))[0]
  assert.equal(dataset.body.rows[0].original_values.hard_allowance, '0.50')
  assert.equal(dataset.body.rows[0].source_asset_id, sourceId)
  assert.equal(dataset.body.rows[0].concentration, '24/5')
  const plan = await api(`/records/${run.plan_id}`)
  assert.equal(plan.body.scientific_profile, 'counterdex.v1')
  assert.equal(plan.body.objective.version, 'research-objective.v1')
  assert.equal(plan.body.objective.question, 'Changed after source preview', 'the exact reviewed source question must survive materialization')

  async function downloadAndReplay(result, name, design = false) {
    const reference = result.artifacts[0]
    await go(design ? 'next' : 'result')
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
  await go('next')
  await page.fill('#design-times', '8, 6')
  await page.fill('#design-allowance', '0.2')
  await page.fill('#design-horizon', '8')
  await page.fill('#design-allowanceDescription', 'Team-reviewed future absolute error bound for this synthetic control')
  await page.check('#design-allowConstruction')
  await page.check('#design-allowContinuation')

  async function prepareDesign() {
    const preview = page.locator('#backend-design details').filter({ has: page.getByText('Exact frozen measurement design', { exact: true }) }).locator('pre')
    const previous = await preview.count() ? await preview.textContent() : ''
    const response = page.waitForResponse(r => /\/runs\/[^/]+\/design-proposals$/.test(r.url()) && r.request().method() === 'POST')
    await page.getByRole('button', { name: 'Prepare measurement design', exact: true }).click()
    assert.equal((await response).status(), 201)
    await page.waitForFunction(previous => {
      const details = [...document.querySelectorAll('#backend-design details')].find(item => item.querySelector('summary').textContent === 'Exact frozen measurement design')
      return details && details.querySelector('pre').textContent !== previous
    }, previous)
    const plan = JSON.parse(await preview.textContent())
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
    const previousJobId = await page.locator('#design-job-id').inputValue()
    const response = page.waitForResponse(r => /\/design-plans\/[^/]+\/jobs$/.test(r.url()) && r.request().method() === 'POST')
    await page.getByRole('button', { name: 'Queue approved design', exact: true }).click()
    assert.equal((await response).status(), 202)
    // The application streams bounded bodies. Read its displayed returned ID
    // instead of depending on Chromium retaining a DevTools copy of that body.
    await page.waitForFunction(previous => {
      const id = document.querySelector('#design-job-id').value
      return id && id !== previous
    }, previousJobId)
    const started = await api(`/design-jobs/${await page.locator('#design-job-id').inputValue()}`)
    await page.waitForFunction(() => /design execution: (completed|failed|cancelled|interrupted)/.test(document.querySelector('#backend-design').textContent), null, { timeout: 125000 })
    const finished = await api(`/design-jobs/${started.id}`)
    assert.equal(finished.state, 'completed', JSON.stringify(finished))
    const suggestion = await api(`/records/${finished.result_id}`)
    assert.equal(suggestion.body.design_tier, expectedTier)
    assert.equal(suggestion.body.verification, 'valid')
    assert.equal(suggestion.body.replay, 'passed')
    assert.equal(await page.locator('[aria-label="Measurement design grid"] tbody tr').count(), 2)
    assert.deepEqual(await page.locator('[aria-label="Measurement design grid"] tbody tr td:first-child').allTextContents(), ['8', '6'])
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

  const followupOrigin = process.env.BEAN_TEST_FOLLOWUP_ORIGIN || 'hypothetical'
  assert.ok(['actual', 'hypothetical'].includes(followupOrigin))
  await page.locator('#followup-origin').selectOption(followupOrigin)
  if (followupOrigin === 'actual') {
    await page.fill('#followup-time', '7')
    await page.fill('#followup-allowance', '0.3')
  }
  await page.fill('#followup-value', '3.4')
  await page.fill('#followup-reason', `Synthetic test of ${followupOrigin} declaration; reviewed acquisition log at 7 h and hard bound 0.3 mg/L. No real measurement claimed.`)
  await page.getByRole('button', { name: `Prepare ${followupOrigin} observation`, exact: true }).click()
  await page.getByRole('button', { name: `Accept reviewed ${followupOrigin} observation`, exact: true }).click()
  await page.getByRole('button', { name: 'Prepare follow-up investigation plan', exact: true }).click()
  await page.locator('#followup-approve-scope').check()
  await page.getByRole('button', { name: 'Approve reviewed follow-up', exact: true }).click()
  await page.getByRole('button', { name: 'Queue approved follow-up', exact: true }).click()
  await page.waitForFunction(baselineId => {
    const status = document.querySelector('#backend-investigations [role="status"]')?.textContent
    const match = status?.match(/^(run_[a-zA-Z0-9]+) · execution:/)
    return match && match[1] !== baselineId
  }, run.id)
  const followupId = (await page.locator('#backend-investigations [role="status"]').textContent()).match(/^(run_[a-zA-Z0-9]+)/)[1]
  assert.equal(new URL(page.url()).hash, '#investigations')
  let followupRun
  for (let attempt = 0; attempt < 150; attempt++) {
    followupRun = await api(`/runs/${followupId}`)
    if (!['queued', 'running', 'cancel_requested'].includes(followupRun.state)) break
    await page.waitForTimeout(1000)
  }
  assert.equal(followupRun.state, 'completed', JSON.stringify(followupRun))
  const observations = await api(`/workspaces/${workspace}/records?kind=observation_proposal`)
  assert.equal(observations[0].body.origin, followupOrigin)
  assert.equal(observations[0].body.row.time, followupOrigin === 'actual' ? '7/1' : positive.suggestion.body.selected_time)
  if (followupOrigin === 'actual') {
    assert.equal(observations[0].body.row.hard_allowance, '3/10')
    assert.deepEqual(observations[0].body.generating_choices, {})
  }
  const followupEvidence = await api(`/records/${followupRun.scenarios[0].result_id}`)
  assert.equal(followupEvidence.body.result.candidate_results.length, 2)
  assert.equal(followupEvidence.body.result.native_replay.operation, 'recheck')
  assert.equal(followupEvidence.body.result.native_replay.dataset_origin, followupOrigin === 'actual' ? 'synthetic' : 'hypothetical')
  await go('result')
  await page.getByRole('region', { name: 'Follow-up candidate checks', exact: true }).waitFor()
  assert.match(await page.locator('#backend-results').textContent(), new RegExp(`Dataset origin: ${followupOrigin === 'actual' ? 'synthetic' : 'hypothetical'}`))

  await downloadAndReplay(followupEvidence.body.result, 'followup')

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
  // Changed bytes cannot reuse a controlled extraction; accepted science stays intact.
  await page.getByRole('link', { name: 'Review', exact: true }).click()
  await openSourcePanel()
  const beforeFallback = await api(`/workspaces/${workspace}/records?kind=dataset`)
  const changedSource = Buffer.concat([await readFile(join(root, 'fixtures/intake/clean.png')), Buffer.from('changed source bytes')])
  await page.locator('#source-image-file').setInputFiles({ name: 'clean.png', mimeType: 'image/png', buffer: changedSource })
  await page.selectOption('#source-origin', 'synthetic')
  await page.getByRole('button', { name: 'Upload source for inspection', exact: true }).click()
  await page.getByRole('button', { name: 'Prepare controlled source proposal', exact: true }).click()
  await page.getByText('Extraction unavailable for these image bytes. No values were accepted or added. Use manual measurements.', { exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Accept reviewed source values', exact: true }).count(), 0)
  assert.deepEqual((await api(`/workspaces/${workspace}/records?kind=dataset`)).map(record => record.id), beforeFallback.map(record => record.id))
  await page.getByRole('button', { name: 'Use controlled example image', exact: true }).click()
  await page.getByRole('button', { name: 'Prepare controlled source proposal', exact: true }).click()
  await page.getByRole('button', { name: 'Accept reviewed source values', exact: true }).waitFor()
  assert.deepEqual(await api(`/workspaces/${workspace}/provider-attempts`), [])

  await page.getByRole('link', { name: 'Report', exact: true }).click()
  await page.getByRole('button', { name: 'Create report for selected run' }).click()
  const [reportDownload] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download exact report JSON' }).click()])
  assert.equal(JSON.parse(await readFile(await reportDownload.path(), 'utf8')).body.run.id, changed.id)
  await page.setViewportSize({ width: 390, height: 844 })
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
  assert.deepEqual(errors, [])
  assert.deepEqual(external, [])
  const storage = await page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage }, readableCookie: document.cookie }))
  assert.deepEqual(storage.local, { 'dr-bean.private-workspace.v1': workspace })
  assert.deepEqual(storage.session, {})
  assert.equal(storage.readableCookie, '')
  const cookies = await context.cookies()
  assert.equal(cookies.length, 1)
  assert.equal(cookies[0].name, 'bean_local_session')
  assert.equal(cookies[0].httpOnly, true)
  assert.equal(cookies[0].sameSite, 'Strict')
  const logout = await context.request.post(`${base}/api/bean/v1/shared-session/logout`, { headers: { Origin: base } })
  assert.equal(logout.status(), 200)
  const revoked = await context.request.get(`${base}/api/bean/v1/workspaces`)
  assert.equal(revoked.status(), 401)
  const denied = await fetch(`${base}/api/bean/v1/workspaces`, { headers: { Origin: 'https://external.invalid' } })
  assert.equal(denied.status, 403)
  console.log('Passed: automatic private browser session, actual browser review/approval/dispatch, real baseline discovery on two reviewed inputs, separately approved positive and no-separation designs from the actual pair, exact native and anchor downloads with installed-engine replay, preserved earlier evidence, reopened design history, zero provider attempts, HttpOnly credentials, explicit revocation, and proxy origin rejection.')
} catch (error) {
  if (activePage) {
    const directory = process.env.BEAN_BROWSER_DIAGNOSTICS_DIR || join(root, 'var/test-evidence/browser-failures')
    const prefix = join(directory, `browser-${Date.now()}-${process.pid}`)
    try {
      await mkdir(directory, { recursive: true })
      await activePage.screenshot({ path: prefix + '.png' })
      const detail = { error: error.message, visible_status: (await activePage.locator('body').innerText()).slice(0, 32768), last_api_response: lastApiResponse }
      await writeFile(prefix + '.json', JSON.stringify(detail, null, 2).split(token).join('[synthetic test credential]'))
      console.error(`Browser failure diagnostics: ${prefix}`)
    } catch { /* Preserve the original failure. */ }
  }
  throw error
} finally {
  await browser?.close()
  for (const child of children.reverse()) if (child.exitCode === null && !child.launchError) child.kill('SIGTERM')
  await Promise.all(children.map(child => child.launchError ? undefined : waitForExit(child)))
  await rm(temp, { recursive: true, force: true })
}
