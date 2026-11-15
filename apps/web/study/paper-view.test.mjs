import test from 'node:test'
import assert from 'node:assert/strict'
import { paperNextHTML } from './paper-view.mjs'
import { page as sym } from './math.mjs'

test('paper follow-up uses the verified witness and actionable evidence links',()=>{
 const html=paperNextHTML({paperReview:{witness:{ke:'2/25'}}},sym)
 assert.match(html,/Revisit the proof at Proposition 3\.1/)
 assert.match(html,/2/)
 for(const target of ['result-readings','result-files','data'])assert.ok(html.includes(`href="#${target}"`))
 assert.doesNotMatch(html,/data-next|prepare-next|approve-next|Possible times|Plan the next measurement/)
})

test('unverified, inconclusive and edited paper results do not claim a refuted premise',()=>{
 for(const outcome of ['certified_counterexample','no_counterexample_found','inconclusive']){
  const html=paperNextHTML({outcome,paperReview:null},sym)
  assert.match(html,/does not establish that the original paper/)
  assert.doesNotMatch(html,/already contradicts|Locate the failed premise|data-next/)
 }
})
