// Reads the files a finished study downloads (the full record, the checker's proof for
// each run and its replay fingerprints) and turns them into plain statements, tables and
// one readable report. Nothing here computes science: every value comes from the files.
import { chartSVG } from './chart.mjs'
import { page, symbols } from './math.mjs'

export const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])

// Exact rationals arrive as "numerator/denominator" strings with up to ~50 digits.
export function toNumber(text) {
  const [a, b = '1'] = String(text).split('/')
  const n = BigInt(a), d = BigInt(b)
  const safe = x => x <= BigInt(Number.MAX_SAFE_INTEGER) && x >= -BigInt(Number.MAX_SAFE_INTEGER)
  if (safe(n) && safe(d)) return Number(n) / Number(d)
  const scale = 10n ** 30n
  return Number((n * scale) / d) / 1e30
}

const significant = (value, digits = 3) => new Intl.NumberFormat('en-US', { maximumSignificantDigits: digits }).format(value)
const fixed = (value, count = 2) => new Intl.NumberFormat('en-US', { minimumFractionDigits: count, maximumFractionDigits: count }).format(value)
const count = value => new Intl.NumberFormat('en-US').format(value)
const when = iso => new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso))
const bytes = size => size < 1024 ? `${size} bytes` : `${significant(size / 1024, 3)} KB`
export const formatRate = value => significant(value, 3)
export const formatConc = value => fixed(value, 2)
// Claim bounds keep at least two decimals, as people write them (0.10, not 0.1).
export const formatBound = value => { const two = value.toFixed(2); return Math.abs(Number(two) - value) < 1e-12 ? two : significant(value, 4) }

function decode(base64) {
  const raw = Uint8Array.from(atob(base64), c => c.charCodeAt(0))
  return JSON.parse(new TextDecoder().decode(raw))
}

// texts: { filename: file text } exactly as downloaded. One record, any number of proofs.
export function fromTexts(texts) {
  const names = Object.keys(texts)
  const reportName = names.find(name => /^dr-bean-report_.*\.json$/.test(name))
  if (!reportName) throw new Error('The study record is missing.')
  const natives = names.filter(name => name.endsWith('.native.json')).map(name => {
    const packet = JSON.parse(texts[name])
    return { name, packet, science: decode(packet.scientific.bytes_base64) }
  })
  const anchors = names.filter(name => name.endsWith('.anchors.json')).map(name => ({ name, json: JSON.parse(texts[name]) }))
  return { texts, reportName, report: JSON.parse(texts[reportName]), natives, anchors }
}

const plainLimits = {
  'Verification is adapter-specific and conditional on reviewed meanings and assumptions.':
    'The check is only as good as the model, units and allowances you reviewed.',
  'A bounded search that finds no counterexample does not prove the claim.':
    'A search that finds no curve outside the claim does not prove the claim.',
  'Fresh replay reruns the same checker; it is not an independently implemented proof system.':
    'Replaying a proof reruns the same checker. It confirms the files, not the method.',
  'An actual observation is a human declaration, not authenticated acquisition.':
    'Marking a reading as measured is your statement. The app does not verify how it was taken.',
}

