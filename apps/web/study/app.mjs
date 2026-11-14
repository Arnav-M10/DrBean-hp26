// Dr. Bean study page: your data in, a checked answer out. Every scientific step runs on
// the server; this page saves inputs, asks for each approval, waits for real results and
// makes the downloaded files readable. Two kinds of study share the four steps:
// concentration over time (research agent + Counterdex exact check) and electron currents
// (the numerical model comparison service, compare-app.mjs).
import { bootstrapSharedSession, readConnection } from '../session.mjs'
import { parseExact } from '../exact.mjs'
import { chartSVG } from './chart.mjs'
import { convert, guessColumns, readingsFrom, tablesFromJSON, tablesFromText } from './intake.mjs'
import { page as sym } from './math.mjs'
import { $, countStatus, failure, readable, saveText, size, status } from './ui.mjs'
import { createComparison } from './compare-app.mjs'
import { curvesFor, escapeHTML, fileView, finding, formatBound, formatRate, fromTexts, nextFinding, nextTable, readableReport, readingTable, summarize } from './results.mjs'

const pause = ms => new Promise(resolve => setTimeout(resolve, ms))
const STORE = 'dr-bean.study.v1'
const LIMITS = { aLow: '0.001', aHigh: '30', keLow: '0.015', keHigh: '0.35', kaLow: '0.4', kaHigh: '8' }
const SAMPLE = {
  name: 'Sample readings', rows: [['0.25', '4.80', '0.50'], ['0.5', '7.20', '0.50'], ['1', '8.00', '0.50'], ['2', '6.80', '0.50'], ['4', '5.70', '0.50']],
  low: '0.10', high: '0.17', origin: 'synthetic', timeOrigin: 'Time of dose', source: 'A made-up allowance of 0.50 mg/L for the sample',
  next: { times: '6, 8', allowance: '0.20', horizon: '8', source: 'A made-up allowance for the sample, not an instrument specification' },
}

let api, workspace, capabilities
let draft = blankDraft()
let study = readStore()          // { sessionId } of the study on screen
let snapshot = null               // latest research session from the server
let results = null                // { data, m } once a report exists
let next = { times: '', allowance: '', horizon: '', source: '' }
let busy = false
// A problem shows once its field has been left with a value or the person pressed the button,
// never while someone is still filling the form in for the first time.
let shown = { tried: false, touched: {} }, nextShown = { tried: false, touched: {} }

// Which kind of study the start screen offers; a viewer convenience, kept in this browser.
const KIND = 'dr-bean.study.kind'
let mode = (() => { try { return localStorage.getItem(KIND) === 'currents' ? 'currents' : 'concentration' } catch { return 'concentration' } })()
function setMode(next) {
  mode = next === 'currents' ? 'currents' : 'concentration'
  try { localStorage.setItem(KIND, mode) } catch { /* the choice just is not remembered */ }
}
const comparisonAvailable = () => capabilities ? capabilities.model_comparison?.available === true : null
const cmp = createComparison({
  route: () => route(), workspace: () => workspace, available: comparisonAvailable,
  seconds: () => capabilities?.model_comparison?.max_compute_seconds ?? 10,
  onConnectionFailure: error => connectionFailure(error),
  save: entry => { study = entry ?? {}; writeStore() },
})

function blankDraft() {
  return { kind: null, name: '', asset: null, tables: [], table: 0, columns: null, allowanceForAll: '', rows: [],
    low: '', high: '', origin: '', timeOrigin: 'Time of dose', source: '', limits: { ...LIMITS } }
}
function readStore() { try { return JSON.parse(localStorage.getItem(STORE) || '{}')[workspace] ?? {} } catch { return {} } }
function writeStore() {
  try {
    const all = JSON.parse(localStorage.getItem(STORE) || '{}')
    all[workspace] = study
    localStorage.setItem(STORE, JSON.stringify(all))
  } catch { /* the study stays on the server; only reopening after a reload needs storage */ }
}

// Numbers are kept exactly as typed, then made exact fractions for the server.
function exact(text) { try { return parseExact(String(text).replace(',', '.')) } catch { return null } }
const value = text => { const e = exact(text); if (!e) return NaN; const [n, d] = e.split('/').map(Number); return n / d }
// A fraction whose denominator only has factors 2 and 5 is shown as a plain decimal.
function decimal(fraction) {
  let [n, d] = fraction.split('/').map(BigInt)
  let twos = 0, fives = 0, rest = d
  while (rest % 2n === 0n) { rest /= 2n; twos++ }
  while (rest % 5n === 0n) { rest /= 5n; fives++ }
  if (rest !== 1n) return fraction
  const places = Math.max(twos, fives), scaled = n * (10n ** BigInt(places)) / d
  const sign = scaled < 0n ? '-' : '', digits = (scaled < 0n ? -scaled : scaled).toString().padStart(places + 1, '0')
  return places ? `${sign}${digits.slice(0, -places)}.${digits.slice(-places)}` : sign + digits
}

// --- Connection -------------------------------------------------------------------------
function setConnection(text, tone = '') {
  $('connection').textContent = text
  $('connection').className = `meta ${tone}`
}

// Same recovery as the main page: say what happened, offer a retry, and offer a new
// private workspace only when the session layer says that is the way forward.
function connectionFailure(error) {
  const message = error.mayStartNew || error.code === 'session_storage_unavailable' ? error.message
    : error.status === 429 ? 'The server cannot open another private session right now. Retry later. Earlier research is kept.'
    : error.status === 404 ? 'Private access is not set up on this server. Ask its owner to check the setup, then retry.'
    : error.kind === 'unreachable' || [502, 503, 504].includes(error.status) ? 'The server is unavailable or still starting. Retry when it is ready.'
    : error.status === 401 ? 'This session is no longer available. Retry the connection to see how to continue.'
    : error.message || 'The private workspace could not be opened. Retry the connection.'
  setConnection('Not connected', 'bad')
  $('connection-message').textContent = message
  $('start-new-workspace').hidden = error.mayStartNew !== true
  $('connection-problem').hidden = false
}

