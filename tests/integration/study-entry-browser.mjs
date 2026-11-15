// Real Chromium and the actual study frontend, with authored HTTP fixtures only.
// This qualifies entry/restoration behavior, not science, authentication, or Gemini.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { parseExact } from '../../apps/web/exact.mjs'
import { paperDraft, VERITY_STUDY } from '../../apps/web/study/paper-study.mjs'

const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || 'playwright')
const root = fileURLToPath(new URL('../../', import.meta.url))
const workspace = 'ws-controlled-study-entry'
const store = 'dr-bean.study.v1'
const paper = { id: 'asset-controlled-paper', workspace_id: workspace, filename: 'Dr-Verity-Riemann-Study.pdf',
  sha256: VERITY_STUDY.sha256, byte_size: VERITY_STUDY.byteSize, media_type: 'application/pdf', pages: [] }
const saved = { sessionId: 'session-controlled-paper', paperAssetId: paper.id }
const draft = paperDraft(paper)
const interval = (lower, upper) => ({ lower: parseExact(lower), upper: parseExact(upper) })
const snapshot = { id: saved.sessionId, workspace_id: workspace, state: 'waiting_review', revision: 1,
  children: [], reports: [], pending_review_digest: 'controlled-review-digest',
  pending_review: { id: 'review-controlled', kind: 'plan', body: { budget: { scientific_wall_seconds: 120 } } },
  reviewed_context: {
    dataset: { body: { experiment_id: 'Authored browser fixture', origin: 'synthetic',
      time_origin: draft.timeOrigin, change_reason: draft.source,
      rows: draft.rows.map((row, i) => ({ id: `obs_${i + 1}`, included: true, time: parseExact(row.time),
        concentration: parseExact(row.value), hard_allowance: parseExact(row.allowance), notes: row.note })) } },
    problem: { body: { target: { parameter: 'ke', closed: true, ...interval(draft.low, draft.high) },
      domain: { A: interval(draft.limits.aLow, draft.limits.aHigh), ke: interval(draft.limits.keLow, draft.limits.keHigh),
        ka: interval(draft.limits.kaLow, draft.limits.kaHigh), rate_order: 'ke_lt_ka' } } },
  },
}
const caps = { contract_version: 'DB-SC-1', policy_version: 'GF-2', science: { available: true },
  deepagents: { dispatch_enabled: true, execution_mode: 'controlled' }, model_comparison: { available: true },
  general_research: { available: true, media_types: ['text/plain', 'application/pdf'], max_assets: 5,
    max_file_bytes: 5242880, max_total_bytes: 10485760, max_pdf_pages: 20,
    analysis: { available: false, execution_mode: 'disabled' } } }
const server = spawn(process.execPath, ['serve.mjs', '0'], { cwd: root + 'apps/web',
  env: { PATH: process.env.PATH, BEAN_WEB_API_PORT: '9' }, stdio: ['ignore', 'pipe', 'inherit'] })
