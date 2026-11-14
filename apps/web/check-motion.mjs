// Owner2 presentation acceptance. Offline API failures and labelled DOM probes
// exercise design boundaries; scientific qualification uses check-research.mjs.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || 'playwright')
const output = resolve('var/design-evidence/after'), results = [], external = [], errors = [], writes = []
await mkdir(output, { recursive: true })
const server = spawn(process.execPath, ['apps/web/serve.mjs', '0'], { env: { ...process.env, BEAN_WEB_API_PORT: '9' }, stdio: ['ignore', 'pipe', 'pipe'] })
let browser
const base = await new Promise((yes, no) => {
  const timer = setTimeout(() => no(new Error('Design server did not start')), 8000)
  server.once('error', no); server.stdout.on('data', bytes => { const found = String(bytes).match(/http:\/\/127\.0\.0\.1:\d+/); if (found) { clearTimeout(timer); yes(found[0]) } })
})
const check = (name, detail) => results.push({ name, passed: true, detail })
try {
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || chromium.executablePath(), args: ['--no-sandbox'] })
  for (const [name, width, height] of [['phone', 390, 844], ['small-phone', 320, 760], ['tablet', 834, 1112], ['laptop', 1440, 1000]]) {
    const context = await browser.newContext({ viewport: { width, height }, ...(process.env.BEAN_DESIGN_RECORD_VIDEO === '1' && name === 'laptop' ? { recordVideo: { dir: resolve('var/design-evidence/video'), size: { width: 1440, height: 1000 } } } : {}) })
    const page = await context.newPage()
    const profiler = await context.newCDPSession(page)
    await profiler.send('Performance.enable')
    page.on('pageerror', error => errors.push(error.message))
    page.on('dialog', dialog => dialog.accept())
    await page.addInitScript(() => {
      window.motionCalls = []
      const animate = Element.prototype.animate
      Element.prototype.animate = function (frames, options) {
        window.motionCalls.push({ target: this.id || this.dataset.motionEvent || this.tagName, duration: options?.duration })
        return animate.call(this, frames, options)
      }
    })
    await page.route('**/*', route => {
      const request = route.request(), url = request.url()
      if (!url.startsWith(base + '/') && !/^(data|blob):/.test(url)) { external.push(url); return route.abort() }
      if (request.method() === 'POST') writes.push(url)
      if (url.includes('/api/bean/v1/')) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ code: 'backend_unavailable', message: 'Offline design acceptance: server unavailable.' }) })
      return route.continue()
    })
    await page.goto(base + '/#start'); await page.waitForLoadState('networkidle')
    await page.waitForSelector('html[data-motion="ready"]')
    const beforeMetrics = Object.fromEntries((await profiler.send('Performance.getMetrics')).metrics.map(metric => [metric.name, metric.value]))
    const dimensions = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth, scheme: getComputedStyle(document.documentElement).colorScheme, family: getComputedStyle(document.body).fontFamily }))
    assert.equal(dimensions.scheme, 'dark'); assert.ok(dimensions.scroll <= width + 1, JSON.stringify(dimensions)); assert.match(dimensions.family, /system|Segoe|apple/)
    await page.evaluate(() => scrollTo(0, 0)); await page.screenshot({ path: `${output}/${name}-start.png`, fullPage: true })
    const steps = page.locator('.steps')
    assert.ok((await steps.boundingBox()).width > width * .7)
    // Keyboard navigation keeps the application's heading focus and hidden pages.
    await page.locator('#step-list > li[data-step="inputs"] > a').focus()
    assert.equal(await page.evaluate(() => getComputedStyle(document.activeElement).outlineStyle), 'solid')
    await page.keyboard.press('Enter')
    await page.waitForFunction(() => document.activeElement.id === 'inputs-title')
    assert.equal(await page.locator('.page:not([hidden])').count(), 1)
    await page.waitForFunction(() => window.motionCalls.some(call => call.target === 'inputs'))
    // A real CSV import keeps long names and values readable/scrollable locally.
    const filename = 'reviewed-measurements-with-a-long-instrument-and-experiment-name-'.repeat(3) + '.csv'
    await page.locator('#csv-file').setInputFiles({ name: filename, mimeType: 'text/csv', buffer: Buffer.from('time,concentration,epsilon\n1,4.123456789012345678901234567890,0.5\n2,3.10,0.5\n') })
    await page.getByRole('button', { name: 'Use these rows', exact: true }).click()
    assert.match(await page.locator('#sources').textContent(), /reviewed-measurements/)
    await page.locator('#source-details summary').click()
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
    // Actual validation, not a fabricated scientific failure or result.
    await page.getByLabel('Row 1, concentration', { exact: true }).fill('not a number')
    await page.locator('#measurements button[type="submit"]').click()
    await page.locator('#rows-errors').waitFor({ state: 'visible' })
    assert.equal(await page.evaluate(() => document.activeElement.id), 'rows-errors')
    await page.screenshot({ path: `${output}/${name}-validation.png`, fullPage: true })
    // Native disclosures: keyboard toggle and immediate closed-focus semantics.
    await page.evaluate(() => { location.hash = 'question' })
    const disclosure = page.locator('#question details').first()
    if (await disclosure.count()) {
      await disclosure.locator('summary').focus(); await page.keyboard.press('Enter')
      assert.equal(await disclosure.evaluate(node => node.open), true)
      await page.keyboard.press('Enter'); assert.equal(await disclosure.evaluate(node => node.open), false)
    }
    // Rapid navigation and actual history never leave an outgoing focusable page.
    for (const hash of ['result', 'inputs', 'next', 'question']) { await page.evaluate(hash => { location.hash = hash }, hash); await page.waitForFunction(hash => location.hash === '#' + hash && document.activeElement.id === hash + '-title', hash) }
    await page.goBack(); await page.waitForFunction(() => document.activeElement.id === 'next-title')
    await page.goForward(); await page.waitForFunction(() => document.activeElement.id === 'question-title')
    assert.equal(await page.locator('.page:not([hidden])').count(), 1)
    assert.equal(await page.evaluate(() => Boolean(document.activeElement.closest('[hidden]'))), false)
    // Hold an actual page animation so a cancellation assertion cannot pass
    // merely because its normal220ms duration elapsed before the next RPC.
    const held = await page.evaluate(async () => {
      const ready = new Promise(resolve => addEventListener('hashchange', () => requestAnimationFrame(() => requestAnimationFrame(() => {
        const animation = document.getAnimations().find(item => item.effect?.target?.id === 'inputs')
        if (animation) { animation.pause(); window.motionHeld = animation }
        resolve(Boolean(animation))
      })), { once: true }))
      location.hash = 'inputs'; return ready
    })
    assert.equal(held, true)
    // The live preference change cancels WAAPI as well as CSS motion.
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.waitForFunction(() => window.motionHeld?.playState === 'idle')
    await page.evaluate(() => { window.motionCalls = []; location.hash = 'result' })
    await page.waitForFunction(() => document.activeElement.id === 'result-title')
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
    assert.equal(await page.evaluate(() => document.getAnimations().length), 0)
    assert.equal(await page.evaluate(() => window.motionCalls.length), 0)
    await page.screenshot({ path: `${output}/${name}-empty-result-reduced.png`, fullPage: true })
    await page.emulateMedia({ reducedMotion: 'no-preference' })
    if (name === 'laptop') {
      // Real 2x CSS zoom plus a separate narrow viewport exercise reflow.
      await page.evaluate(() => { document.documentElement.style.zoom = '2'; location.hash = 'inputs' })
      await page.waitForFunction(() => document.activeElement.id === 'inputs-title')
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
      await page.screenshot({ path: `${output}/zoom-200-inputs.png`, fullPage: true })
      await page.evaluate(() => { document.documentElement.style.zoom = '1' })
      const probes = await page.evaluate(async () => {
        // Explicit presentation test fixtures, never appended to a real activity
        // stream or used as evidence. No model/scientific results are invented.
        const region = document.createElement('section'); region.setAttribute('aria-label', 'Design test fixtures'); region.id = 'design-fixtures'
        const list = document.createElement('ol'); list.dataset.motionStream = 'design-test-only'; region.append(list); document.querySelector('main').append(region)
        const frame = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
        const event = id => { const item = document.createElement('li'); item.dataset.motionEvent = id; item.textContent = 'Presentation fixture'; return item }
        list.append(event('existing')); await frame(); const initial = motionCalls.length
        list.append(event('new')); await frame(); const added = motionCalls.length
        list.replaceChildren(event('existing'), event('new')); await frame(); const replayed = motionCalls.length
        const button = document.createElement('button'); button.textContent = 'Download acknowledgement fixture'; region.append(button)
        await frame(); const beforeClick = motionCalls.length; button.click(); await frame(); const click = motionCalls.length
        button.dispatchEvent(new CustomEvent('bean:download-ready', { bubbles: true, detail: { target: button } })); await frame(); const ready = motionCalls.length
        region.remove(); return { initial, added, replayed, beforeClick, click, ready }
      })
      assert.equal(probes.added, probes.initial + 1); assert.equal(probes.replayed, probes.added)
      assert.equal(probes.click, probes.beforeClick); assert.equal(probes.ready, probes.click + 1)
      check('activity-deduplication-and-confirmed-download-hook', probes)
      await page.evaluate(() => {
        const region = document.createElement('section'); region.id = 'disclosure-focus-probe'; region.setAttribute('aria-label', 'Disclosure keyboard regression fixture')
        const details = document.createElement('details'), summary = document.createElement('summary'), inside = document.createElement('button'), after = document.createElement('button')
        details.id = 'focus-details'; details.open = true; summary.textContent = 'Keyboard regression fixture'; inside.id = 'focus-inside'; inside.textContent = 'Inside'; after.id = 'focus-after'; after.textContent = 'After'
        details.append(summary, inside); region.append(details, after); document.querySelector('main').append(region)
      })
      await page.evaluate(async () => { await Promise.all(document.getAnimations().map(animation => animation.finished.catch(() => {}))) })
      // No wait after closing: a delayed focus exclusion is a real regression.
      for (let repeat = 0; repeat < 3; repeat++) {
        await page.evaluate(() => { const details = document.querySelector('#focus-details'); details.open = true; details.querySelector('summary').focus() })
        await page.evaluate(() => { const details = document.querySelector('#focus-details'); details.open = false; details.querySelector('summary').focus() })
        await page.keyboard.press('Tab')
        assert.equal(await page.evaluate(() => document.activeElement.id), 'focus-after')
      }
      await page.evaluate(() => document.querySelector('#disclosure-focus-probe').remove())
      check('closing-disclosure-immediately-excludes-hidden-controls-from-tab-order', 'Normal motion, no post-close delay; repeated rapid open/close.')
    }
    check(`${name}-responsive-keyboard-disclosure-history-validation-reduced-motion`, dimensions)
    const afterMetrics = Object.fromEntries((await profiler.send('Performance.getMetrics')).metrics.map(metric => [metric.name, metric.value]))
    check(`${name}-observed-layout-cost`, { layout_ms: Math.round((afterMetrics.LayoutDuration - beforeMetrics.LayoutDuration) * 1000), style_ms: Math.round((afterMetrics.RecalcStyleDuration - beforeMetrics.RecalcStyleDuration) * 1000), note: 'Observed Chromium renderer cost across the scripted interactions and captures; not a cross-device performance guarantee.' })
    await context.close()
  }
  assert.deepEqual(errors, []); assert.deepEqual(external, []); assert.deepEqual(writes, [])
  const receipt = { status: 'passed', scope: 'Presentation acceptance; offline API and labelled presentation-only probes. Not scientific qualification.', checks: results, external_requests: external, unexpected_writes: writes }
  await writeFile(`${output}/receipt.json`, JSON.stringify(receipt, null, 2)); console.log(JSON.stringify(receipt, null, 2))
} finally {
  await browser?.close()
  server.kill('SIGTERM')
}
