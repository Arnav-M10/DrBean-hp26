import { parseExact } from './exact.mjs'
import { planRequest } from './manual.mjs'
import { readable } from './result-view.mjs'

export function setupFollowupWorkflow({ context, button, node, exactRecord, openRun }) {
  let rowId = '', origin = 'hypothetical', observedTime = '', observedAllowance = ''
  let source = '', value = '', reason = '', proposal, dataset, problem, plan, approval, run
  function reset() { origin = 'hypothetical'; observedTime = observedAllowance = ''; rowId = `observation_${crypto.randomUUID().replaceAll('-', '')}`; source = value = reason = ''; proposal = dataset = problem = plan = approval = run = undefined }
  function render(parent, job, suggestion, designPlan) {
    if (source !== (suggestion?.id || '')) { reset(); source = suggestion?.id || '' }
    if (!suggestion || suggestion.body.design_tier !== 'checked_pair_separation') return
    const { api, workspace, busy } = context(), result = suggestion.body
    const section = node('section', ''); section.id = 'followup-review'; parent.append(section)
    section.append(node('h3', 'Add the new reading'), node('p', `The comparison suggested ${readable(result.selected_time)} h with an allowance of ±${readable(result.future_hard_allowance)} mg/L. Record an actual reading at the time you really measured it, with an allowance you can justify. Marking a reading as actual is your statement; Dr. Bean cannot verify the instrument.`))
    const originLabel = node('label', 'Where the reading came from'); originLabel.className = 'stack'
    const originSelect = node('select', ''); originSelect.id = 'followup-origin'; originSelect.setAttribute('aria-label', 'Where the reading came from'); originSelect.disabled = busy || Boolean(proposal)
    for (const optionOrigin of ['hypothetical', 'actual']) { const option = node('option', optionOrigin === 'actual' ? 'Actual, measured' : 'Hypothetical, for exploration'); option.value = optionOrigin; originSelect.append(option) }
    originSelect.value = origin
    originSelect.addEventListener('change', () => {
      origin = originSelect.value; value = reason = observedTime = observedAllowance = ''
      const host = section.parentElement; section.remove(); render(host, job, suggestion, designPlan)
    })
    originLabel.append(originSelect); section.append(originLabel)
    if (origin === 'actual') for (const [id, title, current] of [['followup-time', 'Time you measured it (hours since dosing)', observedTime], ['followup-allowance', 'Allowance for this reading (± mg/L)', observedAllowance]]) {
      const label = node('label', title); label.className = 'stack'
      const input = node('input', ''); input.id = id; input.value = current; input.disabled = busy || Boolean(proposal)
      input.addEventListener('input', () => { if (id === 'followup-time') observedTime = input.value; else observedAllowance = input.value })
      label.append(input); section.append(label)
    }
    for (const [id, title, current] of [['followup-value', `${origin} concentration (mg/L)`, value], ['followup-reason', origin === 'actual' ? 'How it was measured and why the allowance holds' : 'How you chose this hypothetical reading', reason]]) {
      const label = node('label', title); label.className = 'stack'
      const input = node('input', ''); input.id = id; input.value = current; input.disabled = busy || Boolean(proposal)
      input.addEventListener('input', () => { if (id === 'followup-value') value = input.value; else reason = input.value })
      label.append(input); section.append(label)
    }
    button(section, `Prepare ${origin} reading`, async () => {
      const concentration = parseExact(value)
      if (concentration.startsWith('-') || !reason.trim()) throw new Error('Enter a concentration of 0 or more and explain how you chose it.')
      const time = origin === 'actual' ? parseExact(observedTime) : result.selected_time
      const allowance = origin === 'actual' ? parseExact(observedAllowance) : result.future_hard_allowance
      if (time.startsWith('-') || allowance.startsWith('-') || allowance === '0/1') throw new Error('Enter a time of 0 or more, an allowance above 0, and why the allowance holds.')
      const historicalProblem = await api.json(`/records/${encodeURIComponent(designPlan.body.request.problem_id)}`)
      const historicalDataset = await api.json(`/records/${encodeURIComponent(historicalProblem.body.dataset_id)}`)
      problem = historicalProblem
      proposal = await api.json(`/workspaces/${workspace}/observation-proposals`, {
        dataset_id: historicalDataset.id, experiment_id: historicalDataset.body.experiment_id, origin,
        row: { id: rowId, time, concentration, hard_allowance: allowance, included: true, notes: reason.trim() },
        source_description: reason.trim(), change_reason: `Review a ${origin} reading against the original selected pair`,
        generating_choices: origin === 'hypothetical' ? { design_job_id: job.id, method: reason.trim() } : {},
      })
    }, Boolean(proposal))
    if (!proposal) return
    if (!dataset) button(section, 'Edit the reading', () => { reset(); source = suggestion.id })
    section.append(exactRecord(`Exact proposed ${origin} reading`, proposal))
    button(section, `Accept ${origin} reading`, async () => {
      dataset = await api.json(`/observation-proposals/${proposal.id}/review`, { proposal_digest: proposal.digest, parent_dataset_id: proposal.body.dataset_id, accepted: true })
    }, Boolean(dataset))
    if (!dataset) return
    section.append(exactRecord(`Readings including the new ${origin} reading`, dataset))
    button(section, 'Prepare recheck', async () => {
      if (problem.body.dataset_id !== dataset.id) problem = await api.json(`/workspaces/${workspace}/problems`, { ...problem.body, dataset_id: dataset.id, dataset_digest: dataset.digest })
      const request = planRequest(problem, `Which original candidates remain compatible with this ${origin} reading?`)
      request.plan.objective.success_criterion = 'Recheck the original fixed pair and retain candidate-specific feedback under the reviewed assumptions.'
      request.plan.followup = { design_job_id: job.id, design_result_id: suggestion.id, design_result_digest: suggestion.digest, observation_proposal_id: proposal.id, source_artifact_id: result.artifacts[0].id }
      plan = await api.json(`/workspaces/${workspace}/plans`, request)
    }, Boolean(plan))
    if (!plan) return
    section.append(exactRecord('Exact recheck plan (needs its own approval)', plan))
    const label = node('label', ` I reviewed this ${origin} follow-up plan and approve this scope.`)
    const check = node('input', ''); check.type = 'checkbox'; check.id = 'followup-approve-scope'; check.disabled = busy || Boolean(approval)
    label.prepend(check); section.append(label)
    const approve = button(section, 'Approve recheck', async () => {
      if (!check.checked) throw new Error('Read the recheck plan, then tick its approval box.')
      approval = await api.json(`/plans/${plan.id}/approvals`, { expected_plan_digest: plan.digest, expected_current_revision_id: problem.id, accepted: true })
    }, true)
    check.addEventListener('change', () => { approve.disabled = busy || Boolean(approval) || !check.checked })
    button(section, 'Run approved recheck', async () => {
      run = await api.json(`/plans/${plan.id}/runs`, { approval_id: approval.id, expected_plan_digest: plan.digest })
      await openRun(run.id)
    }, !approval || Boolean(run))
    if (run) button(section, 'Open recheck result', () => openRun(run.id))
  }
  return { render, reset }
}
