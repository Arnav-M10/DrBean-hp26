// Electron currents: two velocity distributions fitted to the same collector currents by the
// application's numerical comparison service (DB-MODEL-COMPARISON-1). Nothing here computes
// science. It turns the person's table into the reviewed request, checks the request before
// it is sent, and reads the returned record for the page.
import { escapeHTML } from './results.mjs'
import { tex } from './math.mjs'

export const ISO = 'electron_isotropic_maxwellian.v1'
export const BI = 'electron_gyrotropic_bimaxwellian.v1'
export const MODELS = [ISO, BI]
export const NAME = { [ISO]: 'Isotropic Maxwellian', [BI]: 'Bi-Maxwellian' }
const INLINE = { [ISO]: 'isotropic Maxwellian', [BI]: 'bi-Maxwellian' }
export const TONE = { [ISO]: 'iso', [BI]: 'bi' }

// --- Exact decimal text ------------------------------------------------------------------------
const DECIMAL = /^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$/
export const clean = text => { const t = String(text ?? '').trim(); return t.includes(',') && !t.includes('.') ? t.replace(',', '.') : t }
export const isDecimal = text => DECIMAL.test(clean(text)) && clean(text).length <= 40
const within = (text, low, high) => isDecimal(text) && Number(clean(text)) >= low && Number(clean(text)) <= high

// Multiply by 10^power by moving the decimal point, so "42.88" µA becomes "0.00004288" A with
// no binary rounding. Long results fall back to scientific notation, which the contract admits.
export function shift(text, power) {
  const m = /^([+-]?)(\d*)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$/.exec(clean(text))
  if (!m || !(m[2] || m[3])) return null
  const sign = m[1] === '-' ? '-' : ''
  let digits = (m[2] || '') + (m[3] || ''), point = (m[2] || '').length + Number(m[4] || 0) + power
  while (digits.length > 1 && digits[0] === '0') { digits = digits.slice(1); point-- }
  if (/^0+$/.test(digits)) return '0'
  const significant = digits.replace(/0+$/, '')
  const scientific = `${sign}${significant[0]}${significant.length > 1 ? '.' + significant.slice(1) : ''}e${point - 1}`
  if (point <= 0) { digits = '0'.repeat(1 - point) + digits; point = 1 }
  if (point > digits.length) { digits += '0'.repeat(point - digits.length) }
  const whole = digits.slice(0, point).replace(/^0+(?=\d)/, ''), fraction = digits.slice(point).replace(/0+$/, '')
  const plain = sign + whole + (fraction ? '.' + fraction : '')
  return plain.length > 40 ? scientific : plain
}
export const UNIT_POWER = { A: 0, mA: -3, 'µA': -6, nA: -9 }
export const list = text => String(text ?? '').split(/[\s,;]+/).map(clean).filter(Boolean)

// --- Settings -----------------------------------------------------------------------------------
export function settingLabel(s) {
  const low = clean(s.energy_min_eV ?? s.emin), highText = s.energy_max_eV ?? s.emax
  const high = highText === null || highText === undefined || clean(highText) === '' ? null : clean(highText)
  const window = high !== null ? `${low} to ${high} eV` : Number(low) === 0 ? 'all energies' : `above ${low} eV`
  return `${clean(s.angle_deg ?? s.angle)}°, ${window}`
}
export function settingShort(s) {
  const low = clean(s.energy_min_eV ?? s.emin), highText = s.energy_max_eV ?? s.emax
  const high = highText === null || highText === undefined || clean(highText) === '' ? null : clean(highText)
  return [`${clean(s.angle_deg ?? s.angle)}°`, high !== null ? `${low}–${high} eV` : Number(low) === 0 ? 'all' : `≥${low} eV`]
}
const idPart = text => clean(text).replace(/^\+/, '').replace(/-/g, 'm').replace(/\./g, 'p').replace(/[^A-Za-z0-9]/g, '')
function uniqueId(base, used) {
  let id = base.slice(0, 44), n = 2
  while (used.has(id)) id = `${base.slice(0, 40)}_${n++}`
  used.add(id)
  return id
}

