import { liveGeminiAvailable } from './api.mjs'

export function explanationRequest({ runId, text, model, revision, operationId }) {
  if (!runId || !text.trim() || !model || !Number.isSafeInteger(revision) || revision < 0) throw new Error('Open a check and enter a question before asking Gemini.')
  return {
    operation: 'explain', client_operation_id: operationId,
    expected_conversation_revision: revision, run_id: runId, text: text.trim(),
    source_asset_ids: [], context: {},
    consent: { provider: 'gemini', model, source_asset_ids: [], include_notes: true, include_existing_values: true, accepted: true },
  }
}

export function setupAssistantWorkflow({ context, button, node, exactRecord }) {
  let selectedRun, question = '', consent = false, response, pending, budget
  function reset() { selectedRun = response = pending = budget = undefined; question = ''; consent = false }
  function render(parent) {
    const { api, workspace, busy, capabilities, run } = context()
    if (!api || !workspace || !liveGeminiAvailable(capabilities)) return
    if (selectedRun !== run?.id) { reset(); selectedRun = run?.id }
    const section = node('section', ''); section.id = 'gemini-explanation'; parent.append(section)
    section.append(node('h3', 'Ask Gemini about this check'), node('p', `Model: ${capabilities.gemini.model}. Gemini’s answer is commentary only. The result above comes from the checked evidence, and nothing you ask here starts a check or adds a reading.`))
    button(section, 'Show Gemini call budget', async () => { budget = await api.json(`/workspaces/${workspace}/provider-budget`) })
    if (budget) section.append(exactRecord('Server Gemini budget and reservations', budget))
    if (!run || !run.evidence?.length) {
      section.append(node('p', 'Open a finished check to ask Gemini about it.'))
      return
    }
    const questionLabel = node('label', 'Your question about this check'); questionLabel.className = 'stack'
    const input = node('textarea', ''); input.id = 'gemini-question'; input.maxLength = 4000; input.value = question; input.disabled = busy
    input.placeholder = 'What does this result mean, and what should I review next?'
    questionLabel.append(input); section.append(questionLabel)
    section.append(node('p', `Selected run: ${run.id}. The request includes your question, this run's stored research inputs and evidence, and up to eight earlier questions for the same selected references. It sends no source images. One bounded model request is made, with no automatic retry or paid-model fallback.`))
    const consentLabel = node('label', ` Send this question and selected research context to Google Gemini (${capabilities.gemini.model}).`)
    const check = node('input', ''); check.type = 'checkbox'; check.id = 'gemini-explanation-consent'; check.checked = consent; check.disabled = busy
    consentLabel.prepend(check); section.append(consentLabel)
    const send = button(section, pending ? 'Retrieve the same Gemini request' : 'Ask Gemini for an explanation', async () => {
      if (!consent || !question.trim()) throw new Error('Enter a question and accept its disclosure first.')
      if (!pending) {
        const state = await api.json(`/workspaces/${workspace}`)
        pending = explanationRequest({ runId: run.id, text: question, model: capabilities.gemini.model, revision: state.conversation_revision, operationId: crypto.randomUUID() })
      }
      try {
        const loaded = await api.assistantTurn(workspace, pending)
        if (loaded.workspace_id !== workspace || loaded.kind !== 'assistant_response' || loaded.body.input_references.run_id !== run.id) throw new Error('Gemini’s answer belongs to a different check. Reopen this check and ask again.')
        response = loaded; pending = undefined; consent = false
      } catch (error) {
        // A lost response retains the exact original key and body. Resending it
        // retrieves that operation; it never creates another provider attempt.
        if (error.kind === 'rejected') pending = undefined
        throw error
      }
    }, !consent || !question.trim())
    check.addEventListener('change', () => { consent = check.checked; send.disabled = busy || !consent || !question.trim() })
    input.addEventListener('input', () => {
      question = input.value; consent = false; pending = undefined; check.checked = false; send.disabled = true
      send.textContent = 'Ask Gemini for an explanation'
    })
    if (pending) section.append(node('p', 'This request has no confirmed answer yet. Retrieving it asks the server about the same request and does not send a new one. Editing the question makes a new request, which needs your permission again.'))
    if (!response) return
    const body = response.body
    section.append(node('h4', 'Statements from the evidence records'))
    for (const statement of body.critical_statements ?? []) section.append(node('p', statement))
    if (body.model_commentary) section.append(node('h4', 'Gemini commentary, not checked by Dr. Bean'), node('p', body.model_commentary))
    if (body.commentary_status === 'suppressed') section.append(node('p', 'Gemini commentary was withheld because the evidence records did not support it. The recorded results above are unchanged.'))
    if (body.message) section.append(node('p', body.message))
    if (body.code) section.append(node('p', `Response code: ${body.code}.`))
    section.append(exactRecord('Exact assistant response and provider attempt identity', response))
  }
  return { reset, render }
}
