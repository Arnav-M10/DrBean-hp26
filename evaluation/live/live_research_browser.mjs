// C's bounded live-Gemini sprint journey through the connected browser interface.
//
//   LIVE_CASE=dry-run|baseline|clarification LIVE_GRANT=<n> LIVE_OPT_IN=<path to gemini.local.json> \
//   NODE_PATH=... node evaluation/live/live_research_browser.mjs
//
// Lane: live_gemini (dry-run makes zero provider requests). Uses the supported
// launcher on fresh ports with an isolated temporary store; the user's running
// app is untouched. The opt-in file is copied (0600) into the temporary store
// and deleted with it; no credential value is read, printed or recorded.
// Inputs are public synthetic readings only. No automatic retries: every
// provider request is reserved by the product's ledger, and the operator grant
// tool defaults to the frozen 12-request sprint ceiling. An explicitly recorded
// follow-through authorization can enable one bounded qualification-only extension.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import { createRequire } from 'node:module'
import { createServer } from 'node:net'
import { chmod, copyFile, cp, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || 'playwright')
const root = fileURLToPath(new URL('../../', import.meta.url))
const CASE = process.env.LIVE_CASE || 'dry-run'
const GRANT = Number(process.env.LIVE_GRANT || 0)
const UI = process.env.LIVE_UI || 'web'  // 'preview' = the preferred workspace at /workspace-preview/
assert.ok(['web', 'preview'].includes(UI), 'LIVE_UI must be web or preview')
assert.ok(UI === 'web' || CASE !== 'clarification', 'The missing-input contrast uses the file-question path in apps/web')
assert.ok(['dry-run', 'baseline', 'clarification'].includes(CASE), 'LIVE_CASE must be dry-run, baseline or clarification')
assert.ok(CASE === 'dry-run' ? GRANT === 0 : GRANT >= 1 && GRANT <= 8, 'A live case needs LIVE_GRANT in 1..8; dry-run grants nothing')
const commit = (await run('git', ['rev-parse', 'HEAD'])).trim()
// Live runs test one exact commit: application files must match HEAD; only harness files may be layered on top.
const appChanges = (await run('git', ['status', '--porcelain', '--', 'apps', 'packages', 'scripts', 'workspace-preview'])).trim()
assert.ok(!process.env.LIVE_EXPECT_COMMIT || process.env.LIVE_EXPECT_COMMIT === commit, `HEAD ${commit} is not LIVE_EXPECT_COMMIT`)
assert.ok(CASE === 'dry-run' || !appChanges, `Application files differ from the tested commit:\n${appChanges}`)
const overlay = (await run('git', ['status', '--porcelain', '--untracked-files=no'])).trimEnd()
const appBase = (await run('git', ['merge-base', 'HEAD', 'origin/main'])).trim().slice(0, 7)
const appDiff = (await run('git', ['diff', '--name-only', 'origin/main', '--', 'apps', 'packages', 'scripts', 'workspace-preview'])).trim()
const output = resolve(process.env.LIVE_EVIDENCE_DIR || join(root, `evaluation/results/sprint/live-${CASE}-${appBase}`))
const scratch = await mkdtemp(join(tmpdir(), 'drbean-live-sprint-'))
const python = resolve(root, '.venv/bin/python'), engine = resolve(root, '.venv-engine/bin/python')
const apiPort = await freePort(), webPort = await freePort(), base = `http://127.0.0.1:${webPort}`
const env = { PATH: process.env.PATH, LANG: 'C.UTF-8', DRBEAN_VAR_DIR: scratch, BEAN_AUTH_FILE: join(scratch, 'auth.json'),
  BEAN_DEV_API_PORT: String(apiPort), BEAN_DEV_WEB_PORT: String(webPort), BEAN_RESEARCH_MODE: 'live',
  PYTHONPATH: join(root, 'apps/api'), LANGSMITH_TRACING: 'false',
  LIVE_BUDGET_FILE: process.env.LIVE_BUDGET_FILE || join(root, 'evaluation/results/sprint/live-budget.json'),
  ...(process.env.LIVE_QUALIFICATION_EXTENSION ? { LIVE_QUALIFICATION_EXTENSION: process.env.LIVE_QUALIFICATION_EXTENSION } : {}) }
