// Any files, any question. The assistant (the general research service: Gemini when the server
// has it, or its local test responder) reads the files and answers with exact quotes. Where a
// table fits a model Dr. Bean can check, the page also offers that check, so an answer can be
// verified instead of only read. Nothing here interprets science.
import { escapeHTML } from './results.mjs'

// --- What a table can be checked as, from its column names only ---------------------------------
// Unnamed columns are never guessed into a check: a person can still choose one by hand.
const TIME = /(^|\b)(t|time|hours?|hrs?|h|min|mins|minutes?|elapsed|day|days)(\b|$)/i
const CONC = /(conc|concentration|plasma|serum|mg\/l|ng\/ml|µg\/ml|ug\/ml|mcg\/ml|µg\/l|ug\/l)/i
const ANGLE = /(angle|theta|θ|pitch)/i
const CURRENT = /(current|\(a\)|\[a\]|µa|\bua\b|\bna\b|\bma\b|amp)/i
export const CHECKS = {
  concentration: { title: 'Check a claim about the elimination rate', how: 'Exact proof by Counterdex', button: 'Set up the check' },
  currents: { title: 'Compare two electron distributions', how: 'Numerical fit, not an exact proof', button: 'Set up the comparison' },
}
export function checksFor(table) {
  const header = (table.header ?? table.columns ?? []).map(String)
  const has = pattern => header.some(name => pattern.test(name))
  const out = []
  if (has(TIME) && has(CONC) && table.rows.length >= 3) out.push('concentration')
  if (has(ANGLE) && has(CURRENT) && table.rows.length >= 1) out.push('currents')
  return out
}

// Every table in every file, with what it can be checked as.
export function overview(sources) {
  return sources.map((source, s) => ({ ...source, index: s,
    found: source.tables.map((table, t) => ({ table, t, checks: checksFor(table) })) }))
}
export const firstMatch = (sources, kind) => {
  for (const [s, source] of sources.entries()) {
    const t = source.tables.findIndex(table => checksFor(table).includes(kind))
    if (t >= 0) return { s, t }
  }
  return null
}

// The assistant's tables as the intake's tables, so a checked path can start from them.
export function tableFromAnalysis(table, filename) {
  const rows = table.rows.map(row => row.map(cell => cell ?? ''))
  return { file: `the assistant's reading of ${filename}`, page: table.page_number ?? null, width: table.columns.length,
    header: table.columns.map(String), rows, lines: rows.map(() => null), fromAssistant: true }
}

// --- The request, sent only after the person approves this exact disclosure ---------------------
export function analysisRequest({ question, assets, model, operationId }) {
  return { client_operation_id: operationId, question: question.trim(),
    assets: assets.map(asset => ({ id: asset.id, sha256: asset.sha256 })),
    consent: { accepted: true, provider: 'gemini', model, asset_ids: assets.map(asset => asset.id), include_question: true } }
}
export const operationId = () => `study-${Date.now().toString(36)}-${Array.from(crypto.getRandomValues(new Uint8Array(8)), b => b.toString(16).padStart(2, '0')).join('')}`

// --- Reading the answer ----------------------------------------------------------------------------
const KIND = { observation: 'Observation', interpretation: 'Interpretation', hypothesis: 'Hypothesis', method: 'Method', comparison: 'Comparison' }
const UNCERTAINTY = { sd: 'with a standard deviation', se: 'with a standard error', ci: 'with a confidence interval', range: 'with a range', hard_bound: 'with a hard bound', other: 'with a stated uncertainty' }
const NEXT = { collect_data: 'Collect data', review_extracted_values: 'Review the values', check_units: 'Check the units', consult_source: 'Read the source', mathematical_check_candidate: 'Can be checked', other: 'Next step' }

export function readAnalysis(record, assets) {
  const b = record.body
  const byId = new Map(assets.map(asset => [asset.id, asset]))
  const citations = new Map((b.citations ?? []).map(c => [c.id, { ...c, filename: byId.get(c.asset_id)?.filename ?? c.source_label }]))
  return { record, b, assets, citations, controlled: b.execution_mode === 'controlled', model: b.model, created: record.created_at ?? null,
    question: b.question ?? '', failed: b.status === 'completed' ? null : (b.failure?.message || 'The assistant did not finish this reading.') }
}

// How each quote compared with the file's own text (the server checks every quote).
const FOUND = { verified: '', ambiguous: 'found in more than one place', partial_token_match: 'only partly found in the file', not_found: 'not found in the file',
  wrong_page: 'not found on that page', unverifiable_no_text_layer: 'not compared: the page has no text layer', unverifiable_text_layer: 'not compared: the page text is unreliable' }
