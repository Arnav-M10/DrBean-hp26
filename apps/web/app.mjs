import { parseMeasurementsCsv, validateMeasurements, parseExact } from './exact.mjs'
import { validateQuestion } from './question.mjs'
import { setupWorkflow } from './workflow.mjs'
import { setupGeneralWorkspace } from './general-workspace.mjs'
import { setupResearch } from './research.mjs'
import { concentrationChart, readable, toNumber } from './result-view.mjs'

const byId = id => document.getElementById(id)
const sections = ['start', 'inputs', 'question', 'review', 'investigations', 'result', 'next']
const aliases = { '': 'start', research: 'start', report: 'next' }
const stepOf = { start: 'start', inputs: 'inputs', question: 'inputs', review: 'inputs', investigations: 'investigations', result: 'result', next: 'next' }
const pageTitles = { start: 'Start', inputs: 'Measurements', question: 'Claim and assumptions', review: 'Review and approve', investigations: 'Investigate', result: 'Result', next: 'Next measurement' }
const exampleQuestion = { 'experiment-id': 'synthetic_example', 'time-origin': 'Synthetic dose time (t = 0 h)', aMin: '0.001', aMax: '30', keMin: '0.015', keMax: '0.35', kaMin: '0.4', kaMax: '8', targetMin: '0.10', targetMax: '0.17', allowanceOrigin: 'Team-selected synthetic hard allowance of 0.50 mg/L for every reading.' }
const measurementFields = [
  ['time', 'Elapsed time'], ['concentration', 'Concentration'], ['epsilon', 'Hard allowance'],
]
const bounds = [
  ['A', 'Scale', 'mg/L', 'aMin', 'aMax'],
  ['ke', 'Elimination rate', 'h⁻¹', 'keMin', 'keMax'],
  ['ka', 'Absorption rate', 'h⁻¹', 'kaMin', 'kaMax'],
  ['ke', 'Claimed range for the elimination rate', 'h⁻¹', 'targetMin', 'targetMax'],
]
const boundHelp = {
  aMin: 'How tall the curve can be. Search limits, not a claim.',
  keMin: 'How fast the drug can be cleared. The check searches this whole range.',
  kaMin: 'How fast the drug can be absorbed. Must lie entirely above the ke range.',
  targetMin: 'The statement under test: ke lies in this closed range. The check looks for fitting ke values outside it.',
}
const exampleCsv = `time,concentration,epsilon
0.25,4.80,0.50
0.5,7.20,0.50
1,8.00,0.50
2,6.80,0.50
4,5.70,0.50`

let rows = []
let nextRowId = 1
let sources = []
let previewToken = 0
let rowsReviewed = false
let questionReviewed = false

function element(tag, text, attributes = {}) {
  const node = document.createElement(tag)
  if (text) node.textContent = text
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value)
  return node
}

function announce(message) {
  byId('status').textContent = message
}

function addRow(values = {}, sourceId = null) {
  const row = { id: nextRowId++, time: '', concentration: '', epsilon: '', included: true, ...values, sourceId }
  if (sourceId !== null) {
    row.original = Object.fromEntries(measurementFields.map(([field]) => [field, row[field]]))
  }
  rows.push(row)
}

