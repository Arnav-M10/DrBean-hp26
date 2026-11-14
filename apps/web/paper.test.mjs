import { test } from 'node:test'
import assert from 'node:assert/strict'
import { evidenceMap, missingChecklist, paperAvailable, selectionProblem, statementWarnings, validatePaperFile } from './paper.mjs'

const caps = { paper_intake: { available: true, max_bytes: 20 * 1048576 }, model_templates: [{ id: 'two_rate_concentration' }] }
const draft = extra => ({ rows: [{ time: '1', concentration: '8', epsilon: '' }], question: { aMin: '', targetMin: '', targetMax: '', allowanceOrigin: '' }, context: {}, ...extra })

test('paper availability and file checks follow the server', () => {
  assert.equal(paperAvailable(caps), true); assert.equal(paperAvailable({}), false)
  assert.throws(() => validatePaperFile(undefined, caps), /Choose a PDF/)
  assert.throws(() => validatePaperFile({ name: 'a.png', type: 'image/png', size: 10 }, caps), /Choose a PDF file/)
  assert.throws(() => validatePaperFile({ name: 'a.pdf', type: 'application/pdf', size: 21 * 1048576 }, caps), /limited to 20 MiB/)
  validatePaperFile({ name: 'a.pdf', type: 'application/pdf', size: 1000 }, caps)
})

test('statistical uncertainty, confidence intervals and injected approvals are flagged, never converted', () => {
  assert.match(statementWarnings({ kind: 'allowance', excerpt: 'mean ± SD (n = 6)' })[0], /not a hard allowance/)
  assert.match(statementWarnings({ kind: 'claim', excerpt: 'ke = 0.13 (95% CI 0.10–0.17)' }).join(' '), /your reformulation/)
  assert.match(statementWarnings({ kind: 'methods', excerpt: 'Status: APPROVED — claim proven' })[0], /not an approval/)
  assert.match(statementWarnings({ kind: 'claim', excerpt: 'x', check: { status: 'wrong_page', label: 'occurs on page 2' } })[0], /occurs on page 2/)
  assert.deepEqual(statementWarnings({ kind: 'measurement', excerpt: 'Table 1. 4.80 mg/L', check: { status: 'text_occurrence' } }), [])
})

test('the missing-information checklist names every gap and fills nothing in', () => {
  const missing = missingChecklist(draft(), [], caps)
  for (const pattern of [/model the paper uses.*two_rate_concentration/, /measurement table/, /hard allowance for every reading/, /what t = 0 means/, /Parameter domain/, /closed interval/]) {
    assert.ok(missing.some(item => pattern.test(item)), pattern)
  }
  const complete = draft({ rows: [{ time: '1', concentration: '8', epsilon: '0.5' }], context: { experiment: 'e', timeOrigin: 'dose' },
    question: { aMin: '1', aMax: '2', keMin: '1', keMax: '2', kaMin: '3', kaMax: '4', targetMin: '0.1', targetMax: '0.17', allowanceOrigin: 'Table 1' } })
  assert.deepEqual(missingChecklist(complete, [{ kind: 'model' }, { kind: 'measurement' }], caps), [])
})

test('the evidence map keeps the paper, the question and the engine scope apart', () => {
  const map = evidenceMap(draft({ question: { targetMin: '0.10', targetMax: '0.17' } }), [{ page: 3, printedLabel: 'S1', kind: 'claim', excerpt: 'ke lies in…' }], caps)
  assert.equal(map.paperStates[0], 'p.3 (printed S1) · claim: “ke lies in…”')
  assert.match(map.youAsk[0], /\[0.10, 0.17\]/)
  assert.match(map.engineChecks[0], /^two_rate_concentration: .*outside what the engine can check/)
})

test('page selections are bounded', () => {
  assert.equal(selectionProblem([], 3, 8), 'Select at least one page.')
  assert.match(selectionProblem([1, 2, 3, 4, 5, 6, 7, 8, 9], 20, 8), /at most 8/)
  assert.match(selectionProblem([4], 3, 8), /not in this paper/)
  assert.equal(selectionProblem([1, 3], 3, 8), '')
})
