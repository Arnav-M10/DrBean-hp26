// Actual upload -> reviewed inputs -> Deep Agents -> approval -> Counterdex ->
// native download -> separate CPython replay. Provider analysis is prohibited.
import { createRequire } from 'node:module'
import { readFile,mkdir,writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'
import assert from 'node:assert/strict'

const {chromium}=createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE||'playwright')
const url=new URL(process.env.BEAN_VERITY_URL||'http://127.0.0.1:4173/study/')
if(!['127.0.0.1','localhost'].includes(url.hostname))throw Error('Use a local deployment.')
const root=new URL('../../',import.meta.url),overlay=process.env.BEAN_VERITY_OVERLAY==='1'
const fixture=new URL('../../apps/web/study/fixtures/verity-riemann-study.pdf',import.meta.url)
const output=fileURLToPath(new URL('../../var/test-evidence/verity-counterdex/',import.meta.url))
await mkdir(output,{recursive:true})
const browser=await chromium.launch({headless:true})
const checks=[],forbidden=[],errors=[]
const check=(label,ok)=>{assert.ok(ok,label);checks.push(label)}
const prefix='/api/bean/v1'
async function open(){
 const context=await browser.newContext({viewport:{width:1440,height:1050},reducedMotion:'reduce',acceptDownloads:true})
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/api/bean/v1/**',r=>{
  if(/\/(research-analyses|research-analysis-estimates)(\/|$)/.test(new URL(r.request().url()).pathname)){forbidden.push(r.request().url());return r.abort()}
  return r.continue()
 })
 if(overlay)for(const name of ['app.mjs','results.mjs','paper-study.mjs','paper-view.mjs','chart.mjs'])await page.route(`**/study/${name}`,r=>r.fulfill({path:fileURLToPath(new URL(`apps/web/study/${name}`,root)),contentType:'text/javascript; charset=utf-8'}))
 await page.goto(url.href+'#data',{waitUntil:'networkidle'})
 await page.locator('#connection').filter({hasText:'Private workspace'}).waitFor({timeout:20000})
 return page
}
const get=async(page,path)=>page.evaluate(async p=>{const r=await fetch(p,{credentials:'same-origin'});if(!r.ok)throw Error(`GET ${p}: ${r.status}`);return r.json()},prefix+path)
try{
 const page=await open(),caps=await get(page,'/capabilities')
 check('uses the configured controlled graph with the actual science adapter',caps.deepagents.execution_mode==='controlled'&&caps.science.available===true)
 await page.locator('#file').setInputFiles(fileURLToPath(fixture))
 await page.getByRole('button',{name:'Check the proof’s premise',exact:true}).waitFor({timeout:30000})
 check('paper upload stays in overview and offers no competing medicine setup',await page.locator('#overview').isVisible()&&!await page.locator('#editor').isVisible()&&await page.locator('#can-do [data-kind="concentration"]').count()===0)
 await page.getByRole('button',{name:'Check the proof’s premise',exact:true}).click()
 await page.getByRole('heading',{name:'Check the proof’s numerical premise',exact:true}).waitFor()
 check('paper review leads with its proposition and keeps the medicine editor closed',!await page.locator('#claim-title').isVisible()&&(await page.locator('#paper-editor').innerText()).includes('Proposition 3.1'))
 await page.screenshot({path:`${output}/paper-inputs-desktop.png`,fullPage:true})
 await page.setViewportSize({width:390,height:844})
 check('paper review fits a phone',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
 await page.screenshot({path:`${output}/paper-inputs-phone.png`,fullPage:true})
 await page.setViewportSize({width:1440,height:1050})
 await page.getByText('Edit the numerical inputs',{exact:true}).click()
 await page.locator('input[data-key="allowance"]').first().fill('0.6')
 check('editing the paper inputs shows an explicit scope change',await page.locator('.paper-edited').isVisible())
 await page.locator('input[data-key="allowance"]').first().fill('0.50')
 check('restoring the paper inputs clears the edited-study notice',!await page.locator('.paper-edited').isVisible())
 await page.getByText('Edit the numerical inputs',{exact:true}).click()
 check('the exact paper supplies five reviewable inputs, not a saved result',await page.locator('#rows tr').count()===5&&await page.locator('#claim-low').inputValue()==='0.10'&&await page.locator('#claim-high').inputValue()==='0.17')
 check('hard allowances and synthetic origin are explicit',await page.locator('input[data-key="allowance"]').first().inputValue()==='0.50'&&await page.locator('input[name="origin"][value="synthetic"]').isChecked())
 const creation=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname.endsWith('/research-sessions'))
 await page.locator('#prepare').click()
 const session=await(await creation).json()
 await page.locator('#approve-check').waitFor({timeout:45000})
 check('approval retains the paper context',await page.getByRole('heading',{name:'Approve the premise check',exact:true}).isVisible())
 const before=await get(page,`/research-sessions/${session.id}`)
 check('a real maintained plan waits for scientific approval',before.state==='waiting_review'&&before.pending_review.kind==='plan'&&before.children.length===0)
 await page.locator('#approve-check').click()
 await page.getByRole('heading',{name:'A necessary premise of this proof is false.',exact:true}).waitFor({timeout:60000})
 const completed=await get(page,`/research-sessions/${session.id}`)
 check('the approved workflow really completed',completed.state==='completed'&&completed.children.length>0&&completed.reports.length>0)
 check('the controlled coordinator made no physical model calls',completed.usage.physical_calls===0)
 const report=await get(page,`/reports/${completed.reports.at(-1)}/download`)
 const fact=report.body.evidence.find(e=>e.kind==='evidence').body.result
 check('Counterdex actually returned a valid matching counterexample',fact.scientific_outcome==='certified_counterexample'&&fact.verification==='valid'&&fact.expected_binding==='matches'&&fact.replay==='passed')
 const outside=fact.candidate_results.find(c=>c.is_counterexample)
 check('the witness is a freshly checked outside candidate',outside?.outside_closed_claim===true&&outside.verification==='valid')
 const entry=report.body.native_evidence[0]
 const raw=await page.evaluate(async p=>Array.from(new Uint8Array(await(await fetch(p,{credentials:'same-origin'})).arrayBuffer())),prefix+`/artifacts/${entry.artifact.id}`)
 const anchors=await get(page,`/artifacts/${entry.artifact.id}/anchor?download=true`)
 await writeFile(`${output}/native.json`,Buffer.from(raw));await writeFile(`${output}/anchors.json`,JSON.stringify(anchors))
 const engine=process.env.BEAN_VERITY_ENGINE_PYTHON
 if(!engine)throw Error('Supply the prepared CPython 3.11 engine for independent replay.')
 const replay=spawnSync(engine,['-I','-m','counterdex','replay-native',`${output}/native.json`,'--anchors',`${output}/anchors.json`],{encoding:'utf8',timeout:125000,env:{PATH:'/usr/bin:/bin',LANG:'C.UTF-8'}})
 assert.equal(replay.status,0,replay.stderr||replay.stdout)
 const fresh=JSON.parse(replay.stdout)
 check('downloaded native evidence freshly replays outside the browser',fresh.replay==='passed'&&fresh.verification==='valid'&&fresh.expected_binding==='matches'&&fresh.outcome.scientific_outcome==='certified_counterexample')
 await page.evaluate(()=>document.fonts.ready)
 check('the desktop action bar does not cover the evidence chart',await page.evaluate(()=>document.querySelector('#pk-result>.actions').getBoundingClientRect().top>=document.querySelector('#result-answer').getBoundingClientRect().bottom-1))
 await page.screenshot({path:`${output}/desktop.png`,fullPage:true})
 check('the explanation targets the numerical premise, not RH',(await page.locator('#paper-study-review').innerText()).includes('It does not disprove the Riemann hypothesis'))
 await page.locator('#pk-result nav').getByRole('link',{name:'Files',exact:true}).click()
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'Download the readable report',exact:true}).click()
 const html=await readFile(await(await download).path(),'utf8')
 check('paper report has calibration axes with no assumed dose',html.includes('Calibration time (h)')&&!html.includes('hours after dose'))
 check('readable report carries the paper linkage and actual witness',html.includes('Proposition 3.1')&&html.includes('does not disprove the Riemann hypothesis')&&html.includes('Document SHA-256 63bb0647'))
 await writeFile(`${output}/readable-report.html`,html)
 await page.reload({waitUntil:'networkidle'});await page.locator('#file-list').filter({hasText:'Claim check'}).waitFor({timeout:30000})
 await page.locator('#pk-result nav').getByRole('link',{name:'Answer',exact:true}).click()
 await page.getByRole('heading',{name:'A necessary premise of this proof is false.',exact:true}).waitFor()
 check('reload retains the paper-specific explanation and real evidence',await page.locator('#paper-study-review').isVisible())
 const followupMutations=[]
 await page.route('**/research-sessions/**',r=>{
  if(r.request().method()==='POST'&&/\/(advance|inputs|decisions)$/.test(new URL(r.request().url()).pathname)){
   followupMutations.push(r.request().url());return r.abort()
  }
  return r.continue()
 })
 check('paper result offers proof follow-up rather than measurement planning',await page.locator('#to-next').innerText()==='Review the proof’s next steps')
 await page.locator('#to-next').click()
 await page.getByRole('heading',{name:'Revisit the proof at Proposition 3.1',exact:true}).waitFor()
 check('paper next step hides every measurement planning section',!await page.locator('#next-settings').isVisible()&&!await page.locator('#next-review').isVisible()&&!await page.locator('#next-answer').isVisible())
 await page.screenshot({path:`${output}/paper-next-desktop.png`,fullPage:true})
 await page.setViewportSize({width:390,height:844})
 check('paper follow-up fits a phone',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
 await page.screenshot({path:`${output}/paper-next-phone.png`,fullPage:true})
 await page.reload({waitUntil:'networkidle'})
 await page.getByRole('heading',{name:'Revisit the proof at Proposition 3.1',exact:true}).waitFor()
 check('direct next route and reload retain paper follow-up',!await page.locator('#next-times').isVisible())
 await page.locator('#prepare-next').dispatchEvent('click')
 await page.locator('#approve-next').dispatchEvent('click')
 await page.locator('#approve-check').dispatchEvent('click')
 check('paper follow-up and stale measurement controls dispatch no scientific mutations',followupMutations.length===0)
 await page.locator('#paper-followup').getByRole('link',{name:'Back to the result',exact:true}).click()
 await page.setViewportSize({width:390,height:844})
 check('phone layout fits without horizontal overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
 await page.screenshot({path:`${output}/phone.png`,fullPage:true})
 await page.locator('[data-step="data"]').click()
 await page.getByRole('heading',{name:'Check the proof’s numerical premise',exact:true}).waitFor()
 check('reopened saved paper returns to its own review and retained source',!await page.locator('#claim-title').isVisible()&&(await page.locator('.paper-source').innerText()).includes('verity-riemann-study.pdf'))
 await page.locator('[data-action="new-study"]').click()
 check('new study clears the paper context',!await page.locator('#paper-editor').isVisible()&&await page.locator('#start').isVisible())
 await page.locator('[data-action="sample-concentration"]').click()
 check('the explicit concentration sample still has its editable screen',await page.locator('#claim-title').isVisible()&&!await page.locator('#paper-editor').isVisible()&&await page.locator('#time-origin').inputValue()==='Time of dose')
 const negative=await open()
 await negative.locator('#file').setInputFiles({name:'Dr-Verity-Riemann-Study.pdf',mimeType:'application/pdf',buffer:Buffer.concat([await readFile(fixture),Buffer.from('\n% changed\n')])})
 await negative.locator('#overview').getByRole('button',{name:'Ask the assistant',exact:true}).waitFor({timeout:30000})
 check('changed bytes do not activate the document-specific shortcut',await negative.getByRole('button',{name:'Check the proof’s premise',exact:true}).count()===0)
 check('unrecognized files do not enter any experiment editor automatically',!await negative.locator('#editor').isVisible()&&!await negative.locator('#paper-editor').isVisible())
 check('no Gemini analysis or estimate was attempted',forbidden.length===0)
 check('no browser exceptions',errors.length===0)
 const result={mode:overlay?'frontend_source_overlay_real_backend_and_worker':'served_product',checks,passed:checks.length,session:session.id,scientific_outcome:fact.scientific_outcome,witness:fact.candidates.find(c=>c.id===outside.candidate_id).parameter_vector,replay:fresh.replay,forbidden,errors}
 await writeFile(`${output}/result.json`,JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2))
}finally{await browser.close()}
