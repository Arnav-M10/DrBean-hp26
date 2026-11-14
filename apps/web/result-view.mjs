// Presentation only. Every value drawn here comes from a server record that the
// caller already retrieved; this module never computes a scientific verdict.
// Decimal approximations are for reading; exact rationals stay in disclosures.

const SVG = 'http://www.w3.org/2000/svg'

export function toNumber(exact) {
  if (exact === null || exact === undefined || exact === '') return NaN
  const text = String(exact)
  const slash = text.indexOf('/')
  if (slash < 0) return Number(text)
  return Number(text.slice(0, slash)) / Number(text.slice(slash + 1))
}

export function readable(exact, digits = 3) {
  const value = typeof exact === 'number' ? exact : toNumber(exact)
  if (!Number.isFinite(value)) return String(exact ?? '—')
  if (value === 0) return '0'
  const magnitude = Math.abs(value)
  if (magnitude >= 1e5 || magnitude < 1e-3) return value.toExponential(2)
  return Number(value.toPrecision(digits)).toString()
}

// Plain-language reading of a baseline or follow-up result, built from the
// outcome and checking states the server recorded.
export function interpretResult(result) {
  const checked = result.verification === 'valid' && result.expected_binding === 'matches' && result.replay === 'passed'
  if (['review', 'recheck'].includes(result.native_replay?.operation)) {
    const rows = result.candidate_results ?? []
    const excluded = rows.filter(row => row.verification === 'invalid').length
    const compatible = rows.filter(row => row.verification === 'valid').length
    if (!checked) return { tone: 'incomplete', state: ['bad', 'Recheck incomplete'], statement: 'The recheck did not finish with matching evidence, so it does not support a conclusion yet.' }
    const statement = excluded === rows.length && rows.length
      ? 'The new reading rules out both candidates that were being compared.'
      : excluded ? `The new reading rules out ${excluded} of the ${rows.length} candidates being compared; ${compatible} still fit${compatible === 1 ? 's' : ''}.`
        : 'Both candidates still fit after the new reading.'
    return { tone: excluded ? 'challenged' : 'none', state: ['ok', 'Recheck complete'], statement,
      uncertain: 'Only these two candidates were rechecked. Other parameter values were not re-examined, and ruling out both does not show the model is wrong.' }
  }
  switch (result.scientific_outcome) {
    case 'certified_counterexample':
      if (!checked) break
      return { tone: 'challenged', state: ['ok', 'Checked'], statement: 'Your measurements do not force the claim. The checker found parameter values that fit every included reading within its allowance, yet put the elimination rate outside the claimed range.',
        uncertain: 'This does not tell you the true elimination rate or that the model is right. It shows only that, under these allowances and search limits, the claim is not the only possibility.' }
    case 'no_counterexample_found':
      return { tone: 'none', state: ['off', 'Nothing found'], statement: 'The bounded search found no parameter values that fit the readings and fall outside the claim.',
        uncertain: 'This is not proof of the claim. A search with limits can miss a counterexample.' }
    case 'numerical_candidate':
      return { tone: 'incomplete', state: ['wait', 'Not checked'], statement: 'The search found a numerical candidate, but it was not confirmed by exact checking.',
        uncertain: 'A numerical fit alone is not a checked counterexample. Treat this as a lead only.' }
    case 'unsupported':
      return { tone: 'incomplete', state: ['off', 'Unsupported'], statement: 'The configured checker does not support this investigation, so no scientific conclusion was reached.' }
  }
  return { tone: 'incomplete', state: ['wait', 'Incomplete'], statement: 'Checking did not finish successfully, so this result does not support a conclusion.',
    uncertain: 'Incomplete checking never proves the claim. Inspect the technical states below.' }
}

function svg(tag, attributes = {}, text) {
  const node = document.createElementNS(SVG, tag)
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value)
  if (text !== undefined) node.textContent = text
  return node
}

function niceTicks(min, max, count = 5) {
  const span = max - min || 1
  const step = 10 ** Math.floor(Math.log10(span / count))
  const err = (span / count) / step
  const unit = step * (err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1)
  const ticks = []
  for (let value = Math.ceil(min / unit) * unit; value <= max + unit * 1e-9; value += unit) ticks.push(Number(value.toPrecision(10)))
  return ticks
}

