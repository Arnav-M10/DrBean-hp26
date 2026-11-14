import { test } from 'node:test'
import assert from 'node:assert/strict'
import { setupSourceWorkflow } from './source-workflow.mjs'

function element(tag, text = '') {
  return { tag, textContent: text, style: {}, children: [], listeners: {},
    append(...items) { this.children.push(...items) }, prepend(item) { this.children.unshift(item) },
    addEventListener(name, fn) { this.listeners[name] = fn }, setAttribute(key, value) { this[key] = value },
  }
}
function all(parent) { return [parent, ...parent.children.flatMap(all)] }

test('upload stays local and image extraction sends only the selected image after separate consent', async () => {
  const calls = [], source = { id: 'source_one', workspace_id: 'ws_one', body: { origin: 'public', observed_media_type: 'image/png', sha256: 'a'.repeat(64) } }
  const context = { workspace: 'ws_one', busy: false,
    capabilities: { gemini: { dispatch_enabled: true, execution_mode: 'live', model: 'gemini-test' }, source_intake: { execution_mode: 'live', application_review_integration: 'available' } },
    api: { async uploadSource(workspace, file, origin) { calls.push({ kind: 'upload', workspace, origin }); return source },
      async download() { return { bytes: new Uint8Array([1, 2, 3]) } },
      async json(path, body) {
        calls.push({ kind: 'proposal', path, body })
        return { id: 'proposal_one', workspace_id: 'ws_one', kind: 'intake_proposal', body: { source_asset_id: source.id, source_digest: source.body.sha256,
          fields: [{ field_path: 'rows[0].time', original_value: '1', candidate_exact: '1/1', locator: { label: 'Time', excerpt: '1 h' } }] } }
      } },
  }
  const button = (parent, text, action, disabled) => { const item = element('button', text); Object.assign(item, { action, disabled }); parent.append(item); return item }
  const workflow = setupSourceWorkflow({ context: () => context, button, node: element, exactRecord: title => element('details', title), getDraft: () => ({}), useInputs() {}, applyReviewedFields() {} })
  try {
    let parent = element('main'); workflow.render(parent)
    let nodes = all(parent), file = nodes.find(n => n.id === 'source-image-file'), origin = nodes.find(n => n.id === 'source-origin')
    file.files = [{ name: 'public-source.png' }]; file.listeners.change()
    origin.value = 'public'; origin.listeners.change()
    await nodes.find(n => n.textContent === 'Upload source for inspection').action()
    assert.equal(calls.filter(call => call.kind === 'proposal').length, 0)
    parent = element('main'); workflow.render(parent); nodes = all(parent)
    const prepare = nodes.find(n => n.textContent === 'Ask Gemini to read this image'), consent = nodes.find(n => n.id === 'gemini-source-consent')
    assert.equal(prepare.disabled, true)
    await assert.rejects(prepare.action(), /accept/)
    consent.checked = true; consent.listeners.change()
    assert.equal(prepare.disabled, false)
    await prepare.action()
    const request = calls.find(call => call.kind === 'proposal')
    assert.equal(request.body.source_id, source.id)
    assert.deepEqual(request.body.consent.source_asset_ids, [source.id])
    assert.equal(request.body.consent.model, 'gemini-test')
    assert.equal(request.body.consent.include_notes, false)
    assert.equal(request.body.consent.include_existing_values, false)
    assert.equal(request.body.notes, '')
    assert.deepEqual(request.body.existing_values, {})
    assert.equal(calls.filter(call => call.kind === 'proposal').length, 1)
    parent = element('main'); workflow.render(parent); nodes = all(parent)
    assert.equal(nodes.find(n => n.id === 'gemini-source-consent').checked, false)
    assert.ok(nodes.some(n => n.textContent === 'Gemini image proposal. No values are accepted yet.'))
    assert.ok(nodes.some(n => n.textContent === 'Accept reviewed source values'))
  } finally { workflow.reset() }
})
