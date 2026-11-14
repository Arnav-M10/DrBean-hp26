import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { cellsOf, convert, guessColumns, readingsFrom, tablesFromJSON, tablesFromText } from './intake.mjs'
import { finding, formatBound, fromTexts, nextFinding, summarize } from './results.mjs'

test('a lab CSV: text column skipped, minutes and ng/mL recognised, SD never used as an allowance', () => {
  const text = 'Subject,Time (min),Plasma concentration (ng/mL),SD (ng/mL)\nA1,15,4800,310\nA1,30,7200,290\nA1,60,8000,350\n'
  const [table] = tablesFromText(text, { file: 'lab.csv' })
  assert.deepEqual(table.header, ['Time (min)', 'Plasma concentration (ng/mL)', 'SD (ng/mL)'])
  assert.deepEqual(table.rows[0], ['15', '4800', '310'])
  const columns = guessColumns(table)
  assert.deepEqual([columns.time, columns.concentration, columns.allowance, columns.spread], [0, 1, null, 2])
  assert.deepEqual(columns.units, { time: 'min', concentration: 'ng/mL' })
  const rows = readingsFrom(table, columns, { allowanceForAll: '0.5' })
  assert.deepEqual(rows.map(r => r.allowance), ['0.5', '0.5', '0.5'])
  assert.equal(rows[0].line, 2)
})

test('exact unit conversion never rounds', () => {
  assert.equal(convert('15', 'time', 'min'), '1/4')
  assert.equal(convert('20', 'time', 'min'), '1/3')
  assert.equal(convert('2', 'time', 'day'), '48/1')
  assert.equal(convert('4800', 'concentration', 'ng/mL'), '24/5')
  assert.equal(convert('1.5e-3', 'concentration', 'mg/L'), '3/2000')
  assert.equal(convert('4,80', 'concentration', 'mg/L'), '24/5')
})

test('a PDF page: prose around a spaced table, header above it', () => {
  const page = 'Table 2. Plasma concentration after the dose\r\nTime (h)   Concentration (mg/L)   Allowance (mg/L)\r\n0.25   4.80   0.50\r\n0.5   7.20   0.50\r\n1   8.00   0.50\r\nAllowance: assay acceptance limit.'
  const tables = tablesFromText(page, { file: 'report.pdf', page: 2 })
  assert.equal(tables.length, 1)
  assert.equal(tables[0].page, 2)
  assert.deepEqual(tables[0].header, ['Time (h)', 'Concentration (mg/L)', 'Allowance (mg/L)'])
  const columns = guessColumns(tables[0])
  assert.deepEqual([columns.time, columns.concentration, columns.allowance], [0, 1, 2])
})

test('cells: plus-minus, tabs, Markdown tables', () => {
  assert.deepEqual(cellsOf('0.25  4.80 ± 0.50'), ['0.25', '4.80', '0.50'])
  assert.deepEqual(cellsOf('1\t8.00\t0.5'), ['1', '8.00', '0.5'])
  assert.deepEqual(cellsOf('| 2 | 6.80 | 0.50 |'), ['2', '6.80', '0.50'])
  assert.deepEqual(cellsOf('|---|---|---|'), [])
  const markdown = '| time (h) | conc (mg/L) |\n|---|---|\n| 0.5 | 7.2 |\n| 1 | 8 |\n| 2 | 6.8 |'
  assert.equal(tablesFromText(markdown)[0].rows.length, 3)
})

test('JSON: records, column arrays and nested data', () => {
  const records = JSON.stringify({ study: { readings: [{ t_h: 0.5, conc: 7.2 }, { t_h: 1, conc: 8 }, { t_h: 2, conc: 6.8 }] } })
  const [a] = tablesFromJSON(records)
  assert.deepEqual(a.header, ['t_h', 'conc'])
  assert.equal(a.rows.length, 3)
  const [b] = tablesFromJSON(JSON.stringify({ time: [1, 2, 3], concentration: [8, 6.8, 6] }))
  assert.deepEqual(b.rows[2], ['3', '6'])
  assert.deepEqual(tablesFromJSON('not json'), [])
})

test('the saved real run reads back exactly (fixtures made by the working app)', () => {
  const dir = new URL('./fixtures/', import.meta.url)
  const names = readdirSync(dir).filter(name => name.startsWith('dr-bean-'))
  const texts = Object.fromEntries(names.map(name => [name, readFileSync(new URL(name, dir), 'utf8')]))
  const m = summarize(fromTexts(texts))
  assert.equal(m.outcome, 'certified_counterexample')
  assert.equal(m.included.length, 5)
  assert.deepEqual(m.candidates.map(c => c.outside), [false, true])
  assert.ok(m.readingChecks.every(r => r.curves.every(c => c.within)))
  assert.match(finding(m).headline, /below 0\.10 per hour$/)
  assert.equal(nextFinding(m).headline, 'Measure at 8 hours')
  assert.deepEqual(m.next.times.map(t => t.separated), [true, true])
  assert.equal(m.files.length, 5)
  assert.equal(formatBound(0.1), '0.10')
  assert.equal(formatBound(0.125), '0.125')
})

// --- Electron currents (model comparison) ---------------------------------------------------------
const fixture = name => JSON.parse(readFileSync(new URL(`../../../fixtures/model-comparison/${name}`, import.meta.url), 'utf8'))