// --- Draft ----------------------------------------------------------------------------------------
// The made-up sample is the repository's public synthetic request (fixtures/model-comparison),
// shown in µA. Its σ grid and next settings are the same values.
export const SAMPLE = {
  name: 'Sample currents',
  description: 'New synthetic zero-drift electron distribution; density 1e15 m^-3, parallel 4 eV, perpendicular 16 eV. Noise-free forward means computed in binary64 with declared independent Gaussian measurement standard deviations; not acquired data.',
  rows: [['0', '0', '', '4.2889515568973794e-05'], ['0', '8', '', '5.8044647374081788e-06'], ['45', '0', '', '6.7814278469604863e-05'],
    ['45', '8', '', '3.047091949710435e-05'], ['90', '0', '', '8.5779031137947587e-05'], ['90', '8', '', '5.2027612345609876e-05']],
  sigma: '0.0000002', area: '0.000001', efficiency: '0.8', densityMin: '100000000000000', densityMax: '10000000000000000',
  temperatures: '2, 4, 8, 12, 16, 24', maxEvaluations: '100', maxChi: '10', noise: ['0.0000001', '0.000002', '0.00002'], z: '2', seed: '1729', samples: '128',
  settings: [['0', '0'], ['0', '4'], ['0', '8'], ['0', '16'], ['90', '0'], ['90', '4'], ['90', '8'], ['90', '16']],
}

export function blankComparison() {
  return { kind: null, name: '', tables: [], table: 0, columns: null, sigmaForAll: '', rows: [], synthetic: false, description: '',
    area: '0.000001', efficiency: '0.8', densityMin: '1e14', densityMax: '1e16', temperatures: '2, 4, 8, 12, 16, 24',
    maxEvaluations: '100', maxChi: '10', noise: '', z: '2', seed: '1729', samples: '128', settings: [] }
}

export function sampleComparison() {
  const toMicro = text => shift(text, 6)
  return { ...blankComparison(), kind: 'sample', name: SAMPLE.name, synthetic: true, description: SAMPLE.description, area: SAMPLE.area,
    efficiency: SAMPLE.efficiency, densityMin: SAMPLE.densityMin, densityMax: SAMPLE.densityMax, temperatures: SAMPLE.temperatures,
    maxEvaluations: SAMPLE.maxEvaluations, maxChi: SAMPLE.maxChi, noise: SAMPLE.noise.map(toMicro).join(', '), z: SAMPLE.z, seed: SAMPLE.seed, samples: SAMPLE.samples,
    rows: SAMPLE.rows.map(([angle, emin, emax, current]) => ({ angle, emin, emax, current: toMicro(current), sigma: toMicro(SAMPLE.sigma), included: true, note: 'Sample current, made up' })),
    settings: SAMPLE.settings.map(([angle, emin]) => ({ angle, emin, emax: '' })) }
}

// Sensible starting points for a person's own table: their angles at four thresholds, and noise
// at 1, 10 and 100 times their median σ. All of it is shown and editable before anything runs.
export function defaultsFor(d) {
  const angles = [...new Set(d.rows.map(r => clean(r.angle)).filter(a => within(a, 0, 90)))].sort((a, b) => Number(a) - Number(b))
  const settings = (angles.length ? angles : ['0', '90']).slice(0, 4).flatMap(angle => ['0', '4', '8', '16'].map(emin => ({ angle, emin, emax: '' })))
  const sigmas = d.rows.map(r => Number(clean(r.sigma))).filter(v => v > 0).sort((a, b) => a - b)
  const median = sigmas.length ? sigmas[Math.floor(sigmas.length / 2)] : 0
  const noise = median > 0 ? [1, 10, 100].map(f => Number((median * f).toPrecision(3)).toString()).join(', ') : ''
  return { settings: settings.slice(0, 16), noise }
}

