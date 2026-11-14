import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { ComparisonState, approved, canonical, clone, editable, fingerprint, parseCSV, validateDraft, validateRecord } from '../comparison-core.mjs';
import { htmlReport, noiseView, plot, summaryView } from '../comparison-view.mjs';
// Retained numerical-owner fixture is used for renderer UNIT tests only.
// Fresh computation is exercised separately by check-connected.mjs.
const sample=JSON.parse(await readFile(new URL('../../fixtures/model-comparison/synthetic.request.json',import.meta.url)));
const saved=JSON.parse(await readFile(new URL('../../fixtures/model-comparison/synthetic.response.json',import.meta.url)));
const record={kind:'model_comparison',id:'unit-retained-fixture',workspace_id:'unit-workspace',digest:await fingerprint(saved),body:saved};
async function ready(){const s=new ComparisonState();s.load(sample);assert.deepEqual(await s.review(),[]);return s;}
test('static input is byte-identical to the numerical owner example, without copying any response',async()=>{
 assert.equal(await readFile(new URL('../examples/synthetic.request.json',import.meta.url),'utf8'),await readFile(new URL('../../fixtures/model-comparison/synthetic.request.json',import.meta.url),'utf8'));
});
test('canonical frontend review matches the published backend input digest and preserves numeric spelling',async()=>{
 assert.equal(await fingerprint(sample),saved.input_digest);assert.notEqual(await fingerprint({...sample,noise:{...sample.noise,sigma_grid_A:['0.00000010']}}),saved.input_digest);
});
test('loading a sample or changing inputs removes review and approval; review alone does not compute',async()=>{
 const s=await ready();assert.equal(s.draft.approval,'not_reviewed');assert.equal(s.draft.review.reviewed,false);assert.equal(s.busy,false);assert.equal(s.history.length,0);
 s.edit(d=>{d.observations[0].current_A='0.0001';});assert.equal(s.reviewed,null);assert.throws(()=>s.begin(),/Review/);
});
test('experimental origin, unsupported geometry, missing selection and invalid noise/budgets fail review',()=>{
 for(const change of [d=>d.review.origin='experimental',d=>d.channels[0].angle_deg='91',d=>d.channels[0].energy_max_eV='-1',d=>d.selected_channel_ids=[],d=>d.observations[0].sigma_A='0',d=>d.fit.temperature_grid_eV=['2','2.0'],d=>d.fit.max_evaluations=0,d=>d.noise.samples=31,d=>d.noise.z_thresholds=['Infinity']]){const d=editable(sample);change(d);assert.ok(validateDraft(d).length);}
 assert.deepEqual(validateDraft(editable(sample)),[]);
});
test('missing instrument can be explicitly submitted for an honest unsupported result; no calibration is assumed',()=>{
 const d=editable(sample);d.instrument=null;assert.deepEqual(validateDraft(d),[]);assert.equal(approved(d).instrument,null);
});
test('CSV accepts only declared synthetic-current channels and preserves exact scalar strings',()=>{
 assert.deepEqual(parseCSV('channel_id,current_A,sigma_A\na0_e0,4.00e-5,0.00000020',sample.channels),[{channel_id:'a0_e0',current_A:'4.00e-5',sigma_A:'0.00000020'}]);
 for(const text of ['wrong,header\n1,2,3','channel_id,current_A,sigma_A\nunknown,1,2','channel_id,current_A,sigma_A\na0_e0,NaN,2','channel_id,current_A,sigma_A\na0_e0,1,-2'])assert.throws(()=>parseCSV(text,sample.channels));
});
test('one operation is active at a time; repeated explicit identical request retains its operation key',async()=>{
 const s=await ready(),first=s.begin();assert.throws(()=>s.begin(),/progress/);assert.ok(s.accept(record,first));await s.review();const second=s.begin();assert.equal(second.key,first.key);s.accept(record,second);assert.equal(s.history.length,1);
});
test('changed input cannot accept a mismatched result or overwrite earlier immutable evidence',async()=>{
 const s=await ready(),first=s.begin();s.accept(record,first);const retained=canonical(s.record);s.edit(d=>{d.observations[0].current_A='0.0001';});await s.review();const second=s.begin();assert.throws(()=>s.accept(record,second),/exact reviewed request/);assert.equal(canonical(s.record),retained);assert.ok(s.stale);assert.equal(s.history.length,1);
 const changed=clone(record);changed.body.decision='substituted';assert.throws(()=>s.keep(changed),/immutable/);
});
test('late responses are fenced; completion for an earlier review preserves the changed draft',async()=>{
 const s=await ready(),op=s.begin();assert.equal(s.accept(record,{...op}),false);s.edit(d=>{d.review.description='A new draft question';});assert.ok(s.accept(record,op));assert.equal(s.draft.review.description,'A new draft question');assert.ok(s.stale);
});
test('private identity reset clears retained records and pending operation identities',async()=>{
 const s=await ready(),op=s.begin();s.accept(record,op);s.clearIdentity();assert.equal(s.history.length,0);assert.equal(s.record,null);assert.equal(s.pending.size,0);assert.equal(s.reviewed,null);
});
test('numerical status is never upgraded and an unknown contract or binding is rejected',async()=>{
 const changed=clone(record);changed.body.exact_verification='verified';assert.throws(()=>validateRecord(changed));assert.throws(()=>validateRecord(record,{...sample,approval:'different'},saved.input_digest));
});
test('noise display uses returned simulations and explicitly distinguishes 2zσ from an instrument floor',()=>{
 const rendered=noiseView(saved,saved.noise_sweep.length-1);assert.match(rendered,/not an independent instrument detection floor/);assert.match(rendered,/Wilson 95% sampling interval/);assert.match(rendered,/not confidence percentages/);assert.ok(rendered.includes(saved.noise_sweep.at(-1).decision));assert.match(summaryView(saved),/does not establish adequacy/);
});
test('readable report is standalone, complete for all returned cases, and preserves limitations and exact provenance',()=>{
 const report=htmlReport(record,{stale:true});assert.match(report,/Historical result/);assert.ok(report.includes(saved.source_digest));assert.ok(report.includes(saved.input_digest));assert.match(report,/Local parameter|Parameter sensitivity/);assert.match(report,/Conditional simulation at/);assert.ok(!/<script|<link|<img/.test(report));assert.match(report,/default-src 'none'/);for(const sweep of saved.noise_sweep)assert.ok(report.includes(`σ = ${sweep.sigma_A} A; z = ${sweep.z_threshold}`));for(const fit of saved.fits)for(const p of fit.predictions)assert.ok(report.includes(p.predicted_A));
});
test('hostile question is escaped in the HTML report instead of executable markup',()=>{
 const changed=clone(record);changed.body.request.review.description='</script><img src=x onerror=alert(1)>';const report=htmlReport(changed);assert.ok(!report.includes('<img'));assert.match(report,/&lt;img/);
});
test('plots show unavailable for absent or unrepresentable data, and handle constant/long series',()=>{
 assert.match(plot([],{title:'empty'}),/not supplied/);assert.match(plot([{label:'large',points:[[1,1e308]]}],{}),/exceed/);assert.ok(!/NaN|Infinity/.test(plot([{label:'constant',points:[[1,2],[1,2]]}],{})));assert.match(plot([{label:'long',points:Array.from({length:140000},(_,i)=>[i,i])}],{}),/<svg/);
});
