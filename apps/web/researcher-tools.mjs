import { parseExact } from './exact.mjs'

export function templateFields(preview) {
  if (preview?.requires_review !== true || preview.defaults?.requires_review !== true
      || preview.defaults?.format !== 'experiment-template.v1') throw new Error('Unsupported template preview.')
  const { problem_inputs: p, default_hard_allowance, allowance_origin, methods } = preview.defaults
  if (p.model !== 'two_rate_concentration' || p.time_unit !== 'h' || p.concentration_unit !== 'mg/L'
      || p.rate_unit !== '1/h' || p.initial_concentration !== '0/1' || p.target.closed !== true) {
    throw new Error('This template uses unsupported model assumptions or units.')
  }
  return { aMin: p.domain.A.lower, aMax: p.domain.A.upper, keMin: p.domain.ke.lower, keMax: p.domain.ke.upper,
    kaMin: p.domain.ka.lower, kaMax: p.domain.ka.upper, targetMin: p.target.lower, targetMax: p.target.upper,
    allowanceOrigin: `Template default to review: ${allowance_origin}`, methods,
    defaultAllowance: default_hard_allowance }
}

export function setupResearcherTools({ context, getDraft, applyTemplate, button, node, exactRecord, save }) {
  let state
  function reset() { state = { name: '', description: '', allowance: '', left: '', right: '', selected: '', templates: [], preview: null, comparison: null } }
  reset()
  function field(parent, label, key, onChange = () => {}) {
    const wrapper = node('label', label); wrapper.className = 'stack'
    const input = document.createElement('input'); input.value = state[key]; input.maxLength = key === 'description' ? 2000 : 128
    input.addEventListener('input', () => { state[key] = input.value; onChange() })
    wrapper.append(input); parent.append(wrapper)
  }
  function render({ review, investigations, reports }) {
    const { api, workspace, run, report, inputs } = context()
    const ready = Boolean(api && workspace)
    const setup = node('details', ''); setup.open = true; setup.append(node('summary', 'Reusable experiment templates'))
    setup.append(node('p', 'Save the current prepared setup’s units, model, ranges and explicit allowance default. Measurements, experiment identity and approvals are never copied. Applying defaults keeps your current measurement rows; review them for the new experiment.'))
    setup.append(node('p', 'The saved list shows the latest 100 templates in this workspace.'))
    field(setup, 'Template name', 'name'); field(setup, 'Template description', 'description')
    field(setup, 'Default hard allowance (mg/L; exact decimal or fraction)', 'allowance')
    button(setup, 'Save current setup as template', async () => {
      if (!state.name.trim() || !state.allowance.trim()) throw new Error('Enter a template name and a default allowance.')
      const question = getDraft().question
      await api.json(`/workspaces/${workspace}/experiment-templates`, {
        name: state.name.trim(), description: state.description, problem_id: inputs.problem.id,
        problem_digest: inputs.problem.digest, default_hard_allowance: parseExact(state.allowance),
        allowance_origin: question.allowanceOrigin, methods: question.methods || '',
      })
      state.templates = await api.json(`/workspaces/${workspace}/experiment-templates`)
    }, !ready || !inputs)
    button(setup, 'Refresh saved templates', async () => { state.templates = await api.json(`/workspaces/${workspace}/experiment-templates`) }, !ready)
    const select = document.createElement('select'); select.setAttribute('aria-label', 'Saved experiment template')
    const placeholder = node('option', 'Choose a saved template'); placeholder.value = ''; select.append(placeholder)
    for (const template of state.templates) { const option = node('option', template.body.name); option.value = template.id; select.append(option) }
    select.value = state.selected
    const preview = node('div', '')
    select.addEventListener('change', () => { state.selected = select.value; state.preview = null; preview.replaceChildren() })
    setup.append(select)
    button(setup, 'Preview setup template', async () => {
      if (!state.selected) throw new Error('Choose a saved template.')
      const selected = state.selected
      const loaded = await api.json(`/experiment-templates/${encodeURIComponent(selected)}/draft`)
      if (state.selected === selected && loaded.template_id === selected) state.preview = loaded
    }, !ready)
    if (state.preview) {
      preview.append(exactRecord('Unapproved template defaults', state.preview))
      button(preview, 'Apply template defaults to draft', () => {
        if (state.preview?.template_id !== state.selected) throw new Error('Preview the currently selected template first.')
        applyTemplate(templateFields(state.preview)); state.preview = null
      }, !ready)
    }
    setup.append(preview)
    review.append(setup)

    const compare = node('details', ''); compare.open = true; compare.append(node('summary', 'Compare two investigations'))
    compare.append(node('p', 'Enter two run identifiers from this workspace. Compare exact measurements, assumptions and recorded outcomes. This comparison starts no scientific work.'))
    const comparison = node('div', '')
    const clearComparison = () => { state.comparison = null; comparison.replaceChildren() }
    field(compare, 'First run identifier', 'left', clearComparison); field(compare, 'Second run identifier', 'right', clearComparison)
    button(compare, 'Compare investigations', async () => {
      if (!state.left.trim() || !state.right.trim()) throw new Error('Enter both run identifiers.')
      state.comparison = await api.json(`/workspaces/${workspace}/investigations/compare?left_run_id=${encodeURIComponent(state.left.trim())}&right_run_id=${encodeURIComponent(state.right.trim())}`)
    }, !ready)
    if (state.comparison && state.comparison.left.run_id === state.left.trim() && state.comparison.right.run_id === state.right.trim()) {
      const result = state.comparison
      comparison.append(node('p', result.scope))
      if (!result.same_experiment_and_model) comparison.append(node('p', 'These runs name different experiments or models; interpret their outcomes in their separate scopes.'))
      for (const [title, changes] of [['Input changes', result.input_changes], ['Result changes', result.result_changes]]) {
        comparison.append(node('h4', `${title}: ${changes.length}`))
        const table = node('table', ''), head = node('tr', '')
        for (const label of ['Field', 'First investigation', 'Second investigation']) head.append(node('th', label))
        table.append(head)
        for (const change of changes) {
          const row = node('tr', '')
          row.append(node('th', change.path), node('td', change.before_present ? JSON.stringify(change.before) : '(absent)'),
            node('td', change.after_present ? JSON.stringify(change.after) : '(absent)')); table.append(row)
        }
        const region = node('div', ''); region.className = 'table-region'; region.tabIndex = 0; region.append(table); comparison.append(region)
      }
      comparison.append(exactRecord('Exact comparison and record identities', result))
    }
    compare.append(comparison)
    investigations.append(compare)
    if (report && run) button(reports, 'Download reviewer ZIP package', async () => {
      const download = await api.download(`/reports/${report.id}/package`)
      save(download.bytes, `dr-bean-${report.id}-reviewer.zip`, 'application/zip')
    }, !ready)
  }
  return { reset, render }
}