const checks = [], contexts = [], errors = [], external = []
const check = (name, condition) => { assert.ok(condition, name); checks.push(name) }
const timeout = (promise, name) => Promise.race([promise, new Promise((_, reject) => {
  const timer = setTimeout(() => reject(new Error(`${name} timed out`)), 10000); timer.unref()
})])
let browser
try {
  const origin = await timeout(new Promise((resolve, reject) => {
    server.stdout.on('data', bytes => { const match = /http:\/\/127\.0\.0\.1:\d+/.exec(String(bytes)); if (match) resolve(match[0]) })
    server.once('error', reject)
    server.once('exit', code => reject(new Error(`Web server exited ${code}`)))
  }), 'web startup')
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || chromium.executablePath(), args: ['--no-sandbox'] })

  async function open(entry = saved, fragment = '', delayedPath = null) {
    const context = await browser.newContext(); contexts.push(context)
    await context.addInitScript(({ store, workspace, entry }) => {
      // Seed once: reload must exercise the app's retained state, not recreate it.
      if (!sessionStorage.getItem('controlled-entry-seeded')) {
        localStorage.setItem(store, JSON.stringify({ [workspace]: entry }))
        sessionStorage.setItem('controlled-entry-seeded', '1')
      }
    }, { store, workspace, entry })
    const page = await context.newPage(), requests = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('request', request => { if (!request.url().startsWith(origin) && !/^(data|blob):/.test(request.url())) external.push(request.url()) })
    let release, observed
    const held = new Promise(resolve => { release = resolve })
    const requested = new Promise(resolve => { observed = resolve })
    const json = (route, data, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) })
    await page.route('**/api/bean/v1/**', async route => {
      const request = route.request(), path = new URL(request.url()).pathname.replace('/api/bean/v1', '')
      requests.push({ method: request.method(), path })
      if (path === delayedPath) { observed(); await held }
      if (path === '/shared-session/current') return json(route, { mode: 'browser_session', authenticated: true,
        credentials: 'server_managed', workspace_id: workspace })
      if (path === '/capabilities') return json(route, caps)
      if (path === `/research-sessions/${saved.sessionId}`) return json(route, snapshot)
      if (path === `/research-assets/${paper.id}`) return json(route, paper)
      if (path === `/workspaces/${workspace}/research-assets` && request.method() === 'POST') {
        const bytes = request.postDataBuffer()
        return json(route, { id: 'asset-unrelated-text', workspace_id: workspace, filename: 'unrelated-notes.txt',
          sha256: createHash('sha256').update(bytes).digest('hex'), byte_size: bytes.length,
          media_type: 'text/plain', pages: [] }, 201)
      }
      return json(route, { code: 'unimplemented_controlled_fixture', message: path }, 404)
    })
    await page.goto(`${origin}/study/${fragment}`, { waitUntil: 'domcontentloaded' })
    return { page, requests, release, requested }
  }
  const ready = page => page.waitForFunction(() => document.getElementById('connection')?.textContent === 'Private workspace'
    && !document.getElementById('resume-study')?.disabled)
  const blank = async page => await page.locator('#start').isVisible()
    && !await page.locator('#paper-editor').isVisible()
    && !await page.locator('#check').isVisible()
    && !await page.locator('#result').isVisible()
    && await page.locator('#question').inputValue() === ''
    && await page.locator('#study-name').textContent() === ''
  const savedReads = requests => requests.filter(r => /^\/(research-sessions|research-assets|research-analyses|model-comparisons)\//.test(r.path))
  const mutations = requests => requests.filter(r => r.method !== 'GET')
  const retained = page => page.evaluate(({ store, workspace }) => JSON.parse(localStorage.getItem(store))[workspace], { store, workspace })

  for (const fragment of ['', '#data']) {
    const { page, requests } = await open(saved, fragment); await ready(page)
    check(`saved paper does not open on ${fragment || 'bare entry'}`, await blank(page))
    check(`fresh ${fragment || 'bare'} entry reads no saved study and dispatches nothing`, !savedReads(requests).length && !mutations(requests).length)
    check(`fresh ${fragment || 'bare'} entry offers explicit resume and preserves saved identity`, await page.locator('#resume-study').isVisible()
      && JSON.stringify(await retained(page)) === JSON.stringify(saved))
  }

  const resumed = await open(saved, '#data'); await ready(resumed.page)
  await resumed.page.locator('#resume-study').click()
  await resumed.page.waitForFunction(() => location.hash === '#check' && !document.getElementById('check').hidden)
  check('explicit resume reads retained paper and shows its pending approval', await resumed.page.locator('#check-title').textContent() === 'Approve the premise check'
    && savedReads(resumed.requests).length === 2 && !mutations(resumed.requests).length)
  await resumed.page.locator('[data-step="data"]').click()
  await resumed.page.locator('#paper-data-title').waitFor({ state: 'visible' })
  check('Data within an explicitly resumed study keeps the reviewed paper', await resumed.page.locator('.paper-source').innerText() === `${paper.filename} · Page 3 · Proposition 3.1`)
  await resumed.page.locator('[data-step="check"]').click()
  await resumed.page.reload({ waitUntil: 'networkidle' })
  check('explicit approval deep link restores on reload with GET only', await resumed.page.locator('#check').isVisible()
    && await resumed.page.locator('#check-title').textContent() === 'Approve the premise check' && !mutations(resumed.requests).length)
  await resumed.page.locator('[data-action="new-study"]').click()
  check('New study is empty and retains previous history', await blank(resumed.page)
    && JSON.stringify(await retained(resumed.page)) === JSON.stringify(saved) && await resumed.page.locator('#resume-study').isVisible())
  const readsBefore = savedReads(resumed.requests).length
  await resumed.page.reload({ waitUntil: 'networkidle' }); await ready(resumed.page)
  check('New study stays empty after reload without restoring old records', await blank(resumed.page) && savedReads(resumed.requests).length === readsBefore)

  for (const path of [`/research-sessions/${saved.sessionId}`, `/research-assets/${paper.id}`, '/capabilities']) {
    const delayed = await open(saved, '#check', path)
    await timeout(delayed.requested, `delayed ${path}`)
    await delayed.page.locator('[data-action="new-study"]').click()
    delayed.release()
    await delayed.page.waitForLoadState('networkidle'); await ready(delayed.page)
    check(`New study survives late ${path} response`, await blank(delayed.page)
      && JSON.stringify(await retained(delayed.page)) === JSON.stringify(saved) && !mutations(delayed.requests).length)
  }

  const choosingSample = await open(saved, '#data', `/research-sessions/${saved.sessionId}`)
  await ready(choosingSample.page)
  await choosingSample.page.locator('#resume-study').click()
  await timeout(choosingSample.requested, 'explicit resume before sample selection')
  await choosingSample.page.locator('[data-action="sample-concentration"]').click()
  await choosingSample.page.locator('#claim-title').waitFor({ state: 'visible' })
  choosingSample.release()
  await choosingSample.page.waitForLoadState('networkidle')
  check('choosing a new sample cancels an in-flight explicit resume', await choosingSample.page.locator('#claim-title').isVisible()
    && !await choosingSample.page.locator('#paper-editor').isVisible()
    && await choosingSample.page.locator('#study-name').textContent() === 'Sample readings'
    && new URL(choosingSample.page.url()).hash === '#data'
    && savedReads(choosingSample.requests).length === 1 && !mutations(choosingSample.requests).length)

  const choosingUpload = await open(saved, '#data', `/research-sessions/${saved.sessionId}`)
  await ready(choosingUpload.page)
  await choosingUpload.page.locator('#resume-study').click()
  await timeout(choosingUpload.requested, 'explicit resume before file selection')
  await choosingUpload.page.setInputFiles('#file', { name: 'unrelated-notes.txt', mimeType: 'text/plain', buffer: Buffer.from('A new study begins while an old request is pending.') })
  await choosingUpload.page.locator('#overview').waitFor({ state: 'visible' })
  choosingUpload.release()
  await choosingUpload.page.waitForLoadState('networkidle')
  check('uploading a different file cancels an in-flight explicit resume', await choosingUpload.page.locator('#overview').isVisible()
    && await choosingUpload.page.locator('#source-list').innerText().then(t => t.includes('unrelated-notes.txt') && !t.includes(paper.filename))
    && !await choosingUpload.page.locator('#paper-editor').isVisible()
    && await choosingUpload.page.locator('[data-action="paper-check"]').count() === 0
    && savedReads(choosingUpload.requests).length === 1 && mutations(choosingUpload.requests).length === 1
    && mutations(choosingUpload.requests)[0].path.endsWith('/research-assets'))

  for (const entry of [{ kind: 'general', analysisId: 'analysis-controlled', assetIds: [paper.id] },
    { kind: 'currents', comparisonId: 'comparison-controlled' }]) {
    const other = await open(entry, '#data'); await ready(other.page)
    check(`${entry.kind} history does not automatically reopen on Data`, await blank(other.page)
      && !savedReads(other.requests).length && !mutations(other.requests).length)
  }

  const unrelated = await open(saved, '#data'); await ready(unrelated.page)
  await unrelated.page.setInputFiles('#file', { name: 'unrelated-notes.txt', mimeType: 'text/plain', buffer: Buffer.from('Unrelated study notes. No numerical lemma or model is stated.') })
  await unrelated.page.locator('#overview').waitFor({ state: 'visible' })
  check('an unrelated upload is not replaced by the saved paper', await unrelated.page.locator('#source-list').innerText().then(t => t.includes('unrelated-notes.txt'))
    && !await unrelated.page.locator('#paper-editor').isVisible() && await unrelated.page.locator('[data-action="paper-check"]').count() === 0)
  check('upload is the only mutation; no prior scientific session is read', mutations(unrelated.requests).length === 1
    && mutations(unrelated.requests)[0].path.endsWith('/research-assets') && !savedReads(unrelated.requests).length)
  check('all scenarios remain local and produce no page exceptions', external.length === 0 && errors.length === 0)
  console.log(JSON.stringify({ status: 'passed', lane: 'controlled_http_ui', checks: checks.length, names: checks,
    live_model_calls: 0, scientific_jobs: 0, actual_backend_qualification: 'not_run_in_this_lane' }, null, 2))
} finally {
  await Promise.all(contexts.map(context => context.close().catch(() => {})))
  await browser?.close()
  server.kill('SIGTERM')
}