export function summarize(data) {
  const body = data.report.body
  const problem = body.root_inputs.problem.body, dataset = body.root_inputs.dataset.body
  const readings = dataset.rows.map(row => ({
    id: row.id, included: row.included, t: toNumber(row.time), v: toNumber(row.concentration), e: toNumber(row.hard_allowance),
    time: row.original_values?.time ?? significant(toNumber(row.time), 4),
    value: row.original_values?.concentration ?? fixed(toNumber(row.concentration)),
    allowance: row.original_values?.hard_allowance ?? fixed(toNumber(row.hard_allowance)),
  }))
  const included = readings.filter(r => r.included)
  const claim = { low: toNumber(problem.target.lower), high: toNumber(problem.target.upper), closed: problem.target.closed }
  const domain = Object.fromEntries(['A', 'ke', 'ka'].map(k => [k, [toNumber(problem.domain[k].lower), toNumber(problem.domain[k].upper)]]))
  const evidence = body.evidence.find(item => item.kind === 'evidence')
  const result = evidence.body.result
  const verdicts = new Map((result.candidate_results ?? []).map(r => [r.candidate_id, r]))
  const candidates = (result.candidates ?? []).map(c => {
    const verdict = verdicts.get(c.id) ?? {}
    return {
      id: c.id, exact: c.parameter_vector, outside: verdict.outside_closed_claim === true, tone: verdict.outside_closed_claim ? 'outside' : 'inside',
      params: { A: toNumber(c.parameter_vector.A), ke: toNumber(c.parameter_vector.ke), ka: toNumber(c.parameter_vector.ka) },
      fits: c.verification === 'valid' && verdict.verification === 'valid' && !(verdict.violating_observation_ids ?? []).length && !(verdict.unresolved_observation_ids ?? []).length,
    }
  }).sort((a, b) => Number(a.outside) - Number(b.outside))
  const checkProof = data.natives.find(n => n.packet.operation === 'investigate')
  const nextProof = data.natives.find(n => n.packet.operation === 'design')
  const rowsByCandidate = new Map((checkProof?.science.report?.checked?.candidate_results ?? []).map(r => [r.candidate_id, new Map(r.rows.map(row => [row.observation_id, row]))]))
  const readingChecks = included.map(reading => ({
    ...reading,
    curves: candidates.map(c => {
      const row = rowsByCandidate.get(c.id)?.get(reading.id)
      return row ? { tone: c.tone, low: toNumber(row.lower), high: toNumber(row.upper), within: row.status === 'compatible' } : { tone: c.tone, missing: true }
    }),
  }))
  const suggestion = body.evidence.find(item => item.kind === 'suggestion')?.body
  const checked = nextProof?.science.report?.checked
  const next = suggestion && checked ? {
    tier: suggestion.design_tier, verification: suggestion.verification, replay: suggestion.replay,
    selected: suggestion.selected_time ? toNumber(suggestion.selected_time) : null,
    allowance: toNumber(suggestion.future_hard_allowance),
    horizon: toNumber(nextProof.science.design.horizon_policy.maximum_horizon),
    source: nextProof.science.design.allowance_origin?.description ?? '',
    times: (checked.rows ?? []).map(row => ({
      t: toNumber(row.time), separated: row.separated === true, margin: row.margin ? toNumber(row.margin) : 0, gap: row.gap ? toNumber(row.gap) : 0,
      centers: candidates.map(c => ({ tone: c.tone, value: toNumber(row.centers[c.id]) })),
      ranges: candidates.map(c => ({ tone: c.tone, low: toNumber(row.bands[c.id][0]), high: toNumber(row.bands[c.id][1]) })),
    })).sort((a, b) => a.t - b.t),
  } : null
  const sizes = Object.fromEntries(Object.entries(data.texts).map(([name, text]) => [name, new Blob([text]).size]))
  const operation = name => data.natives.find(n => n.name === name)?.packet.operation
  const files = [
    { kind: 'record', name: data.reportName, title: 'Full record', size: sizes[data.reportName],
      about: 'The saved study: readings, claim, approvals, results and the list of proofs.' },
    ...body.native_evidence.flatMap(entry => {
      const step = operation(entry.native_filename) === 'design' ? 'next' : 'check'
      const which = step === 'next' ? 'next measurement' : 'claim check'
      return [
        { kind: 'proof', step, name: entry.native_filename, title: `Checker proof, ${which}`, size: sizes[entry.native_filename],
          sha256: entry.artifact.sha256, about: `Counterdex's exact calculations for the ${which}.` },
        { kind: 'fingerprints', step, name: entry.anchor_filename, title: `Replay fingerprints, ${which}`, size: sizes[entry.anchor_filename],
          about: 'Fingerprints that tie the proof to these readings and this claim.' },
      ]
    }).filter(file => data.texts[file.name] !== undefined),
  ]
  const checker = checkProof?.science.implementation
  return {
    title: dataset.experiment_id, objective: body.objective, created: data.report.created_at, origin: dataset.origin,
    timeOrigin: dataset.time_origin, allowanceSource: dataset.change_reason, readings, included, claim, domain, candidates,
    readingChecks, next, files,
    outcome: result.scientific_outcome, verification: result.verification, replay: result.replay, binding: result.expected_binding,
    search: { attempted: result.baseline_search?.attempted_count ?? 0, feasible: result.baseline_search?.feasible_count ?? 0,
      kept: result.baseline_search?.retained_count ?? 0, partial: result.baseline_search?.partial === true },
    checker: { version: checker?.adapter_version, python: checker?.python, rule: checkProof?.science.report?.checked?.proof_rule },
    approvals: body.scientific_approvals.map(a => ({ scope: a.scope, at: a.created_at })),
    limits: body.limitations.map(text => plainLimits[text] ?? text),
    replay: body.native_evidence.map(entry => entry.replay_command),
  }
}

