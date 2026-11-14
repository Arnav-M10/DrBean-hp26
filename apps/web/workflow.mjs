import { BeanApi, qualifiedScience } from './api.mjs'
import { datasetBody, problemBody, planRequest } from './manual.mjs'
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
export function setupWorkflow(getDraft) {
  let api, capabilities, workspace = '', plan, approval, run, report, frozen, inputs, busy = false
  const fingerprint = () => JSON.stringify(getDraft()) // Edit detection only, never a semantic digest.
  const currentPlan = () => plan && frozen === fingerprint()
  const qualified = () => qualifiedScience(capabilities)
  function reset() { plan = approval = run = report = frozen = inputs = undefined }
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
  async function workspaces() {
    const list = await api.json('/workspaces')
    const select = byId('workspace-select'); select.replaceChildren(node('option', 'Choose workspace')); select.firstChild.value = ''
    for (const item of list) { const o = node('option', item.name); o.value = item.id; select.append(o) }
    select.value = workspace
  }
  async function refreshRun() {
    const loaded = await api.json(`/runs/${encodeURIComponent(byId('run-id').value.trim())}`)
    if (loaded.workspace_id !== workspace) throw new Error('Select the run’s workspace before opening it.')
    const evidence = await Promise.all(loaded.scenarios.filter(s => s.result_id).map(s => api.json(`/records/${encodeURIComponent(s.result_id)}`)))
    run = { ...loaded, evidence }; report = undefined
  }
  function render() {
    const review = byId('backend-review'); review.replaceChildren(node('h3', 'Manual investigation plan'))
    byId('workspace-controls').hidden = !api
    for (const id of ['connect-form', 'new-workspace']) for (const el of byId(id).elements) el.disabled = busy
    byId('workspace-select').disabled = busy
    review.append(node('p', !api ? 'Investigation planning is unavailable. Connect to the local backend above.' : !workspace ? 'Choose a workspace above.' : qualified() ? 'Save reviewed inputs to prepare a provider-free baseline plan.' : 'Plan review is available. Scientific execution is unavailable: Owner 02 must connect and qualify Owner 01’s Counterdex adapter in the API and worker.'))
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
      review.append(node('p', `Plan ${plan.id} · server digest ${plan.digest}`), node('p', `Reviewed objective: ${plan.body.objective?.question ?? 'none recorded'}`), node('p', 'One baseline; no optional scenario. Provider: none; no source transmission. Limits: 0 provider turns, 2 tool calls, 1 scientific reservation, 120 seconds. Design work requires a separate approval.'), exactRecord('Exact frozen dataset and problem', inputs), exactRecord('Exact frozen plan', plan))
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
        if (!qualified() || !currentPlan() || !approval) throw new Error('Qualified adapter and current explicit approval required.')
        run = await api.json(`/plans/${plan.id}/runs`, { approval_id: approval.id, expected_plan_digest: plan.digest })
        report = undefined; location.hash = 'investigations'
      }, !qualified() || !approval || !currentPlan() || Boolean(run && run.plan_id === plan.id))
    }
    const investigations = byId('backend-investigations'), previousId = byId('run-id')?.value || run?.id || ''
    investigations.replaceChildren(node('h3', 'Persisted investigation'))
    const label = node('label', 'Run identifier'); label.className = 'stack'
    const input = document.createElement('input'); input.type = 'text'; input.id = 'run-id'; input.value = previousId
    label.append(input); investigations.append(label)
    button(investigations, 'Open or refresh run', refreshRun, !api || !workspace)
    investigations.append(node('p', 'Use a saved run identifier to reopen authenticated history. Refresh retrieves status; it never reruns a scenario.'))
    if (run) {
      investigations.append(node('p', `${run.id} · execution: ${run.state}`), exactRecord('Run and scenario records', run))
      for (const evidence of run.evidence ?? []) {
        const result = evidence.body.result
        investigations.append(node('h4', `Scenario ${evidence.body.scenario_id}`), node('p', `Outcome: ${result.scientific_outcome}. Verification: ${result.verification}. Expected binding: ${result.expected_binding}. Replay: ${result.replay}. Reason: ${result.reason_code ?? 'none'}.`), node('p', 'These are persisted server states. This browser has not replayed or independently verified scientific evidence.'), exactRecord('Exact evidence record', evidence))
        button(investigations, 'Download exact evidence record', async () => {
          const artifact = await api.download(`/artifacts/${evidence.id}`); save(artifact.bytes, `dr-bean-${evidence.id}.json`)
          byId('status').textContent = `Downloaded exact bytes. SHA-256 ${artifact.digest}. Byte integrity does not establish scientific validity.`
        })
      }
    }
    investigations.append(node('p', 'Next-measurement workflow unavailable: no adopted qualified design adapter is connected. Owner 02 must adopt Owner 01’s projection and artifact mapping; suggestions require their own reviewed plan and approval.'))
    const reports = byId('backend-report'); reports.replaceChildren(node('h3', 'Reviewer snapshot'))
    reports.append(node('p', 'A report freezes the selected run, inputs, evidence and design records at creation. A JSON byte hash is not scientific replay. Public reviewer sharing and portable native bundles are unavailable.'))
    button(reports, 'Create report for selected run', async () => { report = await api.json(`/runs/${run.id}/reports`, {}) }, !api || !run)
    if (report) {
      reports.append(exactRecord('Report snapshot', report))
      button(reports, 'Download exact report JSON', async () => {
        const download = await api.download(`/reports/${report.id}/download`); save(download.bytes, `dr-bean-${report.id}.json`)
        byId('status').textContent = `Downloaded SHA-256 ${download.digest}. Browser replay: unsupported.`
      })
    }
  }
  byId('connect-form').addEventListener('submit', event => {
    event.preventDefault(); perform(async () => {
      const candidate = new BeanApi(byId('bearer').value); byId('bearer').value = ''
      const caps = await candidate.json('/capabilities')
      if (caps.contract_version !== 'DB-SC-1' || caps.policy_version !== 'GF-2') throw new Error('Unsupported API contract or policy version.')
      await candidate.json('/workspaces') // Authenticate before retaining the client.
      api = candidate; capabilities = caps; workspace = ''; reset(); await workspaces()
      byId('connection-status').textContent = `Connected · DB-SC-1 / GF-2. Science: ${qualified() ? 'qualified by server' : 'unavailable'}. Gemini intake and follow-up: unavailable in this frontend; live service qualification and separate payload consent are required.`
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
  render(); return render
}
