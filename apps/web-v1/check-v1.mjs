// Real-browser check of front end v1 against the real API, worker and engine:
// story choreography, page transitions, a real baseline with its drawn figure, dark mode,
// reduced motion and a narrow screen. No fixtures stand in for science; no provider calls.
//   BEAN_COUNTERDEX_PYTHON=/abs/python3.11 node apps/web-v1/check-v1.mjs [--screens DIR]
// Exit 0 passed, 1 failed, 3 unrun (Playwright or runtime missing).
import { spawn } from 'node:child_process'
import { access, mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'node:net'
import { randomBytes } from 'node:crypto'
import { createRequire } from 'node:module'

const unrun = reason => { console.log(JSON.stringify({ status: 'unrun', reason })); process.exit(3) }
let chromium
try { ({ chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || 'playwright')) } catch { unrun('playwright is not installed') }
const root = fileURLToPath(new URL('../../', import.meta.url))
const python = process.env.BEAN_TEST_PYTHON || resolve(root, '.venv/bin/python')
const engine = process.env.BEAN_COUNTERDEX_PYTHON || resolve(root, '.venv-engine/bin/python')
for (const path of [python, engine]) await access(path).catch(() => unrun(`${path} is missing: run scripts/dev/setup.sh`))
const screens = process.argv.includes('--screens') ? process.argv[process.argv.indexOf('--screens') + 1] : null

const checks = []
const check = (id, ok, detail = '') => checks.push({ id, passed: Boolean(ok), detail: String(detail).slice(0, 240) })
const temp = await mkdtemp(join(tmpdir(), 'drbean-v1-'))
const token = randomBytes(40).toString('hex')
const freePort = async () => { const s = createServer(); await new Promise(r => s.listen(0, '127.0.0.1', r)); const p = s.address().port; await new Promise(r => s.close(r)); return p }
const apiPort = await freePort(), webPort = await freePort(), base = `http://127.0.0.1:${webPort}`
const env = { PATH: process.env.PATH, PYTHONPATH: join(root, 'apps/api'), BEAN_DATABASE_PATH: join(temp, 'db.sqlite'), BEAN_BLOB_DIR: join(temp, 'sources'),
  BEAN_ARTIFACT_DIR: join(temp, 'artifacts'), BEAN_AUTH_TOKENS_JSON: JSON.stringify({ v1: token }), BEAN_SCIENCE_ADAPTER: 'counterdex',
  BEAN_COUNTERDEX_PYTHON: engine, BEAN_WEB_API_PORT: String(apiPort) }
const children = []
const start = (cmd, args) => { const c = spawn(cmd, args, { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] }); c.output = ''; for (const s of [c.stdout, c.stderr]) s.on('data', d => { c.output = (c.output + d).slice(-8000) }); children.push(c); return c }
const until = async (probe, what, ms = 90000) => { for (const end = Date.now() + ms; Date.now() < end;) { const v = await probe(); if (v) return v; await new Promise(r => setTimeout(r, 200)) } throw new Error(`timed out: ${what}`) }
const api = async path => { const r = await fetch(`${base}/api/bean/v1${path}`, { headers: { Authorization: `Bearer ${token}` } }); if (!r.ok) throw new Error(`${r.status} ${path}`); return r.json() }

