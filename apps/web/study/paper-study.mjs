// A prepared INPUT transcription, not a prepared result. The ordinary research
// session, approval, worker, Counterdex discovery and native replay decide it.
import { parseExact } from '../exact.mjs'

export const VERITY_STUDY = Object.freeze({
  id: 'verity-riemann-numerical-lemma-v1',
  sha256: '63bb064732d25880228e360d2657f0e1bfdc374f6905020d9f6a914011282c47',
  byteSize: 95608,
  page: 3,
  proposition: 'Proposition 3.1',
  timeOrigin:'Elapsed hours from the synthetic calibration initial state C(0)=0',
  rows: Object.freeze([['0.25','4.80','0.50'],['0.5','7.20','0.50'],['1','8.00','0.50'],['2','6.80','0.50'],['4','5.70','0.50']].map(Object.freeze)),
  limits: Object.freeze({ aLow:'0.001',aHigh:'30',keLow:'0.015',keHigh:'0.35',kaLow:'0.4',kaHigh:'8' }),
})

export function recognizedPaper(assets) {
  if (!Array.isArray(assets) || assets.length !== 1) return null
  const a = assets[0]
  return a?.sha256 === VERITY_STUDY.sha256 && a.byte_size === VERITY_STUDY.byteSize
    && a.media_type === 'application/pdf' ? a : null
}

export function paperDraft(asset) {
  if (!recognizedPaper([asset])) throw new Error('No prepared transcription matches this document.')
  return {
    kind:'paper', paperProfile:VERITY_STUDY.id, name:'Dr Verity — numerical rigidity', asset, tables:[], table:0,
    columns:null, allowanceForAll:'0.50', low:'0.10',high:'0.17',origin:'synthetic',
    timeOrigin:VERITY_STUDY.timeOrigin,
    source:`Author-declared deterministic hard allowance ±0.50 mg/L for every synthetic reading. Transcribed from Proposition 3.1 and Table 1, page 3. PDF SHA-256 ${VERITY_STUDY.sha256}.`,
    limits:{...VERITY_STUDY.limits},
    rows:VERITY_STUDY.rows.map(([time,value,allowance])=>({time,value,allowance,included:true,
      note:`Prepared transcription of synthetic Table 1, page 3; review against the uploaded PDF. SHA-256 ${VERITY_STUDY.sha256}`})),
  }
}

const same = (a,b) => {try {return parseExact(String(a)) === parseExact(String(b))} catch {return false}}

export function paperInputsMatch(draft) {
  return draft.origin==='synthetic' && same(draft.low,'.10') && same(draft.high,'.17')
    && draft.source?.includes(VERITY_STUDY.sha256)
    && draft.timeOrigin?.trim()===VERITY_STUDY.timeOrigin
    && draft.rows.length===VERITY_STUDY.rows.length
    && draft.rows.every((r,i)=>r.included && [r.time,r.value,r.allowance].every((v,j)=>same(v,VERITY_STUDY.rows[i][j])))
    && Object.entries(VERITY_STUDY.limits).every(([k,v])=>same(draft.limits[k],v))
}

export function paperFinding(data, m, asset) {
  if (!recognizedPaper([asset])) return null
  const d=data?.report?.body?.root_inputs?.dataset?.body, p=data?.report?.body?.root_inputs?.problem?.body
  if (!d || !p || d.origin!=='synthetic' || d.time_origin!==VERITY_STUDY.timeOrigin || !d.change_reason?.includes(VERITY_STUDY.sha256)
      || p.model!=='two_rate_concentration' || p.target?.parameter!=='ke' || p.target.closed!==true
      || !same(p.target.lower,'.10') || !same(p.target.upper,'.17') || p.domain?.rate_order!=='ke_lt_ka'
      || d.rows?.length!==VERITY_STUDY.rows.length) return null
  for (const [i,row] of d.rows.entries()) {
    const expected=VERITY_STUDY.rows[i]
    if (!row.included || !same(row.time,expected[0]) || !same(row.concentration,expected[1]) || !same(row.hard_allowance,expected[2])) return null
  }
  for (const [name,low,high] of [['A','aLow','aHigh'],['ke','keLow','keHigh'],['ka','kaLow','kaHigh']]) {
    if (!same(p.domain[name]?.lower,VERITY_STUDY.limits[low]) || !same(p.domain[name]?.upper,VERITY_STUDY.limits[high])) return null
  }
  if (m.outcome!=='certified_counterexample' || m.verification!=='valid' || m.binding!=='matches' || m.replayStatus!=='passed') return null
  const witness=m.candidates.find(c=>c.outside && c.fits)
  if (!witness || m.readingChecks.length!==VERITY_STUDY.rows.length
      || !m.readingChecks.every(row=>row.curves.some(c=>c.candidateId===witness.id && c.within))) return null
  return {
    profile:VERITY_STUDY.id, document:asset.filename, document_sha256:asset.sha256, page:3, proposition:'Proposition 3.1',
    title:'A necessary premise of this proof is false.',
    summary:`Counterdex found a parameter assignment that fits all five stated allowances but has ke = ${witness.exact.ke}, outside the paper’s claimed interval.`,
    witness_id:witness.id, witness:{...witness.exact},
    scope:'This refutes the paper’s numerical rigidity proposition and breaks its proposed proof. It does not disprove the Riemann hypothesis or certify complex analysis.',
    method:'Prepared input transcription; actual Deep Agents plan, scientific approval, Counterdex search, exact fixed-vector check, and native replay.',
  }
}

export const PAPER_CSS=`
#pk-result.paper-result>.actions{position:static;box-shadow:none}
.paper-study-review{margin:25px 0 30px;padding:24px;border:1px solid var(--line);border-radius:12px;background:var(--surface)}
.paper-study-review .paper-review-kicker{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--text-2);margin:0 0 20px}
.paper-study-review .paper-review-steps{display:grid;grid-template-columns:1fr 1fr 1fr;gap:24px}
.paper-study-review h2{font-size:18px;line-height:1.4;letter-spacing:-.01em;font-weight:550;margin:0 0 10px}
.paper-study-review p{font-size:14px;line-height:1.7;color:var(--text-2);margin:8px 0}
.paper-study-review .paper-step{font-size:12px;color:var(--text-3);display:block;margin-bottom:10px}
.paper-study-review .paper-review-number{font-size:26px;color:var(--text);font-variant-numeric:tabular-nums;letter-spacing:-.03em;margin:12px 0}
.paper-study-review .paper-review-scope{border-top:1px solid var(--line);padding-top:16px;margin-top:20px;font-size:13px}
@media(max-width:700px){.paper-study-review{padding:20px}.paper-study-review .paper-review-steps{grid-template-columns:1fr;gap:18px}.paper-study-review .paper-review-steps>div+div{padding-top:18px;border-top:1px solid var(--line)}}
`
