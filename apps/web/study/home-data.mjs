// The numbers on the front page, copied from a saved run of the app (the files in ./fixtures: one
// study, its claim check and its next measurement). All inputs are synthetic. study.test.mjs reads
// the saved files again and checks every value here against them.
// The curves keep the checker's exact fractions; the other values are the app's own numbers.
import { toNumber } from './results.mjs'

export const DOSE = {
  question: "Do these readings force the elimination rate into 0.10 to 0.17 per hour, and what should I measure next?",
  created: "2026-11-14T19:49:21.607Z",
  checker: "0.3.0",
  claim: { low: 0.1, high: 0.17 },
  // [hours, mg/L, ± hard allowance in mg/L], as typed
  readings: [["0.25","4.80","0.50"], ["0.5","7.20","0.50"], ["1","8.00","0.50"], ["2","6.80","0.50"], ["4","5.70","0.50"]],
  // The two curves Counterdex kept, inside the claim first: C(t) = A(e^(-ke t) - e^(-ka t))
  curves: [
    {"tone":"inside","A":"913800036733/100000000000","ke":"1631/12700","ka":"446/127"},
    {"tone":"outside","A":"435060970491/50000000000","ke":"101/1016","ka":"484/127"},
  ],
  outcome: "certified_counterexample",
  search: {"attempted":16384,"feasible":613,"kept":32,"partial":false},
  next: {
    tier: "checked_pair_separation", selected: 8, allowance: 0.2, horizon: 8,
    // At each time (hours): both curves' values in mg/L, inside first, and the range each allows one new reading
    times: [
      {"t":6,"separated":true,"margin":0.16359876449886462,"centers":[4.228682169692155,4.7922809341910195],"bands":[[4.028682169692154,4.428682169692155],[4.592280934191019,4.99228093419102]]},
      {"t":8,"separated":true,"margin":0.25740699615723395,"centers":[3.270817679469357,3.928224675626591],"bands":[[3.0708176794693567,3.4708176794693566],[3.7282246756265907,4.128224675626591]]},
    ],
  },
}


// The concentration study in the shape the study page reads (results.mjs summarize), so the
// front page words it with the study page's own functions.
export function doseStudy(d = DOSE) {
  const candidates = d.curves.map(c => ({ tone: c.tone, outside: c.tone === 'outside', exact: { A: c.A, ke: c.ke, ka: c.ka },
    params: { A: toNumber(c.A), ke: toNumber(c.ke), ka: toNumber(c.ka) } }))
  const included = d.readings.map(([time, value, allowance]) => ({ time, value, allowance, t: Number(time), v: Number(value), e: Number(allowance), included: true }))
  const times = d.next.times.map(t => ({ t: t.t, separated: t.separated, margin: t.margin,
    centers: candidates.map((c, i) => ({ tone: c.tone, value: t.centers[i] })), ranges: candidates.map((c, i) => ({ tone: c.tone, low: t.bands[i][0], high: t.bands[i][1] })) }))
  return { objective: d.question, created: d.created, checker: { version: d.checker }, claim: { ...d.claim, closed: true }, included, candidates,
    outcome: d.outcome, search: d.search, next: { tier: d.next.tier, selected: d.next.selected, allowance: d.next.allowance, horizon: d.next.horizon, times } }
}

