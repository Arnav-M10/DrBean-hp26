import { parseMeasurementsCsv, validateMeasurements } from './exact.mjs'
import { validateQuestion } from './question.mjs'

const byId = id => document.getElementById(id)
const sections = ['inputs', 'question', 'review', 'investigations', 'report']
const measurementFields = [
  ['time', 'Elapsed time'], ['concentration', 'Concentration'], ['epsilon', 'Hard allowance'],
]
const bounds = [
  ['A', 'Scale', 'mg/L', 'aMin', 'aMax'],
  ['ke', 'Elimination rate', 'h⁻¹', 'keMin', 'keMax'],
  ['ka', 'Absorption rate', 'h⁻¹', 'kaMin', 'kaMax'],
  ['ke', 'Target interval for elimination rate', 'h⁻¹', 'targetMin', 'targetMax'],
]
const exampleCsv = `time,concentration,epsilon
0.25,1.72428641,0.1
0.5,2.98306758,0.1
1,4.50851312,0.1
2,5.34984763,0.1
4,4.31013325,0.1`

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
    body.append(tr)
  }
  renderSources()
  if (rowsReviewed) showRowErrors()
}

function measurementsChanged() {
  renderSources()
  if (rowsReviewed) showRowErrors()
}

function renderSources() {
  const included = rows.filter(row => row.included).length
  byId('source-summary').textContent = `${included} included · ${rows.length - included} excluded`
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
  for (const [symbol, label, units, lower, upper] of bounds) {
    const group = element('fieldset', '', { class: 'bound' })
    group.append(element('legend', `${label} (${symbol}, ${units})`))
    if (lower === 'targetMin') group.append(element('p', 'The interval includes both endpoints.'))
    const pair = element('div', '', { class: 'bound-pair' })
    for (const [field, name] of [[lower, 'Lower bound'], [upper, 'Upper bound']]) {
      const label = element('label', name, { class: 'stack' })
      label.append(element('input', '', { id: field, type: 'text', required: '' }))
      pair.append(label)
    }
    group.append(pair)
    byId('bounds').append(group)
  }
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
  summary.replaceChildren(element('h3', 'Draft inputs'))
  const description = measurements.errors.length ? 'Review the measurement table before planning.' :
    `${rows.filter(row => row.included).length} included rows at ${measurements.distinctTimes} distinct times.`
  summary.append(element('p', description), element('a', 'Edit measurements', { href: '#inputs' }))
  if (errors.length) {
    summary.append(element('p', 'Complete the model bounds, target interval, and hard allowance origin.'),
      element('a', 'Edit question', { href: '#question' }))
    return
  }
  summary.append(element('h4', 'Closed target interval'), element('p', `[${question.targetMin.trim()}, ${question.targetMax.trim()}] h⁻¹`),
    element('h4', 'Origin of hard allowances'), element('p', question.allowanceOrigin),
    element('a', 'Edit question', { href: '#question' }))
  const details = element('details')
  const list = element('dl')
  for (const [symbol, label, units, lower, upper] of bounds) {
    list.append(element('dt', `${label} (${symbol}, ${units})`), element('dd', `[${exact[lower]}, ${exact[upper]}]`))
  }
  details.append(element('summary', 'Exact model bounds and target interval'), list)
  summary.append(details)
}

function route(focusHeading = true) {
  const requested = location.hash.slice(1)
  if (requested === 'main') return
  const selected = sections.includes(requested) ? requested : 'inputs'
  for (const section of sections) byId(section).hidden = section !== selected
  for (const link of document.querySelectorAll('.workspace-nav a')) {
    if (link.hash === `#${selected}`) link.setAttribute('aria-current', 'page')
    else link.removeAttribute('aria-current')
  }
  if (selected === 'review') renderReview()
  if (focusHeading) byId(`${selected}-title`).focus()
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
    showImportPreview(imported, { name: file.name, digest, description: 'CSV field text is kept in this draft. The original file bytes stay with you.' })
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
    description: 'Generated with A = 10, ke = 0.2 and ka = 1.0. The observations are rounded. The example uses a team-chosen hard allowance of 0.1 mg/L.',
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
  if (questionReviewed) showQuestionErrors()
})

byId('question-form').addEventListener('submit', event => {
  event.preventDefault()
  questionReviewed = true
  if (showQuestionErrors().errors.length) byId('question-errors').focus()
  else location.hash = 'review'
})

byId('export-draft').addEventListener('click', () => {
  const draft = { format: 'dr-bean-local-draft', version: 1, rows, sources, question: currentQuestion() }
  const url = URL.createObjectURL(new Blob([JSON.stringify(draft, null, 2)], { type: 'application/json' }))
  element('a', '', { href: url, download: 'dr-bean-draft.json' }).click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
  announce('Draft downloaded.')
})

createBounds()
addRow()
renderRows()
route(false)
addEventListener('hashchange', () => route())
