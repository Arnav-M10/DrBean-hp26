// Find tables of numbers in any text a person brings: CSV, TSV, JSON, Markdown, plain
// text or the text layer of a PDF page. Nothing is guessed silently: every proposal says
// where it came from, and the person confirms which columns mean what.
import { parseExact } from '../exact.mjs'

const NUMBER = /^[+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+)(?:e[+-]?\d+)?$/i
const PLUS_MINUS = /^([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*(?:±|\+\/-|\+-)\s*((?:\d+(?:\.\d+)?|\.\d+))$/

export const isNumber = cell => NUMBER.test(String(cell).trim()) && !/^[+-]?\d{1,3}(,\d{3})+$/.test(String(cell).trim())

function csvLine(line, delimiter) {
  const cells = []
  let cell = '', quoted = false
  for (let i = 0; i < line.length; i++) {
    const c = line[i]
    if (quoted) {
      if (c === '"' && line[i + 1] === '"') { cell += '"'; i++ } else if (c === '"') quoted = false; else cell += c
    } else if (c === '"') quoted = true
    else if (c === delimiter) { cells.push(cell.trim()); cell = '' } else cell += c
  }
  cells.push(cell.trim())
  return cells
}

// Split one line into cells, choosing the separator the line itself uses. A line such as "4,80"
// reads as a decimal comma unless the text around it already uses commas to separate cells.
export function cellsOf(line, { commaSeparates = false } = {}) {
  const text = line.replace(/ /g, ' ').trim()
  if (!text) return []
  // In a delimited line an empty cell keeps its column (an optional value left blank); in
  // space-separated text there are no empty cells, only extra spaces.
  let cells, delimited = true
  if (text.includes('\t')) cells = text.split('\t').map(c => c.trim())
  else if (/^\|.*\|$/.test(text)) cells = text.slice(1, -1).split('|').map(c => c.trim())
  // A semicolon separates cells (as in European CSV, where the comma is the decimal mark).
  else if (text.includes(';')) cells = csvLine(text, ';')
  else if (text.includes(',') && (commaSeparates || !/\d,\d{1,2}(\s|$)/.test(text))) cells = csvLine(text, ',')
  else { delimited = false; cells = text.replace(/\s*(?:±|\+\/-|\+-)\s*/g, '  ').split(/\s{2,}|\s+(?=[-+.\d])|(?<=[\d)])\s+/).map(c => c.trim()) }
  // "4.80 ± 0.50" in one cell becomes a value and its allowance.
  return cells.flatMap(cell => {
    const pm = PLUS_MINUS.exec(cell)
    return pm ? [pm[1], pm[2]] : [cell]
  }).filter(cell => (delimited || cell !== '') && !/^:?-{3,}:?$/.test(cell))
}

// Consecutive lines with the same count of numeric cells form a table; the line just
// above one becomes its header when it is not numeric.
export function tablesFromText(text, where = {}) {
  const lines = String(text).replace(/\r\n?/g, '\n').split('\n')
  // A text that writes decimals with a point next to a comma ("0.27,4.4") uses commas only between
  // cells, so its "0,0" is two readings, not the decimal 0,0.
  const commaSeparates = /\d\.\d+\s*,|,\s*[+-]?\d*\.\d/.test(text)
  const tables = []
  let current = null
  const flush = () => { if (current && current.rows.length >= 2) tables.push(current); current = null }
  lines.forEach((line, index) => {
    const cells = cellsOf(line, { commaSeparates })
    // A data line: two or more numbers, at most one label (such as a subject id); blanks allowed.
    const words = cells.filter(c => c !== '' && !isNumber(c)).length
    if (cells.filter(isNumber).length >= 2 && words <= 1) {
      const values = cells.filter(c => c === '' || isNumber(c))
      if (current && current.width === values.length) {
        current.rows.push(values); current.lines.push(index + 1)
      } else {
        flush()
        const above = cellsOf(lines[index - 1] ?? '', { commaSeparates })
        const header = above.length >= values.length - 1 && above.filter(isNumber).length === 0 ? above.slice(-values.length) : null
        current = { ...where, width: values.length, header, rows: [values], lines: [index + 1] }
      }
    } else if (cells.length) {
      flush()
    }
  })
  flush()
  return tables
}

export function tablesFromJSON(text, where = {}) {
  let value
  try { value = JSON.parse(text) } catch { return [] }
  const found = []
  const visit = (node, depth = 0) => {
    if (depth > 6 || !node || typeof node !== 'object') return
    if (Array.isArray(node) && node.length >= 2) {
      if (node.every(item => item && typeof item === 'object' && !Array.isArray(item))) {
        const keys = Object.keys(node[0]).filter(k => node.every(item => item[k] !== undefined && isNumber(item[k])))
        if (keys.length >= 2) found.push({ ...where, width: keys.length, header: keys, rows: node.map(item => keys.map(k => String(item[k]))), lines: [] })
      } else if (node.every(item => Array.isArray(item) && item.length >= 2 && item.every(isNumber))) {
        found.push({ ...where, width: node[0].length, header: null, rows: node.map(item => item.map(String)), lines: [] })
      }
    }
    if (!Array.isArray(node)) {
      const columns = Object.entries(node).filter(([, v]) => Array.isArray(v) && v.length >= 2 && v.every(isNumber))
      if (columns.length >= 2 && columns.every(([, v]) => v.length === columns[0][1].length)) {
        found.push({ ...where, width: columns.length, header: columns.map(([k]) => k), rows: columns[0][1].map((_, i) => columns.map(([, v]) => String(v[i]))), lines: [] })
      }
    }
    for (const child of Array.isArray(node) ? node.slice(0, 50) : Object.values(node)) visit(child, depth + 1)
  }
  visit(value)
  return found
}

const TIME = /(^|\b)(t|time|hours?|hrs?|h|min|mins|minutes?|elapsed|day|days)(\b|$)/i
const CONC = /(conc|concentration|level|plasma|serum|mg\/l|ng\/ml|µg|ug|mcg|mmol|c\(t\)|^c$)/i
const ALLOWANCE = /(allow|tolerance|bound|±|\+\/-|error|uncert|epsilon|eps\b)/i
const SPREAD = /(\bsd\b|s\.d\.|std|stdev|\bse\b|sem|s\.e\.)/i

export function unitsFrom(header = '') {
  const h = header.toLowerCase()
  return {
    time: /(min|minute)/.test(h) ? 'min' : /(day)/.test(h) ? 'day' : 'h',
    concentration: /ng\/ml/.test(h) ? 'ng/mL' : /(µg|ug|mcg)\/l\b/.test(h) ? 'µg/L' : /(µg|ug|mcg)\/ml/.test(h) ? 'µg/mL' : 'mg/L',
  }
}

// Which column is time, concentration and allowance. Standard deviations are flagged, never used.
export function guessColumns(table) {
  const header = table.header ?? []
  const pick = (pattern, avoid = []) => header.findIndex((h, i) => pattern.test(h) && !avoid.includes(i))
  let time = pick(TIME), concentration = pick(CONC, [time]), allowance = pick(ALLOWANCE, [time, concentration])
  const spread = header.findIndex((h, i) => SPREAD.test(h) && ![time, concentration].includes(i))
  if (allowance === spread) allowance = -1
  const numbers = col => table.rows.map(r => Number(String(r[col]).replace(',', '.')))
  if (time < 0) time = [...Array(table.width).keys()].find(col => { const v = numbers(col); return v.every((x, i) => i === 0 || x > v[i - 1]) }) ?? 0
  if (concentration < 0) concentration = [...Array(table.width).keys()].find(col => col !== time && col !== allowance && col !== spread) ?? -1
  if (allowance < 0 && !table.header && table.width >= 3) allowance = [...Array(table.width).keys()].find(col => col !== time && col !== concentration) ?? -1
  return {
    time, concentration, allowance: allowance >= 0 ? allowance : null, spread: spread >= 0 ? spread : null,
    units: { time: unitsFrom(header[time]).time, concentration: unitsFrom(header[concentration]).concentration },
  }
}

const FACTORS = { time: { h: [1n, 1n], min: [1n, 60n], day: [24n, 1n] },
  concentration: { 'mg/L': [1n, 1n], 'µg/mL': [1n, 1n], 'ng/mL': [1n, 1000n], 'µg/L': [1n, 1000n] } }

// Exact unit conversion: "90" minutes becomes "3/2" hours, never a rounded float.
export function convert(value, kind, unit) {
  const text = String(value).trim().replace(',', '.')
  const scientific = /^([+-]?(?:\d+(?:\.\d*)?|\.\d+))e([+-]?\d+)$/i.exec(text)
  let [n, d] = parseExact(scientific ? scientific[1] : text).split('/').map(BigInt)
  if (scientific) {
    const power = BigInt(scientific[2])
    if (power >= 0n) n *= 10n ** power; else d *= 10n ** -power
  }
  const [mul, div] = FACTORS[kind][unit] ?? [1n, 1n]
  let num = n * mul, den = d * div
  const gcd = (a, b) => { a = a < 0n ? -a : a; while (b) [a, b] = [b, a % b]; return a }
  const g = gcd(num, den)
  num /= g; den /= g
  return `${num}/${den}`
}

export function readingsFrom(table, columns, { allowanceForAll = '' } = {}) {
  return table.rows.map((row, i) => ({
    time: row[columns.time] ?? '', value: row[columns.concentration] ?? '',
    allowance: columns.allowance === null ? allowanceForAll : (row[columns.allowance] ?? ''),
    included: true, line: table.lines[i] ?? null,
  }))
}