let browser
try {
  const server = start(python, ['-m', 'uvicorn', 'bean_api.main:create_app', '--factory', '--host', '127.0.0.1', '--port', String(apiPort)])
  start(process.execPath, ['apps/web-v1/serve.mjs', String(webPort)])
  await until(async () => { if (server.exitCode !== null) throw new Error(server.output); return api('/capabilities').catch(() => undefined) }, 'API', 30000)
  start(python, ['-m', 'bean_api.worker'])
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || chromium.executablePath(), args: ['--no-sandbox'] })

  // Story: marks appear step by step and are all present by the last step.
  const context = await browser.newContext({ viewport: { width: 1280, height: 860 } })
  const page = await context.newPage(), errors = [], external = []
  page.on('pageerror', e => errors.push(e.message))
  await page.route('**/*', r => { const u = r.request().url(); if (!u.startsWith(base) && !/^(data|blob):/.test(u)) { external.push(u); return r.abort() } return r.continue() })
  await page.goto(base)
  const visible = () => page.evaluate(() => document.querySelectorAll('#story-plot .on').length)
  check('story-starts-empty', (await visible()) === 0, 'no marks before scrolling')
  const counts = []
  for (const step of ['points', 'reference', 'bands', 'reading']) {
    await page.locator(`.story-steps li[data-step="${step}"]`).scrollIntoViewIfNeeded()
    await page.evaluate(() => scrollBy(0, 1))
    await until(async () => (await page.locator(`.story-steps li[data-step="${step}"].is-active`).count()) > 0, `step ${step}`, 8000)
    counts.push(await visible())
  }
  check('story-builds-step-by-step', counts.every((n, i) => !i || n > counts[i - 1]), counts.join(' < '))
  check('story-ends-decided', await page.locator('#story-plot.decided').count() === 1, '')
  if (screens) await page.screenshot({ path: join(screens, 'v1-story.png') })

  // Notebook pages turn with a view transition; the story steps aside on inner pages.
  await page.evaluate(() => document.getElementById('notebook').scrollIntoView())
  await page.locator('#connection-panel summary').click()
  await page.fill('#bearer', token)
  await page.getByRole('button', { name: 'Connect', exact: true }).click()
  await page.waitForFunction(() => document.querySelector('#connection-status').textContent.includes('Connected'))
  await page.fill('#workspace-name', 'Front end v1 check')
  await page.getByRole('button', { name: 'Create workspace', exact: true }).click()
  await page.waitForFunction(() => document.querySelector('#workspace-select').value !== '')
  const transitions = await page.evaluate(() => { window.__vt = 0; const real = document.startViewTransition?.bind(document); if (real) document.startViewTransition = cb => { window.__vt++; return real(cb) }; return Boolean(real) })
  await page.click('.workspace-nav a[href="#inputs"]')
  await until(async () => !(await page.locator('#inputs').isHidden()), 'inputs page')
  check('page-turn-uses-view-transition', !transitions || await page.evaluate(() => window.__vt) === 1, transitions ? 'startViewTransition called once' : 'browser lacks view transitions; plain route')
  check('story-hidden-on-inner-pages', await page.locator('#story').isHidden(), '')

  // A real baseline through the shared logic, then the drawn figure.
  await page.click('#example'); await page.getByRole('button', { name: 'Use these rows', exact: true }).click()
  await page.click('#measurements button[type=submit]')
  const fields = { 'experiment-id': 'v1_synthetic', 'time-origin': 'Elapsed hours from synthetic t=0', aMin: '0.001', aMax: '30', keMin: '0.015', keMax: '0.35', kaMin: '0.4', kaMax: '8', targetMin: '0.10', targetMax: '0.17', allowanceOrigin: 'Team-selected synthetic hard bound of 0.50 mg/L' }
  for (const [id, value] of Object.entries(fields)) await page.fill(`#${id}`, value)
  await page.selectOption('#dataset-origin', 'synthetic')
  await page.click('#question-form button[type=submit]')
  await page.getByRole('button', { name: 'Save inputs and prepare plan' }).click()
  await page.waitForSelector('#approve-scope'); await page.check('#approve-scope')
  await page.getByRole('button', { name: 'Approve reviewed plan' }).click()
  await page.getByRole('button', { name: 'Plan approved', exact: true }).waitFor()
  await page.getByRole('button', { name: 'Queue approved manual run' }).click()
  await page.waitForSelector('[aria-label="Computed candidate parameters"] tbody tr', { timeout: 120000 })
  await page.waitForSelector('.notebook-figure path.fig-curve', { timeout: 10000 })
  const curves = await page.locator('.notebook-figure path.fig-curve').count(), rows = await page.locator('[aria-label="Computed candidate parameters"] tbody tr').count()
  check('figure-draws-one-curve-per-candidate', curves === rows && curves >= 1, `${curves} curve(s), ${rows} candidate row(s)`)
  check('figure-says-it-is-a-drawing', /a curve is not a check/.test(await page.locator('.notebook-figure figcaption').textContent()), '')
  const legend = await page.locator('.figure-legend').textContent()
  check('figure-labels-each-candidate-against-the-draft-claim', /inside your draft's claim/.test(legend) && /outside your draft's claim/.test(legend), legend)
  const inks = await page.evaluate(() => [...document.querySelectorAll('.notebook-figure path.fig-curve')].map((p, i) => [p.classList.contains('reference'), /inside your draft/.test(document.querySelectorAll('.figure-legend span')[i].textContent)]))
  check('figure-ink-follows-the-claim', inks.every(([blue, inside]) => blue === inside), 'blue exactly when inside the claim')
  check('figure-added-once', await page.locator('.notebook-figure').count() === 1, '')
  if (screens) await page.screenshot({ path: join(screens, 'v1-results.png'), fullPage: true })

  await page.setViewportSize({ width: 390, height: 820 })
  for (const hash of ['investigations', 'inputs', 'research']) {
    await page.evaluate(h => { location.hash = h }, hash); await page.waitForTimeout(400)
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    // Name the widest offender: the deepest element whose removal brings the page back to width.
    const culprits = overflow > 1 ? await page.evaluate(() => {
      const width = () => document.documentElement.scrollWidth - document.documentElement.clientWidth
      let node = document.body, path = []
      for (let depth = 0; depth < 14; depth++) {
        const guilty = [...node.children].find(c => { const d = c.style.display; c.style.display = 'none'; const fixed = width() <= 1; c.style.display = d; return fixed })
        if (!guilty) break
        node = guilty; path.push(`${node.tagName.toLowerCase()}${node.id ? '#' + node.id : ''}${node.classList.length ? '.' + [...node.classList].join('.') : ''}`)
      }
      return path.slice(-3).join(' > ')
    }) : ''
    check(`narrow-${hash}-no-overflow`, overflow <= 1, `${overflow}px ${culprits}`)
  }
  check('no-page-errors', errors.length === 0, errors.join(' | '))
  check('no-external-requests', external.length === 0, external.join(' '))
  check('zero-provider-attempts', (await api(`/workspaces/${await page.locator('#workspace-select').inputValue()}/provider-attempts`)).length === 0, '')

  // Dark mode and reduced motion: everything readable and present without animation.
  const quiet = await browser.newContext({ viewport: { width: 1280, height: 860 }, colorScheme: 'dark', reducedMotion: 'reduce' })
  const still = await quiet.newPage(); await still.goto(base)
  const marks = await still.evaluate(() => [document.querySelectorAll('#story-plot [data-show]').length, document.querySelectorAll('#story-plot .on').length])
  check('reduced-motion-shows-the-whole-figure', marks[0] > 0 && marks[0] === marks[1], `${marks[1]}/${marks[0]} marks`)
  const ink = await still.evaluate(() => getComputedStyle(document.body).backgroundColor)
  check('dark-mode-uses-dark-paper', ink === 'rgb(19, 21, 26)', ink)
  if (screens) await still.screenshot({ path: join(screens, 'v1-dark-reduced.png') })
} catch (error) {
  check('check-completed', false, `${error.stack ?? error}`.slice(0, 600))
} finally {
  await browser?.close()
  for (const c of children) if (c.exitCode === null) c.kill('SIGTERM')
  await Promise.all(children.map(c => new Promise(r => c.exitCode !== null ? r() : c.once('exit', r))))
  await rm(temp, { recursive: true, force: true })
}
for (const c of checks) console.log(`  ${c.passed ? 'ok  ' : 'FAIL'} ${c.id}  ${c.detail}`)
const failed = checks.filter(c => !c.passed)
console.log(`${failed.length ? 'failed' : 'passed'}: ${checks.length - failed.length}/${checks.length}`)
process.exit(failed.length ? 1 : 0)