let connecting = false
async function connect(startNew = false) {
  if (connecting) return
  connecting = true
  setConnection('Connecting…')
  $('connection-problem').hidden = true
  try {
    const opened = await bootstrapSharedSession(undefined, { startNew })
    // A different workspace shares nothing with the old one, so its study starts empty.
    if (workspace && workspace !== opened.session.workspace_id) {
      draft = blankDraft(); snapshot = null; results = null; cmp.reset(); $('study-name').textContent = ''; location.hash = 'data'
    }
    api = opened.api; workspace = opened.session.workspace_id
    api.setConnectionFailureHandler(error => { if (api === opened.api && !connecting) connectionFailure(error) })
    startStatus('')
    study = readStore()
    capabilities = await readConnection(api, '/capabilities')
    connectionLabel()
    await reopen()
    route()
  } catch (error) {
    connectionFailure(error)
  } finally {
    connecting = false
  }
  route()
}

const canRun = () => capabilities?.science?.available && capabilities.deepagents?.dispatch_enabled && capabilities.deepagents.execution_mode !== 'live'

function connectionLabel() {
  if (!api || !capabilities) return
  const research = capabilities.deepagents
  if (mode === 'currents') setConnection(comparisonAvailable() ? 'Private workspace' : 'Comparisons are not available on this server', comparisonAvailable() ? '' : 'bad')
  else if (!capabilities.science?.available) setConnection('The checker is not running on this server', 'bad')
  else if (!research?.dispatch_enabled) setConnection('Checks are turned off on this server', 'bad')
  else if (research.execution_mode === 'live') setConnection('This server uses a live model, which needs consent in the classic view', 'bad')
  else setConnection('Private workspace')
}

async function reopen() {
  if (study.kind === 'currents' && study.comparisonId) {
    try {
      await cmp.reopen(study.comparisonId)
      setMode('currents'); connectionLabel()
      $('study-name').textContent = 'Electron currents'
      if (!location.hash) location.replace('#result')
    } catch (error) {
      if (error.status === 404) { study = {}; writeStore() }
    }
    return
  }
  if (!study.sessionId) return
  try {
    snapshot = await api.json(`/research-sessions/${encodeURIComponent(study.sessionId)}`)
    draftFromSnapshot(snapshot)
    setMode('concentration'); connectionLabel()
    if (snapshot.reports.length) await loadResults()
    if (!location.hash) location.replace('#' + (results ? (results.m.next ? 'next' : 'result') : snapshot.pending_review?.kind === 'plan' ? 'check' : 'data'))
  } catch (error) {
    // Forget the saved study only when the server says it does not exist.
    if (error.status === 404) { study = {}; writeStore() }
  }
}

// --- Draft from the saved study ------------------------------------------------------------
function draftFromSnapshot(s) {
  const { dataset, problem } = s.reviewed_context
  if (!dataset || !problem) return
  const show = text => decimal(text)
  draft = {
    ...blankDraft(), kind: 'saved', name: dataset.body.experiment_id, origin: dataset.body.origin,
    timeOrigin: dataset.body.time_origin, source: dataset.body.change_reason,
    low: decimal(problem.body.target.lower), high: decimal(problem.body.target.upper),
    limits: { aLow: show(problem.body.domain.A.lower), aHigh: show(problem.body.domain.A.upper), keLow: show(problem.body.domain.ke.lower),
      keHigh: show(problem.body.domain.ke.upper), kaLow: show(problem.body.domain.ka.lower), kaHigh: show(problem.body.domain.ka.upper) },
    rows: dataset.body.rows.map(row => ({ time: row.original_values?.time ?? decimal(row.time), value: row.original_values?.concentration ?? decimal(row.concentration),
      allowance: row.original_values?.hard_allowance ?? decimal(row.hard_allowance), included: row.included, note: row.notes })),
  }
  $('study-name').textContent = draft.name
}

// --- Bringing data in ----------------------------------------------------------------------
function startStatus(text, problem = false) {
  $('start-status').hidden = problem || !text
  $('start-status').textContent = problem ? '' : text
  $('start-problem').hidden = !problem
  $('start-problem').textContent = problem ? text : ''
}

async function useFile(file) {
  if (!file) return
  if (!api) return startStatus('Connect first: the page could not open your private workspace.', true)
  if (file.size > 5 * 1024 * 1024) return startStatus('This file is larger than 5 MB. Save the table on its own and try again.', true)
  try {
    startStatus(`Uploading ${file.name}…`)
    const asset = await api.uploadResearchAsset(workspace, file)
    if (asset.media_type.startsWith('image/')) {
      return startStatus('Dr. Bean cannot read numbers from an image here, because the AI reader is off on this server. Type the readings, paste them, or upload a CSV or a PDF with selectable text.', true)
    }
    startStatus(`Reading ${asset.filename || file.name}…`)
    const tables = []
    for (const p of asset.pages.slice(0, 10)) {
      const page = await api.json(`/research-assets/${encodeURIComponent(asset.id)}/pages/${p.page_index}/text`)
      const where = { file: asset.filename || file.name, page: asset.media_type === 'application/pdf' ? p.page_number : null }
      tables.push(...(asset.media_type === 'application/json' ? tablesFromJSON(page.text, where) : tablesFromText(page.text, where)))
    }
    if (!tables.length) return startStatus(`No table of numbers was found in ${asset.filename || file.name}. Paste or type the readings instead.`, true)
    startStatus('')
    const base = { kind: 'file', name: (asset.filename || file.name).replace(/\.[^.]+$/, ''), asset }
    if (mode === 'currents') { $('study-name').textContent = base.name; cmp.useTables(tables, base) } else useTables(tables, base)
  } catch (error) {
    startStatus(readable(error), true)
  }
}

function useTables(tables, base) {
  const best = tables.reduce((pick, t, i) => t.rows.length > tables[pick].rows.length ? i : pick, 0)
  draft = { ...blankDraft(), ...base, tables, table: best }
  applyTable()
  $('study-name').textContent = draft.name
  showEditor()
}

function applyTable() {
  const table = draft.tables[draft.table]
  draft.columns ??= guessColumns(table)
  const c = draft.columns
  const raw = readingsFrom(table, c, { allowanceForAll: draft.allowanceForAll })
  draft.rows = raw.map(r => {
    const where = [table.file, table.page ? `page ${table.page}` : '', r.line ? `line ${r.line}` : ''].filter(Boolean).join(', ')
    const safe = (text, kind, unit) => { try { return decimal(convert(text, kind, unit)) } catch { return String(text) } }
    return {
      time: safe(r.time, 'time', c.units.time), value: safe(r.value, 'concentration', c.units.concentration),
      allowance: c.allowance === null ? draft.allowanceForAll : safe(r.allowance, 'concentration', c.units.concentration),
      included: true, note: `From ${where}: ${[r.time, r.value, c.allowance === null ? null : r.allowance].filter(v => v !== null).join(', ')}`,
    }
  })
  const maxC = Math.max(0, ...draft.rows.map(r => value(r.value)).filter(Number.isFinite))
  if (maxC * 5 > 30) draft.limits.aHigh = String(Math.ceil(maxC * 5))
}

