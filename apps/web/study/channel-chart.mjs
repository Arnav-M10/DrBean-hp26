// Currents by collector setting, drawn as SVG markup in the same style as the concentration
// chart. Each setting is one slot: a measured current with its ±σ bar, and each model's value
// as a short mark, or as a band when a noise width is given.

function niceStep(span, count) {
  const raw = span / count
  const power = 10 ** Math.floor(Math.log10(raw))
  return [1, 2, 2.5, 5, 10].map(m => m * power).find(step => span / step <= count) ?? raw
}
const label = value => Number(value.toPrecision(3)).toString()
const attr = text => String(text).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])

/**
 * groups: [{ label: [line1, line2], observed?: { v, e }, marks: [{ tone: 'iso' | 'bi', v, low?, high? }], selected? }]
 */
export function channelChartSVG({ groups = [], width = 720, height = 320, title = '', unit = 'µA' } = {}) {
  const left = 56, right = 12, top = 22, bottom = 50
  const values = groups.flatMap(g => [...(g.observed ? [g.observed.v + g.observed.e, g.observed.v - g.observed.e] : []), ...g.marks.flatMap(k => [k.high ?? k.v, k.low ?? k.v])])
  const yMin = Math.min(0, ...values), yMax = Math.max(yMin + 1e-12, ...values) * 1.1
  const slot = (width - left - right) / Math.max(1, groups.length)
  const x = i => left + slot * (i + 0.5)
  const y = v => height - bottom - ((v - yMin) / (yMax - yMin)) * (height - top - bottom)
  const step = niceStep(yMax - yMin, 5)
  let svg = `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${attr(title)}"><title>${attr(title)}</title>`
  for (let v = Math.ceil(yMin / step) * step; v <= yMax + 1e-12; v += step) {
    svg += `<line class="grid" x1="${left}" x2="${width - right}" y1="${y(v)}" y2="${y(v)}"/>`
    svg += `<text class="tick" x="${left - 10}" y="${y(v) + 4}" text-anchor="end">${label(v)}</text>`
  }
  svg += `<text class="axis" x="${left}" y="${top - 8}">${attr(unit)}</text>`
  groups.forEach((g, i) => {
    const cx = x(i), half = Math.min(18, slot / 4)
    svg += `<g class="slot${g.selected ? ' selected' : ''}">`
    if (g.selected) svg += `<rect class="slot-fill" x="${cx - slot / 2 + 2}" y="${top}" width="${slot - 4}" height="${height - top - bottom}" rx="4"/>`
    svg += `<text class="slot-label" x="${cx}" y="${height - bottom + 20}" text-anchor="middle">${attr(g.label[0])}</text>`
    if (g.label[1]) svg += `<text class="slot-label sub" x="${cx}" y="${height - bottom + 38}" text-anchor="middle">${attr(g.label[1])}</text>`
    g.marks.forEach((k, j) => {
      const offset = g.marks.length > 1 ? (j === 0 ? -1 : 1) * Math.min(9, slot / 6) : 0
      if (k.low !== undefined && k.high !== undefined) {
        svg += `<rect class="range ${k.tone}" x="${cx + offset - 3}" y="${y(k.high)}" width="6" height="${Math.max(2, y(k.low) - y(k.high))}"/>`
      } else {
        svg += `<line class="mark ${k.tone}" x1="${cx + offset - half / 2}" x2="${cx + offset + half / 2}" y1="${y(k.v)}" y2="${y(k.v)}"/>`
      }
    })
    if (g.observed) {
      const { v, e } = g.observed, hi = y(v + e), lo = y(v - e)
      svg += `<g class="reading">${e > 0 && lo - hi > 3 ? `<path d="M${cx} ${hi}V${lo}M${cx - 5} ${hi}h10M${cx - 5} ${lo}h10"/>` : ''}<circle cx="${cx}" cy="${y(v)}" r="4"/></g>`
    }
    svg += '</g>'
  })
  return svg + '</svg>'
}