function renderRows() {
  renderWorkflow?.()
  const body = byId('rows')
  body.replaceChildren()
  for (const [index, row] of rows.entries()) {
    const number = index + 1
    const tr = element('tr')
    const includeCell = element('td')
    const include = element('input', '', { type: 'checkbox', 'aria-label': `Include row ${number}` })
    include.checked = row.included
    include.addEventListener('change', () => {
      row.included = include.checked
      tr.classList.toggle('excluded', !row.included)
      measurementsChanged()
    })
    includeCell.append(include)
    tr.classList.toggle('excluded', !row.included)
    tr.append(element('th', `${number}`, { scope: 'row' }), includeCell)
    for (const [field, label] of measurementFields) {
      const id = `row-${row.id}-${field}`
      const input = element('input', '', { type: 'text', id, 'aria-label': `Row ${number}, ${label.toLowerCase()}` })
      input.value = row[field]
      input.addEventListener('input', () => {
        row[field] = input.value
        measurementsChanged()
      })
      const cell = element('td')
      cell.append(input)
      tr.append(cell)
    }
    // Deliberate removal for rows typed here. Imported rows stay visible and are excluded instead,
    // so the record of what the source contained is kept.
    const actionCell = element('td')
    if (row.sourceId === null) {
      const remove = element('button', 'Remove', { type: 'button', class: 'secondary', 'aria-label': `Remove row ${number}` })
      remove.addEventListener('click', () => {
        rows = rows.filter(candidate => candidate !== row)
        if (!rows.length) addRow()
        renderRows()
        measurementsChanged()
        announce(`Removed row ${number}.`)
        byId('add-row').focus()
      })
      actionCell.append(remove)
    } else {
      actionCell.append(element('span', 'Imported', { class: 'hint', title: 'Imported rows are kept. Untick Include to leave one out.' }))
    }
    tr.append(actionCell)
    body.append(tr)
  }
  renderSources()
  renderInputPlot()
  if (rowsReviewed) showRowErrors()
}

function measurementsChanged() {
  renderWorkflow?.()
  renderInputPlot()
  renderSources()
  if (rowsReviewed) showRowErrors()
}

function renderSources() {
  const included = rows.filter(row => row.included).length
  byId('source-summary').textContent = `${included} of ${rows.length} rows included. Untick Include to leave a row out of the check without deleting it.`
  byId('source-details').hidden = sources.length === 0
  const list = byId('sources')
  list.replaceChildren(...sources.map(source => {
    const count = rows.filter(row => row.sourceId === source.id).length
    return element('li', `${source.name} · ${count} rows in draft. ${source.description}${source.digest ? ` SHA-256 ${source.digest}.` : ''}`)
  }))
}

function showErrors(container, heading, errors, controlFor) {
  const form = container.closest('form')
  for (const control of form.querySelectorAll('[aria-invalid="true"]')) {
    control.removeAttribute('aria-invalid')
    control.removeAttribute('aria-describedby')
  }
  container.replaceChildren()
  container.hidden = errors.length === 0
  if (!errors.length) return
  const list = element('ul')
  for (const [index, error] of errors.entries()) {
    const control = controlFor(error)
    const item = element('li', '', { id: `${container.id}-${index}` })
    if (control) {
      control.setAttribute('aria-invalid', 'true')
      control.setAttribute('aria-describedby', item.id)
      const link = element('a', error.message, { href: `#${control.id}` })
      link.addEventListener('click', event => {
        event.preventDefault()
        control.focus()
      })
      item.append(link)
    } else {
      item.textContent = error.message
    }
    list.append(item)
  }
  container.append(element('h4', heading), list)
}

function showRowErrors() {
  const result = validateMeasurements(rows)
  showErrors(byId('rows-errors'), 'Check the measurements', result.errors.map(error => ({
    ...error, message: error.index >= 0 ? `Row ${error.index + 1}. ${error.message}` : error.message,
  })), error => byId(`row-${rows[error.index]?.id}-${error.field}`))
  return result
}

function createBounds() {
  const make = ([symbol, label, units, lower, upper]) => {
    const group = element('fieldset', '', { class: lower === 'targetMin' ? 'bound target' : 'bound' })
    group.append(element('legend', `${label} (${symbol}, ${units})`))
    group.append(element('p', boundHelp[lower], { class: 'help' }))
    const pair = element('div', '', { class: 'bound-pair' })
    for (const [field, name] of [[lower, 'Lower bound'], [upper, 'Upper bound']]) {
      const label = element('label', name, { class: 'stack' })
      label.append(element('input', '', { id: field, type: 'text', required: '', inputmode: 'decimal', autocomplete: 'off' }))
      pair.append(label)
    }
    group.append(pair)
    return group
  }
  const container = byId('bounds')
  container.append(make(bounds[3]))
  for (const bound of bounds.slice(0, 3)) byId('search-limits').append(make(bound))
}