function useSample() {
  draft = { ...blankDraft(), kind: 'sample', name: SAMPLE.name, low: SAMPLE.low, high: SAMPLE.high, origin: SAMPLE.origin,
    timeOrigin: SAMPLE.timeOrigin, source: SAMPLE.source, rows: SAMPLE.rows.map(([time, v, allowance]) => ({ time, value: v, allowance, included: true, note: 'Sample reading, made up' })) }
  next = { ...SAMPLE.next }
  $('study-name').textContent = draft.name
  showEditor()
}

function showEditor() {
  study = {}; snapshot = null; results = null; writeStore()
  shown = { tried: false, touched: {} }; nextShown = { tried: false, touched: {} }
  location.hash = 'data'
  route()
  renderMapping()
  $('claim-low').focus({ preventScroll: true })
}

// --- Checks on the draft --------------------------------------------------------------------
function problems() {
  const list = []
  const rows = draft.rows.filter(r => r.included)
  if (rows.length < 3) list.push(['rows', 'Use at least three readings.', 'rows'])
  if (rows.some(r => exact(r.time) === null || exact(r.value) === null)) list.push(['rows', 'Each reading needs a time and a concentration written as numbers.', 'rows'])
  else if (rows.some(r => value(r.time) < 0 || value(r.value) < 0)) list.push(['rows', 'Times and concentrations cannot be negative.', 'rows'])
  if (rows.some(r => !(value(r.allowance) > 0))) list.push(['rows', 'Each reading needs an allowance above zero.', 'rows'])
  if (new Set(rows.map(r => value(r.time))).size < 3) list.push(['rows', 'Use at least three different times.', 'rows'])
  const low = value(draft.low), high = value(draft.high), L = draft.limits
  if (!(low > 0) || !(high >= low)) list.push(['claim', 'Write the claim as two rates above zero, the smaller one first.', 'claim'])
  else if (low < value(L.keLow) || high > value(L.keHigh)) list.push(['claim', `Keep the claim between ${L.keLow} and ${L.keHigh} per hour, the search limits for ${sym.ke}.`, 'claim'])
  if (!draft.origin) list.push(['about', 'Say whether the readings were measured or made up.', 'origin'])
  if (!draft.timeOrigin.trim()) list.push(['about', 'Say when time 0 is.', 'timeOrigin'])
  if (!draft.source.trim()) list.push(['about', 'Say where the allowances come from.', 'source'])
  for (const [k, name] of [['a', sym.A], ['ke', sym.ke], ['ka', sym.ka]]) {
    if (!(value(L[k + 'Low']) > 0) || !(value(L[k + 'High']) > value(L[k + 'Low']))) list.push(['limits', `The search limits for ${name} need a lowest value above zero and a higher highest value.`, 'limits'])
  }
  if (!(value(L.keHigh) < value(L.kaLow))) list.push(['limits', `The highest ${sym.ke} must stay below the lowest ${sym.ka}.`, 'limits'])
  return list
}

// --- Saving and running ------------------------------------------------------------------------

const slug = text => (text || 'study').normalize('NFKD').replace(/[^A-Za-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 64) || 'study'

function datasetBody() {
  return {
    schema_version: 'DB-SC-1', experiment_id: `${slug(draft.name)}-${new Date().toISOString().slice(0, 10)}`, time_origin: draft.timeOrigin.trim(),
    origin: draft.origin, parent_id: null, change_reason: draft.source.trim().slice(0, 2000),
    rows: draft.rows.map((r, i) => ({
      id: `row_${i + 1}`, time: exact(r.time), concentration: exact(r.value), hard_allowance: exact(r.allowance), included: r.included,
      original_values: { time: r.time, concentration: r.value, hard_allowance: r.allowance }, source_asset_id: null, notes: (r.note || '').slice(0, 2000),
    })),
  }
}

function problemBody(dataset) {
  const L = draft.limits
  return {
    schema_version: 'DB-SC-1', dataset_id: dataset.id, dataset_digest: dataset.digest, model: 'two_rate_concentration',
    domain: { A: { lower: exact(L.aLow), upper: exact(L.aHigh) }, ke: { lower: exact(L.keLow), upper: exact(L.keHigh) }, ka: { lower: exact(L.kaLow), upper: exact(L.kaHigh) }, rate_order: 'ke_lt_ka' },
    initial_concentration: '0/1', observable: 'concentration', time_unit: 'h', concentration_unit: 'mg/L', rate_unit: '1/h',
    target: { parameter: 'ke', lower: exact(draft.low), upper: exact(draft.high), closed: true },
  }
}

async function readSession() {
  for (let attempt = 0; ; attempt++) {
    try { return await api.json(`/research-sessions/${encodeURIComponent(study.sessionId)}`) } catch (error) {
      if (error.kind !== 'unreachable' || attempt >= 4) throw error
      await pause(1000 * (attempt + 1))
    }
  }
}

// Waits for the server, describing what is actually happening. No invented progress.
async function waitWhile(pending, statusId, approved) {
  for (let i = 0; ; i++) {
    snapshot = await readSession()
    const s = snapshot.state
    status(statusId, s === 'queued' ? 'Waiting for the worker…' : s === 'running' ? (approved ? 'Running…' : 'The assistant is preparing it…')
      : s === 'waiting_child' ? 'Counterdex is checking your readings…' : '')
    if (!pending(snapshot)) return snapshot
    await pause(i < 30 ? 700 : 1500)
    if (i > 900) throw new Error('This is taking longer than usual. Reload the page later to see where it stands; nothing will run twice.')
  }
}

function stopped(s) {
  if (s.state === 'failed' || s.state === 'cancelled') return `The step stopped (${s.action?.error_code || s.state}). Your saved readings and any finished results are kept.`
  if (s.state === 'needs_reconciliation') return 'The worker was interrupted. Reload the page to continue; nothing will run twice.'
  if (s.pending_review?.kind === 'research_clarification') return `The assistant asks: ${s.pending_review.body.reason}`
  return ''
}

// Where the person goes to fix a problem.
const FIELDS = { claim: () => $(value(draft.low) > 0 ? 'claim-high' : 'claim-low'), origin: () => document.querySelector('[name="origin"]'),
  timeOrigin: () => $('time-origin'), source: () => $('allowance-source'), rows: () => $('rows').querySelector('input[data-key="time"]') ?? document.querySelector('[data-action="add"]'),
  limits: () => { $('limits').open = true; return document.querySelector('[data-limit]') } }

async function prepare() {
  if (busy) return
  const issues = problems()
  if (issues.length) {
    const order = ['claim', 'about', 'rows', 'limits'], first = [...issues].sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]))[0]
    shown.tried = true; renderData(); FIELDS[first[2]]()?.focus(); return
  }
  busy = true; $('prepare').disabled = true
  try {
    status('prepare-status', 'Saving your readings…')
    const dataset = await api.json(`/workspaces/${encodeURIComponent(workspace)}/datasets`, datasetBody())
    status('prepare-status', 'Saving your claim…')
    const problem = await api.json(`/workspaces/${encodeURIComponent(workspace)}/problems`, problemBody(dataset))
    status('prepare-status', 'Starting the study…')
    const created = await api.json(`/workspaces/${encodeURIComponent(workspace)}/research-sessions`, {
      objective: `Do these readings keep ke between ${draft.low} and ${draft.high} per hour?`, problem_id: problem.id,
      expected_problem_digest: problem.digest, source_ids: draft.asset ? [draft.asset.id] : [], mode: 'controlled', design_constraints: null })
    study = { sessionId: created.id }; writeStore()
    await api.json(`/research-sessions/${encodeURIComponent(created.id)}/advance`, { expected_revision: created.revision })
    const s = await waitWhile(s => ['queued', 'running'].includes(s.state), 'prepare-status', false)
    if (s.state === 'waiting_review' && s.pending_review?.kind === 'plan') { status('prepare-status', ''); location.hash = 'check' }
    else status('prepare-status', stopped(s) || 'The assistant did not prepare a check.', 'bad')
  } catch (error) {
    failure('prepare-status', error)
  } finally {
    busy = false; $('prepare').disabled = false
  }
}

