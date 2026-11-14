import { ComparisonState, REQUEST, RESULT, MODEL_INFO, approved, canonical, clone, escape as e, modelName, parseCSV, scalar } from './comparison-core.mjs';
import { plot, table, predictionSeries, predictionsTable, fitTable, inputSummary, summaryView, sensitivityView, noiseView, failureView, provenance, htmlReport, format } from './comparison-view.mjs';
const $=id=>document.getElementById(id),state=new ComparisonState();
let template,connection=null,routeName='data',resultTab='summary',noiseIndex=0,noiseTimer,connectionEpoch=0,requestUncertain=false,serial=0,instrumentDraft;
const announce=message=>{$('announcement').textContent=message;};
const pathGet=(object,path)=>path.split('.').reduce((v,k)=>v?.[k],object);
function pathSet(object,path,value){const keys=path.split('.'),last=keys.pop(),parent=keys.reduce((v,k)=>v[k],object);parent[last]=value;}
function error(message){state.error=message;sync();}
function sync(){
 $('error').hidden=!state.error;$('error').textContent=state.error;
 $('review-consent').disabled=!state.reviewed||!connection||state.busy||requestUncertain;
 $('compare').disabled=!connection||!state.reviewed||!$('review-consent').checked||state.busy||requestUncertain;
 $('draft-status').textContent=state.busy?'Computing the explicitly reviewed request. Your edits remain in this tab.':state.stale?'Draft changed. The retained result still belongs to its original reviewed input.':'Draft in this tab. Navigation preserves your inputs; reload discards unsaved edits.';
 $('job').hidden=!state.operation||(!state.busy&&!requestUncertain&&!state.error);
 $('job-status').textContent=state.busy?'Computation request is in flight. No progress percentage is supplied.':requestUncertain?'The request outcome is uncertain. Read retained history before another deliberate operation.':state.operation?`The requested operation returned${state.record?` status ${state.record.body.status}`:''}.`:'';
 if(state.draft){$('origin').textContent=`${state.draft.review.origin==='synthetic'?'Newly generated synthetic input':state.draft.review.origin==='experimental'?'Experimental input — unsupported':'Origin not yet confirmed'} · ${state.draft.observations.length} observations`;$('area').disabled=$('efficiency').disabled=!state.draft.instrument;}
 if(state.record){$('result-binding').textContent=`${state.stale?'Historical result — draft changed. ':''}Result ${state.record.id}; input ${state.record.body.input_digest}. Applies only to its retained reviewed request.`;$('result-binding').classList.toggle('stale',state.stale);$('result-history').innerHTML=state.history.map((r,i)=>`<option value="${i}" ${r.id===state.record.id?'selected':''}>${e(r.body.status)} — ${e(r.id)}</option>`).join('');}
 for(const id of ['download-html','download-json','download-provenance'])$(id).disabled=!connection||!state.record;
}
function modified(change){state.edit(change);$('review-consent').checked=false;sync();renderInputPlot();}
function renderGeometry(kind){
 const isChannels=kind==='channels',items=state.draft[kind];
 return `<div class="table-region" tabindex="0" role="region" aria-label="${isChannels?'Measurement channels':'Feasible settings'}"><table><thead><tr>${isChannels?'<th scope="col">Use</th>':''}<th scope="col">Identity</th><th scope="col">Angle (°)</th><th scope="col">Energy min (eV)</th><th scope="col">Energy max (eV)</th></tr></thead><tbody>${items.map((c,i)=>`<tr>${isChannels?`<td><label class="check"><input type="checkbox" data-channel="${e(c.id)}" aria-label="Select channel ${e(c.id)}" ${state.draft.selected_channel_ids.includes(c.id)?'checked':''}></label></td>`:''}<td>${e(c.id)}</td>${['angle_deg','energy_min_eV','energy_max_eV'].map(key=>`<td><input data-geometry="${kind}" data-index="${i}" data-coordinate="${key}" value="${e(c[key]??'')}" aria-label="${e(c.id)} ${key}" inputmode="decimal" autocomplete="off" ${key==='energy_max_eV'?'placeholder="High-pass…"':''}></td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function renderRows(){
 $('measurements').innerHTML=state.draft.observations.map((r,i)=>`<tr><td><select data-row="${i}" data-cell="channel_id" aria-label="Channel, observation ${i+1}">${state.draft.channels.map(c=>`<option value="${e(c.id)}" ${r.channel_id===c.id?'selected':''}>${e(c.id)}</option>`).join('')}</select></td>${[['current_A','Current'],['sigma_A','Noise standard deviation']].map(([key,label])=>`<td><input name="observation-${i}-${key}" data-row="${i}" data-cell="${key}" value="${e(r[key])}" aria-label="${label}, observation ${i+1}" inputmode="decimal" autocomplete="off"></td>`).join('')}<td><button class="quiet" data-remove="${i}" aria-label="Remove observation ${i+1}">Remove</button></td></tr>`).join('');
}
function renderInputs(){
 if(!state.draft)return;
 if(state.draft.instrument)instrumentDraft=clone(state.draft.instrument);
 $('description').value=state.draft.review.description;$('data-origin').value=state.draft.review.origin;
 for(const el of document.querySelectorAll('[data-path]'))el.value=pathGet(state.draft,el.dataset.path)??'';
 for(const el of document.querySelectorAll('[data-list]'))el.value=pathGet(state.draft,el.dataset.list).join(', ');
 for(const el of document.querySelectorAll('[data-integer]'))el.value=pathGet(state.draft,el.dataset.integer);
 $('instrument-enabled').checked=!!state.draft.instrument;
 $('models').innerHTML=Object.values(MODEL_INFO).map(m=>`<section class="model-option"><h3>${e(m.label)}</h3><p>${e(m.description)}</p></section>`).join('');
 $('channels').innerHTML=renderGeometry('channels');$('feasible-settings').innerHTML=renderGeometry('feasible_settings');renderRows();renderInputPlot();sync();
}
function renderInputPlot(){if(!state.draft)return;const points=state.draft.observations.map((r,i)=>[i+1,scalar(r.current_A)]).filter(p=>p.every(Number.isFinite));$('input-plot').innerHTML=points.length?`<h3>Input readings only</h3>${plot([],{title:'Unfitted synthetic input currents',xLabel:'Observation index, not time',yLabel:'Current (A)',points})}<p class="helper">Channel geometry and units are retained in review. No model is fitted by this preview plot.</p>`:'';}
async function renderReview(){
 $('review-consent').checked=false;
 if(!state.draft)return;
 $('review-inputs').innerHTML=inputSummary(state.draft);
 try{const errors=await state.review();$('review-errors').hidden=!errors.length;$('review-errors').innerHTML=errors.length?`<h3>Review these inputs</h3><ul>${errors.map(x=>`<li><a href="#${['instrument','fit','noise','feasible_settings'].includes(x.field)?'assumptions':'data'}">${e(x.message)}</a></li>`).join('')}</ul>`:'';}catch(err){error(err.message);}sync();
}
async function readHistory({recover=false}={}){
 if(!connection)throw new Error('Restore the private connection before reading retained history. No computation was retried.');
 const records=await connection.list();records.forEach(record=>state.keep(record));
 if(!state.record&&records.length)state.record=clone(records.at(-1));
 if(recover){requestUncertain=false;state.error='History checked. No computation was retried. A pending or interrupted operation may still be refused; any new request requires explicit review.';}
 if(routeName==='results')renderResult();sync();
}
async function connect({startNew=false}={}){
 const epoch=++connectionEpoch;$('connect').disabled=true;
 try{
  const response=await fetch('./comparison-service.json',{cache:'no-store',credentials:'same-origin',redirect:'error',signal:AbortSignal.timeout(15000)});if(!response.ok)throw new Error('The numerical connection manifest is unavailable on this server.');
  const manifest=await response.json();if(manifest.available!==true)throw new Error(manifest.reason||'Static draft mode. Open this workspace on the ordinary application server for computation.');
  if(manifest.schema_version!=='DB-MODEL-COMPARISON-CONNECTION-1'||manifest.mode!=='private_session'||manifest.module!=='/comparison-api.mjs'||manifest.request_schema!==REQUEST||manifest.result_schema!==RESULT)throw new Error('Unsupported numerical connection. No visitor-supplied API or module URL is accepted.');
  const {connectComparison}=await import('/comparison-api.mjs');
  const connected=await connectComparison({startNew});if(epoch!==connectionEpoch)return;
  if(startNew){state.clearIdentity();requestUncertain=false;}
  connection=connected;connection.setConnectionFailureHandler(err=>{if(connection===connected){connection=null;delete $('connection').dataset.connected;$('connection-heading').textContent='Private connection unavailable';$('connection-detail').textContent=err.message;$('mode-label').textContent='Connection unavailable';error(`Private connection unavailable: ${err.message}. Check connection before continuing.`);$('new-session').hidden=false;}});
  $('connection').dataset.connected='true';$('connection-heading').textContent='Private numerical service connected';$('connection-detail').textContent='Offline computation in this private workspace. Only newly generated synthetic observations are supported; each comparison requires explicit review.';$('mode-label').textContent='Connected numerical mode';$('new-session').hidden=true;
  await readHistory({recover:requestUncertain});if(routeName==='review')await renderReview();
 }catch(err){if(epoch!==connectionEpoch)return;connection=null;state.reviewed=null;delete $('connection').dataset.connected;$('connection-heading').textContent='Draft-only mode — computation unavailable';$('connection-detail').textContent=err.message;$('mode-label').textContent='Draft only';$('new-session').hidden=!(err.kind==='session_recovery'&&err.mayStartNew===true);}
 finally{if(epoch===connectionEpoch){$('connect').disabled=false;sync();}}
}
function renderResult(){
 const record=state.record;$('result-empty').hidden=!!record;$('result-content').hidden=!record;if(!record)return;
 const b=record.body;noiseIndex=Math.max(0,Math.min(noiseIndex,b.noise_sweep.length-1));$('result-status').textContent=`Numerical comparison — ${b.status}`;
 document.querySelectorAll('[data-result]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.result===resultTab)));
 let html=failureView(b);
 if(resultTab==='summary')html+=`<div class="split result-summary"><section>${summaryView(b,noiseIndex)}</section><aside><h3>Measurements and sampled fitted predictions</h3>${b.fits.length?plot(predictionSeries(b),{title:'Returned model predictions and selected observations',xLabel:'Reviewed observation index',yLabel:'Current (A)',points:b.request.observations.map((r,i)=>[i+1,Number(r.current_A)]).filter((_,i)=>b.request.selected_channel_ids.includes(b.request.observations[i].channel_id))}):'<p class="empty">No fitted prediction was returned.</p>'}<p class="helper">Lines guide the eye between returned channel predictions; they are not continuous response curves. Index is not time or energy.</p></aside></div>${fitTable(b)}<details><summary>Returned predictions and residual values</summary>${predictionsTable(b)}</details>`;
 if(resultTab==='residuals')html+=`<h3>Returned residual comparison</h3>${plot(predictionSeries(b,'residual_A'),{title:'Returned residuals',xLabel:'Reviewed observation index',yLabel:'Residual (A)'})}${predictionsTable(b)}`;
 if(resultTab==='sensitivity')html+=`<h3>Local parameter sensitivity</h3><p class="subtle">Returned numerical log-parameter derivatives. Rank deficiency and boundary limits remain visible in the summary; this is not an identifiability proof.</p>${sensitivityView(b)}`;
 if(resultTab==='noise')html+=`<h3>Does noise hide the difference?</h3><p class="subtle">Select a returned case from the explicitly reviewed sweep. This control starts no new computation.</p>${b.noise_sweep.length?`<div class="noise-control"><label for="noise-level">Computed noise case: <output id="noise-value" for="noise-level">σ ${e(b.noise_sweep[noiseIndex].sigma_A)} A; z ${e(b.noise_sweep[noiseIndex].z_threshold)}</output></label><input id="noise-level" type="range" min="0" max="${b.noise_sweep.length-1}" step="1" value="${noiseIndex}" aria-valuetext="sigma ${e(b.noise_sweep[noiseIndex].sigma_A)} A, z ${e(b.noise_sweep[noiseIndex].z_threshold)}" ${b.noise_sweep.length===1?'disabled':''}></div>`:''}<div id="noise-computation">${noiseView(b,noiseIndex)}</div>`;
 if(resultTab==='evidence')html+=`<h3>Original reviewed request</h3>${inputSummary(b.request)}<h3>Limitations</h3><ul>${b.limitations.map(x=>`<li>${e(x)}</li>`).join('')}</ul><h3>Numerical methods and provenance</h3><pre>${e(JSON.stringify(provenance(record),null,2))}</pre><p class="helper">Readable HTML and the bound server JSON describe the same immutable result. The JSON is numerical evidence, not an exact Counterdex native packet.</p>`;
 $('result-panel').innerHTML=html;sync();
}
async function route(){const next=location.hash.slice(1)||'data';if(next==='content')return;routeName=['data','assumptions','review','results'].includes(next)?next:'data';const titles={data:'Compare plasma models',assumptions:'Review the measurement assumptions',review:'Review this comparison',results:'Understand the numerical result'};document.querySelectorAll('.screen').forEach(s=>{s.hidden=s.id!==routeName;});document.querySelectorAll('[data-route]').forEach(a=>{if(a.dataset.route===routeName)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});$('heading').textContent=titles[routeName];$('breadcrumb').textContent={data:'Data & models',assumptions:'Assumptions',review:'Review',results:'Results'}[routeName];$('review-link').hidden=routeName==='review';if(routeName==='review')await renderReview();if(routeName==='results')renderResult();document.title=`${titles[routeName]} · Dr. Bean`;$('heading').focus();announce(titles[routeName]);}
async function compare(){
 if(!connection||!$('review-consent').checked||requestUncertain)return;
 let op;
 try{op=state.begin();sync();const same=state.history.find(r=>canonical(r.body.request)===canonical(op.input));const record=same?await connection.get(same.id):await connection.submit(op.input,{operationKey:op.key});if(!state.accept(record,op))return;noiseIndex=0;announce(same?'Identical retained comparison reopened. No computation was repeated.':`Numerical comparison returned ${record.body.status}.`);if(state.revision===op.revision){if(location.hash==='#results')renderResult();else location.hash='results';}else{renderResult();announce('Comparison returned for earlier reviewed inputs. Your changed draft was retained.');}}
 catch(err){if(op&&state.operation===op){state.busy=false;requestUncertain=err.kind!=='rejected';}error(`${err.message} Earlier evidence is retained. ${requestUncertain?'Read retained history; this request will not be retried automatically.':''}`);}finally{sync();}
}
function save(content,type,filename){const url=URL.createObjectURL(new Blob([content],{type})),a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
async function download(kind){
 if(!connection||!state.record)return;const selected=state.record;
 try{const stem=selected.id.replace(/[^a-zA-Z0-9_-]/g,'_');if(kind==='json'){const d=await connection.download(selected);save(d.bytes,'application/json',d.filename);}else if(kind==='html')save(htmlReport(selected,{stale:state.stale}),'text/html;charset=utf-8',`drbean-${stem}.html`);else save(JSON.stringify(provenance(selected),null,2),'application/json',`drbean-${stem}-provenance.json`);announce(`${kind==='html'?'Readable report':kind==='json'?'Bound server JSON':'Provenance'} download prepared for ${selected.id}.`);}catch(err){error(err.message);}
}
document.addEventListener('input',event=>{const el=event.target;if(!state.draft)return;
 if(el.id==='description')modified(d=>{d.review.description=el.value;});
 if(el.dataset.path)modified(d=>pathSet(d,el.dataset.path,el.value));
 if(el.dataset.list)modified(d=>pathSet(d,el.dataset.list,el.value.split(',').map(x=>x.trim())));
 if(el.dataset.integer)modified(d=>pathSet(d,el.dataset.integer,/^\d+$/.test(el.value)?Number(el.value):null));
 if(el.dataset.row!==undefined)modified(d=>{d.observations[Number(el.dataset.row)][el.dataset.cell]=el.value;});
 if(el.dataset.geometry)modified(d=>{d[el.dataset.geometry][Number(el.dataset.index)][el.dataset.coordinate]=el.dataset.coordinate==='energy_max_eV'&&el.value===''?null:el.value;});
 if(el.id==='noise-level'){const i=Number(el.value),record=state.record,sweep=record.body.noise_sweep[i];$('noise-value').textContent=`σ ${sweep.sigma_A} A; z ${sweep.z_threshold}`;el.setAttribute('aria-valuetext',`sigma ${sweep.sigma_A} A, z ${sweep.z_threshold}`);clearTimeout(noiseTimer);noiseTimer=setTimeout(()=>{if(state.record===record&&routeName==='results'&&resultTab==='noise'){noiseIndex=i;$('noise-computation').innerHTML=noiseView(record.body,i);}},180);}
});
document.addEventListener('change',async event=>{const el=event.target;if(!state.draft)return;
 if(el.id==='review-consent')sync();
 if(el.id==='data-origin')modified(d=>{d.review.origin=el.value;});
 if(el.dataset.channel)modified(d=>{if(el.checked)d.selected_channel_ids.push(el.dataset.channel);else d.selected_channel_ids=d.selected_channel_ids.filter(id=>id!==el.dataset.channel);});
 if(el.id==='instrument-enabled'){if(state.draft.instrument)instrumentDraft=clone(state.draft.instrument);modified(d=>{d.instrument=el.checked?clone(instrumentDraft||template.instrument):null;});renderInputs();}
 if(el.id==='result-history'){clearTimeout(noiseTimer);state.record=clone(state.history[Number(el.value)]);noiseIndex=0;renderResult();}
 if(el.id==='csv'){const file=el.files?.[0];if(!file)return;const revision=state.revision;try{if(file.size>131072)throw new Error('Use a CSV no larger than 128 KiB.');const observations=parseCSV(await file.text(),state.draft.channels);if(revision!==state.revision)throw new Error('The draft changed during import. Import again to replace these observations.');modified(d=>{d.observations=observations;d.review.origin='unconfirmed';d.selected_channel_ids=[...new Set(observations.map(r=>r.channel_id))];d.review.description=`Imported CSV: ${file.name}. Describe the question and newly generated synthetic source before approval.`.slice(0,500);});renderInputs();announce('CSV imported locally. Confirm its origin and review the exact request.');}catch(err){error(err.message);}finally{el.value='';}}
});
document.addEventListener('click',event=>{const remove=event.target.closest('[data-remove]');if(remove){modified(d=>{d.observations.splice(Number(remove.dataset.remove),1);});renderRows();$('add-row').focus();}const tab=event.target.closest('[data-result]');if(tab){clearTimeout(noiseTimer);resultTab=tab.dataset.result;renderResult();}});
$('synthetic').addEventListener('click',()=>{if(!template)return;state.load(template);renderInputs();announce('Newly generated synthetic example loaded. No comparison executed.');});
$('new-draft').addEventListener('click',()=>{if(!template)return;if(state.draft?.observations.length&&!confirm('Replace the working draft? Retained server evidence is kept.'))return;const d=clone(template);d.observations=[];d.selected_channel_ids=[];d.review={reviewed:false,origin:'unconfirmed',description:''};state.load(d);renderInputs();location.hash='data';});
$('add-row').addEventListener('click',()=>{if(!state.draft||state.draft.observations.length>=64){error('Load a draft and use at most 64 observations.');return;}modified(d=>{d.observations.push({channel_id:d.channels[0].id,current_A:'',sigma_A:''});});renderRows();$('measurements').lastElementChild.querySelector('input').focus();});
for(const [button,kind,limit] of [['add-channel','channels',24],['add-setting','feasible_settings',16]])$(button).addEventListener('click',()=>{if(!state.draft||state.draft[kind].length>=limit){error(`Use at most ${limit} ${kind.replace('_',' ')}.`);return;}modified(d=>{let id;do{id=`${kind==='channels'?'channel':'setting'}_${++serial}`;}while(d[kind].some(c=>c.id===id));d[kind].push({id,angle_deg:'0',energy_min_eV:'0',energy_max_eV:null});});$(kind==='channels'?'channels':'feasible-settings').innerHTML=renderGeometry(kind);if(kind==='channels')renderRows();});
$('connect').addEventListener('click',()=>connect());$('new-session').addEventListener('click',()=>{if(confirm('Start a separate private workspace? Earlier evidence remains with the previous identity and will not be transferred.'))connect({startNew:true});});$('compare').addEventListener('click',compare);
$('history').addEventListener('click',async()=>{try{await readHistory({recover:true});}catch(err){error(err.message);}});
$('download-html').addEventListener('click',()=>download('html'));$('download-json').addEventListener('click',()=>download('json'));$('download-provenance').addEventListener('click',()=>download('provenance'));
window.addEventListener('hashchange',route);window.addEventListener('pagehide',()=>clearTimeout(noiseTimer));
try{const response=await fetch('./examples/synthetic.request.json',{cache:'no-store',redirect:'error'});if(!response.ok)throw new Error('The public synthetic input template is unavailable. No saved output was substituted.');template=await response.json();if(template.schema_version!==REQUEST)throw new Error('Unsupported synthetic input template.');const blank=clone(template);blank.observations=[];blank.selected_channel_ids=[];blank.review={reviewed:false,origin:'unconfirmed',description:''};state.load(blank);renderInputs();await route();await connect();}catch(err){error(err.message);$('connection-heading').textContent='Input template unavailable';$('connection-detail').textContent='Restore the public synthetic request fixture before preparing this workflow.';}