// --- Reading a table -------------------------------------------------------------------------------
const ANGLE = /(angle|theta|θ|deg|pitch)/i
const LOW = /(e[ _]?min|e[ _]?low|lower|from|threshold|cut ?off|min(imum)? energy|energy)/i
const HIGH = /(e[ _]?max|e[ _]?high|upper|\bto\b|max(imum)? energy)/i
const CURRENT = /(current|\bi\b|amp|\(a\)|\[a\]|µa|ua|na\b|ma\b)/i
const SIGMA = /(sigma|σ|\bsd\b|std|stdev|error|uncert|noise)/i
export function unitOf(header = '') {
  const h = header.toLowerCase()
  return /(µa|ua|micro)/.test(h) ? 'µA' : /\bna\b|nano|\(na\)/.test(h) ? 'nA' : /\bma\b|milli|\(ma\)/.test(h) ? 'mA' : 'A'
}
export function guessCurrentColumns(table) {
  const header = table.header ?? [], taken = new Set()
  const pick = pattern => { const i = header.findIndex((h, j) => pattern.test(h) && !taken.has(j)); if (i >= 0) taken.add(i); return i }
  let sigma = pick(SIGMA), angle = pick(ANGLE), high = pick(HIGH), low = pick(LOW), current = pick(CURRENT)
  const free = () => [...Array(table.width).keys()].find(i => !taken.has(i) && ![angle, low, high, current, sigma].includes(i)) ?? -1
  if (!table.header) {
    // No names to go on: angle, lowest energy, [highest energy,] current, [σ] in that order.
    const order = table.width >= 5 ? ['angle', 'low', 'high', 'current', 'sigma'] : table.width === 4 ? ['angle', 'low', 'current', 'sigma'] : ['angle', 'low', 'current']
    const at = Object.fromEntries(order.map((name, i) => [name, i]))
    angle = at.angle; low = at.low; high = at.high ?? -1; current = at.current; sigma = at.sigma ?? -1
  }
  if (angle < 0) { angle = free(); taken.add(angle) }
  if (low < 0) { low = free(); taken.add(low) }
  if (current < 0) { current = free(); taken.add(current) }
  return { angle, low, high: high >= 0 ? high : null, current, sigma: sigma >= 0 ? sigma : null,
    units: { current: unitOf(header[current]), sigma: sigma >= 0 ? unitOf(header[sigma]) : unitOf(header[current]) } }
}
export function currentsFrom(table, c, sigmaForAll = '') {
  const micro = (text, unit) => shift(text, (UNIT_POWER[unit] ?? 0) + 6) ?? String(text)
  return table.rows.map((row, i) => ({
    angle: row[c.angle] ?? '', emin: row[c.low] ?? '', emax: c.high === null ? '' : row[c.high] ?? '',
    current: micro(row[c.current] ?? '', c.units.current), sigma: c.sigma === null ? sigmaForAll : micro(row[c.sigma] ?? '', c.units.sigma),
    included: true, note: `From ${[table.file, table.page ? `page ${table.page}` : '', table.lines[i] ? `line ${table.lines[i]}` : ''].filter(Boolean).join(', ')}`,
  }))
}

