import { datasetBody, problemBody } from './manual.mjs'
import { liveGeminiAvailable } from './api.mjs'

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

export function setupSourceWorkflow({ context, getDraft, button, node, exactRecord, useInputs, applyReviewedFields }) {
  let source, imageUrl, proposal, review, fields = [], resolved = new Set(), explanation = '', prepared, materialized, selectedFile, selectedOrigin = '', previewDraft, liveConsent = false, liveProposal = false
  function reset() {
    if (imageUrl) URL.revokeObjectURL(imageUrl)
    source = imageUrl = proposal = review = prepared = materialized = undefined
    selectedFile = previewDraft = undefined; selectedOrigin = ''
    fields = []; resolved = new Set(); explanation = ''; liveConsent = liveProposal = false
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
    const { api, workspace, busy, capabilities } = context()
    const live = liveGeminiAvailable(capabilities) && capabilities.source_intake?.execution_mode === 'live'
      && capabilities.source_intake.application_review_integration === 'available'
    const section = node('section', ''); section.id = 'source-review'; parent.append(section)
    section.append(node('h3', 'Source and value review'), node('p', live
      ? `Gemini (${capabilities.gemini.model}) can propose values from one public or synthetic image after your permission. Upload alone retains the source locally. You must review each proposal before it changes scientific inputs. CSV files belong in Measurements; this upload accepts PNG or JPEG images.`
      : 'Gemini is a disabled placeholder. Upload retains a source locally without extraction or scientific approval. Enter measurements manually when no reviewed proposal is available.'))
    const fileLabel = node('label', 'Public or synthetic source image'); fileLabel.className = 'stack'
    const file = node('input', ''); file.type = 'file'; file.accept = 'image/png,image/jpeg'; file.id = 'source-image-file'; file.disabled = busy
    file.addEventListener('change', () => { selectedFile = file.files[0] })
    if (selectedFile) fileLabel.append(node('span', selectedFile.name))
    fileLabel.append(file); section.append(fileLabel)
    const originLabel = node('label', 'Source origin'); originLabel.className = 'stack'
    const origin = node('select', ''); origin.id = 'source-origin'
    for (const [value, text] of [['', 'Choose origin'], ['synthetic', 'Synthetic'], ['public', 'Public']]) { const option = node('option', text); option.value = value; origin.append(option) }
    origin.value = selectedOrigin; origin.disabled = busy
    origin.addEventListener('change', () => { selectedOrigin = origin.value })
    originLabel.append(origin); section.append(originLabel)
    button(section, 'Upload source for inspection', async () => {
      const selected = selectedFile
      if (!selected) throw new Error('Choose a source image first.')
      const record = await api.uploadSource(workspace, selected, selectedOrigin)
      reset(); await showSource(record)
    }, !api || !workspace)
    if (source) {
      section.append(node('p', `Retained source ${source.id}. Origin: ${source.body.origin}.`))
      const image = node('img', ''); image.src = imageUrl; image.alt = 'Retained source for transcription review'; image.style.maxWidth = '100%'; section.append(image)
    }
    const controlled = capabilities?.source_intake?.execution_mode === 'controlled' && capabilities.source_intake.application_review_integration === 'available'
    section.append(node('p', controlled ? 'Controlled examples are enabled for exact supported synthetic images only. These authored values are not image understanding or Gemini transcription. Unknown or changed images require manual entry.' : 'Controlled proposals are unavailable in this server configuration. Manual entry remains available.'))
    button(section, live ? 'Use sample source image' : 'Use controlled example image', async () => {
      const response = await fetch('/examples/controlled-source.png')
      if (!response.ok) throw new Error('The controlled example image is unavailable. Upload a source or enter measurements manually.')
      const bytes = await response.blob()
      const record = await api.uploadSource(workspace, new File([bytes], 'controlled-source.png', { type: 'image/png' }), 'synthetic')
      reset(); await showSource(record)
    }, !api || !workspace || (!controlled && !live))
    function acceptProposal(loaded, isLive) {
      if (loaded.kind !== 'intake_proposal' || loaded.workspace_id !== workspace || loaded.body.source_asset_id !== source.id || loaded.body.source_digest !== source.body.sha256) throw new Error('Proposal and selected source identities differ.')
      proposal = loaded; review = prepared = materialized = undefined; resolved = new Set()
      liveProposal = isLive
      fields = loaded.body.fields.map(field => ({ field_path: field.field_path, value: field.original_value ?? field.candidate_exact ?? '', origin: 'confirmed_transcription', correction_reason: '' }))
    }
    button(section, 'Prepare controlled source proposal', async () => {
      const loaded = await api.json(`/workspaces/${workspace}/intake-proposals`, { execution_mode: 'controlled', source_id: source.id, expected_source_digest: source.body.sha256 })
      acceptProposal(loaded, false)
    }, !controlled || !source || source.body.origin !== 'synthetic')
    if (live && source) {
      section.append(node('p', 'This sends the displayed image and its source identity to Google Gemini. It makes one bounded request with no automatic retry or paid-model fallback. The free-tier account and server limits apply. No draft measurements or notes are included.'))
      const consentLabel = node('label', ` Send this selected ${source.body.origin} image to ${capabilities.gemini.model} for an unaccepted proposal.`)
      const consent = node('input', ''); consent.type = 'checkbox'; consent.id = 'gemini-source-consent'; consent.checked = liveConsent; consent.disabled = busy
      consentLabel.prepend(consent); section.append(consentLabel)
      const prepare = button(section, 'Ask Gemini to read this image', async () => {
        if (!liveConsent) throw new Error('Review and accept the selected image disclosure first.')
        const loaded = await api.json(`/workspaces/${workspace}/intake-proposals`, {
          source_id: source.id, notes: '', existing_values: {},
          consent: { provider: 'gemini', model: capabilities.gemini.model, source_asset_ids: [source.id], include_notes: false, include_existing_values: false, accepted: true },
        })
        acceptProposal(loaded, true); liveConsent = false
      }, !api || !workspace || !liveConsent)
      consent.addEventListener('change', () => { liveConsent = consent.checked; prepare.disabled = busy || !liveConsent })
    }
    const manual = node('a', 'Continue with manual measurements'); manual.href = '#inputs'; section.append(manual)
    if (!proposal) return
    section.append(node('p', proposal.body.label || (liveProposal ? 'Gemini image proposal. No values are accepted yet.' : 'Controlled example; not Gemini transcription.')))
    if (proposal.body.status === 'unavailable' || fields.length === 0) {
      section.append(node('p', 'Extraction unavailable for these image bytes. No values were accepted or added. Use manual measurements.'))
      return
    }
    section.append(node('p', liveProposal
      ? 'Review every proposed value and source locator against the retained image. Gemini can misread values. A source quotation or model proposal does not establish a scientific result.'
      : 'Review every proposed value against the retained image. Controlled proposals are test output; no live Gemini qualification is claimed.'), exactRecord('Proposal and source locators', proposal))
    fields.forEach((field, index) => {
      const original = proposal.body.fields[index]
      if (!field.value || original.ambiguity) section.append(node('p', `Needs review: ${field.field_path} — ${original.ambiguity || 'No proposed value; enter a reviewed value or assumption.'}`))
      section.append(node('p', `${field.field_path} · original ${original.original_value ?? 'unreadable'} · proposed exact ${original.candidate_exact ?? 'unavailable'} · ${original.locator.label}: ${original.locator.excerpt}`))
      for (const [key, title] of [['value', 'Reviewed value'], ['correction_reason', 'Correction or assumption reason']]) {
        const label = node('label', `${field.field_path} ${title}`); label.className = 'stack'
        const control = node('input', ''); control.value = field[key]; control.disabled = busy || Boolean(review); control.maxLength = key === 'value' ? 256 : 2000
        control.addEventListener('input', () => { field[key] = control.value }); label.append(control); section.append(label)
      }
      const label = node('label', `${field.field_path} value origin`); label.className = 'stack'
      const select = node('select', ''); select.setAttribute('aria-label', field.field_path + ' value origin'); select.disabled = busy || Boolean(review)
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
    button(section, 'Use reviewed values in measurement draft', () => applyReviewedFields(review, source))
    section.append(exactRecord('Source review receipt', review), node('p', 'Use the reviewed values in the measurement draft (replacing its rows), then complete Measurements and Question. Explain the remaining assumptions before creating executable inputs. The server checks exact agreement with this review.'))
    const assumptionLabel = node('label', 'Explanation for the remaining manually reviewed inputs and assumptions'); assumptionLabel.className = 'stack'
    const assumption = node('textarea', ''); assumption.value = explanation; assumption.disabled = busy || Boolean(prepared); assumption.maxLength = 2000
    assumption.addEventListener('input', () => { explanation = assumption.value }); assumptionLabel.append(assumption); section.append(assumptionLabel)
    button(section, 'Preview source-bound inputs', () => {
      if (!explanation.trim()) throw new Error('Explain the remaining manually reviewed inputs and assumptions.')
      const draft = getDraft(), dataset = datasetBody(draft, draft.context), complete = problemBody(draft, { id: '', digest: '' })
      previewDraft = JSON.stringify(draft)
      const { schema_version, dataset_id, dataset_digest, ...problem } = complete
      prepared = { expected_review_digest: review.digest, dataset, problem, human_assumptions: Object.fromEntries(Object.keys(assumptionValues(dataset, problem)).map(path => [path, explanation.trim()])) }
    }, Boolean(prepared))
    if (!prepared) return
    button(section, 'Revise source-bound input preview', () => { prepared = materialized = undefined })
    section.append(exactRecord('Exact source-bound input preview and assumption explanations', prepared))
    button(section, 'Accept preview and prepare investigation plan', async () => {
      if (JSON.stringify(getDraft()) !== previewDraft) throw new Error('Measurements or question changed. Revise the source-bound input preview before continuing.')
      materialized = materialized ?? await api.json(`/workspaces/${workspace}/intake-reviews/${review.id}/materialize`, prepared)
      await useInputs(materialized)
    })
    section.append(node('p', 'The investigation plan requires its own explicit approval before execution.'))
  }
  return { render, reset }
}
