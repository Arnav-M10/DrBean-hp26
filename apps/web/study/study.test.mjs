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
