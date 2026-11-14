import { parseExact } from './exact.mjs'
import { interpretResult } from './result-view.mjs'
import { designExplanation } from './design.mjs'

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

const SESSION_STATES = {
  ready: ['plan', 'Ready for the next step'], queued: ['run', 'Queued'], running: ['run', 'Assistant working'], waiting_child: ['run', 'Checker running'],
  waiting_review: ['wait', 'Waiting for your approval'], waiting_observation: ['wait', 'Waiting for a new reading'], paused: ['off', 'Paused'],
  needs_reconciliation: ['bad', 'Interrupted'], completed: ['ok', 'Complete'], failed: ['bad', 'Failed'], cancelled: ['off', 'Cancelled'],
}
const STEP_STATES = {
  pending: ['plan', 'Suggested'], in_progress: ['run', 'Running'], waiting_review: ['wait', 'Needs your approval'], waiting_observation: ['wait', 'Needs a reading'],
  completed: ['ok', 'Done'], failed: ['bad', 'Failed'], unresolved: ['off', 'Unresolved'], skipped: ['off', 'Skipped'],
}
const EVENT_LABELS = {
  plan_updated: 'Plan updated', action_started: 'Step started', model_attempt_started: 'Assistant asked its model', model_attempt_finished: 'Model reply received',
  tool_requested: 'Tool requested', tool_finished: 'Tool finished', review_required: 'Paused for your review', decision_recorded: 'Your decision recorded',
  resumed: 'Resumed', child_linked: 'Checker job started', evidence_observed: 'Evidence returned', waiting_observation: 'Waiting for a new reading',
  cancel_requested: 'Stop requested', reconciled: 'Recovered after interruption', terminal: 'Finished',
}

