import { parseExact } from './exact.mjs'

const ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/
const SHA = /^[a-f0-9]{64}$/
const ACTIVE = new Set(['queued', 'running', 'waiting_child'])
const clone = value => JSON.parse(JSON.stringify(value))

export function researchSnapshot(value, workspace) {
  if (!value || value.schema_version !== 'DB-RESEARCH-1' || !ID.test(value.id) || value.workspace_id !== workspace
      || !Number.isSafeInteger(value.revision) || value.revision < 0 || !['controlled', 'live'].includes(value.mode)
      || !Array.isArray(value.children) || value.children.length > 4 || !Array.isArray(value.reports) || value.reports.some(id => !ID.test(id))) throw new Error('Invalid or mismatched research snapshot.')
  if (value.pending_review && (!ID.test(value.pending_review.id) || !SHA.test(value.pending_review_digest)
      || value.pending_review.workspace_id !== workspace || value.pending_review.digest !== value.pending_review_digest)) throw new Error('The pending review is not bound to this workspace and digest.')
  return clone(value)
}

export function designConstraints(form) {
  if (![form.times, form.allowance, form.horizon, form.allowanceReason].some(value => value?.trim())) return null
  if (![form.times, form.allowance, form.horizon, form.allowanceReason].every(value => value?.trim())) throw new Error('Enter feasible times, a future hard allowance, its origin and a maximum horizon together.')
  return { feasible_times: form.times.split(',').map(value => parseExact(value)), future_hard_allowance: parseExact(form.allowance),
    maximum_horizon: parseExact(form.horizon), allowance_origin: { kind: form.allowanceOrigin || 'hypothetical', description: form.allowanceReason },
    requested_tier: 'checked_pair_separation', allow_construction: true, allow_continuation: true }
}