export function finding(m, sym = page) {
  const n = m.included.length
  const inside = m.candidates.find(c => !c.outside), outside = m.candidates.find(c => c.outside)
  if (m.outcome === 'certified_counterexample' && outside) {
    const below = outside.params.ke < m.claim.low
    return {
      headline: `Your readings allow ${sym.ke} ${below ? 'below' : 'above'} ${formatBound(below ? m.claim.low : m.claim.high)} per hour`,
      lead: `A curve with ${sym.ke} = ${formatRate(outside.params.ke)} per hour stays within the allowance of all ${n} readings` +
        (inside ? `, and so does one with ${sym.ke} = ${formatRate(inside.params.ke)} inside your claim. These readings cannot tell the two apart.` : '.'),
      limit: `This does not give the true value of ${sym.ke}. It shows that these readings, this model and these allowances do not settle the claim.`,
      tone: 'challenged',
    }
  }
  if (m.outcome === 'no_counterexample_found') {
    return {
      headline: 'No curve outside your claim was found',
      lead: `The checker tried ${count(m.search.attempted)} combinations of ${sym.ka} and ${sym.ke} within the search limits. None fits every reading with ${sym.ke} outside ${formatBound(m.claim.low)} to ${formatBound(m.claim.high)} per hour.`,
      limit: 'This is not proof of the claim. A wider search or different limits could still find one.',
      tone: 'unsettled',
    }
  }
  return { headline: 'The check did not reach a conclusion', lead: `The checker reported "${escapeHTML(m.outcome)}".`, limit: 'Open the full record for the details.', tone: 'unknown' }
}

export function nextFinding(m) {
  const next = m.next
  if (!next) return null
  const best = next.times.find(t => t.t === next.selected)
  if (next.tier !== 'checked_pair_separation' || !best) {
    return { headline: 'No checked time separates the two curves', lead: `With a ±${formatConc(next.allowance)} mg/L allowance, none of the times you gave keeps the two curves' ranges apart. Try other times or a smaller allowance.` }
  }
  const [a, b] = best.centers
  const others = next.times.filter(t => t !== best && t.separated)
  return {
    headline: `Measure at ${formatRate(best.t)} hours`,
    lead: `At ${formatRate(best.t)} h the two curves predict ${formatConc(a.value)} and ${formatConc(b.value)} mg/L. With a ±${formatConc(next.allowance)} mg/L allowance on the new reading, it can fit only one of them, with ${formatConc(best.margin)} mg/L to spare.` +
      (others.length ? ` ${others.map(o => `At ${formatRate(o.t)} h there is ${formatConc(o.margin)} mg/L to spare`).join('. ')}.` : ''),
  }
}

const anchorMeaning = {
  artifact_sha256: 'The proof file itself', dataset_digest: 'Your readings', problem_digest: 'The claim, model and search limits',
  projection_digest: "The checker's copy of the problem", design_digest: 'The next-measurement settings',
  app_request_digest: "The app's request to the checker", run_id: 'The run that made the proof', scenario_id: 'The part of that run',
}

const rawBlock = (label, value) => `<details class="raw"><summary>${escapeHTML(label)}</summary><pre>${escapeHTML(typeof value === 'string' ? value : JSON.stringify(value, null, 2))}</pre></details>`

export function readingTable(m) {
  const heads = m.candidates.map(c => `<th scope="col">${c.outside ? 'Curve outside the claim' : 'Curve inside the claim'}</th>`).join('')
  const rows = m.readingChecks.map(r => `<tr><td>${escapeHTML(r.time)}</td><td>${escapeHTML(r.value)} ± ${escapeHTML(r.allowance)}</td>${r.curves.map(c => c.missing ? '<td class="quiet">not in file</td>' :
    `<td>${formatConc((c.low + c.high) / 2)} <span class="${c.within ? 'ok' : 'bad'}">${c.within ? 'within' : 'outside'}</span></td>`).join('')}</tr>`).join('')
  return `<table class="data"><caption>Each curve value is an exact range from the checker, rounded here. Concentrations in mg/L.</caption>
    <thead><tr><th scope="col">Hours</th><th scope="col">Your reading</th>${heads}</tr></thead><tbody>${rows}</tbody></table>`
}

