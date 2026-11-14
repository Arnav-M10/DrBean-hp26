import { parseExact } from './exact.mjs'
import { planRequest } from './manual.mjs'

export function setupFollowupWorkflow({ context, button, node, exactRecord }) {
  let rowId = ''
  let source = '', value = '', reason = '', proposal, dataset, problem, plan, approval, run
  function reset() { rowId = `hypothetical_${crypto.randomUUID().replaceAll('-', '')}`; source = value = reason = ''; proposal = dataset = problem = plan = approval = run = undefined }
  function render(parent, job, suggestion, designPlan) {
    if (source !== (suggestion?.id || '')) { reset(); source = suggestion?.id || '' }
    if (!suggestion || suggestion.body.design_tier !== 'checked_pair_separation') return
    const { api, workspace, busy } = context(), result = suggestion.body
    const section = node('section', ''); section.id = 'followup-review'; parent.append(section)
    section.append(node('h4', 'Review a hypothetical follow-up'), node('p', `This supported flow checks one hypothetical reading at ${result.selected_time} h with hard allowance ${result.future_hard_allowance} mg/L. Actual acquisition and changed sampling conditions require additional engine support.`))
    for (const [id, title, current] of [['followup-value', 'Hypothetical concentration (mg/L)', value], ['followup-reason', 'How you chose this hypothetical reading', reason]]) {
      const label = node('label', title); label.className = 'stack'
      const input = node('input', ''); input.id = id; input.value = current; input.disabled = busy || Boolean(proposal)
      input.addEventListener('input', () => { if (id === 'followup-value') value = input.value; else reason = input.value })
      label.append(input); section.append(label)
    }
    button(section, 'Prepare hypothetical observation', async () => {
      const concentration = parseExact(value)
      if (concentration.startsWith('-') || !reason.trim()) throw new Error('Enter a nonnegative concentration and explain how you chose it.')
      const historicalProblem = await api.json(`/records/${encodeURIComponent(designPlan.body.request.problem_id)}`)
      const historicalDataset = await api.json(`/records/${encodeURIComponent(historicalProblem.body.dataset_id)}`)
      problem = historicalProblem
      proposal = await api.json(`/workspaces/${workspace}/observation-proposals`, {
        dataset_id: historicalDataset.id, experiment_id: historicalDataset.body.experiment_id, origin: 'hypothetical',
        row: { id: rowId, time: result.selected_time, concentration, hard_allowance: result.future_hard_allowance, included: true, notes: reason.trim() },
        source_description: reason.trim(), change_reason: 'Review a hypothetical reading against the original selected pair',
        generating_choices: { design_job_id: job.id, method: reason.trim() },
      })
    }, Boolean(proposal))
    if (!proposal) return
    section.append(exactRecord('Exact proposed hypothetical observation', proposal))
    button(section, 'Accept reviewed hypothetical observation', async () => {
      dataset = await api.json(`/observation-proposals/${proposal.id}/review`, { proposal_digest: proposal.digest, parent_dataset_id: proposal.body.dataset_id, accepted: true })
    }, Boolean(dataset))
    if (!dataset) return
    section.append(exactRecord('New hypothetical dataset revision', dataset))
    button(section, 'Prepare follow-up investigation plan', async () => {
      if (problem.body.dataset_id !== dataset.id) problem = await api.json(`/workspaces/${workspace}/problems`, { ...problem.body, dataset_id: dataset.id, dataset_digest: dataset.digest })
      const request = planRequest(problem, 'Which original candidates remain compatible with this hypothetical reading?')
      request.plan.objective.success_criterion = 'Recheck the original fixed pair and retain candidate-specific feedback under the reviewed assumptions.'
      request.plan.followup = { design_job_id: job.id, design_result_id: suggestion.id, design_result_digest: suggestion.digest, observation_proposal_id: proposal.id, source_artifact_id: result.artifacts[0].id }
      plan = await api.json(`/workspaces/${workspace}/plans`, request)
    }, Boolean(plan))
    if (!plan) return
    section.append(exactRecord('Exact follow-up plan requiring new approval', plan))
    const label = node('label', ' I reviewed this hypothetical follow-up plan and approve this scope.'); label.className = 'stack'
    const check = node('input', ''); check.type = 'checkbox'; check.id = 'followup-approve-scope'; check.disabled = busy || Boolean(approval)
    label.prepend(check); section.append(label)
    const approve = button(section, 'Approve reviewed follow-up', async () => {
      if (!check.checked) throw new Error('Review the follow-up plan and check its approval box.')
      approval = await api.json(`/plans/${plan.id}/approvals`, { expected_plan_digest: plan.digest, expected_current_revision_id: problem.id, accepted: true })
    }, true)
    check.addEventListener('change', () => { approve.disabled = busy || Boolean(approval) || !check.checked })
    button(section, 'Queue approved follow-up', async () => {
      run = await api.json(`/plans/${plan.id}/runs`, { approval_id: approval.id, expected_plan_digest: plan.digest })
    }, !approval || Boolean(run))
    if (run) section.append(node('p', `Follow-up run ${run.id}. Open this identifier in Persisted investigation to retrieve status, candidate feedback and native evidence.`))
  }
  return { render, reset }
}
