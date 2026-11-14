// Trusted same-origin transport for the preferred UI; scientific authority stays server-side.
import { bootstrapSharedSession, readConnection } from './session.mjs'
import { ApiError } from './api.mjs'
import { datasetBody, problemBody } from './manual.mjs'
const ID=/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/, SHA=/^[a-f0-9]{64}$/
const canonical=v=>Array.isArray(v)?`[${v.map(canonical)}]`:v&&typeof v==='object'?`{${Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k]))}}`:JSON.stringify(v)
function record(value,kind,workspace,body){
 if(value?.kind!==kind||value.workspace_id!==workspace||!ID.test(value.id)||!SHA.test(value.digest))throw new Error('Saved inputs do not match this private workspace.')
 for(const [key,v] of Object.entries(body))if(canonical(value.body[key])!==canonical(v))throw new Error('Saved inputs differ from the exact reviewed values. Stop and inspect the retained records.')
 return value
}
export class ReviewedInputs {
 constructor({api,workspace,getDraft,storage=globalThis.sessionStorage}){this.api=api;this.workspace=workspace;this.getDraft=getDraft;this.storage=storage;this.cache=null;this.pending=null;this.key=`preferred-research-inputs:${workspace}`;try{const p=JSON.parse(storage?.getItem(this.key)||'null');if(p&&['datasets','problems'].some(k=>p.path===`/workspaces/${workspace}/${k}`)&&ID.test(p.key)&&p.body&&typeof p.body==='object')this.pending=p}catch{/* no stored authority */}}
 persist(){if(this.pending)this.storage?.setItem(this.key,JSON.stringify(this.pending));else this.storage?.removeItem(this.key)}
 async post(path,body){if(this.pending)throw new Error('Resolve the unanswered input request before saving another draft. Nothing was resent.')
  this.pending={path,body:structuredClone(body),key:crypto.randomUUID()};this.persist()
  try{const result=await this.api.json(path,body,this.pending.key);this.pending=null;this.persist();return result}catch(error){if(error.kind==='rejected'){this.pending=null;this.persist()}throw error}}
 async retry(){const p=this.pending;if(!p)return;const value=await this.api.json(p.path,p.body,p.key);this.pending=null;this.persist();return value}
 async save(){const draft=structuredClone(this.getDraft()),signature=JSON.stringify(draft);if(this.pending)throw new Error('Resolve the unanswered input request; no automatic resend is allowed.');if(this.cache?.signature===signature)return this.cache.inputs
  const datasetRequest=datasetBody(draft,draft.context);problemBody(draft,{id:'',digest:''})
  const dataset=record(await this.post(`/workspaces/${this.workspace}/datasets`,datasetRequest),'dataset',this.workspace,datasetRequest)
  const problemRequest=problemBody(draft,dataset),problem=record(await this.post(`/workspaces/${this.workspace}/problems`,problemRequest),'problem',this.workspace,problemRequest)
  if(signature!==JSON.stringify(this.getDraft()))throw new Error('The draft changed while saving. Review the current draft before continuing.')
  this.cache={signature,inputs:{dataset,problem}};return this.cache.inputs}
}
let retained
export async function connectResearch({getDraft,startNew=false,storage=globalThis.sessionStorage}={}){
 const shared=await bootstrapSharedSession(undefined,{startNew}),workspaceId=shared.session.workspace_id,identityId=`browser-session:${workspaceId}`
 if(retained&&retained.workspaceId!==workspaceId&&!startNew)throw new ApiError('session_recovery','The private identity changed. Explicitly start a new workspace; no history or pending approval is transferred.',{mayStartNew:true})
 const api=retained?.workspaceId===workspaceId?retained.api:shared.api,capabilities=await readConnection(api,'/capabilities')
 if(capabilities.contract_version!=='DB-SC-1'||capabilities.policy_version!=='GF-2')throw new Error('Unsupported research application contract.')
 const inputs=retained?.workspaceId===workspaceId?retained.inputs:new ReviewedInputs({api,workspace:workspaceId,getDraft,storage})
 const connection={api,capabilities,workspaceId,identityId,session:shared.session,inputs,saveReviewedInputs:()=>inputs.save()}
 retained=connection;return connection
}