export class ResearchController {
  constructor({ getDraft, getSources = () => [], getSourceQuestion = () => '', storage = globalThis.sessionStorage, changed = () => {} } = {}) {
    this.getDraft = getDraft; this.getSources = getSources; this.getSourceQuestion = getSourceQuestion; this.storage = storage; this.changed = changed
    this.connection = {}; this.generation = 0; this.state = this.empty()
  }
  empty() { return { snapshot: null, events: [], evidence: [], history: [], pending: null, error: '', busy: false, form: {}, dataAccepted: false, acceptedDraft: '', reviewAccepted: '', readingAccepted: false } }
  key() { return `drbean-research.v1:${this.connection.identityId}:${this.connection.workspaceId}` }
  emit() { this.changed(this.state) }
  persist() {
    try { this.storage?.setItem(this.key(), JSON.stringify({ sessionId: this.state.snapshot?.id ?? null, pending: this.state.pending, form: this.state.form })) }
    catch { this.state.error = 'Browser storage is unavailable; keep this tab open to retain uncertain request identities.' }
  }
  async connect(connection) {
    const same = this.connection.api === connection.api && this.connection.workspaceId === connection.workspaceId && this.connection.identityId === connection.identityId
    this.connection = connection
    if (same) {
      if (this.state.dataAccepted && this.state.acceptedDraft !== JSON.stringify(this.getDraft())) { this.state.dataAccepted = false; this.emit() }
      return
    }
    const generation = ++this.generation; this.state = this.empty(); this.emit()
    if (!connection.api || !connection.workspaceId || !connection.identityId) return
    try {
      const saved = JSON.parse(this.storage?.getItem(this.key()) || '{}')
      if (saved.form && typeof saved.form === 'object') this.state.form = saved.form
      if (saved.pending && typeof saved.pending.path === 'string' && saved.pending.path.startsWith('/') && ID.test(saved.pending.key)) this.state.pending = saved.pending
      const listing = await connection.api.json(`/workspaces/${connection.workspaceId}/research-sessions`)
      if (generation !== this.generation) return
      this.state.history = listing.items.map(value => researchSnapshot(value, connection.workspaceId))
      if (saved.sessionId && ID.test(saved.sessionId)) await this.refresh(saved.sessionId)
    } catch (error) { if (generation === this.generation) this.state.error = error.message }
    if (generation === this.generation) this.emit()
  }
  async refresh(id = this.state.snapshot?.id) {
    if (!id || this.state.busy) return
    const { api, workspaceId } = this.connection, generation = this.generation
    const current = researchSnapshot(await api.json(`/research-sessions/${id}`), workspaceId)
    const events = await api.json(`/research-sessions/${id}/events?after=-1`)
    const references = [...new Set(current.children.flatMap(job => job.kind === 'design_job' ? [job.result_id].filter(Boolean) : job.scenarios.map(row => row.result_id).filter(Boolean)))]
    const evidence = await Promise.all(references.map(ref => api.json(`/records/${ref}`)))
    if (generation !== this.generation) return
    this.state.snapshot = current; this.state.events = events.items; this.state.evidence = evidence
    this.persist(); this.emit()
  }
  async mutate(path, body, key = crypto.randomUUID()) {
    if (this.state.busy) return
    if (this.state.pending && (this.state.pending.key !== key || this.state.pending.path !== path)) throw new Error('Resolve the uncertain frozen request before starting another operation.')
    const connection = this.connection, generation = this.generation
    this.state.pending = { path, body: clone(body), key }; this.state.busy = true; this.state.error = ''; this.persist(); this.emit()
    try {
      const result = researchSnapshot(await connection.api.json(path, body, key), connection.workspaceId)
      if (generation !== this.generation) return
      this.state.snapshot = result; this.state.pending = null; this.persist()
    } catch (error) {
      if (generation === this.generation) { this.state.error = error.message; if (error.kind === 'rejected') this.state.pending = null; this.persist() }
    } finally { if (generation === this.generation) { this.state.busy = false; this.emit() } }
  }
  async create() {
    if (this.state.busy || this.state.pending) return
    if (!this.state.dataAccepted || this.state.acceptedDraft !== JSON.stringify(this.getDraft())) { this.state.error = 'Review and accept the measurements, units, meanings and assumptions first.'; this.emit(); return }
    const generation = this.generation, connection = this.connection
    this.state.busy = true; this.state.error = ''; this.emit()
    let inputs, body
    try {
      const draft = clone(this.getDraft()), constraints = designConstraints(this.state.form), sources = clone(this.getSources())
      if (!draft.question.goal.trim()) throw new Error('Enter your research question in Question before starting.')
      inputs = await connection.saveReviewedInputs()
      body = { objective: draft.question.goal.trim(), problem_id: inputs.problem.id, expected_problem_digest: inputs.problem.digest,
        source_ids: this.state.form.attachSources ? sources.map(asset => asset.id) : [], mode: 'controlled', design_constraints: constraints }
    } catch (error) { if (generation === this.generation) this.state.error = error.message }
    if (generation !== this.generation) return
    this.state.busy = false
    if (body) await this.mutate(`/workspaces/${connection.workspaceId}/research-sessions`, body)
    else this.emit()
  }
  async createFromSources() {
    const objective = this.getSourceQuestion().trim(), sources = clone(this.getSources())
    if (!objective || objective.length > 2000 || !sources.length) throw new Error('Select retained files and enter a research question of at most 2,000 characters above.')
    await this.mutate(`/workspaces/${this.connection.workspaceId}/research-sessions`, { objective, source_ids: sources.map(asset => asset.id), mode: 'controlled' })
  }
  async advance() { const s = this.state.snapshot; if (s) await this.mutate(`/research-sessions/${s.id}/advance`, { expected_revision: s.revision }) }
  async decide(decision) {
    const s = this.state.snapshot, review = s?.pending_review
    if (!review || (decision === 'approve' && this.state.reviewAccepted !== `${review.id}:${review.digest}`)) throw new Error('Review the exact pending scientific scope and select its approval checkbox.')
    await this.mutate(`/research-sessions/${s.id}/decisions`, { expected_revision: s.revision, pending_review_id: review.id, expected_review_digest: review.digest, decision, accepted: true })
  }
  async retry() { const p = this.state.pending; if (p) await this.mutate(p.path, p.body, p.key) }
  async reconcile() { const s = this.state.snapshot; await this.mutate(`/research-sessions/${s.id}/reconcile`, { expected_revision: s.revision, acknowledged_unknown_outcome: true }) }
  async cancel() { await this.mutate(`/research-sessions/${this.state.snapshot.id}/cancel`, {}) }
  async observe() {
    const s = this.state.snapshot, f = this.state.form, root = s.reviewed_context.dataset
    if (!this.state.readingAccepted || !['actual', 'hypothetical'].includes(f.readingOrigin)) throw new Error('Review the complete new reading and explicitly declare its origin.')
    if (f.readingOrigin === 'hypothetical' && !f.generatingMethod?.trim()) throw new Error('Describe how this hypothetical reading was generated.')
    const observation = { dataset_id: root.id, experiment_id: root.body.experiment_id, origin: f.readingOrigin,
      row: { id: `reading_${crypto.randomUUID()}`, time: parseExact(f.readingTime), concentration: parseExact(f.readingValue), hard_allowance: parseExact(f.readingAllowance), included: true,
        original_values: { time: f.readingTime, concentration: f.readingValue, hard_allowance: f.readingAllowance } },
      source_description: f.readingSource || '', change_reason: f.readingReason || '' }
    if (f.readingOrigin === 'hypothetical') observation.generating_choices = { method: f.generatingMethod || '' }
    await this.mutate(`/research-sessions/${s.id}/observations`, { expected_revision: s.revision, pending_review_id: s.pending_review.id, expected_review_digest: s.pending_review.digest, observation, accepted: true })
  }
  async adopt() {
    const s = this.state.snapshot
    if (!this.state.dataAccepted) throw new Error('Review the inputs or clarification answer before accepting.')
    const body = { expected_revision: s.revision, pending_review_id: s.pending_review.id, expected_review_digest: s.pending_review.digest, accepted: true,
      design_constraints: designConstraints(this.state.form), answers: this.state.form.answer?.trim() ? { clarification: this.state.form.answer } : {} }
    if (this.state.form.useReviewedModel) {
      if (this.state.acceptedDraft !== JSON.stringify(this.getDraft())) throw new Error('Review the current measurement and model draft before adopting it.')
      const generation = this.generation; this.state.busy = true; this.emit()
      try { const inputs = await this.connection.saveReviewedInputs(); body.problem_id = inputs.problem.id; body.expected_problem_digest = inputs.problem.digest }
      finally { if (generation === this.generation) { this.state.busy = false; this.emit() } }
      if (generation !== this.generation) return
    }
    await this.mutate(`/research-sessions/${s.id}/inputs`, body)
  }
}