// ke number line: the claim band, the searched domain and every candidate.
export function keLine({ domain, target, candidates }) {
  const lo = toNumber(domain.lower), hi = toNumber(domain.upper)
  const tLo = toNumber(target.lower), tHi = toNumber(target.upper)
  if (![lo, hi, tLo, tHi].every(Number.isFinite) || hi <= lo) return null
  const width = narrow() ? 380 : 640, left = 16, right = 16, axisY = 84
  const x = value => left + (Math.min(Math.max(value, lo), hi) - lo) / (hi - lo) * (width - left - right)
  const root = svg('svg', { viewBox: `0 0 ${width} 126`, role: 'img', 'aria-labelledby': 'ke-line-title ke-line-desc' })
  root.append(svg('title', { id: 'ke-line-title' }, 'Elimination rate ke: claimed range and checked candidates'))
  const described = candidates.map(c => `${c.id} at ke ≈ ${readable(c.ke)} per hour, ${c.outside ? 'outside' : 'inside'} the claim`).join('; ')
  root.append(svg('desc', { id: 'ke-line-desc' }, `Searched ke from ${readable(lo)} to ${readable(hi)} per hour. Claimed range ${readable(tLo)} to ${readable(tHi)} per hour. ${described}.`))
  root.append(svg('rect', { class: 'claim-band', x: x(tLo), y: axisY - 26, width: Math.max(2, x(tHi) - x(tLo)), height: 34 }))
  root.append(svg('line', { class: 'claim-edge', x1: x(tLo), x2: x(tLo), y1: axisY - 26, y2: axisY + 8 }))
  root.append(svg('line', { class: 'claim-edge', x1: x(tHi), x2: x(tHi), y1: axisY - 26, y2: axisY + 8 }))
  const mid = (x(tLo) + x(tHi)) / 2
  root.append(svg('text', { class: 'claim-label', x: mid, y: axisY - 30, 'text-anchor': 'middle' }, 'Claimed range'))
  root.append(svg('line', { class: 'axis', x1: left, x2: width - right, y1: axisY, y2: axisY }))
  for (const tick of niceTicks(lo, hi, narrow() ? 4 : 6)) {
    root.append(svg('line', { class: 'axis', x1: x(tick), x2: x(tick), y1: axisY, y2: axisY + 5 }))
    root.append(svg('text', { class: 'tick', x: x(tick), y: axisY + 19, 'text-anchor': 'middle' }, readable(tick)))
  }
  root.append(svg('text', { class: 'axis-label', x: width - right, y: axisY + 38, 'text-anchor': 'end' }, 'ke, elimination rate (per hour)'))
  candidates.forEach((candidate, index) => {
    const cx = x(candidate.ke), labelY = 12 + (index % 3) * 14
    root.append(svg('line', { x1: cx, x2: cx, y1: labelY + 3, y2: axisY - 9, stroke: candidate.color, 'stroke-width': 1, 'stroke-dasharray': '2 2' }))
    root.append(svg('circle', { cx, cy: axisY - 9, r: 6, fill: candidate.color, stroke: '#fff', 'stroke-width': 2 }))
    const anchor = cx > width - 110 ? 'end' : cx < 110 ? 'start' : 'middle'
    root.append(svg('text', { class: 'label', x: anchor === 'end' ? cx - 4 : anchor === 'start' ? cx + 4 : cx, y: labelY, 'text-anchor': anchor, fill: candidate.color }, `${candidate.short} · ke ≈ ${readable(candidate.ke)}`))
  })
  return root
}

