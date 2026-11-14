import { setupFollowupWorkflow } from './followup-workflow.mjs'
import { designCandidates, designRequest, designExplanation } from './design.mjs'
import { concentrationChart, readable, toNumber, CANDIDATE_COLORS } from './result-view.mjs'

export function setupDesignWorkflow({ context, perform, button, node, exactRecord, save, openRun }) {
  const followup = setupFollowupWorkflow({ context, button, node, exactRecord, openRun })
  let sourceRun = '', evidenceId = '', draft, plan, approval, frozen, job, jobPlan, suggestion, jobId = ''
  const blank = () => ({ candidateIds: ['', ''], times: '', allowance: '', horizon: '', allowanceOrigin: 'reviewed_hard_bound', allowanceDescription: '', allowConstruction: false, allowContinuation: false })
  function reset() { followup.reset(); sourceRun = evidenceId = jobId = ''; draft = blank(); plan = approval = frozen = job = jobPlan = suggestion = undefined }
  reset()
  const fingerprint = () => JSON.stringify({ sourceRun, evidenceId, draft })
  const currentPlan = () => plan && fingerprint() === frozen
  function edited() {
    if (plan && !currentPlan()) approval = undefined
    const notice = document.getElementById('design-draft-state')
    if (notice) notice.textContent = currentPlan() ? 'The prepared plan matches these design inputs.' : 'Design inputs changed. Prepare a new design before approving or queueing.'
    for (const id of ['approve-design-scope', 'approve-design', 'queue-design']) {
      const control = document.getElementById(id)
      if (control && !currentPlan()) { control.disabled = true; if (control.type === 'checkbox') control.checked = false }
    }
  }
  function field(parent, key, label, { choices, check = false, multiline = false } = {}) {
    const wrapper = node('label', check ? ` ${label}` : label); if (!check) wrapper.className = 'stack'
    const control = document.createElement(choices ? 'select' : multiline ? 'textarea' : 'input')
    control.id = `design-${key}`
    if (choices) for (const [value, text] of choices) { const option = node('option', text); option.value = value; control.append(option) }
    if (check) { control.type = 'checkbox'; control.checked = draft[key] } else {
      if (!choices && !multiline) control.type = 'text'
      control.value = draft[key]
      if (multiline) control.rows = 2
    }
    control.disabled = context().busy
    control.addEventListener('input', () => { draft[key] = check ? control.checked : control.value; edited() })
    if (check) wrapper.prepend(control); else wrapper.append(control)
    parent.append(wrapper); return control
  }
  async function refresh(id = jobId) {
    const { api, workspace } = context()
    const loaded = await api.json(`/design-jobs/${encodeURIComponent(id.trim())}`)
    if (loaded.workspace_id !== workspace) throw new Error('Select the design’s workspace before opening it.')
    const [record, historicalPlan] = await Promise.all([
      loaded.result_id ? api.json(`/records/${encodeURIComponent(loaded.result_id)}`) : undefined,
      api.json(`/records/${encodeURIComponent(loaded.plan_id)}`),
    ])
    job = loaded; jobId = job.id; suggestion = record; jobPlan = historicalPlan
  }
  function render(parent) {
    const { api, workspace, run, busy, available } = context()
    const section = node('section', ''); section.id = 'backend-design'; parent.append(section)
    section.append(node('h2', 'Compare measurement times'), node('p', 'Pick two candidates that both fit your readings. For each time you could measure, the checker tests whether their predicted concentrations are far enough apart that one new reading, within your allowance, could not fit both. This comparison needs its own plan and approval.'))
    if (sourceRun !== (run?.id || '')) {
      sourceRun = run?.id || ''; evidenceId = jobId = ''; draft = blank(); plan = approval = frozen = job = jobPlan = suggestion = undefined
    }
    const eligible = (run?.evidence ?? []).filter(evidence => designCandidates(evidence).length >= 2)
    let evidence = eligible.find(e => e.id === evidenceId)
    if (!evidence && eligible.length) { evidence = eligible[0]; evidenceId = evidence.id; draft.candidateIds = designCandidates(evidence).slice(0, 2).map(c => c.id) }
    if (!evidence) { const empty = node('p', 'This needs a finished check that found two different candidates which both fit your readings. A single counterexample cannot be compared with anything. Run a check, then come back here.'); empty.className = 'note'; section.append(empty) }
    else {
      if (eligible.length > 1) {
        const label = node('label', 'Historical scenario'); label.className = 'stack'
        const select = node('select', ''); select.id = 'design-scenario'; select.disabled = busy
        for (const item of eligible) { const option = node('option', item.body.scenario_id); option.value = item.id; select.append(option) }
        select.value = evidenceId
        select.addEventListener('change', () => perform(() => { evidenceId = select.value; const chosen = eligible.find(e => e.id === evidenceId); draft.candidateIds = designCandidates(chosen).slice(0, 2).map(c => c.id) }))
        label.append(select); section.append(label)
      }
      section.append(node('p', `Comparing candidates from check ${run.id}. Their exact values come from that check's saved evidence.`))
      const candidates = designCandidates(evidence)
      for (let i = 0; i < 2; i++) {
        const label = node('label', i === 0 ? 'First candidate' : 'Second candidate'); label.className = 'stack'
        const select = node('select', ''); select.id = `design-candidate-${i + 1}`; select.disabled = busy
        for (const candidate of candidates) {
          const { A, ke, ka } = candidate.parameter_vector
          const option = node('option', `Candidate ${candidates.indexOf(candidate) + 1}: ke ≈ ${readable(ke)}, ka ≈ ${readable(ka)}, A ≈ ${readable(A)}`); option.value = candidate.id; select.append(option)
        }
        select.value = draft.candidateIds[i]
        select.addEventListener('input', () => { draft.candidateIds[i] = select.value; edited() })
        label.append(select); section.append(label)
      }
      field(section, 'times', 'Times you could measure (hours), separated by commas')
      field(section, 'allowance', 'Allowance for the new reading (± mg/L)')
      field(section, 'allowanceOrigin', 'Where that allowance comes from', { choices: [['reviewed_hard_bound', 'Reviewed hard bound'], ['hypothetical', 'Hypothetical precision assumption']] })
      field(section, 'allowanceDescription', 'Why this allowance is justified (a standard deviation alone is not enough)', { multiline: true })
      field(section, 'horizon', 'Latest elapsed time the comparison may consider (hours)')
      field(section, 'allowConstruction', 'Allow the checker to build exact certificates for these two candidates', { check: true })
      field(section, 'allowContinuation', 'Allow those certificates to extend up to the latest time above', { check: true })
      section.append(node('p', 'Possible outcomes: a checked separating time, numerical guidance only, no separating time, or unavailable. Limits: 120 seconds, two certificate constructions, two pair checks and a 4 MiB evidence file. No AI model is called.'))
      button(section, 'Prepare measurement design', async () => {
        const request = designRequest(run, evidence, draft), snapshot = fingerprint()
        const prepared = await api.json(`/runs/${encodeURIComponent(run.id)}/design-proposals`, request)
        plan = prepared; frozen = snapshot; approval = undefined
      }, !api || !workspace || !available)
      if (plan) {
        const status = node('p', currentPlan() ? 'The prepared plan matches these design inputs.' : 'Design inputs changed. Prepare a new design before approving or queueing.'); status.id = 'design-draft-state'
        section.append(status, exactRecord('Exact frozen measurement design', plan))
        const label = node('label', ' I reviewed the pair, times, allowance, latest time, permissions and limits, and approve only this comparison.')
        const check = document.createElement('input'); check.type = 'checkbox'; check.id = 'approve-design-scope'; check.disabled = busy || Boolean(approval) || !currentPlan()
        label.prepend(check); section.append(label)
        const approve = button(section, approval ? 'Design approved' : 'Approve reviewed design', async () => {
          if (!check.checked || !currentPlan()) throw new Error('Review the current design and check its separate approval box.')
          approval = await api.json(`/design-plans/${plan.id}/approvals`, { accepted: true, expected_plan_digest: plan.digest, expected_current_revision_id: plan.body.request.problem_id })
        }, true); approve.id = 'approve-design'
        check.addEventListener('change', () => { approve.disabled = busy || Boolean(approval) || !currentPlan() || !check.checked })
        if (approval) section.append(exactRecord('Design approval receipt', approval))
        const queue = button(section, 'Queue approved design', async () => {
          if (!currentPlan() || !approval) throw new Error('A matching reviewed design approval is required.')
          job = await api.json(`/design-plans/${plan.id}/jobs`, { approval_id: approval.id, expected_plan_digest: plan.digest })
          jobId = job.id; jobPlan = plan; suggestion = undefined
        }, !available || !currentPlan() || !approval || job?.plan_id === plan.id); queue.id = 'queue-design'
      }
    }
    const label = node('label', 'Comparison identifier'); label.className = 'stack'
    const input = document.createElement('input'); input.type = 'text'; input.id = 'design-job-id'; input.value = jobId; input.disabled = busy
    input.addEventListener('input', () => { jobId = input.value }); label.append(input); section.append(label)
    button(section, 'Open or refresh design', () => refresh(), !api || !workspace)
    section.append(node('p', 'Keep this identifier to reopen the comparison later. A running comparison updates by itself and is never repeated.'))
    if (job) {
      const line = node('p', `${job.id} · design execution: ${job.state}`); line.className = 'tech'
      section.append(line, exactRecord('Persisted design job', job))
      if (jobPlan) { const scope = node('p', `Design result scope: historical run ${jobPlan.body.request.historical_run_id}, scenario ${jobPlan.body.request.scenario_id}, pair ${jobPlan.body.request.candidate_ids.join(' and ')}.`); scope.className = 'tech'; section.append(scope, exactRecord('Approved scope for this design job', jobPlan)) }
      if (job.error_code) section.append(node('p', `Design execution stopped: ${job.error_code}.`))
    }
    if (suggestion) {
      const result = suggestion.body
      const tier = { checked_pair_separation: ['ok', 'Checked separating time'], numerical_guidance: ['wait', 'Numerical guidance only'], no_separation_established: ['off', 'No separating time found'] }[result.design_tier] ?? ['bad', 'Not established']
      const verdict = node('div', ''); verdict.className = 'verdict'; verdict.dataset.tone = result.design_tier === 'checked_pair_separation' ? 'challenged' : 'none'
      const chip = node('span', tier[1]); chip.className = `state ${tier[0]}`
      verdict.append(chip, node('p', result.selected_time ? `Measure at ${readable(result.selected_time)} hours, with an allowance of ±${readable(result.future_hard_allowance)} mg/L.` : 'No time on your list was selected.'), node('p', designExplanation(result)))
      verdict.children[1].className = 'verdict-statement'
      const pairIds = jobPlan?.body?.request?.candidate_ids ?? result.candidate_ids ?? []
      const vectors = jobPlan?.body?.request?.candidate_vectors ?? []
      const dataset = run?.inputs?.dataset?.body
      if (dataset?.rows?.length && vectors.length === 2) {
        const curves = vectors.map((v, i) => ({ A: toNumber(v.A), ke: toNumber(v.ke), ka: toNumber(v.ka), color: CANDIDATE_COLORS[i], dash: i === 1 }))
        const chart = concentrationChart({ rows: dataset.rows.map(row => ({ t: toNumber(row.time), c: toNumber(row.concentration), e: toNumber(row.hard_allowance), included: row.included })), curves, markTime: result.selected_time ? toNumber(result.selected_time) : null })
        if (chart) {
          const figure = node('figure', ''); figure.className = 'chart'; figure.append(chart)
          const legend = node('ul', ''); legend.className = 'legend'
          pairIds.forEach((id, i) => { const item = node('li', ''); const sw = node('span', ''); sw.className = `swatch${i === 1 ? ' dash' : ''}`; sw.style.color = CANDIDATE_COLORS[i]; item.append(sw, `${i === 0 ? 'First' : 'Second'} candidate (ke ≈ ${readable(vectors[i].ke)} h⁻¹)`); legend.append(item) })
          figure.append(legend, node('figcaption', 'Both curves pass through your existing allowance bars, which is why the data cannot tell them apart yet. Where the curves diverge, one new reading can. The dashed vertical line marks the suggested time. Drawn with decimal approximations.'))
          verdict.append(figure)
        }
      }
      section.append(verdict, node('h4', 'Every time you listed'), node('p', `Design tier: ${result.design_tier}. Verification: ${result.verification}. Expected binding: ${result.native_replay?.expected_binding ?? result.verification_record?.expected_binding ?? 'not_supplied'}. Replay: ${result.replay}. Reason: ${result.reason_code}.`), node('p', `Selected elapsed time: ${result.selected_time ?? 'none'} h. Future hard allowance: ${result.future_hard_allowance ?? 'unavailable'} mg/L.`))
      section.lastChild.className = 'tech'; section.lastChild.previousSibling.className = 'tech'
      const region = node('div', ''); region.className = 'table-region'; region.tabIndex = 0; region.setAttribute('role', 'region'); region.setAttribute('aria-label', 'Measurement design grid')
      const table = node('table', ''), head = node('thead', ''), headings = node('tr', ''), body = node('tbody', '')
      for (const title of ['Time (h)', 'State', 'Separation margin (mg/L)', 'Reason']) { const th = node('th', title); th.scope = 'col'; headings.append(th) }
      head.append(headings)
      for (const option of result.options) {
        const row = node('tr', '')
        for (const value of [readable(option.time), option.state, option.exact_margin ? readable(option.exact_margin, 4) : 'not established', option.reason_code]) { const td = node('td', value); if (value !== option.state && value !== option.reason_code) td.title = 'Exact values are in the technical record below'; row.append(td) }
        body.append(row)
      }
      table.append(head, body); region.append(table); section.append(region)
      section.append(node('p', 'Times appear in the order you listed them. The suggested time is the best of these for this pair only; it is not the best possible experiment overall, and it says nothing about other candidates.'))
      if (result.native_replay?.fresh_checked?.rows) section.append(exactRecord('Exact checked prediction bands and margins', result.native_replay.fresh_checked.rows))
      section.append(exactRecord('Exact design evidence record', suggestion))
      for (const reference of result.artifacts ?? []) {
        const name = `dr-bean-${reference.id}`
        section.append(node('h4', 'Download comparison evidence'), node('p', `Native design evidence: ${reference.byte_size.toLocaleString()} bytes, SHA-256 ${reference.sha256}`)); section.lastChild.className = 'tech'
        button(section, 'Download native design evidence', async () => { const file = await api.download(`/artifacts/${encodeURIComponent(reference.id)}`, reference); save(file.bytes, `${name}.native.json`) })
        button(section, 'Download design replay anchors', async () => { const file = await api.download(`/artifacts/${encodeURIComponent(reference.id)}/anchor?download=true`); save(file.bytes, `${name}.anchors.json`) })
        section.append(node('p', 'Replay the retained design and baseline history with the matching Counterdex CPython 3.11 package. Native replay checks supported mathematical facts; browser download hashes establish byte integrity only.'), node('pre', `python3.11 -m counterdex replay-native ${name}.native.json --anchors ${name}.anchors.json`))
      }
      followup.render(section, job, suggestion, jobPlan)
    }
  }
  return { render, reset, pending: () => job && ['queued', 'running', 'cancel_requested'].includes(job.state), refresh: () => refresh(job.id) }
}