async function approve(statusId, buttonId, after) {
  if (busy) return
  const s = snapshot, review = s?.pending_review
  if (!review) return
  busy = true; $(buttonId).disabled = true
  try {
    status(statusId, 'Recording your approval…')
    await api.json(`/research-sessions/${encodeURIComponent(s.id)}/decisions`, { expected_revision: s.revision, pending_review_id: review.id,
      expected_review_digest: s.pending_review_digest, decision: 'approve', accepted: true })
    const done = await waitWhile(x => ['queued', 'running', 'waiting_child'].includes(x.state), statusId, true)
    if (done.state !== 'completed') return status(statusId, stopped(done) || 'The run did not finish.', 'bad')
    status(statusId, 'Reading the results…')
    await loadResults()
    status(statusId, '')
    after()
  } catch (error) {
    failure(statusId, error)
  } finally {
    busy = false; $(buttonId).disabled = false
  }
}

// The same files a person can download, verified byte for byte against their fingerprints.
async function loadResults() {
  const reportId = snapshot.reports.at(-1)
  const texts = {}
  const read = bytes => new TextDecoder().decode(bytes)
  const report = await api.download(`/reports/${encodeURIComponent(reportId)}/download`)
  const reportText = read(report.bytes)
  texts[`dr-bean-${reportId}.json`] = reportText
  for (const entry of JSON.parse(reportText).body.native_evidence) {
    const id = encodeURIComponent(entry.artifact.id)
    texts[entry.native_filename] = read((await api.download(`/artifacts/${id}`, { sha256: entry.artifact.sha256, byte_size: entry.artifact.byte_size })).bytes)
    texts[entry.anchor_filename] = read((await api.download(`/artifacts/${id}/anchor?download=true`)).bytes)
  }
  const data = fromTexts(texts)
  results = { data, m: summarize(data) }
}

async function prepareNext() {
  if (busy) return
  const list = nextProblems()
  if (list.length) { nextShown.tried = true; renderNext(); $(`next-${list[0][1]}`).focus(); return }
  busy = true; $('prepare-next').disabled = true
  const constraints = {
    feasible_times: next.times.split(/[\s,;]+/).filter(Boolean).map(exact), future_hard_allowance: exact(next.allowance), maximum_horizon: exact(next.horizon),
    allowance_origin: { kind: 'hypothetical', description: next.source.trim() }, requested_tier: 'checked_pair_separation', allow_construction: true, allow_continuation: true,
  }
  try {
    let s = snapshot = await readSession()
    if (s.state === 'completed') {
      status('next-status', 'Asking the assistant for the comparison…')
      await api.json(`/research-sessions/${encodeURIComponent(s.id)}/advance`, { expected_revision: s.revision })
      s = await waitWhile(x => ['queued', 'running'].includes(x.state), 'next-status', false)
    }
    if (s.state === 'waiting_review' && s.pending_review?.kind === 'research_clarification' && s.pending_review.body.fields.includes('design_constraints')) {
      status('next-status', 'Giving the assistant your times and allowance…')
      await api.json(`/research-sessions/${encodeURIComponent(s.id)}/inputs`, { expected_revision: s.revision, pending_review_id: s.pending_review.id,
        expected_review_digest: s.pending_review_digest, accepted: true, design_constraints: constraints, answers: {} })
      s = await waitWhile(x => ['queued', 'running'].includes(x.state), 'next-status', false)
    }
    if (s.state === 'waiting_review' && s.pending_review?.kind === 'design_plan') { status('next-status', ''); renderNext() }
    else status('next-status', stopped(s) || 'The assistant did not prepare a comparison.', 'bad')
  } catch (error) {
    failure('next-status', error)
  } finally {
    busy = false; $('prepare-next').disabled = false
  }
}

function nextProblems() {
  const times = next.times.split(/[\s,;]+/).filter(Boolean).map(value), list = []
  if (!times.length || times.some(t => !(t > 0))) list.push(['Give one or more possible times in hours, such as 6, 8.', 'times'])
  else if (results && times.some(t => t <= Math.max(...results.m.included.map(r => r.t)))) list.push(['Choose times after your last reading.', 'times'])
  if (!(value(next.allowance) > 0)) list.push(['The allowance for the new reading must be above zero.', 'allowance'])
  if (!(value(next.horizon) > 0) || times.some(t => t > value(next.horizon))) list.push(['The latest time must be at or after every possible time.', 'horizon'])
  if (!next.source.trim()) list.push(['Say where the new allowance comes from.', 'source'])
  return list
}

