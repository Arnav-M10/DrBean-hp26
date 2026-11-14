// Editor-only smoke for the web workspace: local draft entry, validation and export.
// It starts no backend and is NOT an end-to-end science test. The connected path is
// apps/web/check-backend.mjs; deeper HTTP invariants are Owner 5's suite. Its request monitor
// sees browser requests only and cannot prove the backend made no model call.
//   node tests/integration/web_manual_smoke.mjs
// Exit 0: all checks passed. Exit 1: a check failed. Exit 3: unrun (Playwright absent).
import { spawn } from 'node:child_process'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

let chromium
try {
  ({ chromium } = createRequire(import.meta.url)('playwright'))
} catch {
  console.log(JSON.stringify({ status: 'unrun', reason: 'playwright is not installed (npm install in tests/integration)' }))
  process.exit(3)
}

const rational = /^(0|-?[1-9][0-9]*)\/([1-9][0-9]*)$/
const checks = []
const check = (id, ok, detail = '') => { checks.push({ id, passed: Boolean(ok), detail }); return ok }

const web = fileURLToPath(new URL('../../apps/web/', import.meta.url))
const server = spawn(process.execPath, ['serve.mjs', '0'], { cwd: web, stdio: ['ignore', 'pipe', 'inherit'] })
const url = await new Promise((resolve, reject) => {
  server.stdout.on('data', chunk => { const m = /http:\/\/127\.0\.0\.1:\d+/.exec(String(chunk)); if (m) resolve(m[0]) })
  server.on('exit', code => reject(new Error(`serve.mjs exited with ${code}`)))
  setTimeout(() => reject(new Error('serve.mjs did not start within 10 s')), 10000)
})

let browser
try {
  browser = await chromium.launch() // inside try: a missing browser must not leave the web server running
  const context = await browser.newContext({ acceptDownloads: true })
  const page = await context.newPage()
  const external = []
  const errors = []
  page.on('request', request => { if (!request.url().startsWith(url) && !/^(blob|data):/.test(request.url())) external.push(request.url()) })
  page.on('pageerror', error => errors.push(String(error)))
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
  await page.goto(url)

  // Invalid input: a non-number must block progress with a linked, focused error.
  await page.fill('#row-1-time', 'six o\'clock')
  await page.click('#measurements button[type=submit]')
  check('invalid-input-blocks', await page.isVisible('#rows-errors') && !(await page.isVisible('#question')),
    'a non-numeric time shows errors and stays on Inputs')
  check('invalid-input-marked', (await page.getAttribute('#row-1-time', 'aria-invalid')) === 'true', 'aria-invalid set')

  // An accidental empty row is reported with its repair and can be removed deliberately.
  await page.fill('#row-1-time', '')
  await page.click('#add-row')
  await page.click('#measurements button[type=submit]')
  check('empty-row-names-its-repair', (await page.locator('#rows-errors').innerText()).includes('Fill it in or remove it'), 'empty rows are reported, not guessed or dropped')
  await page.getByRole('button', { name: 'Remove row 2' }).click()
  check('empty-row-removable', (await page.locator('#rows tr').count()) === 1, 'the accidental row was removed on request')

  // Manual path with the synthetic example.
  await page.click('#example')
  await page.getByRole('button', { name: 'Replace rows' }).or(page.getByRole('button', { name: 'Use these rows' })).first().click()
  check('example-loaded', (await page.locator('#rows tr').count()) === 5, 'five synthetic rows')
  check('imported-rows-kept-not-deleted', (await page.getByRole('button', { name: /^Remove row/ }).count()) === 0, 'imported rows can be excluded but not removed')
  await page.click('#measurements button[type=submit]')
  await page.waitForSelector('#question:not([hidden])')
  // The shared synthetic example's team-selected domain and claim.
  const bounds = { aMin: '0.001', aMax: '30', keMin: '0.015', keMax: '0.35', kaMin: '0.4', kaMax: '8', targetMin: '0.10', targetMax: '0.17' }
  for (const [id, value] of Object.entries(bounds)) await page.fill(`#${id}`, value)

  // A complete structured draft must not be blocked by a blank free-text goal.
  await page.fill('#allowanceOrigin', 'Team-chosen hard allowance of 0.50 mg/L for the shared synthetic example.')
  await page.fill('#goal', '')
  await page.click('#question-form button[type=submit]')
  await page.waitForSelector('#review:not([hidden])')
  check('blank-goal-not-blocking', await page.isVisible('#review-summary'), 'review reached with an empty goal')
  const review = await page.locator('#review-summary').textContent() // includes the collapsed exact-values disclosure
  check('review-shows-exact-values', review.includes('[3/200, 7/20]') && review.includes('[1/10, 17/100]'),
    'exact normalized bounds are shown in review')
  check('planning-honestly-unavailable', (await page.locator('#review').innerText()).includes('Investigation planning is unavailable'),
    'the page does not pretend a backend exists')

  // Export: scientific inputs are exact strings, never JavaScript numbers.
  const [download] = await Promise.all([page.waitForEvent('download'), page.click('#export-draft')])
  const draft = JSON.parse(await readFile(await download.path(), 'utf8'))
  const scalars = [...draft.rows.flatMap(row => [row.time, row.concentration, row.epsilon]), ...Object.values(bounds).map((_, i) => draft.question[Object.keys(bounds)[i]])]
  check('export-format', draft.format === 'dr-bean-local-draft' && draft.version === 1, `${draft.format} v${draft.version}`)
  check('export-no-floats', scalars.length === 23 && scalars.every(value => typeof value === 'string'), 'every scientific scalar is a string')
  check('export-keeps-source-spelling', draft.question.keMax === '0.35' && draft.rows[3].concentration === '6.80', 'original spellings retained')
  check('export-keeps-provenance', draft.sources.length === 1 && draft.rows.every(row => row.sourceId === 1 && row.original), 'rows keep their source and original values')

  // The web's exact parser produces DB-SC-1 canonical rationals.
  const exact = await page.evaluate(async values => { const { parseExact } = await import('./exact.mjs'); return values.map(parseExact) }, scalars)
  check('exact-canonical', exact.every(value => rational.test(value)), exact.slice(0, 4).join(' '))

  check('no-external-requests', external.length === 0, external.join(' ') || 'no request left 127.0.0.1 (no provider call, offline assets)')
  check('no-page-errors', errors.length === 0, errors.join(' | '))
  check('no-credentials-in-browser-storage', await page.evaluate(() => localStorage.length + sessionStorage.length === 0) && (await context.cookies()).length === 0, 'no cookies or storage')
} catch (error) {
  check('smoke-completed', false, String(error).slice(0, 300))
} finally {
  await browser?.close()
  server.kill()
}
const failed = checks.filter(item => !item.passed)
console.log(JSON.stringify({ status: failed.length ? 'failed' : 'passed', passed: checks.length - failed.length, total: checks.length, checks }, null, 1))
process.exit(failed.length ? 1 : 0)
