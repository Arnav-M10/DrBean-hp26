// Dr. Bean front page: a saved run played once on the study's own chart, and the steps a study
// takes. Every value comes from home-data.mjs, a saved run the tests check against its files.
// Nothing here talks to the server: the front page opens no workspace and sends nothing.
import { chartSVG } from './chart.mjs'
import { page as sym, tex } from './math.mjs'
import { curvesFor, formatBound } from './results.mjs'
import { doseStudy } from './home-data.mjs'

const $ = id => document.getElementById(id)
const dose = doseStudy()
const outside = dose.candidates.find(c => c.outside)
const still = matchMedia('(prefers-reduced-motion: reduce)')

// The claim, the exact rate of the curve outside it, and Counterdex's mark, typeset by KaTeX.
const low = formatBound(dose.claim.low), high = formatBound(dose.claim.high)
document.querySelectorAll('.m-claim').forEach(el => { el.innerHTML = sym.claim(low, high) })
const [num, den] = outside.exact.ke.split('/')
// The fraction takes the chart's color for the curve outside the claim (--series in styles.css).
$('note-outside-math').innerHTML = tex(`k_e = \\textcolor{#7fb0ff}{\\tfrac{${num}}{${den}}} < ${low}`)
$('q-mark').innerHTML = tex('\\mathbb{Q}')

// --- The run, on the study's own chart ------------------------------------------------------------
const run = $('run'), box = $('run-chart'), replay = $('replay')
const future = { until: dose.next.horizon, times: dose.next.times.map(t => ({ t: t.t, ranges: t.ranges, selected: t.t === dose.next.selected })) }
function draw() {
  const width = Math.round(box.getBoundingClientRect().width) || 640
  const height = Math.round(Math.max(240, Math.min(360, width * 0.52)))
  box.innerHTML = chartSVG({ readings: dose.included, curves: curvesFor(dose), future, width, height,
    title: 'Five readings with their allowances, two curves that fit them all, and the range each allows at 6 and 8 hours' })
    // A soft light under the curve outside the claim, and path lengths so the curves can draw in.
    .replace(/(<svg[^>]*>)/, '$1<defs><filter id="run-glow" x="-10%" y="-50%" width="120%" height="200%"><feGaussianBlur stdDeviation="5"/></filter></defs>')
    .replace(/<path class="curve outside" d="([^"]+)"\/>/, '<path class="curve glow" filter="url(#run-glow)" pathLength="1" d="$1"/><path class="curve outside" pathLength="1" d="$1"/>')
    .replace('<path class="curve inside"', '<path class="curve inside" pathLength="1"')
  box.querySelectorAll('.reading').forEach((g, i) => g.style.setProperty('--d', `${120 + i * 70}ms`))
}
let ending
function play() {
  if (still.matches) return
  clearTimeout(ending)
  replay.hidden = true
  run.classList.remove('play'); void run.offsetWidth; run.classList.add('play')
  // Once it has played, the plain rules hold the finished picture, so a redraw never replays it.
  ending = setTimeout(() => { run.classList.remove('play'); replay.hidden = false }, 4100)
}
replay.addEventListener('click', play)
draw()
play()

