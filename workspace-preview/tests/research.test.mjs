import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {safeCommentary,reportHTML,reviewedInputs} from '../research-view.mjs';
import {interpretResult,readable} from '../../apps/web/result-view.mjs';
import {designExplanation} from '../../apps/web/design.mjs';
const helpers={interpret:interpretResult,readable,design:designExplanation};
// Renderer units only. Actual evidence/replay is exercised by check-research.mjs.
const evidence=[{id:'evidence_unit',body:{result:{scientific_outcome:'no_counterexample_found',verification:'not_performed',replay:'not_performed',artifacts:[]}}}];
const comment={scientific_authority:false,authorship:'controlled_commentary',text:'Review the evidence.',fact_ids:['evidence_unit'],next_action:'clarify'};
test('only explicitly non-authoritative persisted commentary bound to actual evidence is displayed',()=>{
 assert.equal(safeCommentary({body:{agent_commentary:comment}},evidence),comment);
 for(const patch of [{scientific_authority:true},{authorship:'unknown'},{fact_ids:[]},{fact_ids:['other_record']},{text:null}])assert.equal(safeCommentary({body:{agent_commentary:{...comment,...patch}}},evidence),null);
 assert.equal(safeCommentary({body:{}},evidence),null);
});
const snapshot={id:'research_unit',state:'failed',mode:'controlled',objective:'</p><img src=x onerror=alert(1)>',action:{error_code:'controlled_failure'},plan:{body:{steps:[{title:'Review the bound',status:'pending',reason:'Retained evidence needs review.'}]}},reviewed_context:{dataset:{body:{experiment_id:'experiment',origin:'actual',time_origin:'Recorded t=0',change_reason:JSON.stringify({allowance_origin:'Calibration hard bound',methods:'Two-rate assumption'}),rows:[{time:'1/4',concentration:'481/100',hard_allowance:'1/2',included:true}]}},problem:{body:{target:{lower:'1/10',upper:'17/100'},domain:{ke:{lower:'3/200',upper:'7/20'}}}}}};
test('readable failed-parent export preserves scientific status, units, reviewed inputs, exact context and replay instructions',()=>{
 const html=reportHTML(snapshot,evidence,null,helpers);
 for(const text of ['No canonical report','controlled_failure','mg/L','Recorded t=0','Calibration hard bound','481/100','4.81','counterdex replay','--anchors','not_performed','not independent experimental validation'])assert.ok(html.includes(text),text);
 assert.ok(!/<script|<img|<link/.test(html));assert.match(html,/&lt;img/);assert.match(html,/default-src 'none'/);assert.match(html,/Persisted model commentary is unavailable/);
 assert.match(reviewedInputs(snapshot,readable),/0.25/);
});
test('static CSV parser is the same reviewed production parser, and static manifest cannot execute',async()=>{
 assert.equal(await readFile(new URL('../exact-static.mjs',import.meta.url),'utf8'),await readFile(new URL('../../apps/web/exact.mjs',import.meta.url),'utf8'));
 const manifest=JSON.parse(await readFile(new URL('../research-service.json',import.meta.url),'utf8'));assert.equal(manifest.available,false);assert.equal(manifest.module,undefined);
});
