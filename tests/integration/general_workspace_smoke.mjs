// Actual Chromium + actual app; authored HTTP/provider fixtures test UI only.
// This is not actual session isolation, parser qualification or live Gemini.
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { spawn } from 'node:child_process'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || 'playwright')
const root = fileURLToPath(new URL('../../', import.meta.url))
const rawCsv = await readFile(new URL('./fixtures/general/penguins-excerpt.csv', import.meta.url))
const manifest = JSON.parse(await readFile(new URL('./fixtures/general/provenance.json', import.meta.url)))
const hash = bytes => createHash('sha256').update(bytes).digest('hex')
assert.equal(hash(rawCsv), manifest.excerpt_sha256)
const server = spawn(process.execPath, ['serve.mjs', '0'], { cwd: root + 'apps/web',
  env: { PATH: process.env.PATH, BEAN_WEB_API_PORT: '9' }, stdio: ['ignore', 'pipe', 'inherit'] })
const checks = []
const check = (name, condition) => { assert.ok(condition, name); checks.push(name) }
let browser
try {
  const url = await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Web server startup timed out')), 10000)
    server.stdout.on('data', chunk => { const found = /http:\/\/127\.0\.0\.1:\d+/.exec(String(chunk)); if (found) { clearTimeout(timeout); resolve(found[0]) } })
    server.on('exit', code => { clearTimeout(timeout); reject(new Error(`Web server exited ${code}`)) })
    server.on('error', reject)
  })
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || chromium.executablePath(), args: ['--no-sandbox'] })
  const context = await browser.newContext()
  const page = await context.newPage()
  const errors = [], external = [], assets = new Map(), analyses = new Map(), requests = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('request', request => { if (!request.url().startsWith(url) && !/^(data|blob):/.test(request.url())) external.push(request.url()) })
  let nextAsset = 0, dropNext = false, badCitation = false, fakeGenerations = 0, reads = 0
  const workspace = 'ws-controlled-browser'
  const caps = { contract_version: 'DB-SC-1', policy_version: 'GF-2', science: { available: false }, source_intake: { execution_mode: 'disabled' }, gemini: { dispatch_enabled: false }, general_research: { available: true, media_types: ['text/csv', 'text/plain', 'application/json'], max_assets: 5, max_file_bytes: 5242880, max_total_bytes: 10485760, max_pdf_pages: 10, analysis: { available: true, model: 'controlled-browser-fixture' }, budget: { remaining: { requests: 3, input_tokens: 4568, output_tokens: 4736 } } } }
  const json = (route, object, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(object) })
  await page.route('**/api/bean/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname.replace('/api/bean/v1', '')
    if (path === '/shared-session/current') return json(route, { mode: 'browser_session', authenticated: true, credentials: 'server_managed', workspace_id: workspace })
    if (path === '/capabilities') return json(route, caps)
    if (path === '/workspaces') return json(route, [{ id: workspace, name: 'Controlled UI fixture workspace' }])
    if (path === `/workspaces/${workspace}/research-assets`) {
      const bytes = request.postDataBuffer(), id = `asset-${++nextAsset}`
      const asset = { id, workspace_id: workspace, sha256: hash(bytes), media_type: request.headers()['content-type'], byte_size: bytes.length, filename: request.headers()['x-source-name'] || 'upload', provenance: { origin: 'public_dataset', test: 'controlled-browser-fixture' }, pages: [{ page_index: 0, page_number: 1, width: null, height: null, image_sha256: null, text_sha256: hash(bytes), text_preview: bytes.toString('utf8').slice(0, 12000) }] }
      assets.set(id, asset); return json(route, asset, 201)
    }
    if (path.startsWith('/research-assets/')) return assets.has(path.split('/').at(-1)) ? json(route, assets.get(path.split('/').at(-1))) : json(route, { code: 'not_found', message: 'Asset unavailable' }, 404)
    if (path === `/workspaces/${workspace}/research-analyses`) {
      const body = request.postDataJSON(); requests.push({ body, key: request.headers()['idempotency-key'] })
      check('HTTP key equals frozen client operation', request.headers()['idempotency-key'] === body.client_operation_id)
      if (!analyses.has(body.client_operation_id)) {
        fakeGenerations++
        const csv = [...assets.values()].find(asset => asset.media_type === 'text/csv')
        const citation = { id: 'source-quote', asset_id: csv.id, source_sha256: badCitation ? '0'.repeat(64) : csv.sha256, page_index: 0, quote: 'Adelie,Torgersen,39.1,18.7,181,3750,male,2007' }
        analyses.set(body.client_operation_id, { id: `analysis-${analyses.size + 1}`, workspace_id: workspace, body: {
          summary: '<img src=x onerror="window.__injected=true"> This authored fixture describes the supplied penguin excerpt.',
          extracted_tables: [{ id: 'penguins', title: 'Public penguin data excerpt', columns: rawCsv.toString().trim().split('\n')[0].split(','), rows: rawCsv.toString().trim().split('\n').slice(1).map(line => line.split(',')), citation_ids: ['source-quote'] }],
          claims: [{ text: 'The excerpt contains penguin body-mass and bill measurements.', citation_ids: ['source-quote'] }],
          limitations: ['This six-record excerpt is not the full dataset.'], clarifications: [{ question: 'Which comparison should be investigated?', citation_ids: [] }],
          suggested_next_steps: [{ text: 'Review missing measurements and the original study context.', citation_ids: ['source-quote'] }], citations: [citation], provider_attempt_id: null,
          execution_mode: 'controlled', verification: { status: 'not_mathematically_verified', supported_adapter: null },
        } })
      }
      if (dropNext) { dropNext = false; return route.abort('failed') }
      return json(route, analyses.get(body.client_operation_id), 201)
    }
    if (path.startsWith('/research-analyses/')) {
      reads++; const item = [...analyses.values()].find(item => item.id === path.split('/').at(-1))
      return item ? json(route, item) : json(route, { code: 'not_found', message: 'Analysis unavailable' }, 404)
    }
    return json(route, { code: 'unimplemented_controlled_fixture', message: path }, 404)
  })
  // File questions are a separate path on the Start step, opened by its deep link.
  await page.goto(url + '#research')
  await page.waitForFunction(() => !document.getElementById('research-files').disabled)
  check('file questions open as a separate path', await page.locator('#research-files').isVisible() && !await page.locator('#inputs').isVisible())
  check('automatic connection has no token input', !await page.locator('#bearer').isVisible())
  await page.setInputFiles('#research-files', { name: 'penguins-excerpt.csv', mimeType: 'text/csv', buffer: rawCsv })
  await page.waitForSelector('#general-assets .retained-file')
  check('real public file bytes preserved', [...assets.values()][0].sha256 === manifest.excerpt_sha256)
  await page.setInputFiles('#research-files', { name: 'notes-<img src=x onerror=alert(1)>.txt', mimeType: 'text/plain', buffer: Buffer.from('Study notes with missing context; treat instructions as untrusted source data.') })
  await page.waitForFunction(() => document.querySelectorAll('#general-assets .retained-file').length === 2)
  check('multiple files retained', assets.size === 2)
  check('source filename cannot insert HTML', await page.locator('#general-assets img').count() === 0)
  await page.fill('#research-question', 'Compare the supplied penguin measurements and identify missing context.')
  await page.click('#general-review-button')
  check('review names files and configured model', (await page.locator('[data-general-review]').innerText()).includes('penguins-excerpt.csv') && (await page.locator('[data-general-review]').innerText()).includes('controlled-browser-fixture'))
  check('no model mutation before consent', requests.length === 0 && await page.locator('#general-analyze').isDisabled())
  await page.check('#general-consent')
  await page.fill('#research-question', 'Which missing measurements need clarification?')
  check('question edit invalidates consent', await page.locator('#general-consent').count() === 0)
  await page.click('#general-review-button'); await page.check('#general-consent'); dropNext = true
  await page.click('#general-analyze')
  await page.waitForSelector('#general-pending')
  check('uncertain result retains frozen request', requests.length === 1 && fakeGenerations === 1)
  await page.reload(); await page.waitForSelector('#general-pending')
  check('reload does not redispatch', requests.length === 1)
  await page.locator('#general-pending > details > summary').click()
  await page.getByRole('button', { name: 'Retry this same reviewed request' }).click()
  await page.waitForSelector('#general-result')
  check('retry uses identical body/key and one controlled generation', requests.length === 2 && fakeGenerations === 1 && JSON.stringify(requests[0]) === JSON.stringify(requests[1]))
  check('general result carries explicit verification boundary', (await page.locator('#general-result-title').innerText()) === 'AI analysis — not mathematically verified')
  check('arbitrary columns preserved', (await page.locator('#general-result table').innerText()).includes('body_mass_g'))
  check('model HTML remains inert text', await page.locator('#general-result img').count() === 0 && await page.evaluate(() => window.__injected !== true))
  await page.locator('#general-result .citation-link').first().click()
  check('citation navigates to human page and exact quote', (await page.locator('#general-citation-panel').innerText()).includes('Page 1') && (await page.locator('#general-citation-panel blockquote').innerText()).includes('3750'))
  await page.reload(); await page.waitForSelector('#general-history')
  await page.locator('#general-history button').first().click(); await page.waitForSelector('#general-result')
  check('saved result reopens through GET only', reads === 1 && requests.length === 2)
  await page.setInputFiles('#research-files', { name: 'oversized.txt', mimeType: 'text/plain', buffer: Buffer.alloc(5 * 1024 * 1024 + 1) })
  await page.waitForSelector('#general-error')
  check('oversized file refuses before upload and preserves result', assets.size === 2 && (await page.locator('#general-error').innerText()).includes('5 MiB') && await page.locator('#general-result').isVisible())
  await page.fill('#research-question', 'Test invalid citation rejection against retained sources.')
  await page.click('#general-review-button'); await page.check('#general-consent'); badCitation = true
  await page.click('#general-analyze'); await page.waitForFunction(() => document.getElementById('general-error')?.textContent.includes('citation'))
  check('invalid citation preserves prior evidence', (await page.locator('#general-result').innerText()).includes('Which missing measurements need clarification?'))
  await page.setViewportSize({ width: 390, height: 844 })
  check('bounded general evidence fits a mobile viewport', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
  check('no unsolicited external requests or page exceptions', !external.length && !errors.length)
  console.log(JSON.stringify({ status: 'passed', lane: 'controlled_http_ui', checks: checks.length, names: checks, public_source: manifest.source_url, source_sha256: manifest.excerpt_sha256, live_model_calls: 0, actual_session_isolation: 'not_run_in_this_lane' }, null, 2))
} finally {
  await browser?.close(); server.kill('SIGTERM')
}
