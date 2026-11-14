import assert from 'node:assert/strict';
import test from 'node:test';
import { validateQuestion } from './question.mjs';

const question = {
  aMin: '0.001',
  aMax: '30',
  keMin: '0.015',
  keMax: '0.35',
  kaMin: '0.4',
  kaMax: '8',
  targetMin: '0.10',
  targetMax: '0.17',
  allowanceOrigin: 'Team-authored demonstration assumption',
};

test('normalizes exact decimal spellings while preserving the draft', () => {
  const { errors, exact } = validateQuestion(question);
  assert.deepEqual(errors, []);
  assert.deepEqual(exact, {
    aMin: '1/1000',
    aMax: '30/1',
    keMin: '3/200',
    keMax: '7/20',
    kaMin: '2/5',
    kaMax: '8/1',
    targetMin: '1/10',
    targetMax: '17/100',
  });
  assert.equal(question.targetMin, '0.10');
});

test('admits a singleton closed target and overlapping rate ranges', () => {
  const edited = { ...question, kaMin: '0.2', targetMax: '1/10' };
  assert.deepEqual(validateQuestion(edited).errors, []);
});

test('rejects exact bounds that only allow ka at or below ke', () => {
  const edited = { ...question, kaMin: '0.01', kaMax: '3/200' };
  assert.deepEqual(validateQuestion(edited).errors.map(({ field }) => field), ['kaMax']);
});

test('identifies malformed, nonpositive, reversed, and missing values by field', () => {
  const edited = { ...question, aMin: '0', aMax: 'one', targetMax: '0.09', allowanceOrigin: ' ' };
  const { errors, exact } = validateQuestion(edited);
  assert.deepEqual(errors.map(({ field }) => field), ['aMin', 'aMax', 'targetMax', 'allowanceOrigin']);
  assert.equal(exact.aMin, undefined);
  assert.equal(exact.aMax, undefined);
});
