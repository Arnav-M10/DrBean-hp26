import { test } from 'node:test'
import assert from 'node:assert/strict'
import { explanationRequest, setupAssistantWorkflow } from './assistant-workflow.mjs'

test('explanation disclosure binds the exact selected run and sends no source attachment or execution approval', () => {
  const body = explanationRequest({ runId: 'run_one', text: ' Explain this result. ', model: 'gemini-test', revision: 4, operationId: 'turn_one' })
  assert.equal(body.run_id, 'run_one')
  assert.equal(body.expected_conversation_revision, 4)
  assert.equal(body.client_operation_id, 'turn_one')
  assert.equal(body.operation, 'explain')
  assert.equal(body.text, 'Explain this result.')
  assert.deepEqual(body.source_asset_ids, [])
  assert.deepEqual(body.consent.source_asset_ids, [])
  assert.equal(body.consent.model, 'gemini-test')
  assert.equal(body.consent.include_notes, true)
  assert.equal(body.consent.include_existing_values, true)
  assert.equal('approval' in body, false)
  assert.throws(() => explanationRequest({ runId: 'run_one', text: ' ', model: 'gemini-test', revision: 4 }), /question/)
})

// The small DOM fixture exercises the controls rather than invoking a model.
function element(tag, text = '') {
  return { tag, textContent: text, children: [], listeners: {},
    append(...items) { this.children.push(...items) }, prepend(item) { this.children.unshift(item) },
    addEventListener(name, fn) { this.listeners[name] = fn },
  }
}
function all(parent) { return [parent, ...parent.children.flatMap(all)] }

test('explanation makes no provider request before consent and exact same uncertain request is retrieved', async () => {
  const calls = [], context = { workspace: 'ws_one', busy: false, run: { id: 'run_one', evidence: [{}] },
    capabilities: { gemini: { execution_mode: 'live', dispatch_enabled: true, model: 'gemini-test' } },
    api: { async json(path) { calls.push({ read: path }); return { conversation_revision: 2 } },
      async assistantTurn(workspace, body) {
        calls.push({ workspace, body: structuredClone(body) })
        if (calls.filter(call => call.body).length === 1) throw Object.assign(new Error('Uncertain response'), { kind: 'uncertain' })
        return { kind: 'assistant_response', workspace_id: workspace, body: { input_references: { run_id: body.run_id }, critical_statements: ['Stored evidence statement.'], commentary_status: 'suppressed' } }
      } },
  }
  const button = (parent, text, action, disabled) => { const item = element('button', text); Object.assign(item, { action, disabled }); parent.append(item); return item }
  const workflow = setupAssistantWorkflow({ context: () => context, button, node: element, exactRecord: (title) => element('details', title) })
  let parent = element('main'); workflow.render(parent)
  assert.equal(calls.length, 0)
  let nodes = all(parent), question = nodes.find(n => n.id === 'gemini-question'), consent = nodes.find(n => n.id === 'gemini-explanation-consent')
  let send = nodes.find(n => n.textContent === 'Ask Gemini for an explanation')
  assert.equal(send.disabled, true)
  await assert.rejects(send.action(), /accept/)
  question.value = 'Explain this result.'; question.listeners.input()
  assert.equal(send.disabled, true)
  consent.checked = true; consent.listeners.change()
  assert.equal(send.disabled, false)
  await assert.rejects(send.action(), /Uncertain/)
  assert.equal(calls.filter(call => call.body).length, 1)
  parent = element('main'); workflow.render(parent); nodes = all(parent)
  send = nodes.find(n => n.textContent === 'Retrieve the same Gemini request')
  await send.action()
  const modelCalls = calls.filter(call => call.body)
  assert.deepEqual(modelCalls[0], modelCalls[1])
  assert.equal(calls.filter(call => call.read).length, 1)
  parent = element('main'); workflow.render(parent); nodes = all(parent)
  assert.equal(nodes.find(n => n.id === 'gemini-explanation-consent').checked, false)
  assert.ok(nodes.some(n => n.textContent.includes('commentary was withheld')))
  assert.ok(nodes.some(n => n.textContent === 'Stored evidence statement.'))
})