// --- Checks before anything is sent -------------------------------------------------------------
// [area, text, field]: the same shape the concentration form uses, so problems show the same way.
export function comparisonProblems(d) {
  const out = [], rows = d.rows, used = rows.filter(r => r.included)
  if (!used.length) out.push(['rows', 'Use at least one current.', 'rows'])
  if (rows.length > 24) out.push(['rows', 'Use at most 24 currents.', 'rows'])
  if (rows.some(r => !within(r.angle, 0, 90))) out.push(['rows', 'Each angle must be from 0 to 90 degrees.', 'rows'])
  if (rows.some(r => !within(r.emin, 0, 10000) || (clean(r.emax) !== '' && (!within(r.emax, 0, 10000) || Number(clean(r.emax)) <= Number(clean(r.emin))))))
    out.push(['rows', 'Each energy window needs a lowest energy of 0 eV or more, and a highest energy above it or left empty.', 'rows'])
  if (rows.some(r => !isDecimal(r.current) || !isDecimal(shift(r.current, -6) ?? '') || Math.abs(Number(clean(r.current))) > 1e12)) out.push(['rows', 'Each current must be a number in µA.', 'rows'])
  if (rows.some(r => !isDecimal(r.sigma) || !(Number(clean(r.sigma)) >= 1e-9) || Number(clean(r.sigma)) > 1e9 || !isDecimal(shift(r.sigma, -6) ?? ''))) out.push(['rows', 'Each σ must be a number above zero, in µA.', 'rows'])
  if (!d.synthetic) out.push(['about', 'This version compares made-up currents only. Confirm these are made up.', 'synthetic'])
  if (!d.description.trim()) out.push(['about', 'Say how the currents were made.', 'description'])
  else if (d.description.trim().length > 500) out.push(['about', 'Keep the description under 500 characters.', 'description'])
  if (!within(d.area, 1e-12, 0.1)) out.push(['about', 'The collector area must be from 1e-12 to 0.1 m².', 'area'])
  if (!within(d.efficiency, 1e-6, 1)) out.push(['about', 'The efficiency must be above 0 and at most 1.', 'efficiency'])
  const temps = list(d.temperatures)
  if (!within(d.densityMin, 1e8, 1e20) || !within(d.densityMax, 1e8, 1e20) || !(Number(clean(d.densityMax)) > Number(clean(d.densityMin))))
    out.push(['settings', 'The density search needs a lowest and a higher highest value, from 1e8 to 1e20 per m³.', 'settings'])
  if (temps.length < 2 || temps.length > 25 || temps.some(t => !within(t, 0.1, 1000)) || new Set(temps.map(Number)).size !== temps.length)
    out.push(['settings', 'List 2 to 25 different temperatures from 0.1 to 1000 eV.', 'settings'])
  if (!within(d.maxChi, 0.01, 1e6)) out.push(['settings', 'The fit limit must be from 0.01 to 1,000,000.', 'settings'])
  const evals = Number(d.maxEvaluations), n = temps.length, needed = n + n * n
  if (!/^\d+$/.test(clean(d.maxEvaluations)) || evals < 1 || evals > 1000) out.push(['settings', 'The evaluation limit must be a whole number from 1 to 1000.', 'settings'])
  else if (n >= 2 && needed > evals) out.push(['settings', `${n} temperatures need ${needed} fit evaluations, above your limit of ${evals}. Raise the limit or list fewer temperatures.`, 'settings'])
  else if (n >= 2 && needed * used.length > 50000) out.push(['settings', 'This many temperatures and currents is more fitting work than the service allows. List fewer temperatures.', 'settings'])
  const noise = list(d.noise), z = list(d.z), samples = Number(clean(d.samples))
  if (noise.length < 1 || noise.length > 8 || noise.some(s => !isDecimal(s) || !(Number(s) >= 1e-9) || Number(s) > 1e9) || new Set(noise.map(Number)).size !== noise.length)
    out.push(['settings', 'List 1 to 8 different noise levels above zero, in µA.', 'settings'])
  if (z.length < 1 || z.length > 4 || z.some(v => !within(v, 0.1, 10)) || new Set(z.map(Number)).size !== z.length) out.push(['settings', 'List 1 to 4 different band widths from 0.1 to 10.', 'settings'])
  if (!/^\d+$/.test(clean(d.samples)) || samples < 32 || samples > 1024) out.push(['settings', 'Simulated readings must be a whole number from 32 to 1024.', 'settings'])
  if (!/^\d+$/.test(clean(d.seed)) || Number(clean(d.seed)) > 4294967295) out.push(['settings', 'The seed must be a whole number from 0 to 4294967295.', 'settings'])
  if (!d.settings.length || d.settings.length > 16) out.push(['settings', 'List 1 to 16 settings you could measure next.', 'settings'])
  else if (d.settings.some(s => !within(s.angle, 0, 90) || !within(s.emin, 0, 10000) || (clean(s.emax) !== '' && (!within(s.emax, 0, 10000) || Number(clean(s.emax)) <= Number(clean(s.emin))))))
    out.push(['settings', 'Each next setting needs an angle from 0 to 90 degrees and a valid energy window.', 'settings'])
  else if (2 * samples * noise.length * z.length * (used.length + d.settings.length) > 262144)
    out.push(['settings', 'This is more simulation than the service allows. Use fewer simulated readings, noise levels or settings.', 'settings'])
  return out
}