// Concentration over time: readings with allowance whiskers and candidate curves.
export function concentrationChart({ rows, curves = [], markTime = null, height = 300 }) {
  const included = rows.filter(row => Number.isFinite(row.t) && Number.isFinite(row.c))
  if (!included.length) return null
  const width = narrow() ? 380 : 640, pad = { l: 44, r: 12, t: 14, b: 44 }
  const tMax = Math.max(...included.map(r => r.t), markTime ?? 0, ...curves.map(c => c.until ?? 0)) * 1.05
  const curveFns = curves.map(curve => ({ ...curve, f: t => curve.A * (Math.exp(-curve.ke * t) - Math.exp(-curve.ka * t)) }))
  const samples = curveFns.map(curve => Array.from({ length: 121 }, (_, i) => { const t = tMax * i / 120; return [t, curve.f(t)] }))
  const cMax = Math.max(...included.map(r => r.c + (r.e || 0)), ...samples.flat().map(([, c]) => c)) * 1.08
  if (!(tMax > 0) || !(cMax > 0) || !Number.isFinite(tMax) || !Number.isFinite(cMax)) return null
  const x = t => pad.l + t / tMax * (width - pad.l - pad.r)
  const y = c => height - pad.b - Math.max(0, c) / cMax * (height - pad.t - pad.b)
  const root = svg('svg', { viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-labelledby': 'conc-title conc-desc' })
  root.append(svg('title', { id: 'conc-title' }, 'Concentration over time'))
  root.append(svg('desc', { id: 'conc-desc' }, `${included.length} readings with their allowances${curves.length ? ` and ${curves.length} candidate curve${curves.length === 1 ? '' : 's'}` : ''}. Time axis 0 to ${readable(tMax)} hours; concentration axis 0 to ${readable(cMax)} mg/L.`))
  for (const tick of niceTicks(0, cMax, 5)) {
    root.append(svg('line', { class: 'grid', x1: pad.l, x2: width - pad.r, y1: y(tick), y2: y(tick) }))
    root.append(svg('text', { class: 'tick', x: pad.l - 8, y: y(tick) + 4, 'text-anchor': 'end' }, readable(tick)))
  }
  for (const tick of niceTicks(0, tMax, narrow() ? 4 : 7)) {
    root.append(svg('line', { class: 'axis', x1: x(tick), x2: x(tick), y1: height - pad.b, y2: height - pad.b + 5 }))
    root.append(svg('text', { class: 'tick', x: x(tick), y: height - pad.b + 18, 'text-anchor': 'middle' }, readable(tick)))
  }
  root.append(svg('line', { class: 'axis', x1: pad.l, x2: width - pad.r, y1: height - pad.b, y2: height - pad.b }))
  root.append(svg('text', { class: 'axis-label', x: (pad.l + width - pad.r) / 2, y: height - 6, 'text-anchor': 'middle' }, 'Elapsed time (hours)'))
  root.append(svg('text', { class: 'axis-label', x: 12, y: pad.t + 2, transform: `rotate(-90 12 ${pad.t + 2})`, 'text-anchor': 'end' }, 'Concentration (mg/L)'))
  if (markTime !== null && Number.isFinite(markTime)) {
    root.append(svg('line', { class: 'marker-time', x1: x(markTime), x2: x(markTime), y1: pad.t, y2: height - pad.b }))
    root.append(svg('text', { class: 'label', x: x(markTime) - 6, y: pad.t + 12, 'text-anchor': 'end' }, `Suggested reading at ${readable(markTime)} h`))
  }
  curveFns.forEach((curve, index) => {
    const d = samples[index].map(([t, c], i) => `${i ? 'L' : 'M'}${x(t).toFixed(1)},${y(c).toFixed(1)}`).join('')
    root.append(svg('path', { d, fill: 'none', stroke: curve.color, 'stroke-width': 2.25, 'stroke-dasharray': curve.dash ? '7 5' : 'none' }))
  })
  for (const row of included) {
    const cx = x(row.t)
    if (row.e > 0) {
      for (const [a, b] of [[y(row.c - row.e), y(row.c + row.e)]]) root.append(svg('line', { class: 'whisker', x1: cx, x2: cx, y1: a, y2: b }))
      for (const edge of [row.c - row.e, row.c + row.e]) root.append(svg('line', { class: 'whisker', x1: cx - 5, x2: cx + 5, y1: y(edge), y2: y(edge) }))
    }
    root.append(svg('circle', { class: row.included === false ? 'excluded-reading' : 'reading', cx, cy: y(row.c), r: 3.75 }))
  }
  return root
}

// Bean red is reserved for the claim, so candidates never use it.
export const CANDIDATE_COLORS = ['#1f4f8a', '#b25b0e', '#1c6740', '#5b3f8f']
const narrow = () => (globalThis.innerWidth ?? 1024) < 640
