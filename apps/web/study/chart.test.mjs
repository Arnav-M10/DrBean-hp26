import test from 'node:test'
import assert from 'node:assert/strict'
import { chartSVG } from './chart.mjs'

test('a concentration chart does not assume a dose occurred', () => {
  const chart = chartSVG({ readings: [{ t: 1, v: 8, e: 0.5 }] })
  assert.match(chart, />Elapsed time \(h\)<\/text>/)
  assert.match(chart, />mg\/L<\/text>/)
  assert.doesNotMatch(chart, /after dose/i)
})

test('custom axis labels are escaped and leave scientific geometry unchanged', () => {
  const input = { readings: [{ t: 1, v: 8, e: 0.5 }], curves: [{ params: { A: 10, ke: 0.1, ka: 3 }, tone: 'inside' }] }
  const base = chartSVG(input)
  const custom = chartSVG({ ...input, xLabel: 'Calibration time (h)', yLabel: '<response> & "mg/L"' })
  assert.match(custom, />Calibration time \(h\)<\/text>/)
  assert.match(custom, /&lt;response&gt; &amp; &quot;mg\/L&quot;/)
  assert.doesNotMatch(custom, /<response>/)
  const paths = svg => [...svg.matchAll(/<path[^>]*>/g)].map(match => match[0])
  assert.deepEqual(paths(custom), paths(base))
})