// The complete approved request. Called only when the person presses the approval button.
export function comparisonRequest(d) {
  const used = new Set(), channels = [], observations = [], selected = []
  for (const r of d.rows) {
    const high = clean(r.emax) === '' ? null : clean(r.emax)
    const id = uniqueId(`a${idPart(r.angle)}_e${idPart(r.emin)}${high === null ? '' : '_' + idPart(high)}`, used)
    channels.push({ id, angle_deg: clean(r.angle), energy_min_eV: clean(r.emin), energy_max_eV: high })
    observations.push({ channel_id: id, current_A: shift(r.current, -6), sigma_A: shift(r.sigma, -6) })
    if (r.included) selected.push(id)
  }
  const settingIds = new Set()
  return {
    schema_version: 'DB-MODEL-COMPARISON-1', approval: 'approved_for_this_request',
    review: { reviewed: true, origin: 'synthetic', description: d.description.trim() },
    instrument: { kind: 'idealized_normal_energy_planar_collector', acceptance: 'full_incident_half_space', current_convention: 'electron_current_magnitude',
      area_m2: clean(d.area), efficiency: clean(d.efficiency) },
    channels, observations, selected_channel_ids: selected,
    fit: { density_min_m3: clean(d.densityMin), density_max_m3: clean(d.densityMax), temperature_grid_eV: list(d.temperatures),
      max_evaluations: Number(clean(d.maxEvaluations)), max_reduced_chi_square: clean(d.maxChi) },
    noise: { kind: 'independent_gaussian', sigma_grid_A: list(d.noise).map(s => shift(s, -6)), z_thresholds: list(d.z),
      seed: Number(clean(d.seed)), samples: Number(clean(d.samples)) },
    feasible_settings: d.settings.map(s => {
      const high = clean(s.emax) === '' ? null : clean(s.emax)
      return { id: uniqueId(`next_a${idPart(s.angle)}_e${idPart(s.emin)}${high === null ? '' : '_' + idPart(high)}`, settingIds),
        angle_deg: clean(s.angle), energy_min_eV: clean(s.emin), energy_max_eV: high }
    }),
  }
}

// A saved request back into the editable form, so "Change the currents" starts from it.
export function draftFromRequest(req) {
  const observations = req.observations
  const channel = Object.fromEntries(req.channels.map(c => [c.id, c]))
  return { ...blankComparison(), kind: 'saved', name: 'Saved comparison', synthetic: req.review?.origin === 'synthetic', description: req.review?.description ?? '',
    area: req.instrument?.area_m2 ?? '', efficiency: req.instrument?.efficiency ?? '',
    densityMin: req.fit.density_min_m3, densityMax: req.fit.density_max_m3, temperatures: req.fit.temperature_grid_eV.join(', '),
    maxEvaluations: String(req.fit.max_evaluations), maxChi: req.fit.max_reduced_chi_square,
    noise: req.noise.sigma_grid_A.map(s => shift(s, 6)).join(', '), z: req.noise.z_thresholds.join(', '), seed: String(req.noise.seed), samples: String(req.noise.samples),
    rows: observations.map(o => ({ angle: channel[o.channel_id].angle_deg, emin: channel[o.channel_id].energy_min_eV, emax: channel[o.channel_id].energy_max_eV ?? '',
      current: shift(o.current_A, 6), sigma: shift(o.sigma_A, 6), included: req.selected_channel_ids.includes(o.channel_id), note: '' })),
    settings: req.feasible_settings.map(s => ({ angle: s.angle_deg, emin: s.energy_min_eV, emax: s.energy_max_eV ?? '' })) }
}