// --- How it works: lines between the steps, and one pass of data through them ---------------------
const wrap = $('flow-wrap'), lines = $('flow-lines')
const ROW = ['files', 'gemini', 'agents', 'approve', 'counterdex', 'report']
let nodes = null
function layout() {
  nodes = null
  if (getComputedStyle(lines).display === 'none') { lines.innerHTML = ''; return }
  const w = wrap.getBoundingClientRect()
  const r = v => Math.round(v * 10) / 10
  const at = name => {
    const b = wrap.querySelector(`[data-node="${name}"]`).getBoundingClientRect()
    return { l: b.left - w.left, r: b.right - w.left, b: b.bottom - w.top, x: (b.left + b.right) / 2 - w.left, y: (b.top + b.bottom) / 2 - w.top }
  }
  const n = Object.fromEntries([...ROW, 'comparison'].map(k => [k, at(k)]))
  const paths = [
    ...ROW.slice(0, -1).map((k, i) => `M${r(n[k].r + 4)} ${r(n[k].y)}H${r(n[ROW[i + 1]].l - 12)}`),
    `M${r(n.approve.x)} ${r(n.approve.b + 4)}V${r(n.comparison.y)}H${r(n.comparison.l - 12)}`,
    `M${r(n.comparison.r + 4)} ${r(n.comparison.y)}H${r(n.report.x)}V${r(n.report.b + 12)}`,
  ]
  const dot = id => `<g id="${id}" opacity="0"><circle class="pulse-halo" r="10" filter="url(#pulse-glow)"/><circle class="pulse-core" r="4.5"/></g>`
  lines.setAttribute('viewBox', `0 0 ${r(w.width)} ${r(w.height)}`)
  lines.innerHTML = '<defs><marker id="flow-head" viewBox="0 0 10 10" refX="0" refY="5" markerWidth="10" markerHeight="10" markerUnits="userSpaceOnUse" orient="auto"><path class="flow-head" d="M0 0L10 5L0 10Z"/></marker>'
    + '<filter id="pulse-glow" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="4"/></filter></defs>'
    + paths.map(d => `<path class="flow-line" d="${d}" marker-end="url(#flow-head)"/>`).join('') + dot('pulse-main') + dot('pulse-branch')
  nodes = n
}
function light(name) {
  const step = wrap.querySelector(`[data-node="${name}"]`)
  step.classList.add('lit')
  setTimeout(() => step.classList.remove('lit'), 700)
}
// One pass from your files to the report, lighting each step as it arrives; a second dot takes
// the comparison branch from the approval.
function pulse() {
  if (!nodes || still.matches) return
  const n = nodes, x0 = n.files.x, x1 = n.report.x, y = n.files.y, duration = 2800
  const when = x => (x - x0) / (x1 - x0) * duration
  $('pulse-main').animate([
    { transform: `translate(${x0}px, ${y}px)`, opacity: 0 },
    { transform: `translate(${x0 + (x1 - x0) * 0.04}px, ${y}px)`, opacity: 1, offset: 0.04 },
    { transform: `translate(${x1 - (x1 - x0) * 0.04}px, ${y}px)`, opacity: 1, offset: 0.96 },
    { transform: `translate(${x1}px, ${y}px)`, opacity: 0 },
  ], { duration, easing: 'linear' })
  for (const k of ROW) setTimeout(() => light(k), when(n[k].x))
  const points = [[n.approve.x, n.approve.y], [n.approve.x, n.comparison.y], [n.report.x, n.comparison.y], [n.report.x, n.report.y]]
  const lengths = points.slice(1).map((p, i) => Math.hypot(p[0] - points[i][0], p[1] - points[i][1]))
  const total = lengths.reduce((a, b) => a + b, 0), speed = (x1 - x0) / duration
  let walked = 0
  const frames = points.map((p, i) => {
    if (i) walked += lengths[i - 1]
    return { transform: `translate(${p[0]}px, ${p[1]}px)`, offset: walked / total, opacity: i === 0 || i === points.length - 1 ? 0 : 1 }
  })
  setTimeout(() => {
    $('pulse-branch').animate(frames, { duration: total / speed, easing: 'linear' })
    setTimeout(() => light('comparison'), (lengths[0] + n.comparison.x - n.approve.x) / speed)
  }, when(n.approve.x))
}
layout()
document.fonts?.ready.then(layout)
let passed = false
new IntersectionObserver((entries, observer) => {
  if (passed || !entries.some(e => e.isIntersecting)) return
  passed = true
  observer.disconnect()
  setTimeout(pulse, 250)
}, { threshold: 0.6 }).observe(wrap)

// Charts and lines are drawn at the size they are shown, so text keeps the study page's sizes.
let lastWidth = innerWidth, resizing
addEventListener('resize', () => {
  if (innerWidth === lastWidth) return
  lastWidth = innerWidth
  clearTimeout(resizing)
  resizing = setTimeout(() => { draw(); layout() }, 150)
})