export function nextTable(m) {
  if (!m.next) return ''
  const heads = m.candidates.map(c => `<th scope="col">${c.outside ? 'Curve outside the claim' : 'Curve inside the claim'}</th>`).join('')
  const rows = m.next.times.map(t => `<tr${t.t === m.next.selected ? ' class="chosen"' : ''}><td>${formatRate(t.t)}</td>${t.centers.map(c => `<td>${formatConc(c.value)}</td>`).join('')}<td>${t.separated ? `Yes, ${formatConc(t.margin)} to spare` : 'No, the ranges overlap'}</td></tr>`).join('')
  return `<table class="data"><caption>Predicted concentration (mg/L) at each possible time, with a ±${formatConc(m.next.allowance)} mg/L allowance on the new reading.</caption>
    <thead><tr><th scope="col">Hours</th>${heads}<th scope="col">Can one reading decide?</th></tr></thead><tbody>${rows}</tbody></table>`
}

export function fileView(data, m, file, sym = page) {
  if (file.kind === 'fingerprints') {
    const json = data.anchors.find(a => a.name === file.name).json
    const rows = Object.entries(json).map(([key, value]) => `<tr><th scope="row">${escapeHTML(anchorMeaning[key] ?? key)}</th><td class="mono">${value === null ? '<span class="quiet">not used</span>' : escapeHTML(value)}</td></tr>`).join('')
    return `<p>Each line is a fingerprint (a SHA-256 digest or an ID). If any input changed, its fingerprint would change and the replay below would fail.</p>
      <table class="facts"><tbody>${rows}</tbody></table>
      <p>To confirm the proof on your own computer, download it and this file into one folder and run:</p>
      <pre class="command">python3.11 -m counterdex replay-native ${escapeHTML(file.name.replace('.anchors.json', '.native.json'))} --anchors ${escapeHTML(file.name)}</pre>
      ${rawBlock('Show the file as saved', data.texts[file.name])}`
  }
  if (file.kind === 'proof') {
    const science = data.natives.find(n => n.name === file.name).science
    return `<table class="facts"><tbody>
      <tr><th scope="row">What it checked</th><td>${file.step === 'next' ? 'Whether one more reading at your chosen times can tell the two curves apart' : `Whether a curve can fit all your readings with ${sym.ke} outside the claim`}</td></tr>
      <tr><th scope="row">Model</th><td>${sym.modelInline}, starting at 0 mg/L</td></tr>
      <tr><th scope="row">Checker</th><td>Counterdex ${escapeHTML(science.implementation.adapter_version)} on Python ${escapeHTML(science.implementation.python)}</td></tr>
      <tr><th scope="row">Result</th><td>${file.step === 'next' ? escapeHTML(nextFinding(m)?.headline ?? '') : finding(m, sym).headline}</td></tr>
      <tr><th scope="row">File fingerprint</th><td class="mono">${escapeHTML(file.sha256)}</td></tr></tbody></table>
      ${file.step === 'next' ? nextTable(m) : readingTable(m)}
      <p class="quiet">The scientific part of the proof is stored in base64 so its bytes stay exact. It is shown decoded below.</p>
      ${rawBlock('Show the decoded calculations', science)}${rawBlock('Show the file as saved', data.texts[file.name])}`
  }
  return `<table class="facts"><tbody>
      <tr><th scope="row">Question</th><td>${escapeHTML(m.objective)}</td></tr>
      <tr><th scope="row">Readings</th><td>${m.included.length} used of ${m.readings.length}, ${m.origin === 'actual' ? 'measured' : escapeHTML(m.origin)}</td></tr>
      <tr><th scope="row">Claim</th><td>${sym.claim(formatBound(m.claim.low), formatBound(m.claim.high))}, both ends included</td></tr>
      <tr><th scope="row">Saved</th><td>${escapeHTML(when(m.created))}</td></tr></tbody></table>
    <h3>Approvals</h3><ul>${m.approvals.map(a => `<li>${a.scope === 'design' ? 'Next measurement' : 'Claim check'} approved ${escapeHTML(when(a.at))}</li>`).join('')}</ul>
    <h3>Results</h3><ul><li>${finding(m, sym).headline}</li>${m.next ? `<li>${escapeHTML(nextFinding(m).headline)}</li>` : ''}</ul>
    ${rawBlock('Show the file as saved', data.texts[data.reportName])}`
}