// --- Formatting -----------------------------------------------------------------------------------
const significant = (x, digits = 3) => Number(Number(x).toPrecision(digits)).toLocaleString('en-US', { maximumSignificantDigits: digits })
export const micro = text => significant(Number(text) * 1e6, 3)
export function sci(text, unit = '', digits = 3) {
  const x = Number(text)
  if (!Number.isFinite(x)) return escapeHTML(text)
  const a = Math.abs(x)
  if (a === 0 || (a >= 1e-3 && a < 1e5)) return `${significant(x, digits)}${unit ? ' ' + unit : ''}`
  const power = Math.floor(Math.log10(a)), mantissa = Number((x / 10 ** power).toPrecision(digits))
  return tex(`${mantissa}\\times 10^{${power}}${unit ? `\\ \\mathrm{${unit}}` : ''}`)
}
const percent = text => `${Math.round(Number(text) * 100)}%`
const interval = pair => `${Math.round(Number(pair[0]) * 100)} to ${Math.round(Number(pair[1]) * 100)}%`

// --- Reading the result -----------------------------------------------------------------------------
export function readComparison(record) {
  const r = record.body, req = r.request
  const channel = Object.fromEntries(req.channels.map(c => [c.id, c]))
  const fits = Object.fromEntries(r.fits.map(f => [f.model_id, f]))
  const settingById = Object.fromEntries(req.feasible_settings.map(s => [s.id, s]))
  return { record, r, req, channel, fits, settingById, status: r.status, created: record.created_at ?? null,
    selected: req.observations.filter(o => req.selected_channel_ids.includes(o.channel_id)),
    cases: r.noise_sweep ?? [], canPlan: r.status === 'completed' && (r.noise_sweep ?? []).length > 0 }
}

const chi = f => f.reduced_chi_square === null ? 'not defined' : sci(f.reduced_chi_square)
export function comparisonFinding(m) {
  const { r, fits } = m, iso = fits[ISO], bi = fits[BI], limit = escapeHTML(r.request.fit.max_reduced_chi_square)
  const nu = tex('\\chi^2_\\nu')
  const failure = r.failures?.[0]?.message ?? ''
  const caution = 'A closer fit is not proof that a model is right, and the bi-Maxwellian has one more parameter.'
  if (r.status === 'unsupported') return { headline: 'The comparison could not run with these inputs', lead: escapeHTML(failure), limit: '' }
  if (r.status === 'budget_exceeded') return { headline: 'The comparison stopped at its work limit', lead: escapeHTML(failure), limit: '' }
  if (MODELS.some(id => !Object.keys(fits[id]?.parameters ?? {}).length)) return { headline: 'No fit was found on your temperature grid', lead: escapeHTML(failure), limit: '' }
  const both = `${nu} is ${chi(iso)} for the isotropic Maxwellian and ${chi(bi)} for the bi-Maxwellian, with your limit at ${limit}.`
  let headline
  if (iso.adequate_under_declared_threshold && bi.adequate_under_declared_threshold) headline = 'Both distributions fit these currents'
  else if (bi.adequate_under_declared_threshold) headline = 'Only the bi-Maxwellian fits these currents'
  else if (iso.adequate_under_declared_threshold) headline = 'Only the isotropic Maxwellian fits these currents'
  else headline = 'Neither distribution fits these currents'
  const notes = []
  if ([iso, bi].some(f => f.degrees_of_freedom !== null && f.degrees_of_freedom <= 0)) notes.push('There are too few currents to judge every fit.')
  if ([iso, bi].some(f => f.rank_deficient)) notes.push('These settings cannot pin down every parameter. At a single angle the two temperatures cannot be told apart.')
  if ([iso, bi].some(f => f.boundary_limited)) notes.push('A fit sits at the edge of your search limits.')
  const lead = `${both} ${headline.startsWith('Neither') ? 'The instrument model, the noise or the temperature grid may not match these currents.' : headline.startsWith('Both') ? 'These currents do not tell them apart. The next step shows which setting could.' : caution}`
  return { headline, lead, limit: notes.join(' ') }
}