function currentDraft() {
  return { rows, sources, question: currentQuestion(), context: {
    experiment: byId('experiment-id').value, timeOrigin: byId('time-origin').value, origin: byId('dataset-origin').value,
  } }
}

function currentQuestion() {
  const fields = bounds.flatMap(([, , , lower, upper]) => [lower, upper])
  return Object.fromEntries([...fields, 'allowanceOrigin', 'methods', 'goal'].map(field => [field, byId(field).value]))
}

function showQuestionErrors() {
  const result = validateQuestion(currentQuestion())
  showErrors(byId('question-errors'), 'Check the research question', result.errors, error => byId(error.field))
  return result
}

function renderReview() {
  const summary = byId('review-summary')
  const measurements = validateMeasurements(rows)
  const question = currentQuestion()
  const { errors, exact } = validateQuestion(question)
  const context = currentDraft().context
  const included = rows.filter(row => row.included)
  summary.replaceChildren(element('h2', 'What the check will assume'))
  const list = element('dl', '', { class: 'facts' })
  const fact = (term, value, href, missing = false) => {
    const row = element('div'), dd = element('dd')
    dd.append(element('span', value, missing ? { class: 'missing' } : {}), ' ', element('a', missing ? 'Fix this' : 'Edit', { href }))
    row.append(element('dt', term), dd); list.append(row)
  }
  fact('Measurements', measurements.errors.length ? `The table has ${measurements.errors.length} problem${measurements.errors.length === 1 ? '' : 's'} to fix.` :
    `${included.length} included readings at ${measurements.distinctTimes} distinct times, from ${readable(Math.min(...included.map(r => Number(r.time))))} to ${readable(Math.max(...included.map(r => Number(r.time))))} h.${rows.length > included.length ? ` ${rows.length - included.length} excluded.` : ''}`, '#inputs', measurements.errors.length > 0)
  const allowances = [...new Set(included.map(row => row.epsilon.trim()).filter(Boolean))]
  if (!measurements.errors.length) fact('Allowance', allowances.length === 1 ? `Every reading may differ from the curve by at most ±${allowances[0]} mg/L.` : `Readings use ${allowances.length} different allowances, each a hard bound in mg/L.`, '#inputs')
  fact('Claim tested', errors.some(e => e.field.startsWith('target')) ? 'The claimed range is incomplete.' : `The elimination rate ke lies between ${question.targetMin.trim()} and ${question.targetMax.trim()} per hour, endpoints included.`, '#question', errors.some(e => e.field.startsWith('target')))
  fact('Why the allowances hold', question.allowanceOrigin.trim() || 'Not explained yet.', '#question', !question.allowanceOrigin.trim())
  fact('Dataset', context.experiment && context.timeOrigin && context.origin ? `${context.experiment}, ${context.origin} data, t = 0 is “${context.timeOrigin}”.` : 'Experiment name, t = 0 meaning or data origin is missing.', '#question', !(context.experiment && context.timeOrigin && context.origin))
  summary.append(list)
  if (errors.length) {
    const box = element('div', '', { class: 'note wait' })
    box.append(element('p', `${errors.length} item${errors.length === 1 ? '' : 's'} in Claim and assumptions still need attention. `), element('a', 'Go to Claim and assumptions', { href: '#question' }))
    summary.append(box)
    return
  }
  const details = element('details', '', { class: 'technical' })
  const exactList = element('dl')
  for (const [symbol, label, units, lower, upper] of bounds) {
    exactList.append(element('dt', `${label} (${symbol}, ${units})`), element('dd', `[${exact[lower]}, ${exact[upper]}]`))
  }
  details.append(element('summary', 'Exact search limits and claimed range'), exactList)
  summary.append(details)
}

