import { designCandidates, designRequest, designExplanation } from './design.mjs'

export function setupDesignWorkflow({ context, perform, button, node, exactRecord, save }) {
  let sourceRun = '', evidenceId = '', draft, plan, approval, frozen, job, jobPlan, suggestion, jobId = ''
  const blank = () => ({ candidateIds: ['', ''], times: '', allowance: '', horizon: '', allowanceOrigin: 'reviewed_hard_bound', allowanceDescription: '', allowConstruction: false, allowContinuation: false })
  function reset() { sourceRun = evidenceId = jobId = ''; draft = blank(); plan = approval = frozen = job = jobPlan = suggestion = undefined }
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
    const wrapper = node('label', label); wrapper.className = 'stack'
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
    wrapper.append(control); parent.append(wrapper); return control
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
    section.append(node('h3', 'Plan the next measurement'), node('p', 'Choose a feasible elapsed-time grid and hard measurement allowance to compare two fixed baseline candidates. This needs its own reviewed plan and approval.'))
    if (sourceRun !== (run?.id || '')) {
      sourceRun = run?.id || ''; evidenceId = jobId = ''; draft = blank(); plan = approval = frozen = job = jobPlan = suggestion = undefined
    }
    const eligible = (run?.evidence ?? []).filter(evidence => designCandidates(evidence).length >= 2)
    let evidence = eligible.find(e => e.id === evidenceId)
    if (!evidence && eligible.length) { evidence = eligible[0]; evidenceId = evidence.id; draft.candidateIds = designCandidates(evidence).slice(0, 2).map(c => c.id) }
    if (!evidence) section.append(node('p', 'Open a completed baseline with two freshly checked compatible candidates to prepare a design. One counterexample alone cannot support pair design.'))
    else {
      if (eligible.length > 1) {
        const label = node('label', 'Historical scenario'); label.className = 'stack'
        const select = node('select', ''); select.id = 'design-scenario'; select.disabled = busy
        for (const item of eligible) { const option = node('option', item.body.scenario_id); option.value = item.id; select.append(option) }
        select.value = evidenceId
        select.addEventListener('change', () => perform(() => { evidenceId = select.value; const chosen = eligible.find(e => e.id === evidenceId); draft.candidateIds = designCandidates(chosen).slice(0, 2).map(c => c.id) }))
        label.append(select); section.append(label)
      }
      section.append(node('p', `Historical run ${run.id}, scenario ${evidence.body.scenario_id}. Candidate vectors come from its retained checked evidence.`))
      const candidates = designCandidates(evidence)
      for (let i = 0; i < 2; i++) {
        const label = node('label', `Candidate ${i + 1}`); label.className = 'stack'
        const select = node('select', ''); select.id = `design-candidate-${i + 1}`; select.disabled = busy
        for (const candidate of candidates) {
          const { A, ke, ka } = candidate.parameter_vector
          const option = node('option', `${candidate.id}: A=${A}, ke=${ke}, ka=${ka}`); option.value = candidate.id; select.append(option)
        }
        select.value = draft.candidateIds[i]
        select.addEventListener('input', () => { draft.candidateIds[i] = select.value; edited() })
        label.append(select); section.append(label)
      }
      field(section, 'times', 'Feasible elapsed times (hours), separated by commas or spaces')
      field(section, 'allowance', 'Future hard allowance (mg/L)')
      field(section, 'allowanceOrigin', 'Future allowance origin', { choices: [['reviewed_hard_bound', 'Reviewed hard bound'], ['hypothetical', 'Hypothetical precision assumption']] })
      field(section, 'allowanceDescription', 'Why this future hard allowance is appropriate', { multiline: true })
      field(section, 'horizon', 'Maximum approved elapsed-time horizon (hours)')
      field(section, 'allowConstruction', 'Allow fixed-candidate certificate construction', { check: true })
      field(section, 'allowContinuation', 'Allow extension of those certificates through the approved horizon', { check: true })
      section.append(node('p', 'Requested tier: checked pair separation. Numerical guidance, no separation or unavailable results remain possible. Limits: 120 seconds, two fixed-vector constructions, two pair verifications and a 4 MiB native bundle. No model-provider calls.'))
      button(section, 'Prepare measurement design', async () => {
        const request = designRequest(run, evidence, draft), snapshot = fingerprint()
        const prepared = await api.json(`/runs/${encodeURIComponent(run.id)}/design-proposals`, request)
        plan = prepared; frozen = snapshot; approval = undefined
      }, !api || !workspace || !available)
      if (plan) {
        const status = node('p', currentPlan() ? 'The prepared plan matches these design inputs.' : 'Design inputs changed. Prepare a new design before approving or queueing.'); status.id = 'design-draft-state'
        section.append(status, exactRecord('Exact frozen measurement design', plan))
        const label = node('label', ' I reviewed the pair, times, precision, horizon, permissions and limits, and approve only this design.'); label.className = 'stack'
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
    const label = node('label', 'Design job identifier'); label.className = 'stack'
    const input = document.createElement('input'); input.type = 'text'; input.id = 'design-job-id'; input.value = jobId; input.disabled = busy
    input.addEventListener('input', () => { jobId = input.value }); label.append(input); section.append(label)
    button(section, 'Open or refresh design', () => refresh(), !api || !workspace)
    section.append(node('p', 'Keep this design job identifier to reopen its authenticated result. Pending jobs update automatically without repeating computation.'))
    if (job) {
      section.append(node('p', `${job.id} · design execution: ${job.state}`), exactRecord('Persisted design job', job))
      if (jobPlan) section.append(node('p', `Design result scope: historical run ${jobPlan.body.request.historical_run_id}, scenario ${jobPlan.body.request.scenario_id}, pair ${jobPlan.body.request.candidate_ids.join(' and ')}.`), exactRecord('Approved scope for this design job', jobPlan))
      if (job.error_code) section.append(node('p', `Design execution stopped: ${job.error_code}.`))
    }
    if (suggestion) {
      const result = suggestion.body
      section.append(node('h4', 'Measurement design result'), node('p', designExplanation(result)), node('p', `Design tier: ${result.design_tier}. Verification: ${result.verification}. Expected binding: ${result.native_replay?.expected_binding ?? result.verification_record?.expected_binding ?? 'not_supplied'}. Replay: ${result.replay}. Reason: ${result.reason_code}.`), node('p', `Selected elapsed time: ${result.selected_time ?? 'none'} h. Future hard allowance: ${result.future_hard_allowance ?? 'unavailable'} mg/L.`))
      const region = node('div', ''); region.className = 'table-region'; region.tabIndex = 0; region.setAttribute('role', 'region'); region.setAttribute('aria-label', 'Measurement design grid')
      const table = node('table', ''), head = node('thead', ''), headings = node('tr', ''), body = node('tbody', '')
      for (const title of ['Approved time (h)', 'State', 'Exact margin (mg/L)', 'Reason']) { const th = node('th', title); th.scope = 'col'; headings.append(th) }
      head.append(headings)
      for (const option of result.options) {
        const row = node('tr', '')
        for (const value of [option.time, option.state, option.exact_margin ?? 'not established', option.reason_code]) row.append(node('td', value))
        body.append(row)
      }
      table.append(head, body); region.append(table); section.append(region)
      section.append(node('p', 'Every approved time is shown in its reviewed order. A selected time only compares evaluated options for this fixed pair; it is not a globally optimal experiment.'))
      if (result.native_replay?.fresh_checked?.rows) section.append(exactRecord('Exact checked prediction bands and margins', result.native_replay.fresh_checked.rows))
      section.append(exactRecord('Exact design evidence record', suggestion))
      for (const reference of result.artifacts ?? []) {
        const name = `dr-bean-${reference.id}`
        section.append(node('p', `Native design evidence: ${reference.byte_size} bytes · SHA-256 ${reference.sha256}`))
        button(section, 'Download native design evidence', async () => { const file = await api.download(`/artifacts/${encodeURIComponent(reference.id)}`, reference); save(file.bytes, `${name}.native.json`) })
        button(section, 'Download design replay anchors', async () => { const file = await api.download(`/artifacts/${encodeURIComponent(reference.id)}/anchor?download=true`); save(file.bytes, `${name}.anchors.json`) })
        section.append(node('p', 'Replay the retained design and baseline history with the matching Counterdex CPython 3.11 package. Native replay checks supported mathematical facts; browser download hashes establish byte integrity only.'), node('pre', `python3.11 -m counterdex replay-native ${name}.native.json --anchors ${name}.anchors.json`))
      }
    }
  }
  return { render, reset, pending: () => job && ['queued', 'running', 'cancel_requested'].includes(job.state), refresh: () => refresh(job.id) }
}