export function fitRows(m) {
  const d = tex('n'), t = tex('T'), tp = tex('T_\\parallel'), tn = tex('T_\\perp')
  return MODELS.map(id => m.fits[id]).filter(Boolean).map(f => {
    const p = f.parameters
    const temps = f.model_id === ISO ? `${t} = ${escapeHTML(p.temperature_eV ?? '–')} eV` : `${tp} = ${escapeHTML(p.parallel_eV ?? '–')}, ${tn} = ${escapeHTML(p.perpendicular_eV ?? '–')} eV`
    return `<tr class="${TONE[f.model_id]}"><th scope="row"><span class="swatch" aria-hidden="true"></span>${NAME[f.model_id]}</th>
      <td>${p.density_m3 ? `${d} = ${sci(p.density_m3, 'm^{-3}')}` : '–'}<div class="exact">${temps}</div></td>
      <td>${chi(f)}<div class="exact">${f.degrees_of_freedom ?? 0} degrees of freedom</div></td>
      <td>${f.adequate_under_declared_threshold ? 'Yes' : 'No'}</td></tr>`
  }).join('')
}

export function currentsTable(m) {
  const pred = Object.fromEntries(MODELS.map(id => [id, Object.fromEntries((m.fits[id]?.predictions ?? []).map(p => [p.observation_index, p]))]))
  const rows = m.req.observations.map((o, i) => {
    const used = m.req.selected_channel_ids.includes(o.channel_id)
    const cells = MODELS.map(id => { const p = pred[id][i]; return p ? `<td>${micro(p.predicted_A)}<div class="exact">${significant(Number(p.residual_A) / Number(p.sigma_A), 3)} σ off</div></td>` : '<td class="quiet">–</td>' }).join('')
    return `<tr${used ? '' : ' class="unused"'}><th scope="row">${escapeHTML(settingLabel(m.channel[o.channel_id]))}${used ? '' : '<div class="exact">Not used in the fits</div>'}</th>
      <td>${micro(o.current_A)}<div class="exact">±${micro(o.sigma_A)}</div></td>${cells}</tr>`
  }).join('')
  return `<table class="data"><thead><tr><th scope="col">Setting</th><th scope="col">Current <span class="unit">µA</span></th>
    <th scope="col">Isotropic <span class="unit">µA</span></th><th scope="col">Bi-Maxwellian <span class="unit">µA</span></th></tr></thead><tbody>${rows}</tbody></table>`
}

export function caseLabel(c, many) { return `σ ${micro(c.sigma_A)} µA${many ? `, ±${escapeHTML(c.z_threshold)}σ` : ''}` }

export function caseFinding(m, c) {
  const sigma = micro(c.sigma_A), z = escapeHTML(c.z_threshold)
  const ranked = [...c.settings].sort((a, b) => Number(b.numerical_band_margin_A) - Number(a.numerical_band_margin_A))
  const best = c.settings.find(s => s.setting_id === c.suggested_setting_id) ?? ranked[0], setting = m.settingById[best.setting_id]
  const diff = m.r.settings.find(s => s.setting.id === setting.id)?.absolute_difference_A
  const already = c.selected_channel_bands_separated_numerically ? ' Your current readings already separate the two fits at this noise.' : ''
  if (c.suggested_setting_id) {
    const own = best.conditional_simulations.map(s => `${percent(s.outcomes.generating_band_only.frequency)} of those drawn from the ${INLINE[s.generating_model_id]} fit`)
    return { headline: `Measure at ${settingLabel(setting)}`,
      lead: `With noise σ = ${sigma} µA and ±${z}σ bands, the two fitted predictions there differ by ${micro(diff)} µA, leaving a gap of ${micro(best.numerical_band_margin_A)} µA between the bands. In simulated readings at that setting, ${own.join(' and ')} landed only in their own model's band.${already}` }
  }
  return { headline: `No listed setting tells them apart at σ = ${sigma} µA`,
    lead: `The best one, ${settingLabel(setting)}, leaves the ±${z}σ bands overlapping by ${micro(-Number(best.numerical_band_margin_A))} µA. Less noise or other settings would be needed.${already}` }
}