function currentPage() {
  const requested = location.hash.slice(1)
  if (requested === 'main') return null
  const alias = aliases[requested] ?? requested
  return { page: sections.includes(alias) ? alias : 'start', requested }
}

function route(focusHeading = true) {
  const current = currentPage()
  if (!current) return
  const { page, requested } = current
  for (const section of sections) byId(section).hidden = section !== page
  for (const link of document.querySelectorAll('.steps a')) {
    const target = link.hash.slice(1)
    const isSub = link.closest('.substeps')
    const active = isSub ? target === requested || (target === page && requested !== 'report' && requested !== 'research') : stepOf[aliases[target] ?? target] === stepOf[page] && !link.closest('li').querySelector('.substeps')?.contains(link)
    if (isSub ? active : false) link.setAttribute('aria-current', 'page')
    else link.removeAttribute('aria-current')
  }
  for (const item of document.querySelectorAll('#step-list > li')) {
    const isCurrent = item.dataset.step === stepOf[page]
    item.toggleAttribute('data-current', isCurrent)
    const main = item.querySelector(':scope > a')
    if (isCurrent && !item.querySelector('.substeps')) main.setAttribute('aria-current', 'step')
    else if (isCurrent) main.setAttribute('aria-current', 'step')
    else main.removeAttribute('aria-current')
  }
  document.title = `${pageTitles[page]} · Dr. Bean`
  // Keep the current step visible in the narrow-screen strip without moving focus.
  const strip = document.querySelector('.steps'), currentLink = document.querySelector('#step-list > li[data-current] > a')
  if (strip && currentLink && strip.scrollWidth > strip.clientWidth) strip.scrollLeft = currentLink.offsetLeft - 16
  if (page === 'review') renderReview()
  if (requested === 'research') byId('files-path').open = true
  renderWorkflow?.()
  placeSourcePanel(page)
  if (!focusHeading) return
  const focusTarget = requested === 'research' ? byId('research-title') : requested === 'report' ? byId('report-title') : byId(`${page}-title`)
  focusTarget.focus()
  if (requested === 'research' || requested === 'report') focusTarget.scrollIntoView({ block: 'start' })
  else scrollTo({ top: 0 })
}