export const curvesFor = m => m.candidates.map(c => ({ params: c.params, tone: c.tone }))

// One self-contained HTML page with everything in the downloaded files. Math is MathML,
// so it typesets in any current browser without a stylesheet or font download.
export async function readableReport(data, m, fontURL) {
  const sym = symbols('mathml')
  let font = ''
  try {
    const buffer = new Uint8Array(await (await fetch(fontURL)).arrayBuffer())
    let binary = ''
    for (let i = 0; i < buffer.length; i += 0x8000) binary += String.fromCharCode(...buffer.subarray(i, i + 0x8000))
    font = `@font-face{font-family:Atkinson;src:url(data:font/woff2;base64,${btoa(binary)}) format('woff2');font-weight:200 800}`
  } catch { font = '' }
  const f = finding(m, sym), nf = nextFinding(m)
  const chart = chartSVG({ readings: m.included, curves: curvesFor(m), title: 'Readings with allowances and the curves that fit them' })
  const nextChart = m.next ? chartSVG({ readings: m.included, curves: curvesFor(m), title: 'Predicted ranges at the possible times',
    future: { until: m.next.horizon, times: m.next.times.map(t => ({ t: t.t, ranges: t.ranges, selected: t.t === m.next.selected })) } }) : ''
  const candidateRows = m.candidates.map(c => `<tr><th scope="row">${c.outside ? 'Outside the claim' : 'Inside the claim'}</th><td>${formatRate(c.params.ke)}<div class="exact">${sym.exact(c.exact.ke)}</div></td><td>${formatRate(c.params.ka)}<div class="exact">${sym.exact(c.exact.ka)}</div></td><td>${formatRate(c.params.A)}<div class="exact">${sym.exact(c.exact.A)}</div></td><td>${c.fits ? 'Yes, all readings' : 'No'}</td></tr>`).join('')
  const files = m.files.map(file => `<tr><th scope="row">${escapeHTML(file.title)}</th><td class="mono">${escapeHTML(file.name)}</td><td>${escapeHTML(bytes(file.size))}</td></tr>`).join('')
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHTML(m.title)}: Dr. Bean report</title><style>${font}
:root{color-scheme:dark;--bg:#121315;--surface:#1a1c1f;--line:rgba(233,236,240,.12);--text:#e9ecf0;--text2:#acb2bb;--text3:#8e959f;--series:#7fb0ff;--ok:#8cc7a1;--bad:#ee9585}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.55 Atkinson,"Atkinson Hyperlegible Next",system-ui,sans-serif;font-variant-numeric:tabular-nums}
main{max-width:860px;margin:0 auto;padding:48px 24px 64px}h1{font-size:32px;line-height:1.2;font-weight:600;margin:8px 0 12px;text-wrap:balance}
h2{font-size:22px;font-weight:600;margin:48px 0 12px}h3{font-size:17px;font-weight:600;margin:24px 0 8px}p{margin:8px 0;max-width:68ch}.quiet{color:var(--text2)}
math{font-size:1.08em}table{width:100%;border-collapse:collapse;margin:12px 0}th,td{text-align:left;padding:10px 12px 10px 0;border-bottom:1px solid var(--line);vertical-align:top}
thead th{color:var(--text2);font-weight:500}.mono{font-family:ui-monospace,Menlo,monospace;font-size:13px;color:var(--text2);word-break:break-all}.exact{margin-top:4px;color:var(--text2);font-size:14px}
.chart{width:100%;height:auto;margin:12px 0}.chart .grid{stroke:var(--line)}.chart .tick,.chart .axis,.chart .slot-label{fill:var(--text3);font-size:12px}
.chart .curve{fill:none;stroke-width:2}.chart .curve.inside{stroke:var(--text2)}.chart .curve.outside{stroke:var(--series);stroke-width:2.5}
.chart .reading path{stroke:var(--text);stroke-width:1.5;fill:none}.chart .reading circle{fill:var(--text)}.chart .slot-line{stroke:var(--line)}
.chart .range.inside{fill:var(--text2)}.chart .range.outside{fill:var(--series)}.chart .selected .slot-label{fill:var(--text);font-weight:600}
.ok{color:var(--ok)}.bad{color:var(--bad)}pre{white-space:pre-wrap;word-break:break-all;background:var(--surface);padding:12px;border-radius:6px;font-size:13px}
.key{display:flex;gap:24px;color:var(--text2);font-size:14px}.key span::before{content:"";display:inline-block;width:16px;height:3px;margin-right:8px;vertical-align:middle;background:var(--text2)}.key .o::before{background:var(--series)}
@media print{:root{color-scheme:light;--bg:#fff;--surface:#f3f3f3;--line:#d8d8d8;--text:#111;--text2:#444;--text3:#555;--series:#1f5fbf;--ok:#1d6b3a;--bad:#a1281a}main{padding:0}h2{break-after:avoid}table,svg{break-inside:avoid}}
</style></head><body><main>
<p class="quiet">Dr. Bean report, saved ${escapeHTML(when(m.created))}. Made from the files listed at the end.</p>
<h1>${f.headline}</h1><p>${f.lead}</p><p class="quiet">${f.limit}</p>
${chart}<div class="key"><span>Curve inside the claim</span><span class="o">Curve outside the claim</span></div>
<h2>Question</h2><p>${escapeHTML(m.objective)}</p>
<h2>Readings</h2><p class="quiet">${escapeHTML(m.timeOrigin)}. Allowances: ${escapeHTML(m.allowanceSource)}.</p>
<table><thead><tr><th>Hours</th><th>Concentration (mg/L)</th><th>Allowance (± mg/L)</th><th>Used</th></tr></thead><tbody>
${m.readings.map(r => `<tr><td>${escapeHTML(r.time)}</td><td>${escapeHTML(r.value)}</td><td>${escapeHTML(r.allowance)}</td><td>${r.included ? 'Yes' : 'No'}</td></tr>`).join('')}</tbody></table>
<h2>Claim, model and search limits</h2><p>Claim: ${sym.claim(formatBound(m.claim.low), formatBound(m.claim.high))}, both ends included.</p><p>Model: ${sym.model}</p>
<p>The checker searched ${sym.A} from ${formatRate(m.domain.A[0])} to ${formatRate(m.domain.A[1])} mg/L, ${sym.ke} from ${formatRate(m.domain.ke[0])} to ${formatRate(m.domain.ke[1])} and ${sym.ka} from ${formatRate(m.domain.ka[0])} to ${formatRate(m.domain.ka[1])} per hour. It tried ${count(m.search.attempted)} combinations of ${sym.ka} and ${sym.ke}, found ${count(m.search.feasible)} that could fit and checked the best ones exactly.</p>
<h2>The curves</h2><table><thead><tr><th>Curve</th><th>${sym.ke} (per hour)</th><th>${sym.ka} (per hour)</th><th>${sym.A} (mg/L)</th><th>Fits</th></tr></thead><tbody>${candidateRows}</tbody></table>
<h2>Reading by reading</h2>${readingTable(m)}
${m.next ? `<h2>Next measurement</h2><h3>${escapeHTML(nf.headline)}</h3><p>${escapeHTML(nf.lead)}</p>${nextChart}${nextTable(m)}<p class="quiet">Possible times ${m.next.times.map(t => formatRate(t.t)).join(' and ')} h, latest ${formatRate(m.next.horizon)} h. Allowance source: ${escapeHTML(m.next.source)}.</p>` : ''}
<h2>Approvals</h2><ul>${m.approvals.map(a => `<li>${a.scope === 'design' ? 'Next measurement' : 'Claim check'} approved ${escapeHTML(when(a.at))}</li>`).join('')}</ul>
<h2>What this does not show</h2><ul>${m.limits.map(l => `<li>${escapeHTML(l)}</li>`).join('')}</ul>
<h2>Files</h2><table><tbody>${files}</tbody></table>
<p>To confirm a proof yourself, put it next to its fingerprints file and run:</p>${m.replay.map(c => `<pre>${escapeHTML(c)}</pre>`).join('')}
<p class="quiet">Checker: Counterdex ${escapeHTML(m.checker.version)} on Python ${escapeHTML(m.checker.python)}, proof rule ${escapeHTML(m.checker.rule)}.</p>
</main></body></html>`
}
