import { validateMeasurements, parseExact } from './exact.mjs'
import { validateQuestion } from './question.mjs'

export function datasetBody(draft, context) {
  if (validateMeasurements(draft.rows).errors.length) throw new Error('Review the measurement table before saving.')
  if (!context.experiment || !context.timeOrigin || !context.origin) throw new Error('Enter the experiment identifier, elapsed-time origin, and dataset origin in Question.')
  if (draft.sources.some(s => s.name === 'Synthetic two-rate example') && context.origin !== 'synthetic') {
    throw new Error('The synthetic example must retain synthetic origin.')
  }
  return {
    schema_version: 'DB-SC-1', experiment_id: context.experiment, time_origin: context.timeOrigin,
    origin: context.origin, parent_id: null,
    change_reason: JSON.stringify({ allowance_origin: draft.question.allowanceOrigin, methods: draft.question.methods, goal: draft.question.goal }),
    rows: draft.rows.map(row => ({
      id: `row_${row.id}`, time: parseExact(row.time), concentration: parseExact(row.concentration),
      hard_allowance: parseExact(row.epsilon), included: row.included,
      original_values: { time: row.time, concentration: row.concentration, hard_allowance: row.epsilon },
      source_asset_id: null,
      notes: JSON.stringify({ source: draft.sources.find(s => s.id === row.sourceId) ?? null, imported_values: row.original ?? null }),
    })),
  }
}
export function problemBody(draft, dataset) {
  const { exact, errors } = validateQuestion(draft.question)
  if (errors.length) throw new Error('Review the question fields before saving.')
  return {
    schema_version: 'DB-SC-1', dataset_id: dataset.id, dataset_digest: dataset.digest,
    model: 'two_rate_concentration',
    domain: Object.fromEntries([['A', 'a'], ['ke', 'ke'], ['ka', 'ka']].map(([key, prefix]) => [key, { lower: exact[`${prefix}Min`], upper: exact[`${prefix}Max`] }]).concat([['rate_order', 'ke_lt_ka']])),
    initial_concentration: '0/1', observable: 'concentration', time_unit: 'h', concentration_unit: 'mg/L', rate_unit: '1/h',
    target: { parameter: 'ke', lower: exact.targetMin, upper: exact.targetMax, closed: true },
  }
}
// The backend requires an explicit reviewed objective for Counterdex plans. The researcher's goal is
// used when given; a blank goal must not block a complete structured draft, so the question is then
// stated from the exact reviewed target interval. Both strings are shown in the frozen plan for review.
export function researchObjective(problem, goal = '') {
  const { lower, upper } = problem.body.target
  const stated = `Do the reviewed measurements and hard allowances force the elimination rate ke into the closed interval [${lower}, ${upper}] per hour?`
  const question = goal.trim() ? `${goal.trim().slice(0, 1500)} (Reviewed claim: ke in [${lower}, ${upper}] per hour.)` : stated
  return { version: 'research-objective.v1', question,
    success_criterion: 'A checked compatible candidate outside the interval, or an honest unresolved or unavailable status. Nothing here proves the interval.' }
}
export function planRequest(problem, goal = '') {
  return { expected_current_revision_id: problem.id, plan: {
    schema_version: 'DB-SC-1', problem_id: problem.id, problem_digest: problem.digest, dataset_id: problem.body.dataset_id,
    scenarios: [{ id: 'baseline', problem_id: problem.id, problem_digest: problem.digest, kind: 'baseline', label: 'Reviewed manual baseline' }],
    permitted_tools: ['read_scoped_evidence', 'execute_approved_scenario', 'record_allowed_skip', 'return_grounded_explanation'],
    budget: { provider_turns: 0, tool_calls: 2, scientific_reservations: 1, wall_seconds: 120, scientific_wall_seconds: 120 },
    provider_disclosure: { provider: 'none', model: null, source_asset_ids: [], context_fields: [], permission_id: null }, parent_plan_id: null,
    scientific_profile: 'counterdex.v1', objective: researchObjective(problem, goal),
  } }
}