// Step rail, study context and connection hint all read state; none of them act.
function updateChrome() {
  const status = renderWorkflow?.status?.() ?? {}
  const measurements = validateMeasurements(rows), question = validateQuestion(currentQuestion())
  const session = research?.controller?.state?.snapshot
  const inputsReady = !measurements.errors.length && !question.errors.length
  const setStep = (step, state, text) => {
    const item = document.querySelector(`#step-list > li[data-step="${step}"]`)
    if (state) item.dataset.status = state; else delete item.dataset.status
    item.querySelector('.step-state').textContent = text
  }
  setStep('start', status.connected ? 'done' : 'attention', status.connected ? (status.workspace ? 'Connected' : 'Choose a workspace') : 'Not connected')
  setStep('inputs', status.approved ? 'done' : status.planned && status.planCurrent ? 'attention' : '',
    status.approved ? 'Approved' : status.planned && status.planCurrent ? 'Waiting for your approval' : inputsReady ? 'Ready to review' : rows.some(row => row.time || row.concentration) ? 'In progress' : 'Not started')
  const run = status.run
  const researchWaiting = session && ['waiting_review', 'waiting_observation'].includes(session.state)
  setStep('investigations', researchWaiting ? 'attention' : run && ['queued', 'running', 'cancel_requested'].includes(run.state) ? 'running' : run?.state === 'completed' ? 'done' : run && ['failed', 'interrupted'].includes(run.state) ? 'attention' : '',
    researchWaiting ? 'Waiting for you' : run ? { queued: 'Waiting to start', running: 'Running', cancel_requested: 'Stopping', completed: 'Finished', failed: 'Failed', cancelled: 'Cancelled', interrupted: 'Interrupted' }[run.state] ?? run.state : session ? 'Research plan open' : 'Nothing running')
  setStep('result', run?.evidence ? 'done' : '', run?.evidence ? { challenged: 'Claim not forced', none: 'No counterexample found', incomplete: 'Incomplete' }[run.tone] ?? 'Ready' : 'No result yet')
  setStep('next', status.designPending ? 'running' : '', status.designPending ? 'Comparison running' : run?.pairReady ? 'Two candidates to compare' : 'Needs two fitting candidates')

  const pill = byId('connection-pill')
  pill.dataset.state = status.connected ? 'on' : status.mode === 'session_error' ? 'error' : 'off'
  pill.textContent = status.connected ? (status.mode === 'browser_session' ? 'Private workspace' : status.workspace ? 'Connected' : 'Connected, no workspace') : status.mode === 'session_error' ? 'Connection failed' : 'Not connected'
  byId('connection-panel').dataset.state = status.connected && status.workspace ? 'on' : 'off'
  const summary = byId('connection-panel').querySelector('summary'), note = byId('connection-summary-note')
  if (status.connected && status.workspace) {
    const name = byId('workspace-select').selectedOptions[0]?.textContent
    summary.textContent = status.mode === 'browser_session' ? 'Connected to your private workspace' : `Connected to workspace “${name || status.workspace}”`
    note.textContent = 'Saved checks and research plans are stored in this workspace on the server.'
  } else if (status.connected) { summary.textContent = 'Connected: choose a workspace'; note.textContent = 'Pick an existing workspace or create one to keep your work on the server.' }
  else if (status.mode === 'session_error') note.textContent = 'The private session could not be established. Reload once the server is available.'

  const context = byId('study-context')
  const experiment = byId('experiment-id').value.trim()
  const included = rows.filter(row => row.included && row.time !== '' && row.concentration !== '').length
  const target = byId('targetMin').value.trim() && byId('targetMax').value.trim() ? `claim ke ${byId('targetMin').value.trim()}–${byId('targetMax').value.trim()} h⁻¹` : 'claim not set'
  context.replaceChildren(element('strong', experiment || 'Untitled study'), ` — ${included} reading${included === 1 ? '' : 's'}, ${target}. `, status.planCurrent ? 'Inputs saved on the server.' : 'Draft in this tab only.')
  renderResume(status)
  const current = currentPage()
  if (current) placeSourcePanel(current.page)
}

function renderResume(status) {
  const list = byId('resume-list')
  const items = []
  if (status.run) {
    const item = element('div', '', { class: 'resume-item' })
    const text = element('div')
    text.append(element('strong', 'Your latest check'), element('p', `Status: ${status.run.state}. ${status.run.evidence ? 'Evidence recorded.' : ''}`))
    item.append(text, element('a', status.run.evidence ? 'View result' : 'Follow progress', { href: status.run.evidence ? '#result' : '#investigations', class: 'button secondary' }))
    items.push(item)
  }
  for (const previous of research?.controller?.state?.history ?? []) {
    const item = element('div', '', { class: 'resume-item' })
    const text = element('div')
    text.append(element('strong', previous.objective.slice(0, 160)), element('p', `Research plan, ${previous.state.replaceAll('_', ' ')}`))
    const open = element('button', 'Open research plan', { type: 'button', class: 'secondary' })
    open.addEventListener('click', async () => {
      try { await research.controller.refresh(previous.id); location.hash = 'investigations' } catch (error) { announce(error.message) }
    })
    item.append(text, open)
    items.push(item)
  }
  if (!items.length) {
    const empty = element('p', status.connected ? 'No saved checks in this workspace yet. To reopen an earlier check by its ID, go to ' : 'Connect to see the checks saved in your workspace. To reopen a check by its ID, go to ', { class: 'fine' })
    empty.append(element('a', 'Investigate', { href: '#investigations' }), '.')
    items.push(empty)
  }
  list.replaceChildren(...items)
}

