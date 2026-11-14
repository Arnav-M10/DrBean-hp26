import { setupSourceWorkflow } from './source-workflow.mjs'
import { setupAssistantWorkflow } from './assistant-workflow.mjs'
import { ApiError, baselineAvailable, baselineExplanation } from './api.mjs'
import { datasetBody, problemBody, planRequest } from './manual.mjs'
import { setupDesignWorkflow } from './design-workflow.mjs'
import { designAvailable, designCandidates } from './design.mjs'
import { interpretResult, keLine, concentrationChart, readable, toNumber, CANDIDATE_COLORS } from './result-view.mjs'
import { bootstrapSharedSession, readConnection } from './session.mjs'
const byId = id => document.getElementById(id)
function node(tag, text) { const n = document.createElement(tag); n.textContent = text; return n }
function exactRecord(title, record) {
  const d = node('details', ''); d.append(node('summary', title), node('pre', JSON.stringify(record, null, 2))); return d
}
function save(bytes, name) {
  const url = URL.createObjectURL(new Blob([bytes], { type: 'application/json' }))
  const a = document.createElement('a'); a.href = url; a.download = name; a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
export function setupWorkflow(getDraft, applyReviewedFields, { onConnectionChange = () => {}, onRender = () => {} } = {}) {
  let api, capabilities, workspace = '', plan, approval, run, report, frozen, inputs, busy = false, pollTimer
  let connectionMode = 'connecting'
  let connectionIdentity
  const fingerprint = () => JSON.stringify(getDraft()) // Edit detection only, never a semantic digest.
  const currentPlan = () => plan && frozen === fingerprint()
  const currentInputs = () => inputs && frozen === fingerprint()
  async function saveReviewedInputs() {
    if (!api || !workspace) throw new Error('Connect to a private workspace first.')
    if (inputs && frozen === fingerprint()) return inputs
    const draft = getDraft(), snapshot = fingerprint(), client = api, scope = workspace
    const datasetPayload = datasetBody(draft, draft.context)
    problemBody(draft, { id: '', digest: '' })
    const dataset = await client.json(`/workspaces/${scope}/datasets`, datasetPayload)
    const problem = await client.json(`/workspaces/${scope}/problems`, problemBody(draft, dataset))
    if (client !== api || scope !== workspace) throw new Error('The private workspace connection changed while saving inputs. Reopen the original workspace to inspect the saved records.')
    if (snapshot !== fingerprint()) throw new Error('The draft changed while saving. Review the current draft before continuing.')
    inputs = { dataset, problem }; frozen = snapshot; plan = approval = undefined
    return inputs
  }
  const available = () => baselineAvailable(capabilities)
  const designs = setupDesignWorkflow({ context: () => ({ api, workspace, run, busy, available: designAvailable(capabilities) }), perform, button, node, exactRecord, save, openRun: async id => {
    await refreshRun(id); byId('manual-investigations').open = true; location.hash = 'investigations'
  } })
  const assistant = setupAssistantWorkflow({ context: () => ({ api, workspace, run, busy, capabilities }), button, node, exactRecord })
  const sources = setupSourceWorkflow({ context: () => ({ api, workspace, busy, capabilities }), applyReviewedFields, getDraft, button, node, exactRecord, useInputs: async materialized => {
    const prepared = await api.json(`/workspaces/${workspace}/plans`, planRequest(materialized.problem, getDraft().question.goal))
    inputs = materialized; plan = prepared; frozen = fingerprint(); approval = undefined
  } })
  function reset() { sources.reset(); assistant.reset(); clearTimeout(pollTimer); plan = approval = run = report = frozen = inputs = undefined; designs.reset() }
  function button(parent, label, action, disabled = false) {
    const b = node('button', label); b.type = 'button'; b.disabled = disabled || busy || connectionMode !== 'browser_session'
    b.addEventListener('click', () => perform(action)); parent.append(b); return b
  }
  async function perform(action) {
    if (busy) return
    busy = true; byId('backend-error').hidden = true; render()
    try { await action() } catch (error) {
      byId('backend-error').textContent = error.message; byId('backend-error').hidden = false
      if (error.status === 401 || ['unreachable', 'uncertain'].includes(error.kind)) connectionFailure(error)
      else if (!api) byId('connection-panel').open = true
    } finally { busy = false; render() }
  }
  function renderWorkspaces(list) {
    const select = byId('workspace-select'); select.replaceChildren(node('option', 'Choose workspace')); select.firstChild.value = ''
    for (const item of list) { const o = node('option', item.name); o.value = item.id; select.append(o) }
    select.value = workspace
  }
  async function workspaces(selectFirst = false) {
    const list = await readConnection(api, '/workspaces')
    if (selectFirst && !workspace && list.length) workspace = list[0].id
    renderWorkspaces(list)
  }
  async function refreshRun(id = byId('run-id').value.trim()) {
    const loaded = await api.json(`/runs/${encodeURIComponent(id)}`)
    if (loaded.workspace_id !== workspace) throw new Error('Select the run’s workspace before opening it.')
    const evidence = await Promise.all(loaded.scenarios.filter(s => s.result_id).map(s => api.json(`/records/${encodeURIComponent(s.result_id)}`)))
    // Read-only context for the result explanation and chart; a failure only hides the chart.
    let inputsRecords = run?.id === loaded.id ? run.inputs : undefined
    if (!inputsRecords) {
      try {
        const planRecord = await api.json(`/records/${encodeURIComponent(loaded.plan_id)}`)
        const problem = await api.json(`/records/${encodeURIComponent(planRecord.body.problem_id)}`)
        const dataset = await api.json(`/records/${encodeURIComponent(problem.body.dataset_id)}`)
        inputsRecords = { plan: planRecord, problem, dataset }
      } catch { inputsRecords = undefined }
    }
    run = { ...loaded, evidence, inputs: inputsRecords }; report = undefined
  }
  const RUN_STATES = { queued: ['run', 'Waiting to start'], running: ['run', 'Running'], cancel_requested: ['wait', 'Stopping'], completed: ['ok', 'Finished'], failed: ['bad', 'Failed'], cancelled: ['off', 'Cancelled'], interrupted: ['bad', 'Interrupted'] }
  const chip = (kind, text) => { const item = node('span', text); item.className = `state ${kind}`; return item }
  const para = (text, className) => { const item = node('p', text); if (className) item.className = className; return item }
  const link = (text, href, className) => { const item = node('a', text); item.href = href; if (className) item.className = className; return item }
  const technical = (title, ...children) => { const item = node('details', ''); item.className = 'technical'; item.append(node('summary', title), ...children); return item }
  function definitions(pairs) {
    const list = node('dl', ''); list.className = 'facts'
    for (const [term, value] of pairs) { if (!value) continue; const row = node('div', ''); const dd = node('dd', ''); dd.append(value); row.append(node('dt', term), dd); list.append(row) }
    return list
  }
  function renderReview() {
    const review = byId('backend-review'); review.replaceChildren(node('h2', 'Manual Counterdex check'))
    if (!api) review.append(para('Investigation planning is unavailable until your private workspace is ready. Check the connection status above; you can still prepare and download your draft.', 'note wait'))
    else if (!workspace) review.append(para('Choose or create a workspace in the connection panel at the top of this page.', 'note wait'))
    else if (!available()) review.append(para('This server cannot run the manual Counterdex check right now.', 'note wait'))
    review.append(node('h3', '1. Freeze these inputs'), para('Saves the measurements and claim on the server exactly as shown above and prepares a plan for one check. Nothing runs yet. No language model is used.'))
    button(review, 'Save inputs and prepare plan', async () => {
      const goal = getDraft().question.goal, snapshot = fingerprint()
      const reviewed = await saveReviewedInputs()
      const prepared = await api.json(`/workspaces/${workspace}/plans`, planRequest(reviewed.problem, goal))
      if (!currentInputs() || snapshot !== fingerprint()) throw new Error('The draft changed while preparing this plan. Review the current inputs and prepare a new plan.')
      plan = prepared; approval = undefined
    }, !api || !workspace)
    if (!plan) return
    if (!currentPlan()) review.append(para('Draft changed since this plan was saved. Choose Save inputs and prepare plan again before approving.', 'note wait'))
    const budget = plan.body.budget ?? {}, provider = plan.body.provider_disclosure?.provider
    review.append(node('h3', '2. Approve the check'), para('Read exactly what this approval allows. It covers this plan and nothing else.'))
    review.append(definitions([
      ['Question', plan.body.objective.question],
      ['What counts as an answer', plan.body.objective.success_criterion],
      ['What will run', 'One baseline check of the frozen inputs by the Counterdex checker.'],
      ['Limits', `At most ${budget.tool_calls ?? '—'} tool calls, ${budget.scientific_reservations ?? '—'} checker run and ${budget.wall_seconds ?? '—'} seconds.`],
      ['AI involvement', provider === 'none' ? 'None. No language model is called and nothing is sent to an AI provider.' : `Provider ${provider}. Review the technical record.`],
      ['Not included', 'Designing a next measurement. That needs its own approval later.'],
    ]))
    review.append(technical(`Technical record for plan ${plan.id}`, para(`Server digest ${plan.digest}`, 'tech'), exactRecord('Exact frozen dataset and problem', inputs), exactRecord('Exact frozen plan', plan)))
    const label = node('label', ' I reviewed these exact inputs and approve only this check and its limits.')
    const check = document.createElement('input'); check.type = 'checkbox'; check.id = 'approve-scope'; check.disabled = !currentPlan() || Boolean(approval) || busy
    label.prepend(check); review.append(label)
    const approve = button(review, approval ? 'Plan approved' : 'Approve reviewed plan', async () => {
      if (!currentPlan() || !check.checked) throw new Error('Review the current plan and check its approval box.')
      approval = await api.json(`/plans/${plan.id}/approvals`, { expected_plan_digest: plan.digest, expected_current_revision_id: plan.body.problem_id, accepted: true })
    }, true)
    check.addEventListener('change', () => { approve.disabled = !check.checked || busy || Boolean(approval) || !currentPlan() })
    if (approval) review.append(para('Approved. Changing the draft voids this approval.', 'note ok'), technical('Approval receipt', exactRecord('Approval receipt', approval)))
    review.append(node('h3', '3. Start the check'), para('Queues the approved check on the server and takes you to Investigate to follow it. The same approval cannot start a second run.'))
    button(review, 'Queue approved manual run', async () => {
      capabilities = await api.json('/capabilities')
      if (!available() || !currentPlan() || !approval) throw new Error('Available baseline discovery and current explicit approval are required.')
      run = await api.json(`/plans/${plan.id}/runs`, { approval_id: approval.id, expected_plan_digest: plan.digest })
      byId('run-id').value = run.id
      byId('manual-investigations').open = true
      report = undefined; location.hash = 'investigations'
    }, !available() || !approval || !currentPlan() || Boolean(run && run.plan_id === plan.id))
    if (run && run.plan_id === plan.id) review.append(para('', 'fine'), link('This check has started. Follow it on Investigate.', '#investigations'))
  }
  function renderInvestigation() {
    const investigations = byId('backend-investigations'), previousId = byId('run-id')?.value || run?.id || ''
    investigations.replaceChildren(node('h2', 'Current or reopened check'))
    if (!run) investigations.append(para('Open a saved check below, or prepare a manual check from Review inputs.', 'note'))
    else {
      const [kind, label] = RUN_STATES[run.state] ?? ['off', run.state]
      const head = node('div', ''); head.className = 'actions'; head.append(chip(kind, label), para(run.plan_id === plan?.id ? 'The check you approved on Review' : 'A reopened check', 'meta'))
      investigations.append(head)
      const timeline = node('ol', ''); timeline.className = 'timeline'
      const step = (text, cls) => { const item = node('li', text); item.className = cls; timeline.append(item) }
      step('Inputs frozen on the server', 'done'); step('Check approved by you', 'done')
      step(run.state === 'completed' ? 'Counterdex check finished' : run.state === 'running' ? 'Counterdex check running' : run.state === 'queued' ? 'Counterdex check waiting for a worker' : `Counterdex check ${label.toLowerCase()}`, run.state === 'completed' ? 'done' : ['failed', 'interrupted', 'cancelled'].includes(run.state) ? 'failed' : '')
      step(run.evidence?.length ? `Evidence recorded (${run.evidence.length} ${run.evidence.length === 1 ? 'record' : 'records'})` : 'Evidence not recorded yet', run.evidence?.length ? 'done' : '')
      investigations.append(timeline)
      if (run.error_code) investigations.append(para(`The check stopped: ${run.error_code}. Any completed evidence is kept. Review the inputs and start a new check.`, 'note bad'))
      if (run.evidence?.length) {
        const callout = node('div', ''); callout.className = 'callout primary'
        callout.append(para('The check finished and recorded evidence.'), link('View results', '#result', 'button'))
        investigations.append(callout)
      } else if (['queued', 'running', 'cancel_requested'].includes(run.state)) investigations.append(para('This page updates by itself about once a second. Leaving the page does not stop the check.', 'fine'))
      const execution = node('p', `${run.id} · execution: ${run.state}`); execution.setAttribute('role', 'status'); execution.className = 'tech'
      investigations.append(execution, technical('Run and scenario records', exactRecord('Run and scenario records', { ...run, evidence: undefined, inputs: undefined })))
    }
    investigations.append(node('h3', 'Reopen a saved check'))
    const label = node('label', 'Run identifier'); label.className = 'stack'
    const input = document.createElement('input'); input.type = 'text'; input.id = 'run-id'; input.value = previousId; input.spellcheck = false
    label.append(input); investigations.append(label)
    button(investigations, 'Open or refresh run', () => refreshRun(), !api || !workspace)
    investigations.append(para('Keep the run identifier to reopen this check later from the same workspace. Refreshing only reads its status; it never runs the check again.', 'fine'))
  }
  function renderEvidence(parent, evidence) {
    const result = evidence.body.result, meaning = interpretResult(result)
    const problem = run.inputs?.problem?.body, dataset = run.inputs?.dataset?.body, question = run.inputs?.plan?.body?.objective?.question
    const card = node('article', ''); card.className = 'verdict'; card.dataset.tone = meaning.tone; parent.append(card)
    const top = node('div', ''); top.className = 'actions'; top.append(chip(...meaning.state), para(`Scenario ${evidence.body.scenario_id}`, 'meta')); card.append(top)
    if (question) card.append(para(`You asked: ${question}`, 'meta'))
    card.append(para(meaning.statement, 'verdict-statement'))
    const candidates = (result.candidates ?? []).filter(c => c.parameter_vector)
    const target = problem?.target, inClaim = ke => target && toNumber(ke) >= toNumber(target.lower) && toNumber(ke) <= toNumber(target.upper)
    const drawn = candidates.slice(0, 4).map((c, i) => ({ id: c.id, short: `Candidate ${i + 1}`, color: CANDIDATE_COLORS[i], A: toNumber(c.parameter_vector.A), ke: toNumber(c.parameter_vector.ke), ka: toNumber(c.parameter_vector.ka), outside: target ? !inClaim(c.parameter_vector.ke) : false, dash: i % 2 === 1 }))
    if (problem && drawn.length) {
      const line = keLine({ domain: problem.domain.ke, target, candidates: drawn })
      if (line) {
        const figure = node('figure', ''); figure.className = 'chart'
        figure.append(line, node('figcaption', `Shaded band: the claimed range, ke from ${readable(target.lower)} to ${readable(target.upper)} per hour. Each dot is a checked candidate's ke. The axis spans the ke search range you set (${readable(problem.domain.ke.lower)}–${readable(problem.domain.ke.upper)} per hour).`))
        card.append(figure)
      }
    }
    if (dataset?.rows?.length) {
      const rows = dataset.rows.map(row => ({ t: toNumber(row.time), c: toNumber(row.concentration), e: toNumber(row.hard_allowance), included: row.included }))
      const chart = concentrationChart({ rows, curves: drawn.map(c => ({ ...c, until: 0 })) })
      if (chart) {
        const figure = node('figure', ''); figure.className = 'chart'; figure.append(chart)
        const legend = node('ul', ''); legend.className = 'legend'
        const key = (text, color, cls) => { const item = node('li', ''); const sw = node('span', ''); sw.className = `swatch ${cls}`; sw.style.color = color; item.append(sw, text); legend.append(item) }
        key('Your reading ± allowance', '#15202a', 'dot')
        drawn.forEach(c => key(`${c.short}: ke ≈ ${readable(c.ke)} h⁻¹ (${c.outside ? 'outside' : 'inside'} the claim)`, c.color, c.dash ? 'dash' : ''))
        figure.append(legend, node('figcaption', 'Dots are your included readings and the vertical bars are their allowances. Each curve is the model drawn with one candidate\'s parameter values; a curve fits when it passes through every bar. The drawing uses decimal approximations; exact values are in the technical details.'))
        card.append(figure)
      }
    }
    const domain = problem?.domain
    card.append(definitions([
      ['What supports this', result.verification === 'valid' && result.replay === 'passed' ? `${candidates.length ? `${candidates.length} candidate${candidates.length === 1 ? ' was' : 's were'} checked` : 'The result was checked'} with exact arithmetic against every included reading. The evidence matches your saved inputs and can be replayed outside the browser.` : `Checker verification: ${result.verification}. Matches saved inputs: ${result.expected_binding}. Replay: ${result.replay}.`],
      ['It assumes', domain ? `The two-rate model; your allowances; ka above ke; and the search limits A ${readable(domain.A.lower)}–${readable(domain.A.upper)} mg/L, ke ${readable(domain.ke.lower)}–${readable(domain.ke.upper)} h⁻¹, ka ${readable(domain.ka.lower)}–${readable(domain.ka.upper)} h⁻¹.` : 'The reviewed model, allowances and search limits saved with this check.'],
      ['Still uncertain', meaning.uncertain],
    ]))
    const nextStep = node('div', ''); nextStep.className = 'callout primary'
    if (designCandidates(evidence).length >= 2) nextStep.append(para('Two different candidates both fit your readings. A new reading at a well-chosen time could rule one out.'), link('Compare measurement times', '#next', 'button'))
    else if (meaning.tone === 'none') nextStep.append(para('To probe further, widen the search limits or revisit the allowances on Check inputs, then run a new check. The earlier evidence is kept.'), link('Review inputs', '#inputs', 'button secondary'))
    else nextStep.append(para('Take this result away as a report, or revise the inputs and run a new check.'), link('Go to report', '#report', 'button secondary'))
    card.append(nextStep)
    if (candidates.length) {
      const region = node('div', ''); region.className = 'table-region'; region.tabIndex = 0; region.setAttribute('role', 'region'); region.setAttribute('aria-label', 'Computed candidate parameters')
      const table = node('table', ''), head = node('thead', ''), headings = node('tr', ''), body = node('tbody', '')
      for (const title of ['Candidate', 'A (mg/L)', 'ke (h⁻¹)', 'ka (h⁻¹)', 'ke vs claim', 'Checked']) { const th = node('th', title); th.scope = 'col'; headings.append(th) }
      head.append(headings)
      candidates.forEach((candidate, index) => {
        const row = node('tr', ''), v = candidate.parameter_vector
        const name = node('th', `Candidate ${index + 1}`); name.scope = 'row'; row.append(name)
        for (const value of [v.A, v.ke, v.ka]) { const td = node('td', readable(value, 4)); td.title = `Exact: ${value}`; row.append(td) }
        row.append(node('td', target ? (inClaim(v.ke) ? 'Inside' : 'Outside') : '—'), node('td', candidate.verification === 'valid' ? 'Yes' : candidate.verification))
        body.append(row)
      })
      table.append(head, body); region.append(table)
      parent.append(node('h3', 'Candidates'), para('Values are rounded for reading. Each candidate is tied to the exact inputs saved for this check.', 'fine'), region)
    }
    if (['review', 'recheck'].includes(result.native_replay?.operation)) {
      parent.append(node('h3', 'Follow-up candidate checks'), para(`Dataset origin: ${result.native_replay.dataset_origin ?? 'not supplied'}. This review retains the original candidate identities.`))
      const region = node('div', ''); region.className = 'table-region'; region.tabIndex = 0
      region.setAttribute('role', 'region'); region.setAttribute('aria-label', 'Follow-up candidate checks')
      const table = node('table', ''), head = node('thead', ''), headings = node('tr', ''), body = node('tbody', '')
      for (const title of ['Candidate', 'Status after the new reading', 'Readings it misses', 'Reason']) { const th = node('th', title); th.scope = 'col'; headings.append(th) }
      head.append(headings)
      for (const candidate of result.candidate_results ?? []) {
        const state = { valid: 'Still fits', invalid: 'Ruled out' }[candidate.verification] ?? 'Unresolved'
        const row = node('tr', '')
        for (const value of [candidate.candidate_id, state, (candidate.violating_observation_ids ?? []).join(', ') || 'None recorded', candidate.reason_code ?? 'None recorded']) row.append(node('td', value))
        body.append(row)
      }
      table.append(head, body); region.append(table); parent.append(region)
      if (!result.candidate_results?.length) parent.append(para('Candidate-specific feedback is unavailable in this record.', 'note'))
    }
    if (result.artifacts?.length) {
      parent.append(node('h3', 'Download evidence'), para('The native evidence file holds the checker\'s exact working. The replay anchors record which inputs and run it belongs to. Together they let anyone re-run the check with the Counterdex command-line tool.'))
      for (const reference of result.artifacts ?? []) {
        const name = `dr-bean-${reference.id}`
        const row = node('div', ''); row.className = 'actions'; parent.append(row)
        button(row, 'Download native scientific evidence', async () => {
          const download = await api.download(`/artifacts/${encodeURIComponent(reference.id)}`, reference)
          save(download.bytes, `${name}.native.json`)
          byId('status').textContent = 'Native evidence downloaded. Download its separate replay anchors and use a prepared Counterdex interpreter to replay it.'
        })
        button(row, 'Download replay anchors', async () => {
          const download = await api.download(`/artifacts/${encodeURIComponent(reference.id)}/anchor?download=true`)
          save(download.bytes, `${name}.anchors.json`)
        }).className = 'secondary'
        const replayScope = result.replay === 'passed'
          ? 'Replay freshly checks the recorded candidate mathematically; it never reruns discovery.'
          : 'Replay validates evidence integrity and expected identities. It does not rerun discovery or establish the absence of a counterexample.'
        parent.append(technical('Replay this evidence outside the browser', para(`${reference.byte_size.toLocaleString()} bytes, SHA-256 ${reference.sha256}`, 'tech'), para(`Use the matching prepared Counterdex package with CPython 3.11. Supply the separately downloaded anchors as the expected identities. ${replayScope} A matching download hash shows the bytes are intact, not that the mathematics is valid.`), node('pre', `python3.11 -m counterdex replay-native ${name}.native.json --anchors ${name}.anchors.json`)))
      }
    }
    const details = technical('Technical details: states and exact records',
      para(`Outcome: ${result.scientific_outcome}. Verification: ${result.verification}. Expected binding: ${result.expected_binding}. Replay: ${result.replay}. Reason: ${result.reason_code ?? 'none'}.`, 'tech'),
      para(baselineExplanation(result)),
      para('These are persisted server states. This browser has not replayed or independently verified scientific evidence.', 'fine'),
      exactRecord('Exact evidence record', evidence))
    parent.append(details)
    button(details, 'Download exact evidence record', async () => {
      const artifact = await api.download(`/artifacts/${evidence.id}`); save(artifact.bytes, `dr-bean-${evidence.id}.json`)
      byId('status').textContent = `Downloaded exact bytes. SHA-256 ${artifact.digest}. Byte integrity does not establish scientific validity.`
    }).className = 'secondary'
  }
  function renderResults() {
    const results = byId('backend-results'); results.replaceChildren()
    if (!run) {
      const empty = node('div', ''); empty.className = 'block'
      empty.append(node('h2', 'No result yet'), para('Results appear here after an approved check finishes. Start one from Check inputs, or reopen a saved check on Investigate.'), link('Go to Investigate', '#investigations'))
      results.append(empty); return
    }
    if (!run.evidence?.length) {
      const [kind, label] = RUN_STATES[run.state] ?? ['off', run.state]
      const waiting = node('div', ''); waiting.className = 'block'
      waiting.append(chip(kind, label), para(['queued', 'running', 'cancel_requested'].includes(run.state) ? 'The check has not recorded evidence yet. This page fills in when it does.' : `This check ended without evidence${run.error_code ? ` (${run.error_code})` : ''}. No conclusion can be drawn from it.`), link('Follow it on Investigate', '#investigations'))
      results.append(waiting); return
    }
    for (const evidence of run.evidence) renderEvidence(results, evidence)
  }
  function renderNext() {
    const next = byId('backend-next'); next.replaceChildren()
    designs.render(next)
    next.append(para('Adding and checking a new reading is a separate step that appears after a checked comparison. Approving a comparison does not authorise a new reading or a new check.', 'fine'))
  }
  function renderReport() {
    const reports = byId('backend-report'); reports.replaceChildren()
    if (!run) { reports.append(para('Open a finished check first. A report captures one check exactly as it was.', 'note')) }
    else {
      const evidence = run.evidence?.[0], meaning = evidence ? interpretResult(evidence.body.result) : null, problem = run.inputs?.problem?.body, dataset = run.inputs?.dataset?.body
      reports.append(definitions([
        ['Question', run.inputs?.plan?.body?.objective?.question],
        ['Finding', meaning?.statement ?? 'No evidence recorded yet.'],
        ['Inputs', dataset ? `${dataset.rows.filter(r => r.included).length} included readings from ${dataset.experiment_id} (${dataset.origin}); claim ke ${problem ? `${readable(problem.target.lower)}–${readable(problem.target.upper)} h⁻¹` : 'as saved'}.` : ''],
        ['Limits of this finding', 'It holds only for the two-rate model, these allowances and these search limits. It is not clinical guidance and does not identify the true parameters.'],
      ]))
    }
    reports.append(para('A report freezes the selected check, its inputs and its list of evidence at the moment you create it, as a JSON file for reviewers. Public sharing is not available. Native evidence and replay anchors are downloaded from the Result step.', 'fine'))
    const row = node('div', ''); row.className = 'actions'; reports.append(row)
    button(row, 'Create report for selected run', async () => { report = await api.json(`/runs/${run.id}/reports`, {}) }, !api || !run)
    if (report) {
      button(row, 'Download exact report JSON', async () => {
        const download = await api.download(`/reports/${report.id}/download`); save(download.bytes, `dr-bean-${report.id}.json`)
        byId('status').textContent = `Downloaded SHA-256 ${download.digest}. Browser replay: unsupported.`
      }).className = 'secondary'
      reports.append(technical('Report snapshot', exactRecord('Report snapshot', report)))
    }
    if (run?.evidence?.length) reports.append(link('Go to evidence downloads', '#result'))
  }
  function render() {
    Promise.resolve(onConnectionChange({ api, capabilities, workspaceId: workspace, mode: api ? 'browser_session' : connectionMode, identityId: connectionIdentity, saveReviewedInputs })).catch(error => {
      byId('backend-error').textContent = error.message; byId('backend-error').hidden = false
    })
    byId('workspace-controls').hidden = !api || connectionMode !== 'browser_session'
    for (const el of byId('new-workspace').elements) el.disabled = busy || connectionMode !== 'browser_session'
    byId('connection-retry').disabled = busy
    byId('connection-start-new').disabled = busy
    byId('workspace-select').disabled = busy
    renderReview(); renderInvestigation(); renderResults(); renderNext(); renderReport()
    const sourcePanel = byId('backend-source-review'); sourcePanel.replaceChildren(); sources.render(sourcePanel)
    assistant.render(byId('backend-assistant'))
    clearTimeout(pollTimer)
    const pendingRun = run && ['queued', 'running', 'cancel_requested'].includes(run.state)
    if (api && connectionMode === 'browser_session' && (pendingRun || designs.pending()) && !busy) {
      const id = run?.id
      pollTimer = setTimeout(() => perform(async () => {
        if (pendingRun) await refreshRun(id)
        if (designs.pending()) await designs.refresh()
      }), 1000)
    }
    onRender()
  }
  function status() {
    return { connected: Boolean(api) && connectionMode === 'browser_session', workspace, mode: connectionMode, busy, inputsCurrent: Boolean(currentInputs()), planned: Boolean(plan), planCurrent: Boolean(currentPlan()), approved: Boolean(approval && currentPlan()),
      run: run ? { id: run.id, state: run.state, evidence: run.evidence?.length ?? 0, tone: run.evidence?.[0] ? interpretResult(run.evidence[0].body.result).tone : null, pairReady: (run.evidence ?? []).some(e => designCandidates(e).length >= 2) } : null,
      designPending: Boolean(designs.pending()), report: Boolean(report) }
  }
  function connectionFailure(error) {
    connectionMode = 'session_error'
    const message = error.mayStartNew || error.code === 'session_storage_unavailable' ? error.message
      : error.kind === 'uncertain' ? 'The last request may have been accepted. Retry connection to check access, then reconcile that same operation; nothing is resubmitted automatically.'
      : error.status === 429 ? 'The server cannot open another private session right now. Retry later; earlier research is retained.'
      : error.status === 404 ? 'Private access is unavailable on this server. Ask the server owner to check its setup, then retry.'
      : error.kind === 'unreachable' || [502, 503, 504].includes(error.status) ? 'The server is unavailable or still starting. Retry connection when it is ready. Your draft stays in this tab.'
      : error.status === 401 ? 'This session is no longer available. Retry connection to check the supported recovery options.'
      : error.message || 'The private workspace could not be opened. Retry connection.'
    byId('connection-status').textContent = message
    byId('connection-retry').hidden = false
    byId('connection-start-new').hidden = error.mayStartNew !== true
    byId('connection-panel').open = true
  }
  async function connectPrivate(startNew = false) {
    if (busy) return
    busy = true; connectionMode = 'connecting'
    byId('connection-status').textContent = 'Connecting to your private workspace…'
    byId('backend-error').hidden = true
    byId('connection-start-new').hidden = true
    render()
    try {
      const shared = await bootstrapSharedSession(undefined, { startNew })
      const identity = 'browser-session:' + shared.session.workspace_id
      if (connectionIdentity && identity !== connectionIdentity && !startNew) {
        throw new ApiError('session_recovery', 'The browser is now using a different private session. Choose Start a new private workspace to switch this tab. Previous research and pending operations will not be transferred.', { mayStartNew: true })
      }
      // Reuse the same transport on recovery: its frozen operation keys and
      // the workflow's existing records must survive a transient read failure.
      const sameIdentity = connectionIdentity === identity
      const candidate = sameIdentity && api ? api : shared.api
      const caps = await readConnection(candidate, '/capabilities')
      if (caps.contract_version !== 'DB-SC-1' || caps.policy_version !== 'GF-2') throw new Error('This server uses an unsupported application contract.')
      const list = await readConnection(candidate, '/workspaces')
      if (!Array.isArray(list) || !list.some(item => item.id === shared.session.workspace_id)) throw new Error('The private workspace could not be confirmed. Retry connection.')
      const selected = sameIdentity && list.some(item => item.id === workspace) ? workspace : shared.session.workspace_id
      if (!sameIdentity) reset()
      api = candidate; capabilities = caps; workspace = selected; connectionIdentity = identity
      candidate.setConnectionFailureHandler(error => {
        // Child controllers share this transport. A late response from an old
        // identity must not change the current connection or resubmit its work.
        if (api !== candidate || connectionIdentity !== identity || connectionMode === 'connecting') return
        connectionFailure(error)
        render()
      })
      connectionMode = 'browser_session'; renderWorkspaces(list)
      byId('connection-status').textContent = 'Ready. Your private workspace is open.'
      byId('connection-retry').hidden = true
      byId('connection-start-new').hidden = true
      byId('connection-panel').open = false
    } catch (error) {
      connectionFailure(error)
    } finally { busy = false; render() }
  }
  byId('connection-retry').addEventListener('click', () => connectPrivate())
  byId('connection-start-new').addEventListener('click', () => connectPrivate(true))
  byId('workspace-select').addEventListener('change', () => { workspace = byId('workspace-select').value; reset(); render() })
  byId('new-workspace').addEventListener('submit', event => {
    event.preventDefault(); perform(async () => {
      const created = await api.json('/workspaces', { name: byId('workspace-name').value }); workspace = created.id; reset(); await workspaces()
    })
  })
  render.status = status
  render()
  // The only automatic operation is private connection. Every scientific,
  // consent and provider operation still needs its own existing explicit action.
  void connectPrivate()
  return render
}
