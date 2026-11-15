// The assistant's path on the study page: approve the exact disclosure, send it once, and show
// the answer with the words it rests on. The general research service does the reading
// (Gemini when the server has it, or its local test responder). Its answers are never shown as
// checked; where a table fits a checker, the page hands it to that checker instead.
import { generalCapabilities, validateResearchAnalysis } from '../general-workspace.mjs'
import * as G from './general.mjs'
import { escapeHTML } from './results.mjs'
import { $, failure, status } from './ui.mjs'

export function createGeneral({ route, api, workspace, capabilities, sources, question, save, startCheck }) {
  let pending = null          // { question, assets, model, operationId } frozen for approval
  let estimate = null, record = null, m = null, busy = false

  const limits = () => generalCapabilities(capabilities())
  const reset = () => { pending = null; estimate = null; record = null; m = null }
  const reached = {
    data: () => true,
    check: () => Boolean(pending || record),
    result: () => Boolean(m),
    next: () => Boolean(m),
  }

  // What stops the assistant from being asked right now, in plain words, or null.
  function blocker() {
    const l = limits()
    if (!capabilities()) return 'Connecting to the server…'
    if (!l.analysisAvailable) return l.reason || 'The assistant is off on this server.'
    if (!sources().length) return 'Add at least one file.'
    if (sources().length > l.maxFiles) return `The assistant reads at most ${l.maxFiles} files at a time.`
    if (!question().trim()) return 'Write your question first.'
    return null
  }

  function prepare() {
    if (busy || blocker()) return
    const l = limits()
    pending = { question: question().trim(), assets: sources().map(s => s.asset), model: l.model, mode: l.analysisMode, operationId: G.operationId() }
    estimate = null
    $('ai-consent').checked = false
    location.hash = 'check'
    loadEstimate(pending)
  }
  async function loadEstimate(request) {
    try {
      const body = { question: request.question, assets: request.assets.map(a => ({ id: a.id, sha256: a.sha256 })) }
      const result = await api().json(`/workspaces/${encodeURIComponent(workspace())}/research-analysis-estimates`, body)
      if (pending === request) { estimate = result; renderCheck() }
    } catch { /* the estimate only informs; sending still checks everything on the server */ }
  }

  function renderCheck() {
    const req = pending ?? (m ? { question: m.question, assets: m.assets, model: m.model, mode: m.controlled ? 'controlled' : 'live' } : null)
    if (!req) return
    const controlled = req.mode === 'controlled'
    $('ai-check-lead').textContent = controlled
      ? 'This server uses a local test responder instead of Gemini. Nothing leaves this computer, and the response only restates your files.'
      : 'The assistant sends these files and your question to Gemini. Nothing is sent until you approve.'
    const pages = a => a.pages?.length ? `${a.pages.length} page${a.pages.length === 1 ? '' : 's'}` : ''
    const size = a => a.byte_size >= 1048576 ? `${(a.byte_size / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(a.byte_size / 1024))} KB`
    const rows = [
      ['Question', escapeHTML(req.question)],
      ['Files', `<ul class="plain">${req.assets.map(a => `<li>${escapeHTML(a.filename)} <span class="quiet">${[pages(a), size(a)].filter(Boolean).join(', ')}</span></li>`).join('')}</ul>`],
      ['Read by', controlled ? 'Local test responder (no model)' : `Gemini, model ${escapeHTML(req.model)}`],
    ]
    if (estimate?.estimated_input_tokens) rows.push(['Size', `About ${estimate.estimated_input_tokens.toLocaleString('en-US')} tokens of the ${estimate.max_input_tokens.toLocaleString('en-US')} one reading allows${estimate.fits_context === false ? '. Too much: remove a file.' : ''}`])
    rows.push(['What you get', 'A summary, claims with exact quotes from the files, any tables it copied, and next steps. The answer is not checked. Tables that fit a model Dr. Bean can check can be checked afterwards.'])
    $('ai-check-facts').innerHTML = rows.map(([k, v]) => `<tr><th scope="row">${k}</th><td>${v}</td></tr>`).join('')
    $('ai-consent-text').textContent = controlled ? 'I reviewed these files and this question.' : `I agree to send these files and this question to Gemini (${req.model}).`
    const ready = Boolean(pending) && estimate?.fits_context !== false
    $('ai-consent').hidden = !pending; $('ai-consent').parentElement.hidden = !pending
    $('ai-send').hidden = !pending
    $('ai-send').disabled = busy || !ready || !$('ai-consent').checked
    $('ai-check-problem').hidden = Boolean(pending)
    $('ai-check-problem').textContent = pending ? '' : 'This question has been answered. Change the files or question to ask again.'
  }

  async function send() {
    if (busy || !pending || !$('ai-consent').checked) return
    busy = true; renderCheck()
    try {
      status('ai-check-status', pending.mode === 'controlled' ? 'Running the local test responder…' : 'The assistant is reading your files…')
      const request = G.analysisRequest(pending)
      // One explicit request with its own operation id. A repeat after an unclear failure sends
      // the same id, and the server returns the answer it kept instead of asking twice.
      const saved = validateResearchAnalysis(await api().researchAnalysis(workspace(), request), pending.assets, workspace())
      record = saved; m = G.readAnalysis(saved, pending.assets)
      save({ kind: 'general', analysisId: saved.id, assetIds: pending.assets.map(a => a.id) })
      pending = null
      status('ai-check-status', '')
      location.hash = 'result'
    } catch (error) {
      failure('ai-check-status', error)
    } finally {
      busy = false; renderCheck()
    }
  }

  async function reopen(analysisId, assetIds, current = () => true) {
    const assets = await Promise.all(assetIds.map(id => api().json(`/research-assets/${encodeURIComponent(id)}`)))
    if (!current()) return null
    const restored = validateResearchAnalysis(await api().json(`/research-analyses/${encodeURIComponent(analysisId)}`), assets, workspace())
    if (!current()) return null
    record = restored
    m = G.readAnalysis(record, assets)
    return { assets, asked: m.question }
  }

  // Checks that the files or the assistant's tables allow, as buttons that start them.
  function checkButtons() {
    const out = []
    for (const kind of ['concentration', 'currents']) {
      const match = G.firstMatch(sources(), kind)
      if (match) out.push(`<li><div><h3>${G.CHECKS[kind].title}</h3><p>${G.CHECKS[kind].how}, from the table in ${escapeHTML(sources()[match.s].asset.filename)}.</p></div>
        <button type="button" class="primary" data-action="setup" data-kind="${kind}" data-source="${match.s}" data-table="${match.t}">${G.CHECKS[kind].button}</button></li>`)
      else {
        const i = (m?.b.extracted_tables ?? []).findIndex(table => G.checksFor(table).includes(kind))
        if (i >= 0) out.push(`<li><div><h3>${G.CHECKS[kind].title}</h3><p>${G.CHECKS[kind].how}, from the table the assistant copied. Check its values against the file first.</p></div>
          <button type="button" class="primary" data-action="ai-use-table" data-table="${i}" data-kind="${kind}">${G.CHECKS[kind].button}</button></li>`)
      }
    }
    return out
  }

  function renderResult(v) {
    if (!m) return
    $('ai-answer').hidden = v !== 'result'
    $('ai-sources').hidden = v !== 'result-readings'
    $('ai-files').hidden = v !== 'result-files'
    const when = m.created ? new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(m.created)) : ''
    $('ai-note').textContent = `${m.controlled ? 'Local test responder' : `Read by Gemini (${m.model})`}${when ? `, ${when}` : ''}. Not checked.`
    $('ai-title').textContent = m.question.length > 180 ? `${m.question.slice(0, 177)}…` : m.question
    $('ai-summary').textContent = m.failed ?? m.b.summary
    // The test responder already says what it is in its summary; a live answer gets the server's note.
    $('ai-label').textContent = m.controlled ? '' : (m.b.verification?.reason ?? '')
    $('ai-label').hidden = !$('ai-label').textContent
    $('ai-claims').innerHTML = G.claimList(m)
    $('ai-tables').innerHTML = G.tableBlocks(m, G.checksFor)
    const checks = checkButtons()
    $('ai-checkable').innerHTML = checks.length ? `<h2 class="sub">Dr. Bean can check this</h2><ul class="can-do compact">${checks.join('')}</ul>` : ''
    $('ai-questions').innerHTML = G.clarifications(m)
    $('ai-questions-wrap').hidden = !$('ai-questions').innerHTML
    $('ai-limits').innerHTML = (m.b.limitations ?? []).map(l => `<li>${escapeHTML(l)}</li>`).join('') || '<li>None stated.</li>'
    $('ai-source-list').innerHTML = G.sourcesView(m)
    $('ai-file-list').innerHTML = m.assets.map(a => `<li><div><h3>${escapeHTML(a.filename)}</h3><p class="mono">${escapeHTML(a.media_type)}, SHA-256 ${escapeHTML(a.sha256)}</p></div></li>`).join('')
  }

  function renderNext() {
    if (!m) return
    const checks = checkButtons()
    $('ai-next-lead').textContent = checks.length
      ? 'A table in your files fits a model Dr. Bean can check. Checking it turns part of this reading into an answer you can rely on.'
      : 'No table here fits a model Dr. Bean can check yet, so this reading stays unchecked.'
    $('ai-next-checks').innerHTML = checks.length ? `<ul class="can-do">${checks.join('')}</ul>` : ''
    $('ai-steps').innerHTML = G.nextSteps(m)
  }

  document.addEventListener('change', event => { if (event.target.id === 'ai-consent') renderCheck() })
  document.addEventListener('click', event => {
    const target = event.target.closest('[data-action]')
    if (!target) return
    const action = target.dataset.action
    if (action === 'ai-send') send()
    else if (action === 'ai-go-next') location.hash = 'next'
    else if (action === 'ai-view') { $('ai-dialog-body').textContent = JSON.stringify(record, null, 2); $('ai-dialog').showModal() }
    else if (action === 'ai-use-table') {
      const table = m?.b.extracted_tables?.[Number(target.dataset.table)]
      const asset = m?.assets.find(a => a.id === table?.asset_id) ?? m?.assets[0]
      if (table) startCheck(target.dataset.kind, [G.tableFromAnalysis(table, asset?.filename ?? 'a file')], 0, asset)
    }
  })

  return { reached, reset, prepare, blocker, renderCheck, renderResult, renderNext, reopen, hasAnswer: () => Boolean(m), limits }
}
