import { datasetBody, problemBody } from './manual.mjs'

function assumptionValues(dataset, problem) {
  const values = { experiment_id: dataset.experiment_id, time_origin: dataset.time_origin }
  dataset.rows.forEach((row, index) => {
    for (const key of ['time', 'concentration', 'hard_allowance']) values[`rows[${index}].${key}`] = row[key]
    values[`rows[${index}].included`] = String(row.included)
  })
  for (const key of ['model', 'observable', 'initial_concentration', 'time_unit', 'concentration_unit', 'rate_unit']) values[key] = problem[key]
  for (const parameter of ['A', 'ke', 'ka']) for (const side of ['lower', 'upper']) values[`domain.${parameter}.${side}`] = problem.domain[parameter][side]
  for (const key of ['lower', 'upper', 'parameter']) values[`target.${key}`] = problem.target[key]
  return values
}

export function setupSourceWorkflow({ context, getDraft, button, node, exactRecord, useInputs }) {
  let source, imageUrl, proposal, review, fields = [], resolved = new Set(), proposalId = '', explanation = '', prepared, materialized
  function reset() {
    if (imageUrl) URL.revokeObjectURL(imageUrl)
    source = imageUrl = proposal = review = prepared = materialized = undefined
    fields = []; resolved = new Set(); proposalId = explanation = ''
  }
  async function showSource(record) {
    const { api, workspace } = context()
    if (record.workspace_id !== workspace) throw new Error('Select the source workspace first.')
    const downloaded = await api.download(`/source-assets/${encodeURIComponent(record.id)}/content`, record.body)
    if (imageUrl) URL.revokeObjectURL(imageUrl)
    imageUrl = URL.createObjectURL(new Blob([downloaded.bytes], { type: record.body.observed_media_type }))
    source = record
  }
  function render(parent) {
    const { api, workspace, busy } = context()
    const section = node('section', ''); section.id = 'source-review'; parent.append(section)
    section.append(node('h3', 'Source and value review'), node('p', 'Gemini is a disabled placeholder. Upload retains a source locally without extraction or scientific approval. Enter measurements manually when no reviewed proposal is available.'))
    const fileLabel = node('label', 'Public or synthetic source image'); fileLabel.className = 'stack'
    const file = node('input', ''); file.type = 'file'; file.accept = 'image/png,image/jpeg'; file.id = 'source-image-file'; file.disabled = busy
    fileLabel.append(file); section.append(fileLabel)
    const originLabel = node('label', 'Source origin'); originLabel.className = 'stack'
    const origin = node('select', ''); origin.id = 'source-origin'
    for (const [value, text] of [['', 'Choose origin'], ['synthetic', 'Synthetic'], ['public', 'Public']]) { const option = node('option', text); option.value = value; origin.append(option) }
    originLabel.append(origin); section.append(originLabel)
    button(section, 'Upload source for inspection', async () => {
      const selected = file.files[0]
      if (!selected) throw new Error('Choose a source image first.')
      const record = await api.uploadSource(workspace, selected, origin.value)
      reset(); await showSource(record)
    }, !api || !workspace)
    if (source) {
      section.append(node('p', `Retained source ${source.id}. Origin: ${source.body.origin}.`))
      const image = node('img', ''); image.src = imageUrl; image.alt = 'Retained source for transcription review'; image.style.maxWidth = '100%'; section.append(image)
    }
    const label = node('label', 'Existing intake proposal identifier'); label.className = 'stack'
    const input = node('input', ''); input.id = 'source-proposal-id'; input.value = proposalId; input.disabled = busy
    input.addEventListener('input', () => { proposalId = input.value }); label.append(input); section.append(label)
    button(section, 'Open source proposal', async () => {
      const loaded = await api.json(`/records/${encodeURIComponent(proposalId.trim())}`)
      if (loaded.kind !== 'intake_proposal' || loaded.workspace_id !== workspace) throw new Error('Choose an intake proposal from this workspace.')
      const record = await api.json(`/source-assets/${encodeURIComponent(loaded.body.source_asset_id)}`)
      if (record.body.sha256 !== loaded.body.source_digest) throw new Error('Proposal and source identities differ.')
      await showSource(record); proposal = loaded; review = prepared = materialized = undefined; resolved = new Set()
      fields = loaded.body.fields.map(field => ({ field_path: field.field_path, value: field.original_value ?? field.candidate_exact ?? '', origin: 'confirmed_transcription', correction_reason: '' }))
    }, !api || !workspace)
    if (!proposal) return
    section.append(node('p', 'Review every proposed value against the retained image. Controlled proposals are test output; no live Gemini qualification is claimed.'), exactRecord('Proposal and source locators', proposal))
    fields.forEach((field, index) => {
      const original = proposal.body.fields[index]
      section.append(node('p', `${field.field_path} · original ${original.original_value ?? 'unreadable'} · proposed exact ${original.candidate_exact ?? 'unavailable'} · ${original.locator.label}: ${original.locator.excerpt}`))
      for (const [key, title] of [['value', 'Reviewed value'], ['correction_reason', 'Correction or assumption reason']]) {
        const label = node('label', `${field.field_path} ${title}`); label.className = 'stack'
        const control = node('input', ''); control.value = field[key]; control.disabled = busy || Boolean(review); control.maxLength = key === 'value' ? 256 : 2000
        control.addEventListener('input', () => { field[key] = control.value }); label.append(control); section.append(label)
      }
      const label = node('label', `${field.field_path} value origin`); label.className = 'stack'
      const select = node('select', ''); select.disabled = busy || Boolean(review)
      for (const [value, text] of [['confirmed_transcription', 'Confirmed transcription'], ['corrected_transcription', 'Corrected transcription'], ['human_assumption', 'Human assumption']]) { const option = node('option', text); option.value = value; select.append(option) }
      select.value = field.origin; select.addEventListener('change', () => { field.origin = select.value }); label.append(select); section.append(label)
    })
    for (const diagnostic of proposal.body.diagnostics ?? []) {
      const id = `${diagnostic.code}:${diagnostic.field_path}`
      const label = node('label', `Resolved ${id}: ${diagnostic.message}`); label.className = 'stack'
      const check = node('input', ''); check.type = 'checkbox'; check.checked = resolved.has(id); check.disabled = busy || Boolean(review)
      check.addEventListener('change', () => { if (check.checked) resolved.add(id); else resolved.delete(id) }); label.prepend(check); section.append(label)
    }
    button(section, 'Accept reviewed source values', async () => {
      review = await api.json(`/workspaces/${workspace}/intake-proposals/${proposal.id}/review`, { expected_proposal_digest: proposal.digest, reviewed_fields: fields, resolved_diagnostics: [...resolved] })
    }, Boolean(review))
    if (!review) return
    button(section, 'Revise source review', () => { review = prepared = materialized = undefined })
    section.append(exactRecord('Source review receipt', review), node('p', 'Complete Measurements and Question with these reviewed values. Explain the remaining assumptions before creating executable inputs. The server checks exact agreement with this review.'))
    const assumptionLabel = node('label', 'Explanation for the remaining manually reviewed inputs and assumptions'); assumptionLabel.className = 'stack'
    const assumption = node('textarea', ''); assumption.value = explanation; assumption.disabled = busy || Boolean(prepared); assumption.maxLength = 2000
    assumption.addEventListener('input', () => { explanation = assumption.value }); assumptionLabel.append(assumption); section.append(assumptionLabel)
    button(section, 'Preview source-bound inputs', () => {
      if (!explanation.trim()) throw new Error('Explain the remaining manually reviewed inputs and assumptions.')
      const draft = getDraft(), dataset = datasetBody(draft, draft.context), complete = problemBody(draft, { id: '', digest: '' })
      const { schema_version, dataset_id, dataset_digest, ...problem } = complete
      prepared = { expected_review_digest: review.digest, dataset, problem, human_assumptions: Object.fromEntries(Object.keys(assumptionValues(dataset, problem)).map(path => [path, explanation.trim()])) }
    }, Boolean(prepared))
    if (!prepared) return
    button(section, 'Revise source-bound input preview', () => { prepared = materialized = undefined })
    section.append(exactRecord('Exact source-bound input preview and assumption explanations', prepared))
    button(section, 'Accept preview and prepare investigation plan', async () => {
      materialized = materialized ?? await api.json(`/workspaces/${workspace}/intake-reviews/${review.id}/materialize`, prepared)
      await useInputs(materialized)
    })
    section.append(node('p', 'The investigation plan requires its own explicit approval before execution.'))
  }
  return { render, reset }
}
