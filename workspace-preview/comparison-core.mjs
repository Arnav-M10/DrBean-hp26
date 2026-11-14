// Presentation and reviewed-input state for the numerical owner's exact wire contract.
// No physical prediction, fitting, sensitivity or Monte Carlo simulation is performed here.
export const REQUEST='DB-MODEL-COMPARISON-1', RESULT='DB-MODEL-COMPARISON-RESULT-1';
export const clone=value=>structuredClone(value);
export const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function canonical(value){if(Array.isArray(value))return `[${value.map(canonical).join(',')}]`;if(value&&typeof value==='object')return `{${Object.keys(value).sort().map(k=>`${JSON.stringify(k)}:${canonical(value[k])}`).join(',')}}`;return JSON.stringify(value);}
export async function fingerprint(value){const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical(value)));return Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,'0')).join('');}
export function scalar(value){const s=String(value);return /^[-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?$/i.test(s)&&s.length<=40&&Number.isFinite(Number(s))?Number(s):NaN;}
export const MODEL_INFO={
 'electron_isotropic_maxwellian.v1':{label:'Isotropic Maxwellian',description:'One zero-drift electron population with the same thermal energy in all directions. Fits density and one temperature parameter.'},
 'electron_gyrotropic_bimaxwellian.v1':{label:'Gyrotropic bi-Maxwellian',description:'One zero-drift population with separate parallel and perpendicular thermal energies. Fits density and two temperatures; includes the isotropic limit. It is not a mixture of two populations.'}
};
export const modelName=id=>MODEL_INFO[id]?.label||id;
export const settingLabel=c=>`${c.id}: ${c.angle_deg}°; ${c.energy_min_eV}–${c.energy_max_eV===null?'∞':c.energy_max_eV} eV normal energy`;
export function editable(request){const d=clone(request);d.approval='not_reviewed';d.review.reviewed=false;return d;}
export function approved(request){const d=clone(request);d.approval='approved_for_this_request';d.review.reviewed=true;return d;}
export function parseCSV(text,channels){
 if(new TextEncoder().encode(text).byteLength>131072)throw new Error('Use a CSV no larger than 128 KiB.');
 const lines=text.replace(/^\uFEFF/,'').trim().split(/\r?\n/);if(lines.shift()!=='channel_id,current_A,sigma_A')throw new Error('Use the exact CSV header: channel_id,current_A,sigma_A. Units are A.');
 if(!lines.length||lines.length>64)throw new Error('Import 1–64 observations.');
 return lines.map((line,i)=>{const [channel_id,current_A,sigma_A,...extra]=line.split(',').map(s=>s.trim());if(extra.length||!channels.some(c=>c.id===channel_id)||!Number.isFinite(scalar(current_A))||!Number.isFinite(scalar(sigma_A))||scalar(sigma_A)<=0)throw new Error(`Check CSV observation ${i+1}: use a declared channel, a finite current and a positive Gaussian standard deviation.`);return {channel_id,current_A,sigma_A};});
}
export function validateDraft(d){
 const errors=[];const add=(field,message)=>errors.push({field,message});
 if(!d||d.schema_version!==REQUEST)return [{field:'data',message:'Load a supported numerical comparison draft.'}];
 if(d.review.origin!=='synthetic')add('origin','Experimental observations are unsupported by this version. Only explicitly declared newly generated synthetic input can be submitted.');
 if(!d.review.description?.trim()||d.review.description.length>500)add('description','Provide a question and synthetic-data source description, up to 500 characters.');
 const number=(v,lo,hi)=>Number.isFinite(scalar(v))&&scalar(v)>=lo&&scalar(v)<=hi;
 const channels=(items,min,max)=>Array.isArray(items)&&items.length>=min&&items.length<=max&&new Set(items.map(c=>c.id)).size===items.length&&items.every(c=>/^[A-Za-z0-9_-]{1,48}$/.test(c.id)&&number(c.angle_deg,0,90)&&number(c.energy_min_eV,0,10000)&&(c.energy_max_eV===null||number(c.energy_max_eV,0,10000)&&scalar(c.energy_max_eV)>scalar(c.energy_min_eV)));
 if(!channels(d.channels,1,24))add('channels','Review 1–24 uniquely named channels, angles 0–90°, and valid high-pass or band-pass energies. Blank upper energy means high-pass.');
 if(!channels(d.feasible_settings,1,16))add('feasible_settings','Review 1–16 uniquely named feasible settings and their angle/energy constraints.');
 if(!d.observations.length||d.observations.length>64||d.observations.some(r=>!d.channels.some(c=>c.id===r.channel_id)||!number(r.current_A,-1e6,1e6)||!number(r.sigma_A,1e-15,1000)))add('observations','Provide 1–64 observations on declared channels, finite currents and Gaussian standard deviations between 1e-15 and 1000 A.');
 if(!d.selected_channel_ids.length||new Set(d.selected_channel_ids).size!==d.selected_channel_ids.length||d.selected_channel_ids.some(id=>!d.channels.some(c=>c.id===id)||!d.observations.some(r=>r.channel_id===id)))add('channels','Select at least one declared channel with an observation.');
 if(d.instrument && (!number(d.instrument.area_m2,1e-12,.1)||!number(d.instrument.efficiency,1e-6,1)))add('instrument','Review the collector area (1e-12–0.1 m²) and efficiency (1e-6–1).');
 if(!number(d.fit.density_min_m3,1e8,1e20)||!number(d.fit.density_max_m3,1e8,1e20)||scalar(d.fit.density_min_m3)>=scalar(d.fit.density_max_m3))add('fit','Review ordered density bounds within 1e8–1e20 m⁻³.');
 const grid=(v,min,max,lo,hi)=>Array.isArray(v)&&v.length>=min&&v.length<=max&&v.every(x=>number(x,lo,hi))&&new Set(v.map(scalar)).size===v.length;
 if(!grid(d.fit.temperature_grid_eV,2,25,.1,1000))add('fit','Supply 2–25 distinct temperature-grid values between 0.1 and 1000 eV. These are discrete thermal energies kBT/e, not kelvin.');
 if(!Number.isSafeInteger(d.fit.max_evaluations)||d.fit.max_evaluations<1||d.fit.max_evaluations>1000||!number(d.fit.max_reduced_chi_square,.01,1e6))add('fit','Review the fit-work cap (1–1000) and positive declared adequacy threshold (0.01–1e6).');
 if(!grid(d.noise.sigma_grid_A,1,8,1e-15,1000)||!grid(d.noise.z_thresholds,1,4,.1,10))add('noise','Supply 1–8 distinct positive noise levels (1e-15–1000 A) and 1–4 z multipliers (0.1–10).');
 if(!Number.isSafeInteger(d.noise.seed)||d.noise.seed<0||d.noise.seed>4294967295||!Number.isSafeInteger(d.noise.samples)||d.noise.samples<32||d.noise.samples>1024)add('noise','Review the seed (0–4294967295) and samples per case (32–1024).');
 return errors;
}
export function validateRecord(record,input,digest){
 const body=record?.body;if(record?.kind!=='model_comparison'||!record.id||body?.schema_version!==RESULT||!['completed','unsupported','fit_failed','budget_exceeded'].includes(body.status)||body.exact_verification!=='not_performed')throw new Error('Unsupported numerical result contract.');
 if(input&&(canonical(body.request)!==canonical(input)||body.input_digest!==digest))throw new Error('The result does not bind the exact reviewed request. Earlier evidence is retained.');
 if(!Array.isArray(body.fits)||!Array.isArray(body.noise_sweep)||!Array.isArray(body.limitations)||!Array.isArray(body.failures))throw new Error('The numerical result is incomplete.');
 return record;
}
export class ComparisonState{
 constructor(){this.draft=null;this.reviewed=null;this.revision=0;this.record=null;this.history=[];this.busy=false;this.error='';this.operation=null;this.pending=new Map();}
 edit(change){if(!this.draft)return;change(this.draft);this.draft.approval='not_reviewed';this.draft.review.reviewed=false;this.revision++;this.reviewed=null;this.error='';}
 load(request){this.draft=editable(request);this.revision++;this.reviewed=null;this.error='';}
 get stale(){return !!this.record&&(!this.draft||canonical(this.record.body.request)!==canonical(approved(this.draft)));}
 async review(){const errors=validateDraft(this.draft);if(errors.length){this.reviewed=null;return errors;}const revision=this.revision,input=approved(this.draft),digest=await fingerprint(input);if(revision!==this.revision)throw new Error('The draft changed while review was prepared. Review it again.');this.reviewed={input,digest,revision};return [];}
 begin(){if(this.busy)throw new Error('A comparison is already in progress.');if(!this.reviewed||this.reviewed.revision!==this.revision||canonical(this.reviewed.input)!==canonical(approved(this.draft)))throw new Error('Review the current inputs before comparing.');const r=this.reviewed;const key=this.pending.get(r.digest)||crypto.randomUUID();this.pending.set(r.digest,key);this.operation={...clone(r),key};this.busy=true;this.error='';return this.operation;}
 accept(record,operation){if(this.operation!==operation)return false;validateRecord(record,operation.input,operation.digest);this.keep(record);this.record=clone(record);this.busy=false;return true;}
 keep(record){validateRecord(record);const earlier=this.history.find(r=>r.id===record.id);if(earlier&&canonical(earlier)!==canonical(record))throw new Error('An immutable comparison identity changed. Earlier evidence is retained.');if(!earlier)this.history.push(clone(record));}
 clearIdentity(){this.history=[];this.record=null;this.pending.clear();this.operation=null;this.busy=false;this.reviewed=null;}
}
