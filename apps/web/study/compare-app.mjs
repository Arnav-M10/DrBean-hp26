// The electron-current comparison on the study page, in the same four steps as a concentration
// study. The application's numerical service does the fitting. This file collects the inputs,
// shows the complete request for approval, sends it once through the trusted connector and
// shows the immutable record that comes back.
import { connectComparison } from '../comparison-api.mjs'
import { channelChartSVG } from './channel-chart.mjs'
import * as C from './compare.mjs'
import { page as sym } from './math.mjs'
import { escapeHTML } from './results.mjs'
import { $, countStatus, failure, readable, saveBytes, size, status } from './ui.mjs'

const SETTINGS_FIELDS = ['densityMin', 'densityMax', 'temperatures', 'maxChi', 'maxEvaluations', 'noise', 'z', 'samples', 'seed']
const join = items => items.length < 3 ? items.join(' and ') : `${items.slice(0, -1).join(', ')} and ${items.at(-1)}`
// "At 0°: all energies, above 4 eV and above 8 eV." One sentence per angle reads better than a flat list.
function nextSummary(settings) {
  const byAngle = new Map()
  for (const s of settings) {
    const [angle, window] = C.settingLabel(s).split(/, (.+)/)
    byAngle.set(angle, [...(byAngle.get(angle) ?? []), window])
  }
  return [...byAngle].map(([angle, windows]) => `At ${escapeHTML(angle)}: ${escapeHTML(join(windows))}.`).join(' ')
}