export function setupResearch({ root, getDraft, getSources, getSourceQuestion }) {
  const element = (tag, text = '') => { const item = document.createElement(tag); item.textContent = text; return item }
  const controller = new ResearchController({ getDraft, getSources, getSourceQuestion, changed: render })
  let timer
  const save = (bytes, name) => { const url = URL.createObjectURL(new Blob([bytes], { type: 'application/json' })); const a = element('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000) }
  const action = async callback => { try { await callback() } catch (error) { controller.state.error = error.message; render() } }
  function button(parent, title, callback, disabled = false) { const item = element('button', title); item.type = 'button'; item.disabled = disabled || controller.state.busy; item.addEventListener('click', () => action(callback)); parent.append(item); return item }
  function details(parent, title, value) { const item = element('details'); item.append(element('summary', title), element('pre', JSON.stringify(value, null, 2))); parent.append(item) }
  function field(parent, title, key, options = null) {
    const label = element('label', title); label.className = 'stack'
    const input = element(options ? 'select' : 'input'); input.name = key
    if (options) for (const [value, text] of options) { const option = element('option', text); option.value = value; input.append(option) }
    input.value = controller.state.form[key] || ''; input.disabled = controller.state.busy
    input.addEventListener('input', () => { controller.state.form[key] = input.value; controller.state.dataAccepted = false; controller.state.readingAccepted = false; controller.state.reviewAccepted = ''; root.querySelectorAll('input[type="checkbox"]').forEach(check => { check.checked = false }); controller.persist() })
    label.append(input); parent.append(label); return input
  }
  function checkbox(parent, title, checked, change) { const label = element('label', ` ${title}`), input = element('input'); input.type = 'checkbox'; input.checked = checked; input.disabled = controller.state.busy; input.addEventListener('change', () => change(input.checked)); label.prepend(input); parent.append(label) }
  function constraints(parent) {
    const box = element('details'); box.append(element('summary', 'Feasible next-measurement constraints (optional until design)'))
    field(box, 'Feasible elapsed times in hours, separated by commas', 'times')
    field(box, 'Future hard allowance (mg/L)', 'allowance'); field(box, 'Maximum horizon (hours)', 'horizon')
    field(box, 'Allowance origin', 'allowanceOrigin', [['hypothetical', 'Hypothetical prospective bound'], ['reviewed_hard_bound', 'Reviewed hard bound']])
    field(box, 'Why this hard allowance is justified', 'allowanceReason')
    box.append(element('p', 'Design still requires its own exact review and approval. SD or SE alone is not a hard allowance.')); parent.append(box)
  }
  function render() {
    clearTimeout(timer); if (!root) return
    root.replaceChildren(element('h3', 'Maintain a research plan'))
    const state = controller.state, connection = controller.connection, s = state.snapshot, caps = connection.capabilities?.deepagents
    root.append(element('p', 'The coordinator plans and proposes. You review the meanings and separately approve each scientific operation. Counterdex determines supported mathematical results.'))
    if (!connection.api || !connection.workspaceId) { root.append(element('p', 'Connect to a private workspace to retain a research question and plan.')); return }
    if (state.error) { const error = element('p', state.error); error.setAttribute('role', 'alert'); root.append(error) }
    if (caps?.execution_mode !== 'controlled' || !caps?.dispatch_enabled) root.append(element('p', `Coordination unavailable: ${caps?.unavailable_reason || 'No admitted controlled coordinator is configured'}. Saved evidence remains available. Live coordination requires separate disclosure and explicitly allocated provider capacity.`))
    if (state.pending) { root.append(element('p', 'This request has an uncertain response. Refresh is read-only; deliberately retry the same frozen request to reconcile it.')); details(root, 'Pending request', state.pending.body); button(root, 'Retry same request', () => controller.retry()); button(root, 'Refresh saved state', () => controller.refresh()) }
    if (!s) {
      if (controller.getSources().length) {
        root.append(element('p', 'Retain the selected files and question as untrusted research context. This does not convert a paper into concentration data or approve computation.'))
        button(root, 'Save selected files and research question', () => controller.createFromSources(), Boolean(state.pending))
      }
      root.append(element('p', 'Review your measurement table and Question below, then save them here. Arbitrary papers remain general analysis until a supported scientific model and assumptions are reviewed.'))
      constraints(root)
      checkbox(root, 'Attach selected general files as context only; they do not populate or certify these measurements.', Boolean(state.form.attachSources), value => { state.form.attachSources = value; controller.persist() })
      checkbox(root, 'I reviewed the exact measurement values, units, time origin, hard allowances, parameter bounds and question assumptions.', state.dataAccepted, value => { state.dataAccepted = value; state.acceptedDraft = value ? JSON.stringify(getDraft()) : '' })
      button(root, 'Save reviewed inputs and research question', () => controller.create(), Boolean(state.pending))
      for (const previous of state.history) button(root, `Reopen: ${previous.objective}`, () => controller.refresh(previous.id))
      return
    }
    root.append(element('h4', s.objective), element('p', `State: ${s.state} · ${s.mode === 'controlled' ? 'controlled model; real scientific children' : 'live model; separately metered'} · revision ${s.revision}`))
    root.append(element('p', `Used: ${s.usage.logical_turns} logical model turns, ${s.usage.tool_calls} tools, ${s.usage.child_count} scientific reservations. Human waiting releases the worker and does not consume active time.`))
    const plan = element('ol')
    for (const step of s.plan?.body?.steps || []) { const item = element('li', `${step.title}: ${step.status}. ${step.reason || ''}`); plan.append(item) }
    root.append(plan)
    if (!s.plan) root.append(element('p', 'No maintained plan has been recorded yet.'))
    details(root, 'Exact historical reviewed inputs', s.reviewed_context)
    if (s.state === 'ready' || s.state === 'paused') button(root, 'Advance research plan', () => controller.advance(), !caps?.dispatch_enabled || Boolean(state.pending))
    const review = s.pending_review
    if (review && ['plan', 'design_plan'].includes(review.kind)) {
      root.append(element('h4', review.kind === 'design_plan' ? 'Review the separate pair-design operation' : review.body.followup ? 'Review the separate original-candidate recheck' : 'Review the investigation operation'))
      root.append(element('p', `Exact review: ${review.id} · digest ${review.digest}. Data acceptance and plan preparation have not approved computation.`))
      details(root, 'Exact frozen scientific scope, tools and limits', review.body)
      checkbox(root, 'I approve only this frozen scientific scope and its limits.', state.reviewAccepted === `${review.id}:${review.digest}`, value => { state.reviewAccepted = value ? `${review.id}:${review.digest}` : '' })
      button(root, 'Approve exact operation and continue', () => controller.decide('approve'), Boolean(state.pending))
      button(root, 'Reject operation', () => controller.decide('reject'), Boolean(state.pending))
    } else if (review && s.state === 'waiting_observation') {
      root.append(element('h4', 'Review a new reading'), element('p', 'A physical measurement may take as long as needed. Keep the declared time and allowance of this reading; changing them does not reuse a separation guarantee. Actual origin is a human declaration, not instrument authentication.'))
      field(root, 'Elapsed reading time (hours)', 'readingTime'); field(root, 'Concentration (mg/L)', 'readingValue'); field(root, 'This reading’s hard allowance (mg/L)', 'readingAllowance')
      field(root, 'Reading origin', 'readingOrigin', [['', 'Choose origin'], ['actual', 'Actual, declared acquisition'], ['hypothetical', 'Hypothetical, explicitly generated']])
      field(root, 'Source or acquisition description', 'readingSource'); field(root, 'Reason for adding this reading', 'readingReason'); field(root, 'Generating method (required for hypothetical readings)', 'generatingMethod')
      checkbox(root, 'I reviewed this complete new reading and its origin. This does not approve rechecking.', state.readingAccepted, value => { state.readingAccepted = value })
      button(root, 'Accept reading for separate recheck review', () => controller.observe(), Boolean(state.pending))
    } else if (review?.kind === 'research_clarification') {
      root.append(element('h4', 'Clarification required'), element('p', review.body.reason)); field(root, 'Reviewed answer', 'answer'); constraints(root)
      checkbox(root, 'Adopt the supported measurements and model reviewed below for this clarification.', Boolean(state.form.useReviewedModel), value => { state.form.useReviewedModel = value; state.dataAccepted = false; controller.persist() })
      checkbox(root, 'I reviewed this answer and any new measurement constraints.', state.dataAccepted, value => { state.dataAccepted = value; state.acceptedDraft = value ? JSON.stringify(getDraft()) : '' })
      button(root, 'Accept clarified input and continue planning', () => controller.adopt(), Boolean(state.pending))
    }
    if (s.state === 'needs_reconciliation') { root.append(element('p', 'The previous action was interrupted. Recovery reuses the same journal, budget and scientific child; an unknown provider outcome remains reserved.')); button(root, 'Reconcile interrupted action', () => controller.reconcile(), Boolean(state.pending)) }
    if (s.action?.error_code) root.append(element('p', `Action stopped: ${s.action.error_code}. Completed evidence is retained.`))
    button(root, 'Refresh saved state', () => controller.refresh())
    if (!['completed', 'failed', 'cancelled'].includes(s.state)) button(root, 'Cancel research and owned work', () => controller.cancel(), Boolean(state.pending))
    const events = element('details'); events.append(element('summary', 'Actual recorded activity')); const activity = element('ol')
    for (const event of state.events) activity.append(element('li', `${event.timestamp} · ${event.event_type}: ${event.summary}`)); events.append(activity); root.append(events)
    for (const record of state.evidence) {
      const result = record.body.result ?? record.body, card = element('section'); card.className = 'card'; card.append(element('h4', result.design_tier || result.scientific_outcome || 'Retained evidence'))
      card.append(element('p', `Verification: ${result.verification}; expected binding: ${result.expected_binding || result.verification_record?.expected_binding || 'not supplied'}; replay: ${result.replay}. These describe separate properties.`))
      for (const candidate of result.candidate_results ?? []) card.append(element('p', `${candidate.candidate_id}: ${{ valid: 'compatible', invalid: 'excluded' }[candidate.verification] || 'unresolved'}. ${candidate.reason_code || ''}`))
      details(card, 'Exact candidate vectors and scoped results', { candidates: result.candidates, candidate_ids: result.candidate_ids, candidate_results: result.candidate_results, options: result.options, selected_time: result.selected_time, future_hard_allowance: result.future_hard_allowance })
      for (const ref of result.artifacts ?? []) {
        button(card, 'Download native evidence', async () => { const data = await connection.api.download(`/artifacts/${ref.id}`, ref); save(data.bytes, `dr-bean-${ref.id}.native.json`) })
        button(card, 'Download independent replay anchors', async () => { const data = await connection.api.download(`/artifacts/${ref.id}/anchor?download=true`); save(data.bytes, `dr-bean-${ref.id}.anchors.json`) })
        card.append(element('pre', `python3.11 -m counterdex replay-native dr-bean-${ref.id}.native.json --anchors dr-bean-${ref.id}.anchors.json`))
      }
      root.append(card)
    }
    for (const report of s.reports) button(root, 'Download research report snapshot', async () => { const data = await connection.api.download(`/reports/${report}/download`); save(data.bytes, `dr-bean-${report}.json`) })
    root.append(element('p', 'Paused research is retained separately from browser authentication. Expired or revoked credentials cannot resume it; cross-device identity recovery is not implemented.'))
    if (ACTIVE.has(s.state) && !state.busy && !state.pending) timer = setTimeout(() => action(() => controller.refresh()), 1500)
  }
  render()
  return { controller, connectionChanged: connection => controller.connect(connection), sourceContextChanged: () => { if (!controller.state.snapshot) render() } }
}
