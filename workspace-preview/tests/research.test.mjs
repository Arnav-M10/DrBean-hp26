import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {safeCommentary,reportHTML,reviewedInputs,researchIssue,issueHTML,findings} from '../research-view.mjs';
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
test('terminal failures explain the specific interruption while retaining scientific findings and hiding raw codes in details',()=>{
 const cases=[['provider_malformed_tool_call',/instruction.*could not safely use.*not run/],
  ['provider_rate_limited',/service temporarily limited requests/],
  ['provider_budget_exhausted',/approved limit/],['research_provider_allocation_exhausted',/approved limit/],
  ['research_budget_exhausted',/approved limit/],['agent_context_budget_exhausted',/approved limit/],
  ['explanation_unsupported_number',/number.*evidence did not support.*withheld/],
  ['explanation_unsupported_claim',/claim.*evidence did not support.*withheld/]];
 const original=structuredClone(evidence);
 for(const [code,meaning] of cases){
  const failed={...snapshot,action:{error_code:code}},issue=researchIssue(failed,evidence),html=findings(failed,evidence,null,helpers);
  assert.match(issue.message,meaning,code);assert.match(issue.science,/Saved scientific results and available downloads are preserved/);
  assert.match(html,/<details class="research-error-details"><summary>Technical failure details<\/summary><pre>/);
  assert.ok(html.includes(code));assert.ok(!html.replace(/<details\b[\s\S]*?<\/details>/g,'').includes(code));
  assert.ok(html.includes(interpretResult(evidence[0].body.result).statement));
  assert.doesNotMatch(html,/try again automatically|refill|increase.*limit/i);
 }
 assert.deepEqual(evidence,original);
});
test('exhausted allocation does not relabel completed science or grant a retry',()=>{
 const completed={...snapshot,state:'completed',action:{error_code:null},interaction:{quota_exhausted:true}};
 const issue=researchIssue(completed,evidence),html=reportHTML(completed,evidence,null,helpers);
 assert.match(issue.message,/approved limit/);assert.match(issue.next,/confirm authority and remaining capacity/);
 assert.match(issue.next,/refreshing does not add capacity or repeat work/);
 assert.match(html,/state completed/);assert.match(html,/not_performed/);
 assert.equal(researchIssue({...completed,interaction:{quota_exhausted:false}},evidence),null);
});
test('successful completion at capacity keeps the evidence-bound next step and a separate capacity warning',()=>{
 const completed={...snapshot,state:'completed',mode:'gemini',action:{error_code:null},interaction:{quota_exhausted:true,recovery:{required:false}}};
 const report={id:'report_unit',body:{agent_commentary:{...comment,authorship:'model_commentary',next_action:'review_design'}}};
 const original=structuredClone({completed,evidence,report}),html=reportHTML(completed,evidence,report,helpers);
 assert.match(html,/<h3>What should you do next\?<\/h3><p>Review feasible measurement settings for a separate pair-design operation\.<\/p><p class="helper research-capacity">/);
 assert.match(html,/approved limit/);assert.match(html,/confirm authority and remaining capacity/);
 assert.match(html,/refreshing does not add capacity or repeat work/);assert.match(html,/Persisted model commentary/);
 assert.match(html,/state completed/);assert.match(html,/no_counterexample_found/);assert.match(html,/not_performed/);
 assert.ok(html.includes(interpretResult(evidence[0].body.result).statement));
 assert.deepEqual({completed,evidence,report},original);
 const invalid={...report,body:{agent_commentary:{...report.body.agent_commentary,fact_ids:['missing_evidence']}}};
 assert.doesNotMatch(findings(completed,evidence,invalid,helpers),/Review feasible measurement settings|research-capacity/);
 for(const patch of [{state:'failed'}, {action:{error_code:'provider_malformed_tool_call'}}, {interaction:{quota_exhausted:true,recovery:{required:true,code:'provider_outcome_unknown',can_reconcile:false}}}]){
  const interrupted=findings({...completed,...patch},evidence,report,helpers);
  assert.doesNotMatch(interrupted,/Review feasible measurement settings|research-capacity/);
  assert.ok(interrupted.includes(researchIssue({...completed,...patch},evidence).next));
 }
});
test('uncertain request accounting takes priority over a normal failure and requires operator recovery',()=>{
 const interrupted={...snapshot,action:{error_code:'provider_rate_limited'},interaction:{recovery:{required:true,code:'provider_outcome_unknown',can_reconcile:false},quota_exhausted:true}};
 const issue=researchIssue(interrupted,evidence);
 assert.equal(issue.code,'provider_outcome_unknown');assert.match(issue.message,/will not be requested again automatically/);
 assert.match(issue.next,/inspect the retained request accounting/);assert.doesNotMatch(issue.next,/use the explicit reconciliation control/);
 const permitted=researchIssue({...interrupted,interaction:{recovery:{required:true,code:'worker_lost',can_reconcile:true}}},evidence);
 assert.match(permitted.next,/only the work the backend permits/);
});
test('failure before science does not promise results, and unknown technical codes remain escaped',()=>{
 const failed={...snapshot,action:{error_code:'<img src=x onerror=alert(1)>'}};
 const issue=researchIssue(failed,[]),html=issueHTML(failed,[]);
 assert.equal(issue.science,'No scientific result has been returned yet.');
 assert.doesNotMatch(html,/<img|<script/);assert.match(html,/&lt;img/);
 assert.ok(!html.replace(/<details\b[\s\S]*?<\/details>/g,'').includes('onerror'));
});
test('rejected reference request with no scientific child does not claim findings or downloads exist',()=>{
 const empty={...snapshot,children:[],reports:[],action:{error_code:'research_references_invalid'}};
 const issue=researchIssue(empty,[]),html=findings(empty,[],null,helpers);
 assert.match(issue.message,/did not identify the reviewed inputs or evidence/);
 assert.match(issue.message,/That step was not carried out/);
 assert.match(issue.next,/requires its own reviewed scope and approval/);
 assert.match(html,/No scientific findings or downloads are available yet/);
 assert.doesNotMatch(html,/findings and downloads remain usable|Saved scientific results remain available/);
 const later=findings({...empty,children:[{state:'completed'}]},evidence,null,helpers);
 assert.match(later,/Saved scientific results remain available/);
 assert.match(later,/Downloads are shown when an artifact was produced/);
 assert.doesNotMatch(later,/No scientific findings or downloads are available yet|No operation was prepared/);
 assert.ok(later.includes(interpretResult(evidence[0].body.result).statement));
});
