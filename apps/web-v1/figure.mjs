// Small SVG figure toolkit for the notebook theme. Display only: values are converted to
// floating point for drawing; the exact rationals stay in the tables and records.
const NS = 'http://www.w3.org/2000/svg'

export function el(tag, attributes = {}, parent) {
  const node = document.createElementNS(NS, tag)
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value)
  if (parent) parent.append(node)
  return node
}

// C(t) = A (exp(-ke t) - exp(-ka t)), the supported two-rate model.
export const concentration = (t, { A, ke, ka }) => A * (Math.exp(-ke * t) - Math.exp(-ka * t))

// "n/d" or a decimal string -> number, for drawing only.
export function approx(value) {
  const text = String(value ?? '').trim()
  const fraction = /^(-?\d+)\/(\d+)$/.exec(text)
  if (fraction) return Number(fraction[1]) / Number(fraction[2])
  const number = Number(text)
  return Number.isFinite(number) && text !== '' ? number : NaN
}

export function scales({ width, height, margin, xMax, yMax }) {
  const x = t => margin.left + (t / xMax) * (width - margin.left - margin.right)
  const y = c => height - margin.bottom - (c / yMax) * (height - margin.top - margin.bottom)
  return { x, y }
}

export function curvePath(vector, x, y, tMax, steps = 160) {
  let d = ''
  for (let i = 0; i <= steps; i++) {
    const t = (tMax * i) / steps
    d += `${i ? 'L' : 'M'}${x(t).toFixed(2)},${y(Math.max(0, concentration(t, vector))).toFixed(2)}`
  }
  return d
}

export function axes(svg, { width, height, margin, xMax, yMax, xStep = 1, yStep = 2, x, y, xLabel, yLabel }) {
  const grid = el('g', { class: 'fig-grid' }, svg)
  for (let c = yStep; c <= yMax; c += yStep) el('line', { x1: margin.left, x2: width - margin.right, y1: y(c), y2: y(c) }, grid)
  const axis = el('g', { class: 'fig-axis' }, svg)
  el('line', { x1: margin.left, x2: width - margin.right, y1: y(0), y2: y(0) }, axis)
  el('line', { x1: margin.left, x2: margin.left, y1: y(0), y2: margin.top }, axis)
  for (let t = 0; t <= xMax; t += xStep) el('text', { x: x(t), y: y(0) + 18, 'text-anchor': 'middle' }, axis).textContent = t
  for (let c = 0; c <= yMax; c += yStep) el('text', { x: margin.left - 8, y: y(c) + 4, 'text-anchor': 'end' }, axis).textContent = c
  if (xLabel) el('text', { x: width - margin.right, y: height - 4, 'text-anchor': 'end' }, axis).textContent = xLabel
  if (yLabel) el('text', { x: margin.left, y: margin.top - 10, 'text-anchor': 'start' }, axis).textContent = yLabel
  return axis
}