const record = { schema_version: 'c-sprint-live-run.v1', lane: CASE === 'dry-run' ? 'live_gemini (dry run, zero requests)' : 'live_gemini',
  case: CASE, ui: UI, qualification_extension: process.env.LIVE_QUALIFICATION_EXTENSION || null, harness_commit: commit, tested_commit: commit, application_files_match_tested_commit: !appChanges, harness_overlay: overlay ? overlay.split('\n') : [], application_tree: appDiff ? `differs from origin/main: ${appDiff.split('\n').length} files` : `identical to origin/main ${appBase}`, grant: GRANT, started_at: new Date().toISOString(), checks: [], observations: {} }
let browser, context, page, launched = false, tracked = null

async function run(executable, args, extraEnv = null, timeout = 60000) {
  const child = spawn(executable, args, { cwd: root, env: extraEnv || process.env, stdio: ['ignore', 'pipe', 'pipe'] })
  let text = '', timer
  for (const stream of [child.stdout, child.stderr]) stream.on('data', bytes => { text = (text + bytes).slice(-262144) })
  const code = await new Promise((yes, no) => { child.once('error', no); child.once('exit', yes)
    timer = setTimeout(() => { child.kill('SIGTERM'); no(new Error(`${args[0]} timed out`)) }, timeout) }).finally(() => clearTimeout(timer))
  if (code !== 0) throw new Error(`${executable} ${args[0]} exited ${code}: ${text.slice(-2000)}`)
  return text
}
async function freePort() {
  const server = createServer()
  await new Promise((yes, no) => { server.once('error', no); server.listen(0, '127.0.0.1', yes) })
  const port = server.address().port
  await new Promise(yes => server.close(yes))
  return port
}
async function api(path) {
  const response = await context.request.get(`${base}/api/bean/v1${path}`)
  assert.equal(response.status(), 200, `${path}: ${response.status()}`)
  return response.json()
}
const check = (id, detail = '') => { record.checks.push({ id, detail }); console.log(`ok ${id}${detail ? ': ' + detail : ''}`) }
// Node-side polling: Playwright's waitForFunction treats a returned promise as already truthy.
async function poll(predicate, timeout, every = 2000) {
  const end = Date.now() + timeout
  while (Date.now() < end) { if (await predicate()) return; await new Promise(yes => setTimeout(yes, every)) }
  throw new Error(`Timed out after ${timeout} ms`)
}
const list = value => Array.isArray(value) ? value : (value.items || [])
// Settle on the server's state, never on panel text: a request in flight is not a stop.
const ACTIVE_STATES = new Set(['queued', 'running', 'waiting_child'])
async function settledSession(id, timeout) {
  let latest
  await poll(async () => { latest = await api(`/research-sessions/${id}`)
    return !ACTIVE_STATES.has(latest.state) && !latest.provider_usage?.unresolved_attempts }, timeout, 1000)
  return latest
}
const sha = bytes => createHash('sha256').update(bytes).digest('hex')

