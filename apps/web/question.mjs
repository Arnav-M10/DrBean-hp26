import { compareExact, parseExact } from './exact.mjs';

const bounds = [
  { min: 'aMin', max: 'aMax', name: 'Amplitude A', positive: true },
  { min: 'keMin', max: 'keMax', name: 'Elimination rate ke', positive: true },
  { min: 'kaMin', max: 'kaMax', name: 'Absorption rate ka', positive: true },
  { min: 'targetMin', max: 'targetMax', name: 'Target interval for ke', positive: false },
];

function readBound(question, field, positive, errors) {
  let value;
  try {
    value = parseExact(question[field]);
  } catch {
    errors.push({ field, message: 'Enter a decimal, integer, or fraction.' });
    return;
  }
  if (positive && compareExact(value, '0/1') <= 0) {
    errors.push({ field, message: 'Enter a value greater than zero.' });
    return;
  }
  return value;
}

export function validateQuestion(question) {
  const errors = [];
  const exact = {};

  for (const { min, max, name, positive } of bounds) {
    const lower = readBound(question, min, positive, errors);
    const upper = readBound(question, max, positive, errors);
    if (lower !== undefined) exact[min] = lower;
    if (upper !== undefined) exact[max] = upper;
    if (lower !== undefined && upper !== undefined && compareExact(lower, upper) > 0) {
      errors.push({ field: max, message: `${name} upper bound must be at least its lower bound.` });
    }
  }

  if (exact.keMin !== undefined && exact.kaMax !== undefined && compareExact(exact.kaMax, exact.keMin) <= 0) {
    errors.push({ field: 'kaMax', message: 'The bounds must allow the absorption rate ka to exceed the elimination rate ke.' });
  }

  if (typeof question.allowanceOrigin !== 'string' || !question.allowanceOrigin.trim()) {
    errors.push({ field: 'allowanceOrigin', message: 'Describe how you chose the hard allowances.' });
  }

  return { errors, exact };
}
