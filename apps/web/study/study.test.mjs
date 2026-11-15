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

test('a CSV whose first reading is 0,0 keeps its header and every reading', () => {
  // Real dose data often start at 0 h with 0 mg/L (R's Theoph, subject 3).
  const [table] = tablesFromText('Time (h),Theophylline (mg/L)\n0,0\n0.27,4.4\n0.58,6.9\n24.17,1.05\n', { file: 'theoph.csv' })
  assert.deepEqual(table.header, ['Time (h)', 'Theophylline (mg/L)'])
  assert.deepEqual(table.rows, [['0', '0'], ['0.27', '4.4'], ['0.58', '6.9'], ['24.17', '1.05']])
  // A decimal comma still reads as one number where the text has no point decimals.
  assert.deepEqual(cellsOf('4,80'), ['4,80'])
  assert.deepEqual(tablesFromText('Zeit (h);Konzentration (mg/L)\n0,25;4,80\n0,5;7,20\n1;8,00\n')[0].rows[0], ['0,25', '4,80'])
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

// --- Any files and a question -----------------------------------------------------------------------
test('the files decide which checks are offered; unnamed or unrelated tables get none', async () => {
  const G = await import('./general.mjs')
  const [drug] = tablesFromText('Time (min),Plasma concentration (ng/mL)\n15,4800\n30,7200\n60,8000\n', { file: 'lab.csv' })
  const [currents] = tablesFromText('angle (deg),E min (eV),current (uA)\n0,0,42.9\n45,8,30.5\n', { file: 'c.csv' })
  const [co2] = tablesFromText('year,mean (ppm)\n2019,411.66\n2020,414.24\n2021,416.45\n', { file: 'co2.csv' })
  const [bare] = tablesFromText('0.25 4.80\n0.5 7.20\n1 8.00\n', { file: 'bare.txt' })
  const [water] = tablesFromText('Time (h),Water level (m)\n1,2.0\n2,3.5\n3,4.0\n', { file: 'w.csv' })
  assert.deepEqual(G.checksFor(drug), ['concentration'])
  assert.deepEqual(G.checksFor(currents), ['currents'])
  assert.deepEqual(G.checksFor(co2), [])
  assert.deepEqual(G.checksFor(bare), [])
  assert.deepEqual(G.checksFor(water), [])
  const sources = [{ asset: { id: 'a' }, tables: [co2] }, { asset: { id: 'b' }, tables: [drug, currents] }]
  assert.deepEqual(G.firstMatch(sources, 'concentration'), { s: 1, t: 0 })
  assert.deepEqual(G.firstMatch(sources, 'currents'), { s: 1, t: 1 })
  assert.equal(G.overview(sources)[1].found[1].checks[0], 'currents')
})

test('the assistant request discloses exactly the approved files and question', async () => {
  const G = await import('./general.mjs')
  const assets = [{ id: 'research_asset_1', sha256: 'a'.repeat(64), filename: 'x.csv' }, { id: 'research_asset_2', sha256: 'b'.repeat(64), filename: 'y.pdf' }]
  const body = G.analysisRequest({ question: '  What changed?  ', assets, model: 'gemini-x', operationId: 'study-1' })
  assert.equal(body.question, 'What changed?')
  assert.deepEqual(body.assets, [{ id: 'research_asset_1', sha256: 'a'.repeat(64) }, { id: 'research_asset_2', sha256: 'b'.repeat(64) }])
  assert.deepEqual(body.consent, { accepted: true, provider: 'gemini', model: 'gemini-x', asset_ids: ['research_asset_1', 'research_asset_2'], include_question: true })
  assert.match(G.operationId(), /^study-[a-z0-9]+-[0-9a-f]{16}$/)
})

test('the published example answer reads with its quotes, and its tables can start a check', async () => {
  const G = await import('./general.mjs')
  const example = JSON.parse(readFileSync(new URL('../../../shared/contracts/general-research.v1/examples/analysis.json', import.meta.url), 'utf8'))
  const record = example.response.body
  const assets = [...new Set(record.body.citations.map(c => c.asset_id))].map((id, i) => ({ id, filename: `file-${i + 1}.csv`, sha256: 'c'.repeat(64) }))
  const m = G.readAnalysis(record, assets)
  assert.equal(m.controlled, true)
  assert.equal(m.failed, null)
  const claims = G.claimList(m)
  assert.ok(claims.includes('<span class="kind">Observation</span>'))
  assert.ok(claims.includes('“# USE OF NOAA GML DATA”'))
  assert.ok(G.sourcesView(m).includes('Found in the file'))
  const first = record.body.extracted_tables[0]
  const table = G.tableFromAnalysis(first, 'file-1.csv')
  assert.equal(table.fromAssistant, true)
  assert.deepEqual(table.header, first.columns)
  assert.equal(table.rows.length, first.rows.length)
  assert.ok(G.nextSteps(m).includes('Review the values'))
})

// --- The front page ---------------------------------------------------------------------------------
// Every value the front page shows comes from home-data.mjs. Read the saved run again and check that
// the copy is exact and words the same as the study page.
test('the front page shows the saved run exactly, worded as the study page words it', async () => {
  const H = await import('./home-data.mjs'), R = await import('./results.mjs')
  const dir = new URL('./fixtures/', import.meta.url)
  const names = readdirSync(dir).filter(name => name.startsWith('dr-bean-'))
  const m = summarize(fromTexts(Object.fromEntries(names.map(name => [name, readFileSync(new URL(name, dir), 'utf8')]))))
  const d = H.doseStudy()
  assert.deepEqual(d.included.map(({ t, v, e, time, value, allowance }) => ({ t, v, e, time, value, allowance })),
    m.included.map(({ t, v, e, time, value, allowance }) => ({ t, v, e, time, value, allowance })))
  assert.deepEqual(d.candidates.map(({ tone, outside, exact, params }) => ({ tone, outside, exact, params })),
    m.candidates.map(({ tone, outside, exact, params }) => ({ tone, outside, exact, params })))
  assert.deepEqual([d.claim.low, d.claim.high, d.outcome, d.search, d.created, d.checker.version, d.objective],
    [m.claim.low, m.claim.high, m.outcome, m.search, m.created, m.checker.version, m.objective])
  const shown = times => times.map(({ t, separated, margin, centers, ranges }) => ({ t, separated, margin, centers, ranges }))
  assert.deepEqual(d.next.times, shown(m.next.times))
  assert.deepEqual([d.next.tier, d.next.selected, d.next.allowance, d.next.horizon], [m.next.tier, m.next.selected, m.next.allowance, m.next.horizon])
  assert.deepEqual(R.finding(d), R.finding(m))
  assert.deepEqual(R.nextFinding(d), R.nextFinding(m))
  assert.equal(R.nextTable(d), R.nextTable(m))
  // The fraction the page sets in its note is the rate of the curve outside the claim, and it is
  // below the claim's 0.10 exactly (101/1016 < 1/10 because 1010 < 1016).
  assert.equal(d.candidates.find(c => c.outside).exact.ke, '101/1016')
  assert.ok(101 * 10 < 1016)
  // "Measure at 8 h" on the page is the run's chosen time.
  assert.equal(R.nextFinding(m).headline, 'Measure at 8 hours')
  assert.equal(d.next.selected, 8)
})

test('the front page links only to the study, its own sections and the source, and loads nothing from elsewhere', () => {
  const html = readFileSync(new URL('./index.html', import.meta.url), 'utf8')
  const ids = new Set([...html.matchAll(/\sid="([^"]+)"/g)].map(match => match[1]))
  for (const [, href] of html.matchAll(/\shref="([^"]*)"/g)) {
    if (href.startsWith('#')) assert.ok(href === '#main' || ids.has(href.slice(1)), `missing section ${href}`)
    else assert.ok(['app', './', 'https://github.com/Arnav-M10/DrBean-hp26'].includes(href) || /^(fonts|vendor)\/|\.css$/.test(href), `unexpected link ${href}`)
  }
  for (const [, src] of html.matchAll(/\ssrc="(logos\/[^"]+)"/g)) {
    assert.doesNotMatch(readFileSync(new URL(src, import.meta.url), 'utf8'), /<script|\son[a-z]+=|href=/i, src)
  }
  for (const [, src] of html.matchAll(/\ssrc="([^"]*)"/g)) assert.doesNotMatch(src, /^(https?:)?\/\//)
  assert.equal([...html.matchAll(/data-start/g)].length, 3)
  // Its sections never take a study step's name: those links open the study (the redirect in <head>).
  for (const step of ['data', 'check', 'result', 'next']) assert.ok(!ids.has(step), step)
  assert.match(html, /\^#\(data\|check\|result\|next\)\(-\|\$\)/)
  // The front page reads the study page's storage key to offer the saved study.
  const key = readFileSync(new URL('./app.mjs', import.meta.url), 'utf8').match(/const STORE = '([^']+)'/)[1]
  assert.ok(readFileSync(new URL('./home.mjs', import.meta.url), 'utf8').includes(`'${key}'`))
  // The study page's logo leads back to the front page.
  assert.match(readFileSync(new URL('./app.html', import.meta.url), 'utf8'), /<a class="brand" href="\.\/">/)
})
