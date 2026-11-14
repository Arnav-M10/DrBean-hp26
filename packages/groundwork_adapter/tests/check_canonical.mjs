// Fixture-only interoperability check. The server owns admission/canonicalization;
// this is not a production client canonicalizer or shared transport schema.
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';

const fixture = JSON.parse(readFileSync(new URL('../fixtures/canonicalization_golden.json', import.meta.url), 'utf8'));
function ordered(value) {
  if (Array.isArray(value)) return value.map(ordered);
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, ordered(value[key])]));
  }
  return value;
}
const bytes = Buffer.from(JSON.stringify(ordered(fixture.body)), 'utf8');
assert.equal(bytes.toString('hex'), fixture.canonical_utf8_hex);
assert.equal(createHash('sha256').update(Buffer.from('dr-bean:report:v1\n')).update(bytes).digest('hex'), fixture.semantic_digest);
console.log('DB-SC-1 canonical byte and semantic digest fixture matches Node.');