// --- Rendering --------------------------------------------------------------------------------
const VIEWS = { data: 'data', check: 'check', result: 'result', 'result-readings': 'result', 'result-files': 'result', next: 'next' }
const STEPS = ['data', 'check', 'result', 'next']
// Any other fragment (the skip link's #main) keeps the step on screen.
let lastView = 'data'
const view = () => { const hash = location.hash.slice(1); if (hash in VIEWS || !hash) lastView = hash || 'data'; return lastView }
const pkReached = {
  data: () => true,
  check: () => Boolean(snapshot && (snapshot.pending_review?.kind === 'plan' || snapshot.children.length)),
  result: () => Boolean(results),
  next: () => Boolean(results && results.m.outcome === 'certified_counterexample' && results.m.candidates.length === 2),
}

const reached = new Proxy({}, { get: (_, step) => (mode === 'currents' ? cmp.reached : pkReached)[step] })

function route() {
  let v = view()
  if (!reached[VIEWS[v]]()) v = 'data'
  const section = VIEWS[v]
  const currents = mode === 'currents'
  for (const step of ['check', 'result', 'next']) { $(`pk-${step}`).hidden = currents; $(`cmp-${step}`).hidden = !currents }
  document.querySelector('[data-label="data"]').textContent = currents ? 'Data and models' : 'Data and claim'
  document.querySelector('[data-label="check"]').textContent = currents ? 'Comparison' : 'Check'
  document.querySelectorAll('main > section').forEach(s => { s.hidden = s.id !== section })
  const index = STEPS.indexOf(section)
  document.querySelectorAll('[data-step]').forEach((link, i) => {
    const step = link.dataset.step
    if (step === section) link.setAttribute('aria-current', 'step'); else link.removeAttribute('aria-current')
    link.classList.toggle('done', i < index && reached[STEPS[i + 1]]())
    if (reached[step]()) link.removeAttribute('aria-disabled'); else link.setAttribute('aria-disabled', 'true')
  })
  if (section === 'data') renderDataStep()
  if (section === 'check') currents ? cmp.renderCheck() : renderCheck()
  if (section === 'result') currents ? cmp.renderResult(v) : renderResult(v)
  if (section === 'next') currents ? cmp.renderNext() : renderNext()
  const titles = { data: 'Your data', check: currents ? 'Approve the comparison' : 'Approve the check', result: 'Result', next: 'Next measurement' }
  document.title = `${titles[section]}: Dr. Bean`
  $('announce').textContent = titles[section]
}

// Step 1 shows the start screen until there is a draft of the kind on screen.
const START = {
  concentration: { lead: 'Concentration over time, from any file. Dr. Bean finds the numbers, you confirm them, and the checker tests your claim about the elimination rate.', note: '' },
  currents: { lead: 'Electron currents from a planar collector at several angles and energy windows, from any file. Dr. Bean fits an isotropic and a bi-Maxwellian distribution to the same currents and finds the setting that could tell them apart.',
    note: 'This version compares made-up currents only. The fits are numerical, not exact proofs.' },
}
function renderDataStep() {
  const currents = mode === 'currents', editing = currents ? cmp.editing() : Boolean(draft.kind)
  $('start').hidden = editing
  $('editor').hidden = currents || !draft.kind
  $('cmp-editor').hidden = !currents || !cmp.editing()
  if (!editing) return renderStart()
  if (currents) cmp.renderData(); else renderData()
}
function renderStart() {
  document.querySelectorAll('[name="study-kind"]').forEach(input => {
    input.checked = input.value === mode
    input.disabled = input.value === 'currents' && comparisonAvailable() === false
  })
  $('start-lead').textContent = START[mode].lead
  $('start-note').hidden = !START[mode].note
  $('start-note').textContent = START[mode].note
}

function renderData() {
  if (!draft.kind) return
  for (const id of ['claim-low', 'claim-high']) if (document.activeElement !== $(id)) $(id).value = draft[id === 'claim-low' ? 'low' : 'high']
  if (document.activeElement !== $('time-origin')) $('time-origin').value = draft.timeOrigin
  if (document.activeElement !== $('allowance-source')) $('allowance-source').value = draft.source
  document.querySelectorAll('[name="origin"]').forEach(input => { input.checked = input.value === draft.origin })
  document.querySelectorAll('[data-limit]').forEach(input => { if (document.activeElement !== input) input.value = draft.limits[input.dataset.limit] })
  const where = draft.kind === 'sample' ? 'Sample readings, made up for trying Dr. Bean. Change any value.'
    : draft.kind === 'file' ? `From ${escapeHTML(draft.asset?.filename || draft.name)}. The original file is saved with your study. Check every value against it.`
    : draft.kind === 'saved' ? 'The readings and claim saved with this study. Changing them starts a new check.'
    : draft.kind === 'paste' ? 'From the table you pasted. Check every value.' : 'Type your readings below.'
  $('source-line').innerHTML = where
  if (!document.activeElement?.dataset?.row) renderRows()
  // A reading without an allowance yet is still drawn, as a point without its bar.
  const points = draft.rows.filter(r => r.included).map(r => ({ t: value(r.time), v: value(r.value), e: value(r.allowance) }))
    .filter(p => [p.t, p.v].every(Number.isFinite) && p.t >= 0 && p.v >= 0).map(p => ({ ...p, e: p.e > 0 ? p.e : 0 }))
  const title = points.every(p => p.e > 0) ? `${points.length} readings with their allowances` : `${points.length} readings, some without an allowance yet`
  $('data-chart').innerHTML = points.length ? chartSVG({ readings: points, title, ...size('data-chart', 270) }) : '<p class="empty">Readings appear here as you add them.</p>'
  $('used-count').textContent = `${draft.rows.filter(r => r.included).length} of ${draft.rows.length} readings used`
  const list = problems(), visible = list.filter(([, , field]) => shown.tried || shown.touched[field])
  for (const area of ['rows', 'claim', 'about', 'limits']) {
    const items = visible.filter(([where]) => where === area).map(([, text]) => text)
    $(`problems-${area}`).hidden = !items.length
    $(`problems-${area}`).innerHTML = items.join(' ')
  }
  if (visible.some(([where]) => where === 'limits')) $('limits').open = true
  $('prepare').disabled = busy || !canRun()
  if (!canRun() && api) status('prepare-status', 'Checks cannot run on this server right now.', 'bad')
  else if (!busy) countStatus('prepare-status', shown.tried ? list.length : 0)
}