// The image-review path spans all three Check-inputs views, so its panel follows
// the person between them and stays open once an image has been retained.
function placeSourcePanel(page) {
  const panel = byId('source-path')
  if (!['inputs', 'question', 'review'].includes(page)) return
  const host = byId(page)
  if (panel.parentElement !== host) host.append(panel)
  const active = Boolean(byId('backend-source-review').querySelector('img'))
  if (active) panel.open = true
  panel.querySelector('summary').textContent = active ? 'Values read from your lab-sheet image' : 'Read values from a lab-sheet image instead'
}

function renderInputPlot() {
  const figure = byId('input-plot')
  const exactNumber = value => { try { return toNumber(parseExact(value)) } catch { return NaN } }
  const points = rows.map(row => ({ t: exactNumber(row.time), c: exactNumber(row.concentration), e: exactNumber(row.epsilon) || 0, included: row.included }))
    .filter(row => row.included && row.time !== '' && Number.isFinite(row.t) && Number.isFinite(row.c) && row.t >= 0)
  figure.querySelector('svg')?.remove()
  figure.hidden = points.length < 2
  if (points.length < 2) return
  const chart = concentrationChart({ rows: points, height: 220 })
  if (chart) figure.prepend(chart)
}

function showImportPreview(importedRows, source) {
  const container = byId('import-preview')
  const repeated = sources.some(existing => source.digest ? existing.digest === source.digest : existing.name === source.name)
  const hasMeasurements = () => rows.some(row => row.sourceId || measurementFields.some(([field]) => row[field] !== ''))
  const hasDraft = hasMeasurements()
  const actions = element('div', '', { class: 'actions' })
  const commit = replace => {
    if (replace && !hasDraft && hasMeasurements()) {
      showImportPreview(importedRows, source)
      return
    }
    if (replace) rows = []
    source.id = sources.length + 1
    sources.push(source)
    for (const row of importedRows) addRow(row, source.id)
    container.hidden = true
    renderRows()
    byId('add-row').focus()
    announce(`Added ${importedRows.length} rows.`)
  }
  for (const [label, replace] of hasDraft ? [['Append rows', false], ['Replace rows', true]] : [['Use these rows', true]]) {
    const button = element('button', label, { type: 'button' })
    button.addEventListener('click', () => commit(replace))
    actions.append(button)
  }
  const cancel = element('button', 'Cancel import', { type: 'button', class: 'secondary' })
  cancel.addEventListener('click', () => {
    container.hidden = true
    byId('csv-file').focus()
  })
  actions.append(cancel)
  container.replaceChildren(element('h4', source.name),
    element('p', `${importedRows.length} rows to review · 0 excluded · hours and mg/L`),
    element('p', source.description))
  if (source.digest) container.append(element('p', `SHA-256 ${source.digest}`, { class: 'digest' }))
  if (repeated) container.append(element('p', 'This source was already imported. Appending adds another copy of its rows.'))
  container.append(actions)
  container.hidden = false
  actions.querySelector('button').focus()
}

byId('csv-file').addEventListener('change', async event => {
  const file = event.target.files[0]
  event.target.value = ''
  if (!file) return
  const token = ++previewToken
  byId('import-preview').hidden = true
  announce(`Reading ${file.name}`)
  try {
    const bytes = await file.arrayBuffer()
    const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes)
    const imported = parseMeasurementsCsv(text)
    if (!imported.length) throw new Error('Add at least one row below the CSV header.')
    const hash = globalThis.crypto?.subtle ? await crypto.subtle.digest('SHA-256', bytes) : null
    const digest = hash && Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, '0')).join('')
    if (token !== previewToken) return
    showImportPreview(imported, { name: file.name, digest, description: 'The CSV values are copied into this draft. The file itself is not uploaded.' })
  } catch (error) {
    if (token !== previewToken) return
    const message = element('p', `${file.name}: ${error.message}`, { role: 'alert' })
    byId('import-preview').replaceChildren(message)
    byId('import-preview').hidden = false
  }
})