export function setupResearch({ root, getDraft, getSources, getSourceQuestion, onChange = () => {} }) {
  const element = (tag, text = '', className = '') => { const item = document.createElement(tag); item.textContent = text; if (className) item.className = className; return item }
  const chip = ([kind, text]) => element('span', text, `state ${kind}`)
  const controller = new ResearchController({ getDraft, getSources, getSourceQuestion, changed: () => { render(); onChange() } })
  let timer
  const save = (bytes, name) => { const url = URL.createObjectURL(new Blob([bytes], { type: 'application/json' })); const a = element('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000) }
  const action = async callback => { try { await callback() } catch (error) { controller.state.error = error.message; render() } }
  function button(parent, title, callback, disabled = false, className = '') { const item = element('button', title, className); item.type = 'button'; item.disabled = disabled || controller.state.busy; item.addEventListener('click', () => action(callback)); parent.append(item); return item }
  function details(parent, title, value, className = '') { const item = element('details', '', className); item.append(element('summary', title), element('pre', JSON.stringify(value, null, 2))); parent.append(item); return item }
  function field(parent, title, key, options = null) {
    const label = element('label', title, 'stack')
    const input = element(options ? 'select' : 'input'); input.name = key
    if (options) for (const [value, text] of options) { const option = element('option', text); option.value = value; input.append(option) }
    input.value = controller.state.form[key] || ''; input.disabled = controller.state.busy
    input.addEventListener('input', () => { controller.state.form[key] = input.value; controller.state.dataAccepted = false; controller.state.readingAccepted = false; controller.state.reviewAccepted = ''; root.querySelectorAll('input[type="checkbox"]').forEach(check => { check.checked = false }); controller.persist() })
    label.append(input); parent.append(label); return input
  }
  function checkbox(parent, title, checked, change) { const label = element('label', ` ${title}`), input = element('input'); input.type = 'checkbox'; input.checked = checked; input.disabled = controller.state.busy; input.addEventListener('change', () => change(input.checked)); label.prepend(input); parent.append(label) }
  function constraints(parent) {
    const box = element('details'); box.append(element('summary', 'Measurement times you could add later (optional for now)'))
    box.append(element('p', 'Only needed when the plan reaches comparing two candidates. You will review and approve that comparison separately.', 'fine'))
    field(box, 'Feasible elapsed times in hours, separated by commas', 'times')
    field(box, 'Allowance for the future reading (mg/L)', 'allowance'); field(box, 'Latest time you could measure (hours)', 'horizon')
    field(box, 'Where that allowance comes from', 'allowanceOrigin', [['hypothetical', 'Hypothetical prospective bound'], ['reviewed_hard_bound', 'Reviewed hard bound']])
    field(box, 'Why this allowance is justified', 'allowanceReason')
    box.append(element('p', 'A standard deviation or standard error alone is not an allowance.', 'fine')); parent.append(box)
  }
  function describeEvidence(record) {
    const result = record.body.result ?? record.body
    if (result.design_tier) return { title: 'Measurement-time comparison', text: designExplanation(result) }
    if (result.scientific_outcome || result.native_replay) return { title: 'Checker result', text: interpretResult(result).statement }
    return { title: 'Retained evidence', text: 'Evidence recorded by the server.' }
  }
  function render() {
    clearTimeout(timer); if (!root) return
    const state = controller.state, connection = controller.connection, s = state.snapshot, caps = connection.capabilities?.deepagents
    root.replaceChildren(element('h2', 'Research plan with the assistant'))
    root.append(element('p', 'The research assistant keeps a step-by-step plan, proposes each scientific operation and stops for your approval before it runs. It is built with LangChain Deep Agents. Every mathematical result still comes from the Counterdex checker, never from the assistant.'))
    if (!connection.api || !connection.workspaceId) { root.append(element('p', 'Connect to a private workspace to keep a research question and plan.', 'note')); return }
    if (state.error) { const error = element('p', state.error, 'errors'); error.setAttribute('role', 'alert'); root.append(error) }
    const enabled = caps?.execution_mode === 'controlled' && caps?.dispatch_enabled
    if (!enabled) root.append(element('p', `The assistant cannot take new steps on this server: ${caps?.unavailable_reason || 'no controlled coordinator is configured'}. Saved plans and their evidence can still be opened. The approved check above works without it.`, 'note wait'))
    if (state.pending) {
      const box = element('div', '', 'callout'); root.append(box)
      box.append(element('h3', 'A request did not get a clear answer'), element('p', 'The server may or may not have accepted it. Refresh only reads saved state. Retry sends the same frozen request again, so it cannot be applied twice.'))
      details(box, 'The pending request', state.pending.body, 'technical'); button(box, 'Retry same request', () => controller.retry()); button(box, 'Refresh saved state', () => controller.refresh(), false, 'secondary')
    }
    if (!s) {
      const start = element('section'); root.append(start)
      start.append(element('h3', 'Start a research plan'))
      const goal = getDraft().question.goal.trim()
      start.append(element('p', goal ? `Question: “${goal}”` : 'Add a question first: write it in Claim and assumptions under “Your question in your own words.”', goal ? '' : 'note wait'))
      start.append(element('p', 'The plan uses the measurements and claim from Check inputs. Creating it saves them on the server; it does not run anything.', 'fine'))
      if (controller.getSources().length) {
        start.append(element('p', 'You can also keep the files selected under “Ask about a paper or data file” as context. They will not become measurements or approve any computation.'))
        button(start, 'Save selected files and research question', () => controller.createFromSources(), Boolean(state.pending), 'secondary')
      }
      constraints(start)
      if (controller.getSources().length) checkbox(start, 'Attach the selected files as context only. They do not fill in or certify the measurements.', Boolean(state.form.attachSources), value => { state.form.attachSources = value; controller.persist() })
      checkbox(start, 'I reviewed the measurement values, units, time origin, allowances, search limits and claim.', state.dataAccepted, value => { state.dataAccepted = value; state.acceptedDraft = value ? JSON.stringify(getDraft()) : '' })
      button(start, 'Create research plan', () => controller.create(), Boolean(state.pending))
      if (state.history.length) {
        start.append(element('h3', 'Saved research plans'))
        for (const previous of state.history) button(start, `Reopen: ${previous.objective.slice(0, 120)}`, () => controller.refresh(previous.id), false, 'secondary')
      }
      return
    }
    root.append(element('h3', 'Your question'), element('h4', s.objective, 'objective'))
    const status = element('div', '', 'actions'); status.append(chip(SESSION_STATES[s.state] ?? ['off', s.state]), element('span', s.mode === 'controlled' ? 'Controlled assistant: scripted planning model, real checker jobs' : 'Live model: each call is metered', 'meta'))
    root.append(status)
    const review = s.pending_review
    const turn = element('div', '', 'callout primary')
    if (review && ['plan', 'design_plan'].includes(review.kind)) {
      root.append(turn)
      turn.append(element('h3', review.kind === 'design_plan' ? 'Approve a measurement-time comparison' : review.body.followup ? 'Approve rechecking the original candidates' : 'Approve the proposed check'))
      turn.append(element('p', 'The assistant proposed this operation and stopped. Nothing runs until you approve. Accepting your inputs earlier did not approve it.'))
      details(turn, 'Exactly what would run: scope, tools and limits', review.body, 'technical')
      checkbox(turn, 'I approve only this operation and its limits.', state.reviewAccepted === `${review.id}:${review.digest}`, value => { state.reviewAccepted = value ? `${review.id}:${review.digest}` : '' })
      const row = element('div', '', 'actions'); turn.append(row)
      button(row, 'Approve this operation', () => controller.decide('approve'), Boolean(state.pending))
      button(row, 'Reject', () => controller.decide('reject'), Boolean(state.pending), 'danger')
    } else if (review && s.state === 'waiting_observation') {
      root.append(turn)
      turn.append(element('h3', 'Enter the new reading'), element('p', 'Take the measurement whenever you can. Record its real time and allowance; changing them means the earlier comparison no longer applies. Declaring a reading as actual is your statement, not instrument authentication.'))
      field(turn, 'Elapsed time of the reading (hours)', 'readingTime'); field(turn, 'Concentration (mg/L)', 'readingValue'); field(turn, 'Allowance for this reading (mg/L)', 'readingAllowance')
      field(turn, 'Where the reading came from', 'readingOrigin', [['', 'Choose origin'], ['actual', 'Actual, measured'], ['hypothetical', 'Hypothetical, made up for exploration']])
      field(turn, 'Source or acquisition notes', 'readingSource'); field(turn, 'Why you are adding it', 'readingReason'); field(turn, 'How it was generated (hypothetical readings only)', 'generatingMethod')
      checkbox(turn, 'I reviewed this reading and its origin. This does not approve rechecking.', state.readingAccepted, value => { state.readingAccepted = value })
      button(turn, 'Submit reading for review', () => controller.observe(), Boolean(state.pending))
    } else if (review?.kind === 'research_clarification') {
      root.append(turn)
      turn.append(element('h3', 'The assistant needs more information'), element('p', review.body.reason)); field(turn, 'Your answer', 'answer'); constraints(turn)
      checkbox(turn, 'Use the measurements and claim from Check inputs for this answer.', Boolean(state.form.useReviewedModel), value => { state.form.useReviewedModel = value; state.dataAccepted = false; controller.persist() })
      checkbox(turn, 'I reviewed this answer and any new measurement times.', state.dataAccepted, value => { state.dataAccepted = value; state.acceptedDraft = value ? JSON.stringify(getDraft()) : '' })
      button(turn, 'Send answer and continue planning', () => controller.adopt(), Boolean(state.pending))
    } else if (s.state === 'ready' || s.state === 'paused') {
      root.append(turn)
      turn.append(element('h3', 'Let the assistant take its next step'), element('p', 'It updates the plan and either proposes an operation for your approval or asks you a question. It cannot run a check without your approval.'))
      button(turn, 'Continue research plan', () => controller.advance(), !enabled || Boolean(state.pending))
    } else if (s.state === 'needs_reconciliation') {
      root.append(turn)
      turn.append(element('h3', 'Recover the interrupted step'), element('p', 'The last step stopped unexpectedly. Recovery reuses the same journal, budget and checker job; an unknown model outcome stays counted.'))
      button(turn, 'Reconcile interrupted action', () => controller.reconcile(), Boolean(state.pending))
    }
    if (s.action?.error_code) root.append(element('p', `The last step stopped: ${s.action.error_code}. Completed evidence is kept.`, 'note bad'))
    root.append(element('h3', 'Plan'))
    if (!s.plan) root.append(element('p', 'The assistant has not written a plan yet. Continue the research plan to let it draft one.', 'note'))
    else {
      const plan = element('ol', '', 'plan-list')
      for (const step of s.plan.body.steps) {
        const item = element('li'), text = element('div')
        text.append(element('strong', step.title)); if (step.reason) text.append(element('p', step.reason))
        item.append(text, chip(STEP_STATES[step.status] ?? ['off', step.status])); plan.append(item)
      }
      root.append(plan)
    }
    root.append(element('h3', 'What has happened'))
    if (!state.events.length) root.append(element('p', 'No recorded activity yet.', 'fine'))
    else {
      const recent = element('ol', '', 'timeline')
      for (const event of state.events.slice(-6)) {
        const item = element('li', '', event.event_type === 'review_required' || event.event_type === 'waiting_observation' ? 'waiting' : ['tool_finished', 'evidence_observed', 'decision_recorded', 'terminal'].includes(event.event_type) ? 'done' : '')
        const time = element('time', new Date(event.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })); time.dateTime = event.timestamp
        item.append(time, element('strong', EVENT_LABELS[event.event_type] ?? event.event_type), event.summary ? ` — ${event.summary}` : '')
        recent.append(item)
      }
      root.append(recent)
      const all = element('details', '', 'technical'); all.append(element('summary', `All ${state.events.length} recorded events (technical)`)); const activity = element('ol')
      for (const event of state.events) activity.append(element('li', `${event.timestamp} · ${event.event_type}: ${event.summary}`)); all.append(activity); root.append(all)
    }
    root.append(element('p', `Used ${s.usage.logical_turns} of 16 assistant turns, ${s.usage.tool_calls} of 24 tool calls and ${s.usage.child_count} of 4 checker jobs. Time spent waiting for you is not counted.`, 'meta'))
    if (state.evidence.length) root.append(element('h3', 'Evidence returned to the plan'))
    for (const record of state.evidence) {
      const result = record.body.result ?? record.body, described = describeEvidence(record), card = element('section', '', 'callout'); card.style.borderLeftColor = 'var(--rule-strong)'
      card.append(element('h4', described.title), element('p', described.text))
      for (const candidate of result.candidate_results ?? []) card.append(element('p', `${candidate.candidate_id}: ${{ valid: 'still fits', invalid: 'ruled out' }[candidate.verification] || 'unresolved'}. ${candidate.reason_code || ''}`, 'fine'))
      const row = element('div', '', 'actions'); card.append(row)
      for (const ref of result.artifacts ?? []) {
        button(row, 'Download native evidence', async () => { const data = await connection.api.download(`/artifacts/${ref.id}`, ref); save(data.bytes, `dr-bean-${ref.id}.native.json`) }, false, 'secondary')
        button(row, 'Download research replay anchors', async () => { const data = await connection.api.download(`/artifacts/${ref.id}/anchor?download=true`); save(data.bytes, `dr-bean-${ref.id}.anchors.json`) }, false, 'secondary')
      }
      const tech = details(card, 'Technical details', { verification: result.verification, expected_binding: result.expected_binding || result.verification_record?.expected_binding, replay: result.replay, candidates: result.candidates, candidate_ids: result.candidate_ids, candidate_results: result.candidate_results, options: result.options, selected_time: result.selected_time, future_hard_allowance: result.future_hard_allowance }, 'technical')
      for (const ref of result.artifacts ?? []) tech.append(element('pre', `python3.11 -m counterdex replay-native dr-bean-${ref.id}.native.json --anchors dr-bean-${ref.id}.anchors.json`))
      root.append(card)
    }
    for (const report of s.reports) button(root, 'Download research report snapshot', async () => { const data = await connection.api.download(`/reports/${report}/download`); save(data.bytes, `dr-bean-${report}.json`) }, false, 'secondary')
    details(root, 'Exact inputs this plan was created with', s.reviewed_context, 'technical')
    const controls = element('div', '', 'actions'); root.append(controls)
    button(controls, 'Refresh saved state', () => controller.refresh(), false, 'secondary')
    if (!['completed', 'failed', 'cancelled'].includes(s.state)) button(controls, 'Stop this research plan', async () => { if (confirm('Stop this research plan and any work it owns? Evidence already recorded is kept, but the plan cannot be resumed.')) await controller.cancel() }, Boolean(state.pending), 'danger')
    root.append(element('p', 'This plan is saved on the server. Signing in again with the same identity reopens it; expired or revoked access cannot resume it, and moving it to another identity is not supported.', 'fine'))
    if (ACTIVE.has(s.state) && !state.busy && !state.pending) timer = setTimeout(() => action(() => controller.refresh()), 1500)
  }
  render()
  return { controller, connectionChanged: connection => controller.connect(connection), sourceContextChanged: () => { if (!controller.state.snapshot) render() } }
}