try {
  await mkdir(output, { recursive: true })
  const optIn = process.env.LIVE_OPT_IN
  assert.ok(optIn, 'LIVE_OPT_IN must name the existing free-tier opt-in file')
  await copyFile(optIn, join(scratch, 'gemini.local.json'))
  await chmod(join(scratch, 'gemini.local.json'), 0o600)
  await run(python, ['-m', 'bean_api.bootstrap'], env, 15000)
  await run(python, ['scripts/dev/launcher.py', 'start'], env, 90000)
  launched = true
  const capabilities = await (await fetch(`${base}/api/bean/v1/capabilities`)).json()
  const deep = capabilities.deepagents, gemini = capabilities.gemini
  record.observations.capabilities = { deepagents: { execution_mode: deep.execution_mode, dispatch_enabled: deep.dispatch_enabled,
    unavailable_reason: deep.unavailable_reason, session_limits: deep.session_limits },
    gemini: { model: gemini?.model, execution_mode: gemini?.execution_mode, dispatch_enabled: gemini?.dispatch_enabled,
      retry_policy: gemini?.retry_policy, billing_verified: gemini?.billing_verified } }
  assert.equal(deep.execution_mode, 'live', JSON.stringify(record.observations.capabilities))
  assert.equal(deep.dispatch_enabled, true)
  assert.equal(gemini.model, 'gemini-3.5-flash-lite')
  check('server-configured-for-live-free-tier-coordination', `model ${gemini.model}, retry ${gemini.retry_policy}`)

  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || chromium.executablePath() })
  context = await browser.newContext({ acceptDownloads: true })
  page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  if (UI === 'preview') {
    // The preferred workspace: same private access, its own controls, the production ResearchController.
    await page.goto(base + '/workspace-preview/')
    await page.locator('#research-example').waitFor({ state: 'visible', timeout: 30000 })
    await page.waitForFunction(() => !document.querySelector('#research-mode')?.textContent.includes('Static'), null, { timeout: 30000 })
    await page.locator('#research-example').click()
    await page.goto(base + '/workspace-preview/#question')
    await page.locator('#accept-inputs').check()
    await page.locator('#start-research').click()
    await page.locator('#save-provider-consent').waitFor({ state: 'visible', timeout: 30000 })
    const sessions = await page.evaluate(async () => {
      const ws = await (await fetch('/api/bean/v1/workspaces', { credentials: 'same-origin' })).json()
      const list = Array.isArray(ws) ? ws : (ws.items || [])
      const out = []
      for (const w of list) { const r = await (await fetch(`/api/bean/v1/workspaces/${w.id}/research-sessions`, { credentials: 'same-origin' })).json(); out.push(...(r.items || []).map(s => ({ ...s, workspace: w.id }))) }
      return out
    })
    assert.equal(sessions.length, 1, 'Exactly one session created by the preferred workspace')
    let session = sessions[0]
    const workspace = session.workspace_id || session.workspace
    tracked = { session: session.id, workspace }
    assert.equal(session.mode, 'live'); assert.equal(session.provider_allocation.physical_requests, 0)
    check('live-session-created-from-the-preferred-workspace-with-zero-default-allocation', session.id)
    assert.equal(await page.locator('#continue-plan').isDisabled(), true, 'Continue must stay disabled before consent and capacity')
    await page.locator('#provider-consent').check()
    await page.locator('#save-provider-consent').click()
    await poll(async () => (await api(`/research-sessions/${session.id}`)).interaction?.provider_consent_required === false || /consent saved/i.test(await page.locator('body').innerText()), 30000)
    check('consent-recorded-through-the-preferred-workspace')
    assert.equal(list(await api(`/workspaces/${workspace}/provider-attempts`)).length, 0, 'Saving inputs or consent must not call the provider')
    if (CASE === 'dry-run') {
      assert.equal(await page.locator('#continue-plan').isDisabled(), true, 'Continue must stay disabled with no operator allocation')
      check('preferred-workspace-continue-disabled-without-allocation')
    } else {
      record.observations.grant = JSON.parse(await run(python, ['evaluation/live/operator_grant.py', join(scratch, 'bean.sqlite3'), session.id,
        String(GRANT), '64000', String(Math.min(16000, GRANT * 512)), `${CASE}-preview-${commit}`], env))
      check('operator-granted-explicit-allocation', `${GRANT} requests; sprint total ${record.observations.grant.sprint_granted_total}/${record.observations.grant.ceiling}`)
      await page.locator('#refresh-research').click()
      await page.waitForFunction(() => !document.querySelector('#continue-plan')?.disabled, null, { timeout: 20000 })
      const beforeAdvance = (await api(`/research-sessions/${session.id}`)).revision
      await page.locator('#continue-plan').click()
      // Wait until the click has reached the server (revision moves) and the action is no longer moving.
      const settle = async (fromRevision, timeout) => { await poll(async () => { const s = await api(`/research-sessions/${session.id}`)
        return s.revision > fromRevision && !['queued', 'running', 'waiting_child'].includes(s.state) && !s.provider_usage?.unresolved_attempts }, timeout); return api(`/research-sessions/${session.id}`) }
      session = await settle(beforeAdvance, 240000)
      record.observations.after_first_advance = { state: session.state, revision: session.revision, child_count: session.children.length, pending_review: session.pending_review?.kind ?? null, error_code: session.action?.error_code ?? null, usage: session.usage }
      if (session.pending_review?.kind === 'plan') {
        assert.equal(session.children.length, 0, 'No science before approval')
        assert.equal(await page.locator('#approve-science').isDisabled(), true)
        check('live-plan-stops-for-approval-with-no-child-in-the-preferred-workspace')
        await page.locator('#approve-scope').check()
        const beforeDecision = session.revision
        await page.locator('#approve-science').click()
        session = await settle(beforeDecision, 300000)
      }
      record.observations.final = { state: session.state, pending_review: session.pending_review?.kind ?? null, error_code: session.action?.error_code ?? null,
        usage: session.usage, provider_allocation: session.provider_allocation, reports: session.reports,
        children: session.children.map(child => ({ id: child.id, kind: child.kind, state: child.state, scientific_reservations: child.scientific_reservations })),
        plan_steps: session.plan?.body?.steps?.map(step => ({ title: step.title, status: step.status })) ?? [],
        interaction: session.interaction ?? null }
      await page.locator('#refresh-research').click()
      await page.waitForFunction(({state,revision}) => { const status=document.querySelector('#research-status'); return status?.dataset.state===state && Number(status.dataset.revision)>=revision }, {state:session.state,revision:session.revision}, {timeout:30000})
      record.observations.preferred_ui_text = { status: await page.locator('#research-status').innerText().catch(() => null),
        findings: await page.locator('#research-findings').innerText().catch(() => null), error: await page.locator('#research-error').innerText().catch(() => null) }
    }
    globalThis.__live = { session, workspace }
  } else {
  // Automatic private access: the browser gets its own private workspace without a pasted credential.
    await page.goto(base + (CASE === 'clarification' ? '#research' : '#inputs'))
    await page.waitForFunction(() => document.querySelector('#workspace-select').value !== '', null, { timeout: 30000 })
    const workspace = await page.locator('#workspace-select').inputValue()
    const panel = page.locator('#durable-research')

    if (CASE === 'clarification') {
      // Missing reviewed model: only an untrusted file and a question, no measurements or claim.
      const file = join(scratch, 'synthetic-notes.csv')
      await writeFile(file, 'note\nSynthetic public example: concentration readings were not supplied.\n')
      await page.locator('#research-files').setInputFiles(file)
      await page.locator('#general-assets article').first().waitFor()
      await page.locator('#general-assets input[type=checkbox]').first().check()
      await page.locator('#research-question').fill('Does a one-compartment oral model with ke between 0.10 and 0.17 per hour fit my readings?')
      await page.evaluate(() => { location.hash = 'investigations' })
      await panel.getByRole('button', { name: 'Save selected files and research question', exact: true }).click()
    } else {
      const file = join(scratch, 'public-synthetic-readings.csv')
      await writeFile(file, 'time,concentration,epsilon\n0.25,4.80,0.50\n0.5,7.20,0.50\n1,8.00,0.50\n2,6.80,0.50\n4,5.70,0.50\n')
      await page.locator('#csv-file').setInputFiles(file)
      await page.getByRole('button', { name: 'Use these rows', exact: true }).click()
      await page.getByLabel('Row 1, concentration', { exact: true }).fill('4.81')
      await page.click('#measurements button[type=submit]')
      for (const [id, value] of Object.entries({ 'experiment-id': 'c-live-sprint-public-synthetic', 'time-origin': 'Synthetic elapsed hours from t=0',
        aMin: '0.001', aMax: '30', keMin: '0.015', keMax: '0.35', kaMin: '0.4', kaMax: '8', targetMin: '0.10', targetMax: '0.17',
        allowanceOrigin: 'Synthetic hard bound of 0.50 mg/L for a public example, not an instrument claim',
        goal: 'Do these synthetic readings challenge the claimed ke range of 0.10 to 0.17 per hour, and what should be measured next?' })) await page.fill(`#${id}`, value)
      await page.selectOption('#dataset-origin', 'synthetic')
      await page.click('#question-form button[type=submit]')
      await page.goto(base + '#investigations')
      await panel.getByText('Feasible next-measurement constraints (optional until design)', { exact: true }).click()
      for (const [name, value] of Object.entries({ times: '8, 6', allowance: '0.2', horizon: '8', allowanceReason: 'Synthetic prospective hard bound for a public example' }))
        await panel.locator(`[name="${name}"]`).fill(value)
      await panel.getByLabel('I reviewed the exact measurement values, units, time origin, hard allowances, parameter bounds and question assumptions.', { exact: true }).check()
      await panel.getByRole('button', { name: 'Save reviewed inputs and research question', exact: true }).click()
    }
    await panel.getByRole('button', { name: 'Save provider consent', exact: true }).waitFor({ timeout: 30000 })
    let session = (await api(`/workspaces/${workspace}/research-sessions`)).items[0]
    tracked = { session: session.id, workspace }
    assert.equal(session.mode, 'live')
    assert.equal(session.provider_allocation.physical_requests, 0)
    check('live-session-created-from-the-browser-with-zero-default-allocation', session.id)

    // Consent through the UI: the exact disclosure, explicitly accepted.
    await panel.getByLabel('I consent to sending this research question, reviewed inputs, plan, retained evidence and source references to the disclosed Gemini model.', { exact: true }).check()
    await panel.getByRole('button', { name: 'Save provider consent', exact: true }).click()
    await page.waitForFunction(() => document.querySelector('#durable-research').textContent.match(/(Provider consent|Consent) saved/), null, { timeout: 30000 })
    check('consent-recorded-through-the-browser')
    record.observations.consent = { at: new Date().toISOString(), provider_consent_required: (await api(`/research-sessions/${session.id}`)).interaction?.provider_consent_required ?? null }
    const attemptsBefore = list(await api(`/workspaces/${workspace}/provider-attempts`)).length
    assert.equal(attemptsBefore, 0, 'Saving inputs or consent must not call the provider')

    if (CASE === 'dry-run') {
      const advance = panel.getByRole('button', { name: 'Advance research plan', exact: true })
      assert.equal(await advance.isDisabled(), true, 'Advance must stay disabled with no operator allocation')
      const revision = (await api(`/research-sessions/${session.id}`)).revision
      const refused = await page.evaluate(async ({ id, revision }) => {
        const response = await fetch(`/api/bean/v1/research-sessions/${id}/advance`, { method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', 'Idempotency-Key': 'c-dry-run' }, body: JSON.stringify({ expected_revision: revision }) })
        return { status: response.status, text: await response.text() }
      }, { id: session.id, revision })
      record.observations.unallocated_advance = { status: refused.status, code: (() => { try { return JSON.parse(refused.text).code } catch { return refused.text.slice(0, 200) } })() }
      assert.equal(refused.status, 409, JSON.stringify(record.observations.unallocated_advance))
      check('unallocated-live-advance-refused-before-any-request', record.observations.unallocated_advance.code)
    } else {
      const granted = JSON.parse(await run(python, ['evaluation/live/operator_grant.py', join(scratch, 'bean.sqlite3'), session.id,
        String(GRANT), '64000', String(Math.min(16000, GRANT * 512)), `${CASE}-${commit}`], env))
      record.observations.grant = granted
      check('operator-granted-explicit-allocation', `${granted.granted} requests; sprint total ${granted.sprint_granted_total}/${granted.ceiling}`)
      await panel.getByRole('button', { name: 'Refresh saved state', exact: true }).first().click()
      const advance = panel.getByRole('button', { name: 'Advance research plan', exact: true })
      await page.waitForFunction(() => [...document.querySelectorAll('#durable-research button')].some(b => b.textContent === 'Advance research plan' && !b.disabled), null, { timeout: 15000 })
      await advance.click()
      const settled = async (timeout) => {
        await page.waitForFunction(() => {
          const text = document.querySelector('#durable-research').textContent
          return /Review the investigation operation|Review the separate|The assistant needs more information|State: (completed|failed|cancelled|needs_reconciliation)|The last step stopped|Why the assistant stopped/.test(text)
        }, null, { timeout })
        return settledSession(session.id, timeout)
      }
      session = await settled(240000)
      record.observations.after_first_advance = { state: session.state, pending_review: session.pending_review?.kind ?? null,
        error_code: session.action?.error_code ?? null, usage: session.usage }
      if (CASE === 'baseline' && session.pending_review?.kind === 'plan') {
        assert.equal(session.children.length, 0, 'No science before approval')
        const approve = panel.getByRole('button', { name: 'Approve exact operation and continue', exact: true })
        assert.equal(await approve.isDisabled(), true)
        check('live-plan-stops-for-approval-with-no-child')
        await panel.getByLabel('I approve only this frozen scientific scope and its limits.', { exact: true }).check()
        await approve.click()
        await page.waitForFunction(() => /State: (completed|failed|cancelled|needs_reconciliation)|The last step stopped|Why the assistant stopped|Review the separate/.test(
          document.querySelector('#durable-research').textContent), null, { timeout: 300000 })
        session = await settledSession(session.id, 300000)
      }
      record.observations.final = { state: session.state, pending_review: session.pending_review?.kind ?? null,
        error_code: session.action?.error_code ?? null, usage: session.usage, provider_allocation: session.provider_allocation,
        children: session.children.map(child => ({ id: child.id, kind: child.kind, state: child.state, scientific_reservations: child.scientific_reservations })),
        reports: session.reports, plan_steps: session.plan?.body?.steps?.map(step => ({ title: step.title, status: step.status })) ?? [] }
    }

    globalThis.__live = { session, workspace }
  }
  const { session, workspace } = globalThis.__live
  // Provider ledger, events and evidence: public fields only.
  const attempts = list(await api(`/workspaces/${workspace}/provider-attempts`))
  // Whole attempt records: ids, states, budgets, prompt hashes and provider-reported usage; never prompts or keys.
  record.observations.attempts = attempts
  record.observations.provider_usage = (await api(`/research-sessions/${session.id}`)).provider_usage ?? null
  record.observations.model_tool_calls = JSON.parse(await run(python, ['evaluation/live/extract_tool_calls.py', join(scratch, 'bean.sqlite3'), session.id], env, 30000))
  const events = (await api(`/research-sessions/${session.id}/events?after=-1`)).items
  record.observations.events = events.map(event => ({ sequence: event.sequence ?? null, at: event.created_at ?? event.at ?? null,
    type: event.event_type, summary: event.summary, references: event.reference_ids,
    execution_mode: event.execution_mode ?? event.body?.execution_mode ?? null }))
  record.physical_requests = attempts.length
  if (UI === 'preview' && session.state === 'completed' && session.reports?.length) {
    await page.getByText('Persisted model commentary', { exact: true }).waitFor({ timeout: 30000 })
    record.observations.preferred_ui_text.findings = await page.locator('#research-findings').innerText()
  }
  if (session.reports?.length) {
    const report = await context.request.get(`${base}/api/bean/v1/reports/${session.reports.at(-1)}/download`)
    assert.equal(report.status(), 200)
    const bytes = await report.body()
    const reread = await context.request.get(`${base}/api/bean/v1/reports/${session.reports.at(-1)}/download`)
    assert.equal(reread.status(), 200)
    assert.equal(sha(await reread.body()), sha(bytes), 'Report snapshot is unchanged on a fresh download')
    record.observations.report_snapshot_repeat_digest_matches = true
    await writeFile(join(output, 'research-report.json'), bytes)
    const reportBody = JSON.parse(bytes).body
    record.observations.report = { id: session.reports.at(-1), sha256: sha(bytes), fields: Object.keys(reportBody),
      commentary_status: reportBody.commentary_status ?? null, model_failure: reportBody.model_failure ?? null,
      evidence_count: reportBody.evidence?.length ?? null, native_evidence_count: reportBody.native_evidence?.length ?? null }
    for (const entry of JSON.parse(bytes).body.native_evidence || []) {
      const native = await context.request.get(`${base}${entry.download_path}`), anchor = await context.request.get(`${base}${entry.anchor_path}`)
      assert.equal(native.status(), 200); assert.equal(anchor.status(), 200)
      const nativePath = join(output, entry.native_filename), anchorPath = join(output, entry.anchor_filename)
      await writeFile(nativePath, await native.body()); await writeFile(anchorPath, await anchor.body())
      const replay = JSON.parse(await run(engine, ['-I', '-m', 'counterdex', 'replay-native', nativePath, '--anchors', anchorPath], null, 120000))
      await writeFile(join(output, entry.native_filename + '.replay.json'), JSON.stringify(replay, null, 2) + '\n')
      record.observations.replay = [...(record.observations.replay || []), { evidence_id: entry.evidence_id, integrity: replay.integrity,
        replay: replay.replay, expected_binding: replay.expected_binding, verification: replay.verification, outcome: replay.outcome?.scientific_outcome ?? replay.fresh_checked?.tier }]
    }
  }
  // L7: an ordinary reload keeps the same private session and its saved results.
  try {
    const before = await api(`/research-sessions/${session.id}`)
    await page.reload({ waitUntil: 'domcontentloaded' })
    if (UI === 'web') {
      await page.waitForFunction(() => document.querySelector('#workspace-select')?.value !== '', null, { timeout: 30000 })
      await page.evaluate(() => { location.hash = 'investigations' })
      await page.waitForFunction(({ state, revision }) => (document.querySelector('#durable-research')?.textContent || '')
        .includes(`State: ${state} · revision ${revision}`), { state: before.state, revision: before.revision }, { timeout: 30000 })
    } else {
      await page.waitForFunction(({ state, revision }) => { const status = document.querySelector('#research-status')
        return status?.dataset.state === state && Number(status.dataset.revision) >= revision }, { state: before.state, revision: before.revision }, { timeout: 30000 })
    }
    const after = await api(`/research-sessions/${session.id}`)
    const shownWorkspace = UI === 'web' ? await page.locator('#workspace-select').inputValue() : workspace
    const panel = await page.locator(UI === 'web' ? '#durable-research' : '#research-status').innerText()
    record.observations.reload = { same_workspace: shownWorkspace === workspace, same_session: after.id === before.id,
      state: after.state, revision_unchanged: after.revision === before.revision,
      reports_unchanged: JSON.stringify(after.reports) === JSON.stringify(before.reports),
      // The report button lives on the separate Next page, so count it whether or not that page is shown.
      report_download_offered: UI !== 'web' || !before.reports?.length ||
        await page.locator('button', { hasText: 'Download research report snapshot' }).count() > 0 }
    record.observations.reload.passed = Object.entries(record.observations.reload).every(([key, value]) => key === 'state' || value === true)
    if (record.observations.reload.passed) check('reload-keeps-the-same-session-and-results', `${after.state} r${after.revision}`)
  } catch (error) {
    record.observations.reload = { passed: false, error: String(error.message).slice(0, 600) }
  }
  assert.deepEqual(errors, [])
  record.status = 'completed'
} catch (error) {
  record.status = 'error'
  record.error = String(error.message).slice(0, 4000)
  if (page) await page.screenshot({ path: join(output, 'failure.png'), fullPage: true }).catch(() => {})
  if (page) record.panel_text = await page.locator('#durable-research').innerText({ timeout: 5000 }).catch(() => null)
  if (tracked && context && record.physical_requests === undefined) {
    try {
      const attempts = list(await api(`/workspaces/${tracked.workspace}/provider-attempts`))
      record.observations.attempts = attempts
      record.physical_requests = attempts.length
      const latest = await api(`/research-sessions/${tracked.session}`)
      record.observations.at_failure = { state: latest.state, pending_review: latest.pending_review?.kind ?? null,
        error_code: latest.action?.error_code ?? null, usage: latest.usage, provider_allocation: latest.provider_allocation,
        children: latest.children?.map(child => ({ id: child.id, kind: child.kind, state: child.state })) ?? [], reports: latest.reports }
      record.observations.model_tool_calls = JSON.parse(await run(python, ['evaluation/live/extract_tool_calls.py', join(scratch, 'bean.sqlite3'), tracked.session], env, 30000))
    } catch (accounting) {
      record.accounting_error = String(accounting.message).slice(0, 600)
    }
  }
  process.exitCode = 1
} finally {
  record.finished_at = new Date().toISOString()
  await writeFile(join(output, 'record.json'), JSON.stringify(record, null, 2) + '\n')
  await browser?.close()
  if (launched) await run(python, ['scripts/dev/launcher.py', 'stop'], env, 60000).catch(error => { console.error(error.message); process.exitCode = 1 })
  if (process.env.LIVE_RETAIN_STORE_DIR) {
    const keep = resolve(process.env.LIVE_RETAIN_STORE_DIR)
    if (keep.startsWith(root)) console.error('Not retaining the store: LIVE_RETAIN_STORE_DIR must be outside the repository')
    else {
      await mkdir(keep, { recursive: true }).catch(() => {})
      for (const name of ['bean.sqlite3', 'bean.sqlite3-wal', 'bean.sqlite3-shm'])
        await copyFile(join(scratch, name), join(keep, name)).catch(() => {})
      // Blob and artifact folders hold native evidence bytes; the opt-in file sits at the store root and is never copied.
      for (const folder of ['sources', 'artifacts'])
        await cp(join(scratch, folder), join(keep, folder), { recursive: true }).catch(() => {})
    }
  }
  await rm(scratch, { recursive: true, force: true })
  console.log(JSON.stringify({ status: record.status, case: CASE, physical_requests: record.physical_requests ?? null, output }, null, 2))
}