byId('example').addEventListener('click', () => {
  previewToken++
  showImportPreview(parseMeasurementsCsv(exampleCsv), {
    name: 'Synthetic two-rate example',
    description: 'Synthetic example with five readings. The team chose the 0.50 mg/L allowances. Review the search limits and the claim on the next page; results come only from the inputs you save.',
  })
})

byId('add-row').addEventListener('click', () => {
  addRow()
  renderRows()
  byId(`row-${rows.at(-1).id}-time`).focus()
})

byId('measurements').addEventListener('submit', event => {
  event.preventDefault()
  rowsReviewed = true
  if (showRowErrors().errors.length) byId('rows-errors').focus()
  else location.hash = 'question'
})

byId('question-form').addEventListener('input', () => {
  renderWorkflow?.()
  if (questionReviewed) showQuestionErrors()
})

byId('question-form').addEventListener('submit', event => {
  event.preventDefault()
  questionReviewed = true
  if (showQuestionErrors().errors.length) byId('question-errors').focus()
  else location.hash = 'review'
})

byId('export-draft').addEventListener('click', () => {
  const draft = { format: 'dr-bean-local-draft', version: 1, ...currentDraft() }
  const url = URL.createObjectURL(new Blob([JSON.stringify(draft, null, 2)], { type: 'application/json' }))
  element('a', '', { href: url, download: 'dr-bean-draft.json' }).click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
  announce('Draft downloaded.')
})

let renderWorkflow
createBounds()
let research
const general = setupGeneralWorkspace({ root: byId('general-workspace'), onChange: () => research?.sourceContextChanged() })
research = setupResearch({ root: byId('durable-research'), getDraft: currentDraft, getSources: () => general.controller.state.assets, getSourceQuestion: () => general.controller.state.question, onChange: () => updateChrome() })
renderWorkflow = setupWorkflow(currentDraft, (review, source) => {
  const accepted = new Map()
  for (const field of review.body.reviewed_fields) {
    const match = /^rows\[(\d+)\]\.(time|concentration|hard_allowance)$/.exec(field.field_path)
    if (!match) continue
    const index = Number(match[1]), row = accepted.get(index) || {}
    row[match[2] === 'hard_allowance' ? 'epsilon' : match[2]] = field.normalized_value
    accepted.set(index, row)
  }
  if (!accepted.size) throw new Error('This review has no supported measurement rows. Enter measurements manually.')
  rows = []; sources = [{ id: source.id, name: 'Reviewed source image', description: 'Values you accepted from the reviewed source image. The source review keeps the original text and every correction.' }]
  for (const [, values] of [...accepted].sort((a, b) => a[0] - b[0])) addRow(values, source.id)
  rowsReviewed = false; questionReviewed = false
  byId('dataset-origin').value = source.body.origin === 'synthetic' ? 'synthetic' : ''
  renderRows(); location.hash = 'inputs'; announce('Reviewed values copied into the measurement table. Fill in any missing fields and the claim before saving inputs.')
}, { onConnectionChange: async connection => { await Promise.all([general.connectionChanged(connection), research.connectionChanged(connection)]) }, onRender: () => updateChrome() })

byId('start-example').addEventListener('click', () => {
  // Prefill only empty claim fields; every value stays visible and editable for review.
  let filled = false
  for (const [id, value] of Object.entries(exampleQuestion)) if (!byId(id).value.trim()) { byId(id).value = value; filled = true }
  if (!byId('dataset-origin').value) byId('dataset-origin').value = 'synthetic'
  byId('example-note').hidden = !filled
  location.hash = 'inputs'
  byId('example').click()
})
byId('question-form').addEventListener('input', () => updateChrome())
addRow()
renderRows()
route(false)
updateChrome()
addEventListener('hashchange', () => route())
// The draft lives only in this tab until it is saved, so warn before it is lost.
addEventListener('beforeunload', event => {
  const typed = rows.some(row => row.time || row.concentration) || byId('targetMin').value.trim()
  if (typed && !renderWorkflow?.status?.().planCurrent) { event.preventDefault(); event.returnValue = '' }
})
