import { test } from 'node:test'
import assert from 'node:assert/strict'
import { BeanApi, qualifiedScience } from './api.mjs'
import { datasetBody, problemBody, planRequest, researchObjective } from './manual.mjs'

test('uncertain mutation retry retains its operation key and token never enters body or URL', async () => {
  const seen = []
  const api = new BeanApi('private-token', async (url, options) => {
    seen.push({ url, ...options })
    if (seen.length === 1) throw new Error('connection lost')
    return new Response('{}')
  })
  await assert.rejects(api.json('/plans/p/approvals', { accepted: true }))
  await api.json('/plans/p/approvals', { accepted: true })
  assert.equal(seen[0].headers['Idempotency-Key'], seen[1].headers['Idempotency-Key'])
  assert.equal(seen[0].headers.Authorization, 'Bearer private-token')
  assert.ok(!seen[0].url.includes('private-token') && !seen[0].body.includes('private-token'))
})
test('mismatched download bytes are rejected', async () => {
  const api = new BeanApi('token', async () => new Response('{}', { headers: { 'X-Artifact-SHA256': 'incorrect' } }))
  await assert.rejects(api.download('/artifacts/e'), /digest mismatch/)
})
test('unknown or unqualified capabilities fail closed', () => {
  assert.equal(Boolean(qualifiedScience({})), false)
  assert.equal(Boolean(qualifiedScience({ contract_version: 'DB-SC-1', policy_version: 'GF-2', science: { verified_in_environment: false } })), false)
})
test('manual wire mapping preserves excluded duplicates, original spelling and server identities', () => {
  const draft = { rows: [0, 1, 2, 2].map((t, i) => ({ id: i + 1, time: `${t}.00`, concentration: '1.20', epsilon: '0.1', included: i !== 3 })), sources: [], question: {
    aMin: '1', aMax: '12', keMin: '0.1', keMax: '0.3', kaMin: '0.5', kaMax: '2', targetMin: '0.10', targetMax: '17/100', allowanceOrigin: 'Reviewed hard bound', methods: '', goal: '',
  } }
  const dataset = datasetBody(draft, { experiment: 'exp', timeOrigin: 'Dose at t=0', origin: 'actual' })
  assert.equal(dataset.rows.length, 4)
  assert.equal(dataset.rows[3].included, false)
  assert.equal(dataset.rows[3].time, dataset.rows[2].time)
  assert.equal(dataset.rows[0].original_values.concentration, '1.20')
  const problem = problemBody(draft, { id: 'server-dataset', digest: 'server-digest' })
  assert.equal(problem.dataset_digest, 'server-digest')
  const plan = planRequest({ id: 'server-problem', digest: 'server-problem-digest', body: problem })
  assert.equal(plan.plan.scenarios[0].problem_digest, 'server-problem-digest')
  assert.equal(plan.plan.provider_disclosure.provider, 'none')
})

test('plans carry the Counterdex profile and an explicit objective even when the goal is blank', () => {
  const problem = { id: 'p', digest: 'd', body: { dataset_id: 'ds', target: { lower: '1/10', upper: '17/100' } } }
  const blank = planRequest(problem, '   ').plan
  assert.equal(blank.scientific_profile, 'counterdex.v1')
  assert.match(blank.objective.question, /closed interval \[1\/10, 17\/100\]/)
  assert.ok(blank.objective.success_criterion.includes('Nothing here proves the interval'))
  const stated = researchObjective(problem, 'Is the literature range justified?')
  assert.ok(stated.question.startsWith('Is the literature range justified?'))
  assert.ok(stated.question.includes('[1/10, 17/100]'))
  assert.ok(researchObjective(problem, 'x'.repeat(5000)).question.length <= 2000)
})