function renderMapping() {
  const box = $('mapping')
  if (!['file', 'paste'].includes(draft.kind) || !draft.tables.length) { box.hidden = true; $('allowance-hint').hidden = false; return }
  const table = draft.tables[draft.table], c = draft.columns
  const names = Array.from({ length: table.width }, (_, i) => table.header?.[i] || `Column ${i + 1}`)
  const options = (selected, none) => (none ? `<option value=""${selected === null ? ' selected' : ''}>${none}</option>` : '') + names.map((n, i) => `<option value="${i}"${i === selected ? ' selected' : ''}>${escapeHTML(n)}</option>`).join('')
  const tables = draft.tables.map((t, i) => `<option value="${i}"${i === draft.table ? ' selected' : ''}>Table ${i + 1}: ${t.rows.length} rows${t.page ? `, page ${t.page}` : ''}</option>`).join('')
  box.hidden = false
  box.innerHTML = `
    ${draft.tables.length > 1 ? `<label class="field">Table<select data-map="table">${tables}</select></label>` : ''}
    <label class="field">Time<select data-map="time">${options(c.time)}</select></label>
    <label class="field narrow">In<select data-map="timeUnit"><option value="h"${c.units.time === 'h' ? ' selected' : ''}>hours</option><option value="min"${c.units.time === 'min' ? ' selected' : ''}>minutes</option><option value="day"${c.units.time === 'day' ? ' selected' : ''}>days</option></select></label>
    <label class="field">Concentration<select data-map="concentration">${options(c.concentration)}</select></label>
    <label class="field narrow">In<select data-map="concUnit">${['mg/L', 'µg/mL', 'ng/mL', 'µg/L'].map(u => `<option value="${u}"${c.units.concentration === u ? ' selected' : ''}>${u}</option>`).join('')}</select></label>
    <label class="field">Allowance<select data-map="allowance">${options(c.allowance, 'One value for every reading')}</select></label>
    ${c.allowance === null ? `<label class="field narrow">Value (mg/L)<input data-map="allowanceForAll" inputmode="decimal" value="${escapeHTML(draft.allowanceForAll)}"></label>` : ''}
    ${c.spread !== null ? `<p class="hint wide">"${escapeHTML(names[c.spread])}" looks like a standard deviation, so it is not used. An allowance is the largest gap you accept between a curve and a reading.</p>` : ''}`
  $('allowance-hint').hidden = c.spread !== null
}

function renderRows() {
  $('rows').innerHTML = draft.rows.map((r, i) => `<tr${r.included ? '' : ' class="unused"'}${r.note ? ` title="${escapeHTML(r.note)}"` : ''}>
    <td><input type="checkbox" aria-label="Use reading ${i + 1}" data-row="${i}" data-key="included"${r.included ? ' checked' : ''}></td>
    ${[['time', 'Hours'], ['value', 'Concentration in mg/L'], ['allowance', 'Allowance in mg/L']].map(([key, label]) =>
      `<td><input inputmode="decimal" autocomplete="off" spellcheck="false" aria-label="${label}, reading ${i + 1}" value="${escapeHTML(r[key])}" data-row="${i}" data-key="${key}"></td>`).join('')}
    <td><button type="button" class="icon" aria-label="Remove reading ${i + 1}" data-action="remove" data-row="${i}"><svg aria-hidden="true"><use href="#i-x"/></svg></button></td></tr>`).join('')
}

function renderCheck() {
  const s = snapshot, review = s?.pending_review
  const plan = review?.body
  const used = draft.rows.filter(r => r.included)
  const times = used.map(r => value(r.time))
  $('check-facts').innerHTML = [
    ['Readings', `${used.length} readings from ${Math.min(...times)} to ${Math.max(...times)} hours`],
    ['Claim', `${sym.claim(draft.low, draft.high)}, both ends included`],
    ['Model', sym.modelInline],
    ['What runs', `Counterdex searches for curves that stay within every allowance while putting ${sym.ke} outside the claim, then checks the best ones exactly. If it finds none, that does not prove the claim.`],
    ['Limit', plan?.budget ? `One run of up to ${plan.budget.scientific_wall_seconds ?? plan.budget.wall_seconds} seconds` : 'One run'],
  ].map(([k, v]) => `<tr><th scope="row">${k}</th><td>${v}</td></tr>`).join('')
  $('check-exact').textContent = review ? JSON.stringify({ review_id: review.id, review_digest: s.pending_review_digest, plan }, null, 2) : ''
  const ready = review?.kind === 'plan' && s.state === 'waiting_review'
  $('approve-check').hidden = !ready
  $('check-problem').hidden = ready
  $('check-problem').textContent = ready ? '' : s?.children.length ? 'This check has already run.' : 'Prepare the check first.'
}

