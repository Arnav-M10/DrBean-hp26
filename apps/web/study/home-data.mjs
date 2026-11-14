// The numbers on the front page, copied from two saved runs of the app. All inputs are synthetic.
// study.test.mjs reads the saved files again and checks every value here against them.
//   Drug levels: the files in ./fixtures (one study: the claim check and the next measurement).
//   Electron currents: fixtures/model-comparison/synthetic.response.json at the repository root.
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
  // The command that replays the claim check's proof, from the study's record
  replay: "python3.11 -m counterdex replay-native dr-bean-native_artifact_e327f0a214b546a8b50185718fdfd1eb.native.json --anchors dr-bean-native_artifact_e327f0a214b546a8b50185718fdfd1eb.anchors.json",
}

export const CURRENTS = {
  status: "completed",
  limit: "10",
  fits: [
    {"model_id":"electron_isotropic_maxwellian.v1","parameters":{"temperature_eV":"12","density_m3":"858714774872191"},"reduced_chi_square":"12746.515235338473","degrees_of_freedom":4,"rank_deficient":false,"boundary_limited":false,"adequate_under_declared_threshold":false},
    {"model_id":"electron_gyrotropic_bimaxwellian.v1","parameters":{"parallel_eV":"4","perpendicular_eV":"16","density_m3":"1000000000000000"},"reduced_chi_square":"9.5661975164574175e-29","degrees_of_freedom":3,"rank_deficient":false,"boundary_limited":false,"adequate_under_declared_threshold":true},
  ],
  // Each setting used in the fits: its label, the current with ±σ, and both fitted predictions (µA)
  groups: [
    {"label":["0°","all"],"observed":{"v":42.88951556897379,"e":0.19999999999999998},"marks":[{"tone":"iso","v":63.79118997880333},{"tone":"bi","v":42.88951556897379}]},
    {"label":["0°","≥8 eV"],"observed":{"v":5.804464737408178,"e":0.19999999999999998},"marks":[{"tone":"iso","v":32.75148897857796},{"tone":"bi","v":5.804464737408178}]},
    {"label":["45°","all"],"observed":{"v":67.81427846960486,"e":0.19999999999999998},"marks":[{"tone":"iso","v":63.79118997880333},{"tone":"bi","v":67.81427846960486}]},
    {"label":["45°","≥8 eV"],"observed":{"v":30.47091949710435,"e":0.19999999999999998},"marks":[{"tone":"iso","v":32.75148897857796},{"tone":"bi","v":30.470919497104347}]},
    {"label":["90°","all"],"observed":{"v":85.77903113794758,"e":0.19999999999999998},"marks":[{"tone":"iso","v":63.79118997880333},{"tone":"bi","v":85.77903113794758}]},
    {"label":["90°","≥8 eV"],"observed":{"v":52.027612345609874,"e":0.19999999999999998},"marks":[{"tone":"iso","v":32.75148897857796},{"tone":"bi","v":52.027612345609874}]},
  ],
  // The best next setting at each noise level tested (σ in µA)
  cases: [["0.1","Measure at 0°, above 4 eV"], ["2","Measure at 0°, above 4 eV"], ["20","No listed setting tells them apart at σ = 20 µA"]],
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

// The electron comparison in the shape compare.mjs reads (readComparison), for its wording.
export function currentsStudy(c = CURRENTS) {
  return { r: { status: c.status, failures: [], request: { fit: { max_reduced_chi_square: c.limit } } }, fits: Object.fromEntries(c.fits.map(f => [f.model_id, f])) }
}