export function settingsTable(m, c) {
  const ranked = [...c.settings].sort((a, b) => Number(b.numerical_band_margin_A) - Number(a.numerical_band_margin_A))
  const rows = ranked.map(s => {
    const p = m.r.settings.find(x => x.setting.id === s.setting_id), apart = Number(s.numerical_band_margin_A) > 0
    return `<tr${s.setting_id === c.suggested_setting_id ? ' class="pick"' : ''}><th scope="row">${escapeHTML(settingLabel(m.settingById[s.setting_id]))}</th>
      <td>${micro(p.predictions_A[ISO])}</td><td>${micro(p.predictions_A[BI])}</td>
      <td>${apart ? `${micro(s.numerical_band_margin_A)} µA gap` : `<span class="quiet">overlap ${micro(-Number(s.numerical_band_margin_A))} µA</span>`}</td></tr>`
  }).join('')
  return `<table class="data"><thead><tr><th scope="col">Setting</th><th scope="col">Isotropic <span class="unit">µA</span></th><th scope="col">Bi-Maxwellian <span class="unit">µA</span></th><th scope="col">Bands</th></tr></thead><tbody>${rows}</tbody></table>`
}

export function simulationTable(m, c) {
  const best = c.settings.find(s => s.setting_id === c.suggested_setting_id)
  if (!best) return ''
  const cell = f => `${percent(f.frequency)}<div class="exact">${interval(f.wilson_95)}</div>`
  const rows = best.conditional_simulations.map(s => `<tr><th scope="row">${NAME[s.generating_model_id]} fit</th><td>${cell(s.outcomes.generating_band_only)}</td><td>${cell(s.outcomes.both_bands)}</td><td>${cell(s.outcomes.other_band_only)}</td><td>${cell(s.outcomes.neither_band)}</td></tr>`).join('')
  return `<h2 class="sub">${best.conditional_simulations[0].samples} simulated readings at ${escapeHTML(settingLabel(m.settingById[best.setting_id]))}</h2>
    <table class="data"><thead><tr><th scope="col">Drawn from</th><th scope="col">Own band only</th><th scope="col">Both bands</th><th scope="col">Other band only</th><th scope="col">Neither</th></tr></thead><tbody>${rows}</tbody></table>
    <p class="hint">Ranges are 95% intervals for the simulation's sampling only. They are not the chance that a model is true.</p>`
}

// Chart input for the result: each used current with ±σ, and both fitted predictions.
export function resultGroups(m) {
  const pred = Object.fromEntries(MODELS.map(id => [id, Object.fromEntries((m.fits[id]?.predictions ?? []).map(p => [p.observation_index, Number(p.predicted_A) * 1e6]))]))
  return m.req.observations.map((o, i) => ({ o, i })).filter(({ o }) => m.req.selected_channel_ids.includes(o.channel_id)).map(({ o, i }) => ({
    label: settingShort(m.channel[o.channel_id]), observed: { v: Number(o.current_A) * 1e6, e: Number(o.sigma_A) * 1e6 },
    marks: MODELS.filter(id => pred[id][i] !== undefined).map(id => ({ tone: TONE[id], v: pred[id][i] })),
  }))
}
// Chart input for one noise case: both predictions at each next setting with their ±zσ bands.
export function caseGroups(m, c) {
  const band = Number(c.z_threshold) * Number(c.sigma_A) * 1e6
  return m.r.settings.map(s => ({ label: settingShort(s.setting), selected: s.setting.id === c.suggested_setting_id,
    marks: MODELS.map(id => { const v = Number(s.predictions_A[id]) * 1e6; return { tone: TONE[id], v, low: v - band, high: v + band } }) }))
}
