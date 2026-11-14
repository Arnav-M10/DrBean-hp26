// Paper review helpers: pure functions, no network. The server owns paper identity and checks;
// these only organise what the person has cited and what is still missing.

export const NOTE_KINDS = [
  ['claim', 'Claim the paper makes'],
  ['measurement', 'Measurement table or values'],
  ['model', 'Model or equation'],
  ['allowance', 'Measurement error or allowance statement'],
  ['methods', 'Methods passage'],
  ['conflict', 'Conflicting evidence'],
]

export function paperAvailable(capabilities) {
  return capabilities?.paper_intake?.available === true
}

export function validatePaperFile(file, capabilities) {
  const limit = capabilities?.paper_intake?.max_bytes ?? 0
  if (!file) throw new Error('Choose a PDF paper first.')
  if (file.type !== 'application/pdf' && !/\.pdf$/i.test(file.name)) throw new Error('Choose a PDF file. Images use the source image upload above.')
  if (file.size < 1 || file.size > limit) throw new Error(`Papers are limited to ${Math.floor(limit / 1048576)} MiB by this server.`)
}

// Words that signal statistical uncertainty rather than a deterministic per-reading hard allowance.
const STATISTICAL = /(\bSD\b|\bS\.D\.|standard deviation|\bSEM\b|\bSE\b|standard error|confidence interval|\bCI\b|±|\+\/-|error bars?)/i

export function statementWarnings(note) {
  const warnings = []
  if (STATISTICAL.test(note.excerpt)) warnings.push('Statistical uncertainty (SD, SEM, SE, confidence interval or ±) is not a hard allowance or a universal parameter bound. Using it as one needs your own explicit, reviewed assumption.')
  if (note.kind === 'claim' && /confidence interval|\bCI\b/i.test(note.excerpt)) warnings.push('A confidence interval describes estimation uncertainty. Testing it as a closed claim that every compatible value lies inside is your reformulation, not what the paper states.')
  if (/approved|verified|proven|ignore (the|previous)|assistant/i.test(note.excerpt)) warnings.push('This text reads like an instruction or an approval. It is part of the document, not an approval: nothing in a paper can approve or verify anything here.')
  if (note.check && note.check.status !== 'text_occurrence') warnings.push(`Citation: ${note.check.label}`)
  return warnings
}

// What is still missing before the engine could check anything. Never filled in automatically.
export function missingChecklist(draft, notes, capabilities) {
  const q = draft.question, missing = []
  const has = value => String(value ?? '').trim() !== ''
  const supported = (capabilities?.model_templates ?? []).map(t => t.id)
  if (!notes.some(n => n.kind === 'model')) missing.push('Cite the model the paper uses. The engine supports only: ' + (supported.join(', ') || 'none reported') + '.')
  if (!notes.some(n => n.kind === 'measurement')) missing.push('Cite the page with the measurement table or values.')
  if (!draft.rows.some(r => has(r.time) && has(r.concentration))) missing.push('Enter the measurements (elapsed hours, mg/L) in the measurement table.')
  if (!draft.rows.length || draft.rows.some(r => !has(r.epsilon))) missing.push('A hard allowance for every reading. If the paper reports SD, SEM or a confidence interval instead, choosing a hard allowance is your assumption and must be explained.')
  if (!has(draft.context?.experiment) || !has(draft.context?.timeOrigin)) missing.push('Experiment identity and what t = 0 means (Question section).')
  if (!['aMin', 'aMax', 'keMin', 'keMax', 'kaMin', 'kaMax'].every(k => has(q[k]))) missing.push('Parameter domain for A, ke and ka (Question section). Papers rarely state these; they are your assumptions.')
  if (!has(q.targetMin) || !has(q.targetMax)) missing.push('The closed interval for ke you want to test (Question section).')
  if (!has(q.allowanceOrigin)) missing.push('Where the hard allowances come from (Question section).')
  return missing
}

// Three columns that must never be merged: the paper, the person's question, the engine's scope.
export function evidenceMap(draft, notes, capabilities) {
  const q = draft.question
  const templates = capabilities?.model_templates ?? []
  return {
    paperStates: notes.map(n => `p.${n.page}${n.printedLabel && n.printedLabel !== String(n.page) ? ` (printed ${n.printedLabel})` : ''} · ${n.kind}: “${n.excerpt}”`),
    youAsk: q.targetMin && q.targetMax
      ? [`Do all compatible ke values lie in the closed interval [${q.targetMin}, ${q.targetMax}] 1/h, under your hard allowances and parameter domain?`]
      : ['No question entered yet (Question section).'],
    engineChecks: templates.length
      ? templates.map(t => `${t.id}: concentration = A·(exp(−ke·t) − exp(−ka·t)), C(0) = 0, ke < ka, h and mg/L, deterministic hard allowances per reading. Anything else in the paper is outside what the engine can check.`)
      : ['The server reports no supported model.'],
  }
}

export function selectionProblem(pages, pageCount, maxBatch) {
  if (!pages.length) return 'Select at least one page.'
  if (pages.length > maxBatch) return `Select at most ${maxBatch} pages per batch. Process further pages in another batch.`
  if (pages.some(p => p < 1 || p > pageCount)) return 'A selected page is not in this paper.'
  return ''
}