test('exact decimal shifts never round', async () => {
  const { shift } = await import('./compare.mjs')
  assert.equal(shift('4.2889515568973794e-05', 6), '42.889515568973794')
  assert.equal(shift('0.0000002', 6), '0.2')
  assert.equal(shift('42.88', -6), '0.00004288')
  assert.equal(shift('4.2e1', -6), '0.000042')
  assert.equal(shift('-1.5', -3), '-0.0015')
  assert.equal(shift('0', 6), '0')
  assert.equal(Number(shift('1e-30', -6)), 1e-36)
  assert.ok(shift('1.234567890123e-30', -6).length <= 40)
  assert.equal(shift('abc', 6), null)
})

test('the sample currents rebuild the repository synthetic request value for value', async () => {
  const C = await import('./compare.mjs')
  const request = C.comparisonRequest(C.sampleComparison()), original = fixture('synthetic.request.json')
  assert.deepEqual(C.comparisonProblems(C.sampleComparison()), [])
  assert.deepEqual(request.channels, original.channels)
  assert.deepEqual(request.selected_channel_ids, original.selected_channel_ids)
  assert.deepEqual(request.feasible_settings, original.feasible_settings)
  assert.deepEqual(request.review, original.review)
  assert.deepEqual(request.instrument, original.instrument)
  request.observations.forEach((o, i) => {
    assert.equal(o.channel_id, original.observations[i].channel_id)
    assert.equal(Number(o.current_A), Number(original.observations[i].current_A))
    assert.equal(Number(o.sigma_A), Number(original.observations[i].sigma_A))
  })
  assert.deepEqual(request.noise.sigma_grid_A.map(Number), original.noise.sigma_grid_A.map(Number))
  assert.deepEqual({ ...request.fit, density_min_m3: Number(request.fit.density_min_m3), density_max_m3: Number(request.fit.density_max_m3) },
    { ...original.fit, density_min_m3: Number(original.fit.density_min_m3), density_max_m3: Number(original.fit.density_max_m3) })
  // A saved request comes back into the form and out again with the same values.
  const again = C.comparisonRequest(C.draftFromRequest(original))
  assert.deepEqual(again.observations.map(o => Number(o.current_A)), original.observations.map(o => Number(o.current_A)))
  assert.deepEqual(again.feasible_settings, original.feasible_settings)
})

test('problems name what to fix, including the service work limits', async () => {
  const C = await import('./compare.mjs')
  const d = C.sampleComparison()
  d.synthetic = false; d.rows[0].angle = '120'; d.temperatures = '1, 2, 3, 4, 5, 6, 7, 8, 9, 10'
  const fields = C.comparisonProblems(d).map(([, text, field]) => [field, text])
  assert.ok(fields.some(([f]) => f === 'synthetic'))
  assert.ok(fields.some(([f, text]) => f === 'rows' && /0 to 90/.test(text)))
  assert.ok(fields.some(([f, text]) => f === 'settings' && /110 fit evaluations/.test(text)))
})

test('a CSV of currents: columns, units and σ are recognised', async () => {
  const C = await import('./compare.mjs')
  const text = 'angle (deg),E min (eV),E max (eV),current (uA),sigma (uA)\n0,0,,42.9,0.2\n45,8,20,30.5,0.2\n90,0,,85.8,0.2\n'
  const [table] = tablesFromText(text, { file: 'currents.csv' })
  const c = C.guessCurrentColumns(table)
  assert.deepEqual([c.angle, c.low, c.high, c.current, c.sigma], [0, 1, 2, 3, 4])
  assert.deepEqual(c.units, { current: 'µA', sigma: 'µA' })
  const rows = C.currentsFrom(table, c)
  assert.deepEqual(rows.map(r => [r.angle, r.emin, r.emax, r.current, r.sigma]), [['0', '0', '', '42.9', '0.2'], ['45', '8', '20', '30.5', '0.2'], ['90', '0', '', '85.8', '0.2']])
  const inAmps = C.currentsFrom(table, { ...c, units: { current: 'A', sigma: 'A' } })
  assert.equal(inAmps[0].current, '42900000')
})

test('the computed synthetic response reads as an honest answer and a next setting', async () => {
  const C = await import('./compare.mjs')
  const m = C.readComparison({ id: 'cmp_fixture', body: fixture('synthetic.response.json'), created_at: '2026-11-14T12:00:00Z' })
  const f = C.comparisonFinding(m)
  assert.equal(f.headline, 'Only the bi-Maxwellian fits these currents')
  assert.match(f.lead, /not proof/)
  assert.equal(m.canPlan, true)
  const first = C.caseFinding(m, m.cases[0])
  assert.equal(first.headline, 'Measure at 0°, above 4 eV')
  const last = C.caseFinding(m, m.cases[2])
  assert.match(last.headline, /^No listed setting tells them apart at σ = 20 µA$/)
  assert.ok(C.settingsTable(m, m.cases[0]).includes('class="pick"'))
  assert.equal(C.simulationTable(m, m.cases[2]), '')
  assert.equal(C.resultGroups(m).length, 6)
  assert.equal(C.caseGroups(m, m.cases[0]).filter(g => g.selected).length, 1)
})
