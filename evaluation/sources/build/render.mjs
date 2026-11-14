// Renders the synthetic sheets to PNG and writes expected transcriptions.
// Usage: node evaluation/sources/build/render.mjs [sheet-id ...]
// The committed PNG bytes are the frozen source. Re-rendering with another
// browser build may change bytes, which requires a new manifest version.
import { createHash } from 'node:crypto'
import { mkdir, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { sheets } from './sheets.mjs'

const { chromium } = createRequire(import.meta.url)('playwright')
const out = new URL('../', import.meta.url)
const esc = text => String(text).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))
const field = (name, text, extra = '') => `<span data-field="${name}" ${extra}>${esc(text)}</span>`

function html(s) {
  const table = `<table><thead><tr><th>${field('time_header', s.timeHeader)}</th><th>${field('concentration_header', s.concHeader)}</th><th>${field('allowance_header', s.allowHeader)}</th></tr></thead><tbody>${
    s.rows.map(([t, c], i) => `<tr><td>${field(`row${i + 1}_time`, t)}</td><td>${field(`row${i + 1}_concentration`, c)}</td><td>${
      field(`row${i + 1}_allowance`, s.allowance, s.blot === 'allowance' ? 'class="blot"' : '')}</td></tr>`).join('')}</tbody></table>`
  const bounds = `<table class="bounds"><thead><tr><th>Parameter</th><th>Lower</th><th>Upper</th></tr></thead><tbody>${
    s.bounds.map(([k, label, lo, hi]) => `<tr><td>${esc(label)}</td><td>${field(`${k}_min`, lo)}</td><td>${field(`${k}_max`, hi)}</td></tr>`).join('')}</tbody></table>`
  let target = esc(s.target)
  for (const [name, text] of Object.entries(s.targetFields)) target = target.replace(esc(text), field(name, text))
  const blocks = {
    model: `<h2>Model</h2><p>${field('model', s.model)}</p>`,
    data: `<h2>Measurements</h2>${table}<p>${field('allowance_note', s.allowanceNote)}</p>`,
    bounds: `<h2>Parameter bounds</h2>${bounds}`,
    target: `<h2>Research question</h2><p data-field="target_statement">${target}</p>`,
    notes: s.notes.length ? `<h2>Notes</h2>${s.notes.map((n, i) => `<p>${field(`note${i + 1}`, n)}</p>`).join('')}` : '',
  }
  const body = s.style === 'columns'
    ? `<div class="cols"><div>${blocks.bounds}${blocks.target}${blocks.model}</div><div>${blocks.data}${blocks.notes}</div></div>`
    : blocks.model + blocks.data + blocks.bounds + blocks.target + blocks.notes
  return `<!doctype html><meta charset="utf-8"><style>
    body{margin:0;padding:36px 44px;width:912px;background:#fff;color:#111;font:17px/1.45 ${s.style === 'serif' ? 'Georgia,"DejaVu Serif",serif' : '"DejaVu Sans",Arial,sans-serif'}}
    h1{font-size:25px;margin:0 0 4px} h2{font-size:18px;margin:20px 0 6px;border-bottom:1px solid #999}
    .banner{background:#fde68a;border:2px solid #92400e;padding:6px 10px;font-weight:700;margin:8px 0 6px}
    table{border-collapse:collapse;margin:6px 0} th,td{border:1px solid #444;padding:5px 12px;text-align:left}
    .cols{display:grid;grid-template-columns:1fr 1fr;gap:28px} p{margin:6px 0}
    .blot{position:relative} .blot::after{content:"";position:absolute;left:0.52em;top:0.38em;width:0.62em;height:0.8em;background:#3b2f2f;border-radius:45%;transform:rotate(18deg)}
  </style><h1>${field('title', s.title)}</h1>
  <div class="banner">SYNTHETIC TEST SOURCE. Invented values. Not laboratory data. Sheet ${esc(s.id)}.</div>${body}`
}

const exact = text => {
  const m = /^(\d+)(?:\.(\d+))?$/.exec(text) ?? /^(\d+)\/(\d+)$/.exec(text)
  if (!m) return null
  let [n, d] = text.includes('/') ? [BigInt(m[1]), BigInt(m[2])] : [BigInt(m[1] + (m[2] ?? '')), 10n ** BigInt((m[2] ?? '').length)]
  const gcd = (a, b) => (b ? gcd(b, a % b) : a)
  const g = gcd(n, d)
  return `${n / g}/${d / g}`
}

const wanted = process.argv.slice(2)
const browser = await chromium.launch()
await mkdir(new URL('expected/', out), { recursive: true })
for (const s of sheets.filter(s => !wanted.length || wanted.includes(s.id))) {
  const page = await browser.newPage({ viewport: { width: 1000, height: 600 }, deviceScaleFactor: 1 })
  await page.setContent(html(s))
  const png = await page.screenshot({ fullPage: true, type: 'png' })
  const size = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.scrollHeight])
  const regions = await page.$$eval('[data-field]', nodes => nodes.map(n => {
    const r = n.getBoundingClientRect()
    return [n.dataset.field, n.textContent, [Math.floor(r.x), Math.floor(r.y), Math.ceil(r.width), Math.ceil(r.height)]]
  }))
  await page.close()
  const fields = {}
  for (const [name, text, region] of regions) {
    const blotted = s.blot === 'allowance' && /_allowance$/.test(name)
    fields[name] = {
      printed_text: text, region_xywh_px: region,
      exact_value: blotted ? null : exact(text),
      ...(blotted ? { legibility: 'decimal point obscured; reads as 0.2 or 2', generator_value_withheld_from_grading: true } : {}),
    }
  }
  const expected = {
    sheet_id: s.id, purpose: s.purpose, synthetic: true, media_type: 'image/png',
    sha256: createHash('sha256').update(png).digest('hex'), bytes: png.length, width_px: size[0], height_px: size[1],
    page: 1, fields, intentionally_missing: s.missing, ambiguities: s.ambiguities,
    embedded_instructions_are_untrusted_content: s.id.startsWith('c06'),
    transcription_basis: 'derived from the generator specification (sheets.mjs), not from OCR',
    human_visual_review: 'pending: a teammate must compare this file with the PNG before live grading',
  }
  await writeFile(new URL(`${s.id}.png`, out), png)
  await writeFile(new URL(`expected/${s.id}.json`, out), JSON.stringify(expected, null, 2) + '\n')
  console.log(s.id, png.length, size.join('x'), expected.sha256.slice(0, 12))
}
await browser.close()
