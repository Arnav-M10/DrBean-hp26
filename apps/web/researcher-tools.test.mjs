import test from 'node:test'
import assert from 'node:assert/strict'
import { templateFields } from './researcher-tools.mjs'

const preview = { requires_review: true, defaults: { format: 'experiment-template.v1', requires_review: true,
  problem_inputs: { model: 'two_rate_concentration', initial_concentration: '0/1', time_unit: 'h', concentration_unit: 'mg/L', rate_unit: '1/h',
    domain: { A: { lower: '1/1', upper: '30/1' }, ke: { lower: '1/100', upper: '1/2' }, ka: { lower: '1/1', upper: '8/1' } },
    target: { lower: '1/10', upper: '1/5', closed: true } },
  default_hard_allowance: '1/2', allowance_origin: 'Reviewed calibration', methods: 'Confirm units' } }

test('template application preserves exact setup but never supplies experiment identity or approval', () => {
  const fields = templateFields(preview)
  assert.equal(fields.keMin, '1/100')
  assert.equal(fields.defaultAllowance, '1/2')
  assert.match(fields.allowanceOrigin, /default to review/)
  for (const key of ['experiment-id', 'dataset-origin', 'time-origin', 'approval_id', 'rows']) assert.equal(key in fields, false)
})

test('unsupported units and accepted-looking template envelopes fail before applying', () => {
  assert.throws(() => templateFields({ ...preview, requires_review: false }))
  const changed = structuredClone(preview); changed.defaults.problem_inputs.time_unit = 'min'
  assert.throws(() => templateFields(changed), /unsupported/)
})