const found = c => FOUND[c.status] ?? 'not checked against the file'
const SUPPORT = { partially_supported: 'Only partly supported by its quotes.', unsupported: 'Not supported by its quotes.',
  unverifiable: 'Its quotes could not be compared with the file.', uncited: 'No quote given.' }

export function quotes(m, ids = []) {
  return ids.map(id => m.citations.get(id)).filter(Boolean).map(c => `<blockquote class="quote${c.status === 'verified' ? '' : ' unverified'}">
    <p>“${escapeHTML(c.quote)}”</p><cite>${escapeHTML(c.filename)}, page ${c.page_number ?? c.page_index + 1}${c.status === 'verified' ? '' : `, ${found(c)}`}</cite></blockquote>`).join('')
}

export function claimList(m) {
  const claims = m.b.claims ?? []
  if (!claims.length) return '<p class="quiet">The assistant made no claims about these files.</p>'
  return `<ol class="claims">${claims.map(c => `<li><p><span class="kind">${KIND[c.kind] ?? 'Claim'}</span>${escapeHTML(c.text)}</p>
    ${c.uncertainty && UNCERTAINTY[c.uncertainty] ? `<p class="meta">Stated ${UNCERTAINTY[c.uncertainty]}.</p>` : ''}
    ${SUPPORT[c.support] ? `<p class="meta bad">${SUPPORT[c.support]}</p>` : ''}
    ${quotes(m, c.citation_ids)}</li>`).join('')}</ol>`
}

export function tableBlocks(m, checkable) {
  return (m.b.extracted_tables ?? []).map((table, i) => {
    const kinds = checkable(table)
    return `<section class="found-table"><div class="found-head"><div><h3>${escapeHTML(table.title || `Table ${i + 1}`)}</h3>
      <p class="meta">${escapeHTML(m.assets.find(a => a.id === table.asset_id)?.filename ?? '')}${table.page_number ? `, page ${table.page_number}` : ''}. Copied by the assistant; check it against the file.</p></div>
      <div class="file-actions">${kinds.map(kind => `<button type="button" class="secondary small" data-action="ai-use-table" data-table="${i}" data-kind="${kind}">${kind === 'concentration' ? 'Check these values' : 'Compare with these currents'}</button>`).join('')}</div></div>
      <div class="table-scroll"><table class="data"><thead><tr>${table.columns.map(c => `<th scope="col">${escapeHTML(c)}</th>`).join('')}</tr></thead>
      <tbody>${table.rows.slice(0, 40).map(row => `<tr>${row.map(cell => `<td>${cell === null ? '<span class="quiet">empty</span>' : escapeHTML(cell)}</td>`).join('')}</tr>`).join('')}</tbody></table></div></section>`
  }).join('')
}

export function nextSteps(m) {
  const steps = m.b.suggested_next_steps ?? []
  if (!steps.length) return '<p class="quiet">The assistant suggested no next steps.</p>'
  return `<ol class="claims">${steps.map(s => `<li><p><span class="kind">${NEXT[s.kind] ?? 'Next step'}</span>${escapeHTML(s.text)}</p>
    ${s.rationale ? `<p class="meta">${escapeHTML(s.rationale)}</p>` : ''}${quotes(m, s.citation_ids)}</li>`).join('')}</ol>`
}

export function clarifications(m) {
  const items = m.b.clarifications ?? []
  return items.length ? `<ul class="limit-list">${items.map(c => `<li>${escapeHTML(c.question)}${c.reason ? ` <span class="quiet">${escapeHTML(c.reason)}</span>` : ''}</li>`).join('')}</ul>` : ''
}

export function sourcesView(m) {
  const groups = new Map()
  for (const c of m.citations.values()) {
    const key = `${c.filename}|${c.page_number ?? c.page_index + 1}`
    groups.set(key, [...(groups.get(key) ?? []), c])
  }
  if (!groups.size) return '<p class="quiet">The answer quotes nothing from the files.</p>'
  return [...groups].map(([key, list]) => {
    const [file, page] = key.split('|')
    return `<section class="source-group"><h3>${escapeHTML(file)}, page ${escapeHTML(page)}</h3>${list.map(c => `<blockquote class="quote${c.status === 'verified' ? '' : ' unverified'}"><p>“${escapeHTML(c.quote)}”</p>
      <cite>${c.status === 'verified' ? 'Found in the file' : found(c).replace(/^./, x => x.toUpperCase())}</cite></blockquote>`).join('')}</section>`
  }).join('')
}
