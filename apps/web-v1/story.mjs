// The opening worked example: a scroll-driven figure. Every number is from the engine's
// documented synthetic decision example (packages/groundwork_adapter/docs/DECISION_EXAMPLE.md),
// drawn for illustration. Nothing here is computed for, or claims anything about, your data.
import { axes, curvePath, el, scales } from './figure.mjs'

const readings = [[0.25, 4.8], [0.5, 7.2], [1, 8.0], [2, 6.8], [4, 5.7]]
const allowance = 0.5
const reference = { A: 9.138, ke: 0.128425, ka: 3.511811 }
const outside = { A: 8.701219, ke: 0.099409, ka: 3.811024 }
const bands = { time: 8, reference: [3.070818, 3.470818], outside: [3.728225, 4.128225] }
const newReading = 3.270818

const svg = document.getElementById('story-plot')
const steps = [...document.querySelectorAll('.story-steps li')]
const order = steps.map(step => step.dataset.step)

if (svg) {
  const width = 640, height = 420, margin = { top: 34, right: 26, bottom: 44, left: 44 }, xMax = 9, yMax = 10
  const { x, y } = scales({ width, height, margin, xMax, yMax })
  axes(svg, { width, height, margin, xMax, yMax, x, y, xLabel: 'elapsed time (h)', yLabel: 'concentration (mg/L)' })
  const show = (node, step, index) => { node.dataset.show = step; if (index !== undefined) node.style.setProperty('--i', index); return node }

  readings.forEach(([t, c], i) => {
    show(el('line', { class: 'fig-bar', x1: x(t), x2: x(t), y1: y(c - allowance), y2: y(c + allowance) }, svg), 'allowances', i)
  })
  const refPath = show(el('path', { class: 'fig-curve reference', d: curvePath(reference, x, y, xMax) }, svg), 'reference')
  show(el('text', { class: 'fig-tag reference', x: x(2.9), y: y(4.25) }, svg), 'reference').textContent = 'ke ≈ 0.128 · inside the claim'
  const outPath = show(el('path', { class: 'fig-curve outside', d: curvePath(outside, x, y, xMax) }, svg), 'outside')
  show(el('text', { class: 'fig-tag outside', x: x(4.9), y: y(6.35) }, svg), 'outside').textContent = 'ke ≈ 0.099 · outside the claim'
  readings.forEach(([t, c], i) => show(el('circle', { class: 'fig-point', cx: x(t), cy: y(c), r: 5 }, svg), 'points', i))

  show(el('line', { class: 'fig-time', x1: x(bands.time), x2: x(bands.time), y1: y(0), y2: margin.top }, svg), 'bands')
  show(el('line', { class: 'fig-band reference', x1: x(bands.time) - 9, x2: x(bands.time) - 9, y1: y(bands.reference[0]), y2: y(bands.reference[1]) }, svg), 'bands')
  show(el('line', { class: 'fig-band outside', x1: x(bands.time) + 9, x2: x(bands.time) + 9, y1: y(bands.outside[0]), y2: y(bands.outside[1]) }, svg), 'bands')
  show(el('text', { class: 'fig-label', x: x(bands.time) + 20, y: y(1.2), 'text-anchor': 'end' }, svg), 'bands').textContent = 'possible readings at 8 h'

  show(el('circle', { class: 'fig-reading', cx: x(bands.time) - 9, cy: y(newReading), r: 6.5 }, svg), 'reading')
  show(el('line', { class: 'fig-strike', x1: x(bands.time) + 2, x2: x(bands.time) + 16, y1: y(bands.outside[1]) - 4, y2: y(bands.outside[0]) + 4 }, svg), 'reading')
  show(el('line', { class: 'fig-strike', x1: x(bands.time) + 16, x2: x(bands.time) + 2, y1: y(bands.outside[1]) - 4, y2: y(bands.outside[0]) + 4 }, svg), 'reading')
  show(el('text', { class: 'fig-label', x: x(bands.time) - 18, y: y(newReading) + 4, 'text-anchor': 'end' }, svg), 'reading').textContent = 'new reading 3.27 mg/L'

  for (const path of [refPath, outPath]) path.style.setProperty('--len', Math.ceil(path.getTotalLength()))

  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches
  const activate = name => {
    const reached = order.indexOf(name)
    for (const step of steps) step.classList.toggle('is-active', step.dataset.step === name)
    for (const node of svg.querySelectorAll('[data-show]')) node.classList.toggle('on', order.indexOf(node.dataset.show) <= reached)
    svg.classList.toggle('decided', name === 'reading')
  }
  if (reduce || !('IntersectionObserver' in window)) activate(order.at(-1))
  else {
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) if (entry.isIntersecting) activate(entry.target.dataset.step)
    }, { rootMargin: '-45% 0px -45% 0px' })
    for (const step of steps) observer.observe(step)
  }
}