export function createComparison({ route, workspace, available, seconds, onConnectionFailure, save }) {
  let draft = C.blankComparison()
  let pending = null            // the complete request, frozen for approval
  let record = null, m = null   // the retained comparison on screen
  let changedSinceRun = false, caseIndex = 0, busy = false, conn = null
  let shown = { tried: false, touched: {} }

  // The connector confirms the private session and the server's comparison capability itself.
  async function connection() {
    if (conn && conn.workspaceId === workspace()) return conn
    try { conn = await connectComparison() } catch (error) {
      if (error.mayStartNew || error.status === 401) onConnectionFailure(error)
      throw error
    }
    const mine = conn
    mine.setConnectionFailureHandler(error => { if (conn === mine) onConnectionFailure(error) })
    return mine
  }

  function reset() {
    draft = C.blankComparison(); pending = null; record = null; m = null
    changedSinceRun = false; caseIndex = 0; conn = null; shown = { tried: false, touched: {} }
  }
  function begin(next) {
    reset(); draft = next
    save(null)
    location.hash = 'data'
    route()
    renderMapping()
  }
  function withDefaults(d) {
    const fill = C.defaultsFor(d)
    if (!d.settings.length) d.settings = fill.settings
    if (!C.list(d.noise).length) d.noise = fill.noise
    return d
  }
  function applyTable(d) {
    d.columns ??= C.guessCurrentColumns(d.tables[d.table])
    d.rows = C.currentsFrom(d.tables[d.table], d.columns, d.sigmaForAll)
  }
  function useTables(tables, base, preferred) {
    const best = preferred ?? tables.reduce((pick, t, i) => t.rows.length > tables[pick].rows.length ? i : pick, 0)
    const d = { ...C.blankComparison(), ...base, tables, table: best }
    applyTable(d)
    begin(withDefaults(d))
  }
  const sample = () => begin(C.sampleComparison())
  const type = () => begin(withDefaults({ ...C.blankComparison(), kind: 'typed', name: 'My currents',
    rows: [0, 1, 2, 3].map(() => ({ angle: '', emin: '', emax: '', current: '', sigma: '', included: true })) }))

  async function reopen(id, current = () => true) {
    const client = await connection()
    if (!current()) return
    const restored = await client.get(id)
    if (!current()) return
    record = restored
    m = C.readComparison(record)
    draft = C.draftFromRequest(record.body.request)
    pending = null; changedSinceRun = false; caseIndex = firstSuggestion()
  }
  const firstSuggestion = () => Math.max(0, (m?.cases ?? []).findIndex(c => c.suggested_setting_id))

  const reached = {
    data: () => true,
    check: () => Boolean(pending || record),
    result: () => Boolean(m),
    next: () => Boolean(m?.canPlan),
  }

  // --- Step 1 ---------------------------------------------------------------------------------
  function sourceLine() {
    if (draft.kind === 'sample') return 'Made-up currents from the repository’s synthetic example, in µA. Change any value.'
    const table = draft.tables[draft.table]
    if (draft.kind === 'file' && table?.fromAssistant) return `From ${table.file}${table.page ? `, page ${table.page}` : ''}. The assistant copied these values: check every one against the file.`
    if (draft.kind === 'file') return `From ${draft.name}. The original file is saved in your workspace. Check every value against it.`
    if (draft.kind === 'paste') return 'From the table you pasted. Check every value.'
    if (draft.kind === 'saved') return 'The currents saved with this comparison. Changing them needs a new approval.'
    return 'Type your currents below.'
  }

  function renderData() {
    const editing = Boolean(draft.kind)
    $('cmp-editor').hidden = !editing
    if (!editing) return
    document.querySelectorAll('#cmp-editor [data-cfield]').forEach(el => {
      if (el.type === 'checkbox') el.checked = Boolean(draft[el.dataset.cfield])
      else if (document.activeElement !== el) el.value = draft[el.dataset.cfield] ?? ''
    })
    $('cmp-source').textContent = sourceLine()
    if (document.activeElement?.dataset?.crow === undefined) renderRows()
    if (document.activeElement?.dataset?.cset === undefined) renderSettingRows()
    const groups = draft.rows.filter(r => r.included && C.isDecimal(r.current) && C.isDecimal(r.angle) && C.isDecimal(r.emin))
      .map(r => ({ label: C.settingShort(r), observed: { v: Number(C.clean(r.current)), e: Math.max(0, Number(C.clean(r.sigma)) || 0) }, marks: [] }))
    $('cmp-data-chart').innerHTML = groups.length ? channelChartSVG({ groups, title: `${groups.length} currents with their σ`, ...size('cmp-data-chart', 270) })
      : '<p class="empty">Currents appear here as you add them.</p>'
    $('cmp-used').textContent = `${draft.rows.filter(r => r.included).length} of ${draft.rows.length} currents used`
    const list = C.comparisonProblems(draft), visible = list.filter(([, , field]) => shown.tried || shown.touched[field])
    for (const area of ['rows', 'about', 'settings']) {
      const items = visible.filter(([where]) => where === area).map(([, text]) => text)
      $(`cmp-problems-${area}`).hidden = !items.length
      $(`cmp-problems-${area}`).textContent = items.join(' ')
    }
    if (visible.some(([where]) => where === 'settings')) $('cmp-settings').open = true
    const ready = available()
    $('cmp-prepare').disabled = busy || ready === false
    if (ready === false) status('cmp-prepare-status', 'Comparisons are not available on this server.', 'bad')
    else if (!busy) countStatus('cmp-prepare-status', shown.tried ? list.length : 0)
  }

  const cells = (row, index, keys, attr) => keys.map(([key, label]) =>
    `<td><input inputmode="decimal" autocomplete="off" spellcheck="false" aria-label="${label}, ${attr === 'crow' ? 'current' : 'setting'} ${index + 1}" value="${escapeHTML(row[key])}" data-${attr}="${index}" data-${attr === 'crow' ? 'ckey' : 'skey'}="${key}"${key === 'emax' ? ' placeholder="none"' : ''}></td>`).join('')
  const ROW_KEYS = [['angle', 'Angle in degrees'], ['emin', 'Lowest energy in eV'], ['emax', 'Highest energy in eV, empty for none'], ['current', 'Current in µA'], ['sigma', 'σ in µA']]
  function renderRows() {
    $('cmp-rows').innerHTML = draft.rows.map((r, i) => `<tr${r.included ? '' : ' class="unused"'}${r.note ? ` title="${escapeHTML(r.note)}"` : ''}>
      <td><input type="checkbox" aria-label="Use current ${i + 1}" data-crow="${i}" data-ckey="included"${r.included ? ' checked' : ''}></td>${cells(r, i, ROW_KEYS, 'crow')}
      <td><button type="button" class="icon" aria-label="Remove current ${i + 1}" data-action="cmp-remove" data-index="${i}"><svg aria-hidden="true"><use href="#i-x"/></svg></button></td></tr>`).join('')
  }
  function renderSettingRows() {
    $('cmp-next-rows').innerHTML = draft.settings.map((s, i) => `<tr>${cells(s, i, ROW_KEYS.slice(0, 3), 'cset')}
      <td><button type="button" class="icon" aria-label="Remove setting ${i + 1}" data-action="cmp-remove-setting" data-index="${i}"><svg aria-hidden="true"><use href="#i-x"/></svg></button></td></tr>`).join('')
  }

  function renderMapping() {
    const box = $('cmp-mapping')
    if (!['file', 'paste'].includes(draft.kind) || !draft.tables.length) { box.hidden = true; return }
    const table = draft.tables[draft.table], c = draft.columns
    const names = Array.from({ length: table.width }, (_, i) => table.header?.[i] || `Column ${i + 1}`)
    const options = (selected, none) => (none ? `<option value=""${selected === null ? ' selected' : ''}>${none}</option>` : '')
      + names.map((n, i) => `<option value="${i}"${i === selected ? ' selected' : ''}>${escapeHTML(n)}</option>`).join('')
    const units = selected => Object.keys(C.UNIT_POWER).map(u => `<option value="${u}"${u === selected ? ' selected' : ''}>${u}</option>`).join('')
    const tables = draft.tables.map((t, i) => `<option value="${i}"${i === draft.table ? ' selected' : ''}>Table ${i + 1}: ${t.rows.length} rows${t.page ? `, page ${t.page}` : ''}</option>`).join('')
    box.hidden = false
    box.innerHTML = `${draft.tables.length > 1 ? `<label class="field">Table<select data-cmap="table">${tables}</select></label>` : ''}
      <label class="field">Angle<select data-cmap="angle">${options(c.angle)}</select></label>
      <label class="field">From energy<select data-cmap="low">${options(c.low)}</select></label>
      <label class="field">To energy<select data-cmap="high">${options(c.high, 'No upper limit')}</select></label>
      <label class="field">Current<select data-cmap="current">${options(c.current)}</select></label>
      <label class="field narrow">In<select data-cmap="currentUnit">${units(c.units.current)}</select></label>
      <label class="field">σ<select data-cmap="sigma">${options(c.sigma, 'One value for every current')}</select></label>
      ${c.sigma === null ? `<label class="field narrow">Value (µA)<input data-cmap="sigmaForAll" inputmode="decimal" value="${escapeHTML(draft.sigmaForAll)}"></label>`
        : `<label class="field narrow">In<select data-cmap="sigmaUnit">${units(c.units.sigma)}</select></label>`}`
  }

  function edited() {
    pending = null
    if (record) changedSinceRun = true
    if (draft.kind === 'saved') draft.kind = 'typed'
    renderData()
  }

  const FOCUS = { rows: () => $('cmp-rows').querySelector('input[data-ckey="angle"]') ?? document.querySelector('[data-action="cmp-add"]'),
    synthetic: () => $('cmp-synthetic'), description: () => $('cmp-description'), area: () => $('cmp-area'), efficiency: () => $('cmp-efficiency'),
    settings: () => { $('cmp-settings').open = true; return $('cmp-settings').querySelector('input') } }

  function prepare() {
    if (busy) return
    withDefaults(draft)
    const issues = C.comparisonProblems(draft)
    if (issues.length) {
      const order = ['about', 'rows', 'settings'], first = [...issues].sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]))[0]
      shown.tried = true; renderData(); FOCUS[first[2]]()?.focus(); return
    }
    pending = C.comparisonRequest(draft)
    location.hash = 'check'
  }

  // --- Step 2 ---------------------------------------------------------------------------------
  function facts(req) {
    const used = req.observations.filter(o => req.selected_channel_ids.includes(o.channel_id))
    const channel = Object.fromEntries(req.channels.map(c => [c.id, c]))
    const angles = [...new Set(used.map(o => Number(channel[o.channel_id].angle_deg)))].sort((a, b) => a - b)
    return [
      ['Currents', `${used.length} of ${req.observations.length} currents, at ${join(angles.map(a => `${a}°`))}`],
      ['How they were made', escapeHTML(req.review.description)],
      ['Models', `Isotropic Maxwellian (${sym.n}, ${sym.T}) and bi-Maxwellian (${sym.n}, ${sym.Tpar}, ${sym.Tperp}), fitted to the same currents through${sym.current}with ${sym.tauNormal}.`],
      ['Instrument', `Ideal planar collector that takes the whole incident half-space. Area ${escapeHTML(req.instrument.area_m2)} m², efficiency ${escapeHTML(req.instrument.efficiency)}.`],
      ['Fit', `Temperatures ${req.fit.temperature_grid_eV.map(escapeHTML).join(', ')} eV, density from ${C.sci(req.fit.density_min_m3)} to ${C.sci(req.fit.density_max_m3, 'm^{-3}')}. A fit passes when ${sym.chi} is at most ${escapeHTML(req.fit.max_reduced_chi_square)}.`],
      ['Noise', `σ of ${req.noise.sigma_grid_A.map(C.micro).join(', ')} µA with ±${req.noise.z_thresholds.map(escapeHTML).join(', ±')}σ bands. ${req.noise.samples} simulated readings each, seed ${req.noise.seed}.`],
      ['Next settings', nextSummary(req.feasible_settings)],
      ['Limit', `One run of up to ${seconds()} seconds. Numerical, not an exact proof.`],
    ].map(([k, v]) => `<tr><th scope="row">${k}</th><td>${v}</td></tr>`).join('')
  }
  function renderCheck() {
    const req = pending ?? record?.body.request
    $('cmp-check-facts').innerHTML = req ? facts(req) : ''
    $('cmp-check-exact').textContent = req ? JSON.stringify(req, null, 2) : ''
    $('cmp-approve').hidden = !pending
    $('cmp-check-problem').hidden = Boolean(pending)
    $('cmp-check-problem').textContent = pending ? '' : record ? 'This comparison has already run. Change the currents to run a new one.' : 'Review the comparison first.'
  }
  async function approve() {
    if (busy || !pending) return
    busy = true; $('cmp-approve').disabled = true
    try {
      status('cmp-check-status', 'Fitting both distributions and simulating readings…')
      // One explicit request. Pressing again after an unclear failure resends the same bytes,
      // which the server answers with the record it already kept instead of running twice.
      record = await (await connection()).submit(pending)
      m = C.readComparison(record); pending = null; changedSinceRun = false; caseIndex = firstSuggestion()
      save({ kind: 'currents', comparisonId: record.id })
      status('cmp-check-status', '')
      location.hash = 'result'
    } catch (error) {
      failure('cmp-check-status', error)
    } finally {
      busy = false; $('cmp-approve').disabled = false
    }
  }

  // --- Steps 3 and 4 ----------------------------------------------------------------------------
  function renderResult(v) {
    if (!m) return
    $('cmp-answer').hidden = v !== 'result'
    $('cmp-readings').hidden = v !== 'result-readings'
    $('cmp-files').hidden = v !== 'result-files'
    const when = m.created ? new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(m.created)) : ''
    $('cmp-result-note').textContent = `${when ? `Ran ${when}` : 'Ran'} on the numerical service (${m.r.numerical_backend})`
    $('cmp-stale').hidden = !changedSinceRun
    $('cmp-stale').textContent = changedSinceRun ? 'You changed the currents after this run. This result is for the currents you approved.' : ''
    const f = C.comparisonFinding(m)
    $('cmp-title').textContent = f.headline
    $('cmp-lead').innerHTML = f.lead
    $('cmp-limit').textContent = f.limit
    $('cmp-limit').hidden = !f.limit
    const groups = C.resultGroups(m)
    if (v === 'result') $('cmp-result-chart').innerHTML = groups.length && m.r.fits.length ? channelChartSVG({ groups, title: 'Each current with ±σ and both fitted predictions', ...size('cmp-result-chart') }) : ''
    $('cmp-fits').innerHTML = C.fitRows(m) || '<tr><td colspan="4" class="quiet">No fit was kept.</td></tr>'
    $('cmp-readings-table').innerHTML = C.currentsTable(m)
    $('cmp-file-about').textContent = `${m.record.id}.json holds the exact request, both fits, ${m.cases.length} noise cases and the limits. Input fingerprint ${m.r.input_digest.slice(0, 16)}…`
    $('cmp-limitations').innerHTML = m.r.limitations.map(l => `<li>${escapeHTML(l)}</li>`).join('')
    $('cmp-to-next').hidden = !m.canPlan
    $('cmp-next-unavailable').hidden = m.canPlan
    $('cmp-next-unavailable').textContent = m.canPlan ? '' : 'A next measurement needs at least one fit that passes.'
  }

  function renderNext() {
    if (!m?.canPlan) return
    const cases = m.cases, many = new Set(cases.map(c => c.z_threshold)).size > 1
    caseIndex = Math.min(caseIndex, cases.length - 1)
    $('cmp-cases').innerHTML = cases.map((c, i) => `<button type="button" data-action="cmp-case" data-index="${i}" aria-pressed="${i === caseIndex}">${C.caseLabel(c, many)}</button>`).join('')
    const c = cases[caseIndex], f = C.caseFinding(m, c)
    $('cmp-next-title').textContent = f.headline
    $('cmp-next-lead').innerHTML = f.lead
    $('cmp-next-chart').innerHTML = channelChartSVG({ groups: C.caseGroups(m, c), title: `Both fitted predictions at each setting, with ±${c.z_threshold}σ bands`, ...size('cmp-next-chart') })
    $('cmp-next-table').innerHTML = C.settingsTable(m, c)
    $('cmp-simulation').innerHTML = C.simulationTable(m, c)
  }

  function view() {
    $('cmp-dialog-body').textContent = JSON.stringify(record, null, 2)
    $('cmp-dialog').showModal()
  }
  async function download(button) {
    if (!record) return
    const label = button.querySelector('span') ?? button, before = label.textContent, where = button.dataset.status
    button.disabled = true; label.textContent = 'Checking the file…'
    try {
      // The connector checks the downloaded bytes against this exact record before handing them over.
      const { bytes, filename } = await (await connection()).download(record)
      saveBytes(`dr-bean-comparison-${filename}`, bytes, 'application/json')
      if (where) status(where, '')
      $('announce').textContent = 'Numerical export downloaded'
    } catch (error) {
      if (where) failure(where, error); else $('announce').textContent = readable(error)
    } finally { button.disabled = false; label.textContent = before }
  }

  // --- Events -------------------------------------------------------------------------------------
  document.addEventListener('input', event => {
    const el = event.target, d = el.dataset
    if (!draft.kind) return
    if (d.crow !== undefined) {
      const row = draft.rows[Number(d.crow)]
      if (row) row[d.ckey] = el.type === 'checkbox' ? el.checked : el.value
      if (el.type === 'checkbox') el.closest('tr').classList.toggle('unused', !el.checked)
      edited()
    } else if (d.cset !== undefined) {
      const setting = draft.settings[Number(d.cset)]
      if (setting) setting[d.skey] = el.value
      edited()
    } else if (d.cfield) {
      draft[d.cfield] = el.type === 'checkbox' ? el.checked : el.value
      edited()
    } else if (d.cmap === 'sigmaForAll') {
      draft.sigmaForAll = el.value
      draft.rows.forEach(r => { r.sigma = el.value })
      renderRows(); edited()
    }
  })
  // Leaving a field marks it, so its problem may show from then on.
  document.addEventListener('change', event => {
    const el = event.target, d = el.dataset
    if (!draft.kind) return
    if (d.cmap && d.cmap !== 'sigmaForAll') {
      if (d.cmap === 'table') { draft.table = Number(el.value); draft.columns = null }
      else if (d.cmap === 'currentUnit') draft.columns.units.current = el.value
      else if (d.cmap === 'sigmaUnit') draft.columns.units.sigma = el.value
      else draft.columns[d.cmap] = el.value === '' ? null : Number(el.value)
      applyTable(draft); renderMapping(); renderRows(); edited()
    }
    const field = d.crow !== undefined || d.cmap ? 'rows' : d.cset !== undefined ? 'settings'
      : d.cfield ? (SETTINGS_FIELDS.includes(d.cfield) ? 'settings' : d.cfield) : null
    if (field) { shown.touched[field] = true; renderData() }
  })
  document.addEventListener('click', event => {
    const target = event.target.closest('[data-action]')
    if (!target) return
    const action = target.dataset.action, index = Number(target.dataset.index)
    if (action === 'cmp-add') {
      draft.rows.push({ angle: '', emin: '', emax: '', current: '', sigma: draft.sigmaForAll || '', included: true })
      renderRows(); edited(); $('cmp-rows').lastElementChild?.querySelector('[data-ckey="angle"]')?.focus()
    } else if (action === 'cmp-remove') { draft.rows.splice(index, 1); renderRows(); edited() }
    else if (action === 'cmp-add-setting') {
      draft.settings.push({ angle: '', emin: '', emax: '' })
      renderSettingRows(); edited(); $('cmp-next-rows').lastElementChild?.querySelector('input')?.focus()
    } else if (action === 'cmp-remove-setting') { draft.settings.splice(index, 1); renderSettingRows(); edited() }
    else if (action === 'cmp-prepare') prepare()
    else if (action === 'cmp-approve') approve()
    else if (action === 'cmp-go-next') location.hash = 'next'
    else if (action === 'cmp-case') { caseIndex = index; renderNext() }
    else if (action === 'cmp-view') view()
    else if (action === 'cmp-download') download(target)
  })

  return { reached, reset, sample, type, useTables, reopen, renderData, renderCheck, renderResult, renderNext, renderMapping,
    editing: () => Boolean(draft.kind), hasResult: () => Boolean(m), canPlan: () => Boolean(m?.canPlan), name: () => draft.name }
}
