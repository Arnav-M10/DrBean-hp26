import test from 'node:test'
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { recognizedPaper, paperDraft, paperFinding, VERITY_STUDY } from './paper-study.mjs'
import { parseExact } from '../exact.mjs'

const bytes=readFileSync(new URL('./fixtures/verity-riemann-study.pdf',import.meta.url))
const asset={id:'research_asset_paper',filename:'Dr-Verity-Riemann-Study.pdf',media_type:'application/pdf',byte_size:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')}

test('only the exact revised document selects the prepared input transcription',()=>{
  assert.equal(asset.byte_size,VERITY_STUDY.byteSize);assert.equal(asset.sha256,VERITY_STUDY.sha256)
  assert.equal(recognizedPaper([asset]),asset)
  assert.ok(recognizedPaper([{...asset,filename:'renamed.pdf'}]))
  for(const input of [[],[asset,asset],[{...asset,sha256:'a'.repeat(64)}],[{...asset,byte_size:asset.byte_size+1}],[{...asset,media_type:'text/plain'}]])assert.equal(recognizedPaper(input),null)
})

test('the profile contains reviewed inputs, not a verdict or a stored witness',()=>{
  const d=paperDraft(asset)
  assert.equal(d.rows.length,5);assert.equal(d.origin,'synthetic')
  assert.equal(d.low,'0.10');assert.equal(d.high,'0.17')
  assert.ok(d.rows.every(r=>r.allowance==='0.50'))
  assert.ok(d.source.includes(asset.sha256))
  assert.doesNotMatch(JSON.stringify(d),/certified_counterexample|101\/1016|candidate_id|verification/)
})

function evidence(){
  const draft=paperDraft(asset)
  const p={model:'two_rate_concentration',target:{parameter:'ke',closed:true,lower:'1/10',upper:'17/100'},domain:{rate_order:'ke_lt_ka'}}
  for(const [name,l,h] of [['A','aLow','aHigh'],['ke','keLow','keHigh'],['ka','kaLow','kaHigh']])p.domain[name]={lower:parseExact(draft.limits[l]),upper:parseExact(draft.limits[h])}
  const d={origin:'synthetic',change_reason:draft.source,rows:draft.rows.map(r=>({included:r.included,time:parseExact(r.time),concentration:parseExact(r.value),hard_allowance:parseExact(r.allowance)}))}
  const data={report:{body:{root_inputs:{dataset:{body:d},problem:{body:p}}}}}
  const m={outcome:'certified_counterexample',verification:'valid',binding:'matches',replayStatus:'passed',
    candidates:[{id:'fresh-witness',outside:true,fits:true,tone:'outside',exact:{A:'9/1',ke:'2/25',ka:'4/1'}}],
    readingChecks:Array.from({length:5},()=>({curves:[{candidateId:'fresh-witness',tone:'outside',within:true}]}))}
  return {data,m}
}

test('paper interpretation requires the actual verified result and uses its returned witness',()=>{
  const {data,m}=evidence();const r=paperFinding(data,m,asset)
  assert.equal(r.witness.ke,'2/25');assert.equal(r.witness_id,'fresh-witness')
  assert.match(r.scope,/does not disprove the Riemann hypothesis/)
  for(const [k,v] of [['outcome','no_counterexample_found'],['verification','invalid'],['binding','mismatch'],['replayStatus','failed']])assert.equal(paperFinding(data,{...m,[k]:v},asset),null)
  assert.equal(paperFinding(data,{...m,candidates:[]},asset),null)
  assert.equal(paperFinding(data,{...m,readingChecks:[]},asset),null)
  const wrongRows=m.readingChecks.map(r=>({curves:r.curves.map(c=>({...c,candidateId:'different-outside-witness'}))}))
  assert.equal(paperFinding(data,{...m,readingChecks:wrongRows},asset),null)
})

test('edited measurements, allowances, domains, source identity or claims lose the paper-specific conclusion',()=>{
  for(const edit of [x=>x.data.report.body.root_inputs.dataset.body.rows[0].concentration='99/1',
    x=>x.data.report.body.root_inputs.dataset.body.rows[0].hard_allowance='1/1',
    x=>x.data.report.body.root_inputs.problem.body.target.upper='1/5',
    x=>x.data.report.body.root_inputs.problem.body.domain.A.upper='50/1',
    x=>x.data.report.body.root_inputs.dataset.body.change_reason='Different source',
    x=>x.m.readingChecks[0].curves[0].within=false]){
    const x=evidence();edit(x);assert.equal(paperFinding(x.data,x.m,asset),null)
  }
})
