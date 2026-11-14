import { setupSourceWorkflow } from './source-workflow.mjs'
import { setupAssistantWorkflow } from './assistant-workflow.mjs'
import { BeanApi, baselineAvailable, baselineExplanation, liveGeminiAvailable } from './api.mjs'
import { datasetBody, problemBody, planRequest } from './manual.mjs'
import { setupDesignWorkflow } from './design-workflow.mjs'
import { designAvailable } from './design.mjs'
import { bootstrapSharedSession } from './session.mjs'
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
export function setupWorkflow(getDraft, applyReviewedFields, { onConnectionChange = () => {} } = {}) {
  let api, capabilities, workspace = '', plan, approval, run, report, frozen, inputs, busy = false, pollTimer
  let connectionMode = 'local_owner'
  let connectionIdentity
  const fingerprint = () => JSON.stringify(getDraft()) // Edit detection only, never a semantic digest.
  const currentPlan = () => plan && frozen === fingerprint()
  const available = () => baselineAvailable(capabilities)
  const designs = setupDesignWorkflow({ context: () => ({ api, workspace, run, busy, available: designAvailable(capabilities) }), perform, button, node, exactRecord, save, openRun: async id => { await refreshRun(id); location.hash = 'investigations' } })
  const assistant = setupAssistantWorkflow({ context: () => ({ api, workspace, run, busy, capabilities }), button, node, exactRecord })
  const sources = setupSourceWorkflow({ context: () => ({ api, workspace, busy, capabilities }), applyReviewedFields, getDraft, button, node, exactRecord, useInputs: async materialized => {
    const prepared = await api.json(`/workspaces/${workspace}/plans`, planRequest(materialized.problem, getDraft().question.goal))
    inputs = materialized; plan = prepared; frozen = fingerprint(); approval = undefined
  } })
  function reset() { sources.reset(); assistant.reset(); clearTimeout(pollTimer); plan = approval = run = report = frozen = inputs = undefined; designs.reset() }
  function button(parent, label, action, disabled = false) {
    const b = node('button', label); b.type = 'button'; b.disabled = disabled || busy
    b.addEventListener('click', () => perform(action)); parent.append(b); return b
  }
  async function perform(action) {
    if (busy) return
    busy = true; byId('backend-error').hidden = true; render()
    try { await action() } catch (error) {
      byId('backend-error').textContent = error.message; byId('backend-error').hidden = false; byId('connection-panel').open = true
    } finally { busy = false; render() }
  }
  async function workspaces(selectFirst = false) {
    const list = await api.json('/workspaces')
    if (selectFirst && !workspace && list.length) workspace = list[0].id
    const select = byId('workspace-select'); select.replaceChildren(node('option', 'Choose workspace')); select.firstChild.value = ''
    for (const item of list) { const o = node('option', item.name); o.value = item.id; select.append(o) }
    select.value = workspace
  }
  async function refreshRun(id = byId('run-id').value.trim()) {
    const loaded = await api.json(`/runs/${encodeURIComponent(id)}`)
    if (loaded.workspace_id !== workspace) throw new Error('Select the run’s workspace before opening it.')
    const evidence = await Promise.all(loaded.scenarios.filter(s => s.result_id).map(s => api.json(`/records/${encodeURIComponent(s.result_id)}`)))
    run = { ...loaded, evidence }; report = undefined
  }
  function render() {
    Promise.resolve(onConnectionChange({ api, capabilities, workspaceId: workspace, mode: connectionMode, identityId: connectionIdentity })).catch(error => {
      byId('backend-error').textContent = error.message; byId('backend-error').hidden = false
    })
    const review = byId('backend-review'); review.replaceChildren(node('h3', 'Manual investigation plan'))
    byId('workspace-controls').hidden = !api
    for (const id of ['connect-form', 'new-workspace']) for (const el of byId(id).elements) el.disabled = busy
    byId('workspace-select').disabled = busy
    review.append(node('p', !api ? 'Investigation planning is unavailable. Connect to the local backend above.' : !workspace ? 'Choose a workspace above.' : available() ? 'Save reviewed inputs to prepare a baseline investigation. Counterdex will search and check these exact inputs. No model-provider calls are used.' : `Plan review is available. Baseline execution is unavailable: ${capabilities?.science?.reason || 'the configured runtime does not offer baseline discovery'}.`))
    button(review, 'Save inputs and prepare plan', async () => {
      const draft = getDraft(), snapshot = fingerprint()
      const datasetPayload = datasetBody(draft, draft.context)
      // Validate the question before creating any records.
      problemBody(draft, { id: '', digest: '' })
      const dataset = await api.json(`/workspaces/${workspace}/datasets`, datasetPayload)
      const problem = await api.json(`/workspaces/${workspace}/problems`, problemBody(draft, dataset))
      const prepared = await api.json(`/workspaces/${workspace}/plans`, planRequest(problem, draft.question.goal))
      plan = prepared; inputs = { dataset, problem }; frozen = snapshot; approval = undefined
    }, !api || !workspace)
    if (plan) {
      review.append(node('p', `Plan ${plan.id} · server digest ${plan.digest}`), node('h4', 'Question for this investigation'), node('p', plan.body.objective.question), node('p', plan.body.objective.success_criterion), node('p', 'One baseline; no optional scenario. Provider: none; no source transmission. Limits: 0 provider turns, 2 tool calls, 1 scientific reservation, 120 seconds. Design work requires a separate approval.'), exactRecord('Exact frozen dataset and problem', inputs), exactRecord('Exact frozen plan', plan))
      if (!currentPlan()) review.append(node('p', 'Draft changed. Prepare a new plan before approving or queueing.'))
      const label = node('label', ' I reviewed the exact frozen plan and approve only this scope.')
      const check = document.createElement('input'); check.type = 'checkbox'; check.id = 'approve-scope'; check.disabled = !currentPlan() || Boolean(approval) || busy
      label.prepend(check); review.append(label)
      const approve = button(review, approval ? 'Plan approved' : 'Approve reviewed plan', async () => {
        if (!currentPlan() || !check.checked) throw new Error('Review the current plan and check its approval box.')
        approval = await api.json(`/plans/${plan.id}/approvals`, { expected_plan_digest: plan.digest, expected_current_revision_id: plan.body.problem_id, accepted: true })
      }, true)
      check.addEventListener('change', () => { approve.disabled = !check.checked || busy || Boolean(approval) || !currentPlan() })
      if (approval) review.append(exactRecord('Approval receipt', approval))
      button(review, 'Queue approved manual run', async () => {
        capabilities = await api.json('/capabilities')
        if (!available() || !currentPlan() || !approval) throw new Error('Available baseline discovery and current explicit approval are required.')
        run = await api.json(`/plans/${plan.id}/runs`, { approval_id: approval.id, expected_plan_digest: plan.digest })
        byId('run-id').value = run.id
        report = undefined; location.hash = 'investigations'
      }, !available() || !approval || !currentPlan() || Boolean(run && run.plan_id === plan.id))
    }
    const investigations = byId('backend-investigations'), previousId = byId('run-id')?.value || run?.id || ''
    investigations.replaceChildren(node('h3', 'Persisted investigation'))
    const label = node('label', 'Run identifier'); label.className = 'stack'
    const input = document.createElement('input'); input.type = 'text'; input.id = 'run-id'; input.value = previousId
    label.append(input); investigations.append(label)
    button(investigations, 'Open or refresh run', () => refreshRun(), !api || !workspace)
    investigations.append(node('p', 'Keep the run identifier to reopen authenticated history. Pending runs update automatically. Refresh retrieves status; it never reruns a scenario.'))
    if (run) {
      const execution = node('p', `${run.id} · execution: ${run.state}`); execution.setAttribute('role', 'status')
      investigations.append(execution, exactRecord('Run and scenario records', run))
      if (run.error_code) investigations.append(node('p', `Execution stopped: ${run.error_code}. Any completed evidence remains below.`))
      for (const evidence of run.evidence ?? []) {
        const result = evidence.body.result
        investigations.append(node('h4', `Scenario ${evidence.body.scenario_id}`), node('p', baselineExplanation(result)), node('p', `Outcome: ${result.scientific_outcome}. Verification: ${result.verification}. Expected binding: ${result.expected_binding}. Replay: ${result.replay}. Reason: ${result.reason_code ?? 'none'}.`), node('p', 'These are persisted server states. This browser has not replayed or independently verified scientific evidence.'))
        if (result.candidates?.length) {
          const region = node('div', ''); region.className = 'table-region'; region.tabIndex = 0; region.setAttribute('role', 'region'); region.setAttribute('aria-label', 'Computed candidate parameters')
          const table = node('table', ''), head = node('thead', ''), headings = node('tr', ''), body = node('tbody', '')
          for (const title of ['Candidate', 'A (mg/L)', 'ke (1/h)', 'ka (1/h)', 'Verification']) { const th = node('th', title); th.scope = 'col'; headings.append(th) }
          head.append(headings)
          for (const candidate of result.candidates) {
            const row = node('tr', '')
            for (const value of [candidate.id, candidate.parameter_vector.A, candidate.parameter_vector.ke, candidate.parameter_vector.ka, candidate.verification]) row.append(node('td', value))
            body.append(row)
          }
          table.append(head, body); region.append(table); investigations.append(node('p', 'Computed candidate parameters are exact rational values. Each candidate remains bound to this reviewed problem.'), region)
        }
        if (['review', 'recheck'].includes(result.native_replay?.operation)) {
          investigations.append(node('h4', 'Follow-up candidate checks'), node('p', `Dataset origin: ${result.native_replay.dataset_origin ?? 'not supplied'}. This review retains the original candidate identities.`))
          const region = node('div', ''); region.className = 'table-region'; region.tabIndex = 0
          region.setAttribute('role', 'region'); region.setAttribute('aria-label', 'Follow-up candidate checks')
          const table = node('table', ''), head = node('thead', ''), headings = node('tr', ''), body = node('tbody', '')
          for (const title of ['Candidate', 'Recorded status', 'Violating observations', 'Reason']) {
            const th = node('th', title); th.scope = 'col'; headings.append(th)
          }
          head.append(headings)
          for (const candidate of result.candidate_results ?? []) {
            const state = { valid: 'Compatible', invalid: 'Excluded' }[candidate.verification] ?? 'Unresolved'
            const row = node('tr', '')
            for (const value of [candidate.candidate_id, state, (candidate.violating_observation_ids ?? []).join(', ') || 'None recorded', candidate.reason_code ?? 'None recorded']) row.append(node('td', value))
            body.append(row)
          }
          table.append(head, body); region.append(table); investigations.append(region)
          if (!result.candidate_results?.length) investigations.append(node('p', 'Candidate-specific feedback is unavailable in this record.'))
        }
        investigations.append(exactRecord('Exact evidence record', evidence))
        button(investigations, 'Download exact evidence record', async () => {
          const artifact = await api.download(`/artifacts/${evidence.id}`); save(artifact.bytes, `dr-bean-${evidence.id}.json`)
          byId('status').textContent = `Downloaded exact bytes. SHA-256 ${artifact.digest}. Byte integrity does not establish scientific validity.`
        })
        for (const reference of result.artifacts ?? []) {
          const name = `dr-bean-${reference.id}`
          investigations.append(node('h4', `Native scientific evidence ${reference.id}`), node('p', `${reference.byte_size} bytes · SHA-256 ${reference.sha256}`))
          button(investigations, 'Download native scientific evidence', async () => {
            const download = await api.download(`/artifacts/${encodeURIComponent(reference.id)}`, reference)
            save(download.bytes, `${name}.native.json`)
            byId('status').textContent = 'Native evidence downloaded. Download its separate replay anchors and use a prepared Counterdex interpreter to replay it.'
          })
          button(investigations, 'Download replay anchors', async () => {
            const download = await api.download(`/artifacts/${encodeURIComponent(reference.id)}/anchor?download=true`)
            save(download.bytes, `${name}.anchors.json`)
          })
          const instructions = node('details', '')
          const replayScope = result.replay === 'passed'
            ? 'Replay freshly checks the recorded candidate mathematically; it never reruns discovery.'
            : 'Replay validates evidence integrity and expected identities. It does not rerun discovery or establish the absence of a counterexample.'
          instructions.append(node('summary', 'Replay this evidence outside the browser'), node('p', `Use the matching prepared Counterdex package with CPython 3.11. Supply the separately downloaded anchors as the expected identities. ${replayScope} Browser download hashes establish byte integrity only.`), node('pre', `python3.11 -m counterdex replay-native ${name}.native.json --anchors ${name}.anchors.json`))
          investigations.append(instructions)
        }
      }
    }
    designs.render(investigations)
    assistant.render(investigations)
    investigations.append(node('p', 'Adding and checking a follow-up observation is a separate workflow. A design approval does not authorize a new observation or investigation.'))
    const sourcePanel = byId('backend-source-review'); sourcePanel.replaceChildren(); sources.render(sourcePanel)
    const reports = byId('backend-report'); reports.replaceChildren(node('h3', 'Reviewer snapshot'))
    reports.append(node('p', 'A report freezes the selected run, inputs and evidence inventory at creation. Download native scientific evidence and its separate replay anchors from Investigations. A report JSON byte hash is not scientific replay. Public reviewer sharing is unavailable.'))
    button(reports, 'Create report for selected run', async () => { report = await api.json(`/runs/${run.id}/reports`, {}) }, !api || !run)
    if (report) {
      reports.append(exactRecord('Report snapshot', report))
      button(reports, 'Download exact report JSON', async () => {
        const download = await api.download(`/reports/${report.id}/download`); save(download.bytes, `dr-bean-${report.id}.json`)
        byId('status').textContent = `Downloaded SHA-256 ${download.digest}. Browser replay: unsupported.`
      })
    }
    clearTimeout(pollTimer)
    const pendingRun = run && ['queued', 'running', 'cancel_requested'].includes(run.state)
    if (api && (pendingRun || designs.pending()) && !busy) {
      const id = run?.id
      pollTimer = setTimeout(() => perform(async () => {
        if (pendingRun) await refreshRun(id)
        if (designs.pending()) await designs.refresh()
      }), 1000)
    }
  }
  byId('connect-form').addEventListener('submit', event => {
    event.preventDefault(); perform(async () => {
      const candidate = new BeanApi(byId('bearer').value); byId('bearer').value = ''
      const caps = await candidate.json('/capabilities')
      if (caps.contract_version !== 'DB-SC-1' || caps.policy_version !== 'GF-2') throw new Error('Unsupported API contract or policy version.')
      await candidate.json('/workspaces') // Authenticate before retaining the client.
      api = candidate; capabilities = caps; connectionMode = 'local_owner'; connectionIdentity = 'local-owner:' + crypto.randomUUID(); workspace = ''; reset(); await workspaces()
      byId('connection-status').textContent = `Connected · DB-SC-1 / GF-2. Baseline discovery: ${available() ? 'available; each result is checked separately' : 'unavailable'}. ${liveGeminiAvailable(capabilities) ? `Gemini (${capabilities.gemini.model}) is enabled for separately approved image intake and explanations. Manual scientific runs make no model-provider calls.` : 'Gemini remains disabled. No model-provider calls are made by this manual workflow.'}`
    })
  })
  byId('disconnect').addEventListener('click', () => {
    api = capabilities = undefined; workspace = ''; reset(); byId('bearer').value = ''
    byId('connection-status').textContent = 'Disconnected. Investigation planning is unavailable.'; render()
  })
  byId('workspace-select').addEventListener('change', () => { workspace = byId('workspace-select').value; reset(); render() })
  byId('new-workspace').addEventListener('submit', event => {
    event.preventDefault(); perform(async () => {
      const created = await api.json('/workspaces', { name: byId('workspace-name').value }); workspace = created.id; reset(); await workspaces()
    })
  })
  render()
  // GPT1's bootstrap is the only automatic-authentication boundary. It returns
  // nonsecret metadata and a cookie transport; shared-demo is never a fallback.
  ;(async () => {
    let shared
    try {
      shared = await bootstrapSharedSession()
      if (!shared) return // The local owner boundary alone returns 404.
    } catch (error) {
      connectionMode = 'session_error'; byId('connect-form').hidden = true
      byId('connection-panel').open = true
      byId('connection-panel').querySelector('summary').textContent = 'Private workspace connection'
      byId('connection-panel').querySelector('p').textContent = 'The private browser session is unavailable. No owner credentials are requested here. Reload after the server is available.'
      byId('connection-status').textContent = 'The private browser session could not be established. Reload after the server is available.'
      byId('backend-error').textContent = error.message; byId('backend-error').hidden = false
      render(); return
    }
    byId('connect-form').hidden = true
    byId('connection-panel').querySelector('summary').textContent = 'Private workspace connection'
    byId('connection-panel').querySelector('p').textContent = 'Your browser has a private workspace. Gemini uses the server owner’s configuration and shared application allowance. No access token or Gemini key is entered here.'
    await perform(async () => {
      const candidate = shared.api
      const caps = await candidate.json('/capabilities')
      if (caps.contract_version !== 'DB-SC-1' || caps.policy_version !== 'GF-2') throw new Error('Unsupported shared server.')
      api = candidate; capabilities = caps; connectionMode = 'browser_session'
      connectionIdentity = 'browser-session:' + shared.session.workspace_id
      workspace = shared.session.workspace_id; reset(); await workspaces()
      byId('connection-status').textContent = 'Connected automatically to your private workspace. No API key or access token is needed.'
    })
  })()
  return render
}
