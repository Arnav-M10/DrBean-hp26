// Concentration over time, drawn as SVG markup. Used by the workspace and by the
// downloadable readable report, so both show the same picture. Styling comes from
// the classes below; the page or report supplies the colors.

const model = (p, t) => p.A * (Math.exp(-p.ke * t) - Math.exp(-p.ka * t))

function niceStep(span, count) {
  const raw = span / count
  const power = 10 ** Math.floor(Math.log10(raw))
  return [1, 2, 2.5, 5, 10].map(m => m * power).find(step => span / step <= count) ?? raw
}

const label = value => Number(value.toFixed(2)).toString()
const attr = text => String(text).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])

/**
 * readings: [{t, v, e}] included readings with their hard allowance
 * curves:   [{params: {A, ke, ka}, tone: 'inside' | 'outside', name}]
 * future:   {times: [{t, ranges: [{tone, low, high}], selected}], until}
 */
export function chartSVG({ readings = [], curves = [], future = null, width = 720, height = 360, title = '' } = {}) {
  const left = 52, right = 20, top = 20, bottom = 44
  const lastTime = Math.max(4, ...readings.map(r => r.t), future?.until ?? 0)
  const tMax = lastTime * 1.04
  const peaks = curves.flatMap(c => Array.from({ length: 81 }, (_, i) => model(c.params, tMax * i / 80)))
  const ranges = (future?.times ?? []).flatMap(slot => slot.ranges.map(r => r.high))
  const yMax = Math.max(1, ...readings.map(r => r.v + r.e), ...peaks, ...ranges) * 1.1
  const x = t => left + (t / tMax) * (width - left - right)
  const y = v => height - bottom - (v / yMax) * (height - top - bottom)
  const yStep = niceStep(yMax, 5), xStep = niceStep(lastTime, 8)
  let svg = `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${attr(title)}"><title>${attr(title)}</title>`
  for (let v = 0; v <= yMax + 1e-9; v += yStep) {
    svg += `<line class="grid" x1="${left}" x2="${width - right}" y1="${y(v)}" y2="${y(v)}"/>`
    svg += `<text class="tick" x="${left - 10}" y="${y(v) + 4}" text-anchor="end">${label(v)}</text>`
  }
  for (let t = 0; t <= lastTime + 1e-9; t += xStep) {
    svg += `<text class="tick" x="${x(t)}" y="${height - bottom + 20}" text-anchor="middle">${label(t)}</text>`
  }
  svg += `<text class="axis" x="${left}" y="${top - 6}">mg/L</text>`
  svg += `<text class="axis" x="${width - right}" y="${height - 6}" text-anchor="end">hours after dose</text>`
  for (const c of curves) {
    let d = ''
    for (let i = 0; i <= 160; i++) {
      const t = tMax * i / 160
      d += `${i ? 'L' : 'M'}${x(t).toFixed(2)} ${y(model(c.params, t)).toFixed(2)}`
    }
    svg += `<path class="curve ${c.tone}" d="${d}"/>`
  }
  for (const slot of future?.times ?? []) {
    const offsets = slot.ranges.length > 1 ? [-6, 6] : [0]
    svg += `<g class="slot${slot.selected ? ' selected' : ''}">`
    svg += `<line class="slot-line" x1="${x(slot.t)}" x2="${x(slot.t)}" y1="${top}" y2="${height - bottom}"/>`
    slot.ranges.forEach((r, i) => {
      svg += `<rect class="range ${r.tone}" x="${x(slot.t) + offsets[i] - 3}" y="${y(r.high)}" width="6" height="${Math.max(2, y(r.low) - y(r.high))}"/>`
    })
    svg += `<text class="slot-label" x="${x(slot.t)}" y="${top + 12}" text-anchor="middle">${label(slot.t)} h</text></g>`
  }
  for (const r of readings) {
    const cx = x(r.t), cy = y(r.v), hi = y(r.v + r.e), lo = y(Math.max(0, r.v - r.e))
    const bar = r.e > 0 ? `<path d="M${cx} ${hi}V${lo}M${cx - 5} ${hi}h10M${cx - 5} ${lo}h10"/>` : ''
    svg += `<g class="reading">${bar}<circle cx="${cx}" cy="${cy}" r="4"/></g>`
  }
  return svg + '</svg>'
}
