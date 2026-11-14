// Dr. Bean front page. Fills the study screens on the page from two saved runs (home-data.mjs)
// with the study page's own wording, charts and math, so the page shows what the app showed.
// Nothing here talks to the server: the front page opens no workspace and sends nothing.
import { chartSVG } from './chart.mjs'
import { channelChartSVG } from './channel-chart.mjs'
import { comparisonFinding } from './compare.mjs'
import { page as sym, tex } from './math.mjs'
import { curvesFor, escapeHTML, finding, formatBound, formatRate, nextFinding, nextTable } from './results.mjs'
import { CURRENTS, DOSE, currentsStudy, doseStudy } from './home-data.mjs'

const $ = id => document.getElementById(id)
const dose = doseStudy(), currents = currentsStudy()
const outside = dose.candidates.find(c => c.outside)

// A study saved in this browser (the study page's own storage key): the main button reopens it.
try {
  const saved = Object.values(JSON.parse(localStorage.getItem('dr-bean.study.v1') || '{}'))
  if (saved.some(s => s?.sessionId || s?.analysisId || s?.comparisonId)) document.querySelectorAll('[data-start]').forEach(a => { a.textContent = 'Open your study' })
} catch { /* storage is optional; the button still starts a study */ }

// Symbols in headings and tables
for (const [name, html] of [['m-ke', sym.ke], ['m-ka', sym.ka], ['m-A', sym.A], ['m-chi', sym.chi]]) document.querySelectorAll(`.${name}`).forEach(el => { el.innerHTML = html })

// Hero: the answer screen of the saved check
const f = finding(dose)
$('hero-note').textContent = `Checked ${new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(dose.created))} with Counterdex ${dose.checker.version}`
$('hero-result').innerHTML = f.headline
$('hero-lead').innerHTML = f.lead

// Files and question
$('how-question').textContent = dose.objective

// Exact checks: the rate of the curve outside the claim, as the checker wrote it
const [num, den] = outside.exact.ke.split('/')
$('proof-model').innerHTML = sym.model
// The fraction takes the chart color of the curve outside the claim (--series in styles.css).
$('proof-moment').innerHTML = tex(`k_e = \\textcolor{#7fb0ff}{\\dfrac{${num}}{${den}}} < ${formatBound(dose.claim.low)}\\ \\mathrm{h}^{-1}`, { display: true })
$('proof-line').textContent = `The elimination rate of the curve outside the claim, which stays within the allowance of all ${dose.included.length} readings. The claim starts at ${formatBound(dose.claim.low)} per hour.`
$('proof-search').textContent = `In this study it tried ${dose.search.attempted.toLocaleString('en-US')} combinations of the two rates, found ${dose.search.feasible.toLocaleString('en-US')} that could fit and checked the best ones exactly.`
$('proof-curves').innerHTML = dose.candidates.map(c => `<tr class="${c.tone}"><th scope="row"><span class="swatch" aria-hidden="true"></span>${c.outside ? 'Outside the claim' : 'Inside the claim'}</th>
  <td>${formatRate(c.params.ke)}<div class="exact">${sym.exact(c.exact.ke)}</div></td><td>${formatRate(c.params.ka)}<div class="exact">${sym.exact(c.exact.ka)}</div></td>
  <td>${formatRate(c.params.A)}<div class="exact">${sym.exact(c.exact.A)}</div></td></tr>`).join('')
$('proof-replay').textContent = DOSE.replay

// The next measurement
const nf = nextFinding(dose)
$('measure-result').textContent = nf.headline
$('measure-lead').textContent = nf.lead
$('measure-table').innerHTML = nextTable(dose)

// Electron currents
const cf = comparisonFinding(currents)
$('currents-result').textContent = cf.headline
$('currents-lead').innerHTML = cf.lead
$('currents-cases').innerHTML = CURRENTS.cases.map(([sigma, next]) => `<tr><th scope="row">σ ${escapeHTML(sigma)} µA</th><td>${escapeHTML(next.replace(/^Measure at /, '').replace(/^No listed setting tells them apart at .*$/, 'None of the listed settings'))}</td></tr>`).join('')

// The approval, worded as the study page words it
const times = dose.included.map(r => r.t)
$('approve-facts').innerHTML = [
  ['Readings', `${dose.included.length} readings from ${Math.min(...times)} to ${Math.max(...times)} hours`],
  ['Claim', `${sym.claim(formatBound(dose.claim.low), formatBound(dose.claim.high))}, both ends included`],
  ['Model', sym.modelInline],
  ['What runs', `Counterdex searches for curves that stay within every allowance while putting ${sym.ke} outside the claim, then checks the best ones exactly. If it finds none, that does not prove the claim.`],
].map(([k, v]) => `<tr><th scope="row">${k}</th><td>${v}</td></tr>`).join('')

// Charts are drawn at the width they are shown, so their labels keep the study page's size.
const area = (el, cap) => {
  const width = Math.round(el.getBoundingClientRect().width) || 640
  return { width, height: Math.round(Math.max(200, Math.min(cap, width * 0.52))) }
}
let first = true
function draw() {
  const charts = {
    'hero-chart': el => chartSVG({ readings: dose.included, curves: curvesFor(dose), title: 'Five readings with their allowances and the two curves that fit them', ...area(el, Number(el.dataset.cap)) }),
    'measure-chart': el => chartSVG({ readings: dose.included, curves: curvesFor(dose), title: 'Predicted ranges at the possible times, from the checked comparison', ...area(el, Number(el.dataset.cap)),
      future: { until: dose.next.horizon, times: dose.next.times.map(t => ({ t: t.t, ranges: t.ranges, selected: t.t === dose.next.selected })) } }),
    'currents-chart': el => channelChartSVG({ groups: CURRENTS.groups, title: 'Currents at each collector setting with both fitted predictions', ...area(el, Number(el.dataset.cap)) }),
  }
  for (const [id, svg] of Object.entries(charts)) {
    let markup = svg($(id))
    // The hero's curves draw in once, on the first paint only.
    if (first && id === 'hero-chart') markup = markup.replace('<svg class="chart"', '<svg class="chart draw"').replaceAll('<path class="curve', '<path pathLength="1" class="curve')
    $(id).innerHTML = markup
  }
  first = false
}
draw()
let lastWidth = innerWidth, resizing
addEventListener('resize', () => {
  if (innerWidth === lastWidth) return
  lastWidth = innerWidth
  clearTimeout(resizing); resizing = setTimeout(draw, 150)
})