function renderResult(v) {
  if (!results) return
  const { m } = results
  document.querySelectorAll('[data-view]').forEach(link => { if (link.hash === '#' + v) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current') })
  $('result-answer').hidden = v !== 'result'
  $('result-readings').hidden = v !== 'result-readings'
  $('result-files').hidden = v !== 'result-files'
  const f = finding(m)
  $('result-note').textContent = `Checked ${new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(m.created))} with Counterdex ${m.checker.version}`
  $('result-title').innerHTML = f.headline
  $('result-lead').innerHTML = f.lead
  $('result-limit').innerHTML = f.limit
  if (v === 'result') $('result-chart').innerHTML = chartSVG({ readings: m.included, curves: curvesFor(m), title: 'Your readings with their allowances and the curves that fit them', ...size('result-chart') })
  $('candidates').innerHTML = m.candidates.map(c => `<tr class="${c.tone}"><th scope="row"><span class="swatch" aria-hidden="true"></span>${c.outside ? 'Outside the claim' : 'Inside the claim'}</th>
    <td>${formatRate(c.params.ke)}<div class="exact">${sym.exact(c.exact.ke)}</div></td><td>${formatRate(c.params.ka)}<div class="exact">${sym.exact(c.exact.ka)}</div></td>
    <td>${formatRate(c.params.A)}<div class="exact">${sym.exact(c.exact.A)}</div></td></tr>`).join('') || '<tr><td colspan="4" class="quiet">No curve was kept.</td></tr>'
  $('result-search').textContent = `The checker tried ${m.search.attempted.toLocaleString('en-US')} combinations of the two rates inside the search limits, found ${m.search.feasible.toLocaleString('en-US')} that could fit and checked the best ones exactly.`
  $('result-readings-table').innerHTML = readingTable(m)
  const groups = [['Full record', 'The saved study in one file: readings, claim, approvals, results and the list of proofs.', f => f.kind === 'record'],
    ['Claim check', "Counterdex's exact calculations for the check, and the fingerprints that tie them to your readings.", f => f.step === 'check'],
    ['Next measurement', "Counterdex's exact calculations for the comparison, and their fingerprints.", f => f.step === 'next']]
  $('file-list').innerHTML = groups.map(([title, about, pick]) => ({ title, about, files: m.files.filter(pick) })).filter(g => g.files.length).map(g => `<li><div><h3>${escapeHTML(g.title)}</h3><p>${escapeHTML(g.about)}</p></div>
    <div class="file-actions">${g.files.map(file => `<button type="button" class="secondary small" data-action="view-file" data-file="${m.files.indexOf(file)}">View ${file.kind === 'record' ? 'record' : file.kind === 'proof' ? 'proof' : 'fingerprints'}</button>`).join('')}</div></li>`).join('')
  const canPlan = reached.next()
  $('to-next').hidden = !canPlan
  $('next-unavailable').hidden = canPlan
  $('next-unavailable').textContent = canPlan ? '' : 'A next-measurement plan needs two fitting curves, one inside and one outside the claim. This check did not find that pair.'
}

function renderNext() {
  const m = results?.m
  const answered = Boolean(m?.next)
  const reviewing = !answered && snapshot?.state === 'waiting_review' && snapshot.pending_review?.kind === 'design_plan'
  $('next-settings').hidden = answered || reviewing
  $('next-review').hidden = !reviewing
  $('next-answer').hidden = !answered
  if (answered) {
    const nf = nextFinding(m)
    $('next-title').textContent = nf.headline
    $('next-lead').textContent = nf.lead
    $('next-result-chart').innerHTML = chartSVG({ readings: m.included, curves: curvesFor(m), title: 'Predicted ranges at the possible times, from the checked comparison', ...size('next-result-chart'),
      future: { until: m.next.horizon, times: m.next.times.map(t => ({ t: t.t, ranges: t.ranges, selected: t.t === m.next.selected })) } })
    $('next-table').innerHTML = nextTable(m)
    return
  }
  if (reviewing) {
    const request = snapshot.pending_review.body.request
    $('next-facts').innerHTML = [
      ['Curves to compare', `The two curves from your check, with ${sym.ke} = ${m.candidates.map(c => formatRate(c.params.ke)).join(' and ')} per hour`],
      ['Possible times', `${request.feasible_times.map(t => decimal(t)).join(', ')} hours`],
      ['Allowance for the new reading', `±${decimal(request.future_hard_allowance)} mg/L`],
      ['Latest time', `${decimal(request.maximum_horizon)} hours`],
      ['Allowance source', escapeHTML(request.allowance_origin?.description ?? '')],
    ].map(([k, v]) => `<tr><th scope="row">${k}</th><td>${v}</td></tr>`).join('')
    return
  }
  for (const field of ['times', 'allowance', 'horizon', 'source']) if (document.activeElement !== $(`next-${field}`)) $(`next-${field}`).value = next[field]
  const list = nextProblems(), visible = list.filter(([, field]) => nextShown.tried || nextShown.touched[field])
  $('next-problems').hidden = !visible.length
  $('next-problems').textContent = visible.map(([text]) => text).join(' ')
  $('prepare-next').disabled = busy
  if (!busy) countStatus('next-status', nextShown.tried ? list.length : 0)
  if (!m) return
  const times = next.times.split(/[\s,;]+/).filter(Boolean).map(value).filter(t => t > 0), allowance = value(next.allowance), horizon = value(next.horizon)
  const model = (p, t) => p.A * (Math.exp(-p.ke * t) - Math.exp(-p.ka * t))
  $('next-chart').innerHTML = chartSVG({ readings: m.included, curves: curvesFor(m), title: 'The two curves continued to your possible times, with the allowance around each prediction', ...size('next-chart'),
    future: list.length ? { until: Math.max(4, horizon || 0), times: [] } : { until: horizon, times: times.map(t => ({ t, ranges: m.candidates.map(c => ({ tone: c.tone, low: model(c.params, t) - allowance, high: model(c.params, t) + allowance })) })) } })
}

// --- Events ----------------------------------------------------------------------------------
document.addEventListener('input', event => {
  const el = event.target
  if (el.dataset.row !== undefined) {
    const row = draft.rows[Number(el.dataset.row)]
    if (row) row[el.dataset.key] = el.type === 'checkbox' ? el.checked : el.value
    if (el.type === 'checkbox') el.closest('tr').classList.toggle('unused', !el.checked)
    if (draft.kind === 'saved') draft.kind = 'typed'
    renderData()
  } else if (el.dataset.field) {
    draft[el.dataset.field] = el.value
    renderData()
  } else if (el.dataset.limit) {
    draft.limits[el.dataset.limit] = el.value
    renderData()
  } else if (el.dataset.next) {
    next[el.dataset.next] = el.value
    renderNext()
  } else if (el.dataset.map === 'allowanceForAll') {
    draft.allowanceForAll = el.value
    draft.rows.forEach(r => { r.allowance = el.value })
    renderRows(); renderData()
  }
})

// Leaving a field with a value marks it, so its problem may show from then on.
document.addEventListener('change', event => {
  const d = event.target.dataset
  if (d.next) { nextShown.touched[d.next] = true; renderNext(); return }
  if (!draft.kind) return
  const field = d.row !== undefined || d.map ? 'rows' : d.limit ? 'limits'
    : ['low', 'high'].includes(d.field) ? (d.field === 'high' || draft.high.trim() ? 'claim' : null) : d.field || null
  if (field) { shown.touched[field] = true; renderData() }
})

document.addEventListener('change', event => {
  const el = event.target
  if (!el.dataset.map || el.dataset.map === 'allowanceForAll') return
  if (el.dataset.map === 'table') { draft.table = Number(el.value); draft.columns = null }
  else if (el.dataset.map === 'timeUnit') draft.columns.units.time = el.value
  else if (el.dataset.map === 'concUnit') draft.columns.units.concentration = el.value
  else draft.columns[el.dataset.map] = el.value === '' ? null : Number(el.value)
  applyTable(); renderMapping(); renderRows(); renderData()
})

document.addEventListener('click', event => {
  const target = event.target.closest('[data-action], [data-step]')
  if (!target) return
  if (target.dataset.step && target.getAttribute('aria-disabled') === 'true') { event.preventDefault(); return }
  const action = target.dataset.action
  if (action === 'sample' && mode === 'currents') { $('study-name').textContent = 'Sample currents'; cmp.sample() }
  else if (action === 'type' && mode === 'currents') { $('study-name').textContent = 'My currents'; cmp.type() }
  else if (action === 'sample') useSample()
  else if (action === 'type') { draft = { ...blankDraft(), kind: 'typed', name: 'My readings', rows: [0, 1, 2].map(() => ({ time: '', value: '', allowance: '', included: true })) }; $('study-name').textContent = draft.name; showEditor() }
  else if (action === 'paste') { $('paste-text').value = ''; $('paste-problem').hidden = true; $('paste-dialog').showModal() }
  else if (action === 'use-paste') {
    const tables = [...tablesFromJSON($('paste-text').value), ...tablesFromText($('paste-text').value, { file: 'the pasted table' })]
    if (!tables.length) { $('paste-problem').hidden = false; $('paste-problem').textContent = 'No table of numbers was found. Put one reading per line, with its time and concentration.'; return }
    $('paste-dialog').close()
    if (mode === 'currents') { $('study-name').textContent = 'Pasted currents'; cmp.useTables(tables, { kind: 'paste', name: 'Pasted currents' }) }
    else useTables(tables, { kind: 'paste', name: 'Pasted readings' })
  }
  else if (action === 'close') target.closest('dialog').close()
  else if (action === 'add') { draft.rows.push({ time: '', value: '', allowance: draft.allowanceForAll || '', included: true }); renderRows(); renderData(); $('rows').lastElementChild?.querySelector('[data-key="time"]')?.focus() }
  else if (action === 'remove') { draft.rows.splice(Number(target.dataset.row), 1); renderRows(); renderData() }
  else if (action === 'retry-connection') connect()
  else if (action === 'start-new-workspace') connect(true)
  else if (action === 'start-over' || action === 'new-study') { draft = blankDraft(); cmp.reset(); study = {}; snapshot = null; results = null; writeStore(); $('study-name').textContent = ''; location.hash = 'data'; route() }
  else if (action === 'prepare') prepare()
  else if (action === 'approve-check') approve('check-status', 'approve-check', () => { location.hash = 'result' })
  else if (action === 'go-next') { if (draft.kind === 'sample' && !next.times) next = { ...SAMPLE.next }; location.hash = 'next' }
  else if (action === 'prepare-next') prepareNext()
  else if (action === 'approve-next') approve('next-run-status', 'approve-next', () => renderNext())
  else if (action === 'view-file') openFile(results.m.files[Number(target.dataset.file)])
  else if (action === 'save-file' && viewing) saveText(viewing.name, results.data.texts[viewing.name], 'application/json')
  else if (action === 'report') downloadReport(target)
})

document.addEventListener('change', event => {
  if (event.target.name !== 'study-kind') return
  setMode(event.target.value); startStatus(''); connectionLabel(); route()
})

// Clearing the input lets the same file be chosen again after a failed upload.
$('file').addEventListener('change', event => { const file = event.target.files[0]; event.target.value = ''; useFile(file) })
const drop = $('drop')
drop.addEventListener('dragover', event => { event.preventDefault(); drop.classList.add('over') })
drop.addEventListener('dragleave', () => drop.classList.remove('over'))
drop.addEventListener('drop', event => { event.preventDefault(); drop.classList.remove('over'); useFile(event.dataTransfer.files[0]) })

let viewing = null
function openFile(file) {
  viewing = file
  $('file-title').textContent = file.title
  $('file-body').innerHTML = fileView(results.data, results.m, file)
  $('file-dialog').showModal()
}

async function downloadReport(button) {
  const label = button.querySelector('span'), before = label.textContent
  button.disabled = true; label.textContent = 'Preparing…'
  try {
    saveText(`dr-bean-report-${slug(results.m.title)}.html`, await readableReport(results.data, results.m, 'fonts/atkinson-next-latin.woff2'), 'text/html')
    $('announce').textContent = 'Readable report downloaded'
  } finally { button.disabled = false; label.textContent = before }
}

// On wide screens each step's buttons stay in view while a long table scrolls under them;
// the hairline above them shows only while something is underneath.
const bars = [...document.querySelectorAll('.actions')].map(bar => {
  const end = Object.assign(document.createElement('div'), { className: 'actions-end' })
  end.setAttribute('aria-hidden', 'true'); bar.after(end)
  return [bar, end]
})
let barFrame = 0
const updateBars = () => {
  barFrame = 0
  for (const [bar, end] of bars) bar.classList.toggle('stuck', end.offsetParent !== null && end.getBoundingClientRect().top > innerHeight + 1)
}
const queueBars = () => { barFrame ||= requestAnimationFrame(updateBars) }
addEventListener('scroll', queueBars, { passive: true })
new ResizeObserver(queueBars).observe(document.body)

let resizing
window.addEventListener('resize', () => { clearTimeout(resizing); resizing = setTimeout(route, 150) })
window.addEventListener('hashchange', route)
document.querySelectorAll('.m-ke').forEach(el => { el.innerHTML = sym.ke })
document.querySelectorAll('.m-ka').forEach(el => { el.innerHTML = sym.ka })
document.querySelectorAll('.m-A').forEach(el => { el.innerHTML = sym.A })
document.querySelectorAll('.m-chi').forEach(el => { el.innerHTML = sym.chi })
$('cmp-equation').innerHTML = `${sym.current}<p class="meta">with ${sym.tauNormal}. Both models predict each current this way; the bi-Maxwellian has separate ${sym.Tpar} and ${sym.Tperp}, the isotropic one a single ${sym.T}.</p>`
$('model-equation').innerHTML = `${sym.model}<p class="meta">Concentration starts at 0 mg/L, and ${sym.order}.</p>`
route()
connect()
