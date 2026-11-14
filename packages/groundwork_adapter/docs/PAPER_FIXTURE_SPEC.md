# Scientific content for the synthetic paper fixture

Owner 1 handoff, based on main `cbfa5ef0494bb681d4d8748cfd2d2487a1e0887d`.
This specifies scientific content and acceptance requirements, not an API schema
or a rendered document. Owner 4 owns PDF/scan bytes, layout and page manifests;
Owner 2 owns authoritative paper/review/materialization contracts. No public
paper or new paper interface was located in the inspected published refs/logs.

## Authored content

Suggested title: **Synthetic two-rate concentration experiment: a deterministic
robustness exercise**. Mark every page **SYNTHETIC — authored test data, not a
publication or collected measurements**. Do not invent authors, affiliations,
DOIs, instruments, ethics approvals, confidence intervals or acquisition claims.

Suggested physical page 1 contains the model, assumptions and reviewed question;
page 2 contains Table 1 and the separate future-measurement exercise. These
page assignments become authoritative only after Owner 4 renders and hashes the
actual bytes. Printed page labels and physical page numbers remain distinct.

State the selected model exactly:

`C(t) = A * (exp(-ke*t) - exp(-ka*t))`, `C(0) = 0`, `0 < ke < ka`.

Time is elapsed hours from the reviewed fixed initial state. Concentration and
`A` use mg/L; rates use 1/h. This is one synthetic trajectory, with no repeated
dosing, infusion, pooling of subjects, population inference or estimated
nonzero initial concentration. `A` is the effective amplitude; it supplies no
separate bioavailability, dose or volume estimate.

Table 1 must contain these exact original strings. All rows are included.
The last column is an authored deterministic absolute allowance, **not SD, SEM,
a confidence interval, instrument resolution or a claimed measured error**.

| Row | Elapsed time (h) | Synthetic concentration (mg/L) | Authored hard allowance (mg/L) |
|---|---:|---:|---:|
| 1 | 0.25 | 4.80 | 0.50 |
| 2 | 0.5 | 7.20 | 0.50 |
| 3 | 1 | 8.00 | 0.50 |
| 4 | 2 | 6.80 | 0.50 |
| 5 | 4 | 5.70 | 0.50 |

Explicit reviewed parameter domain: `A=[0.001,30] mg/L`,
`ke=[0.015,0.35] 1/h`, `ka=[0.4,8] 1/h`, with `upper(ke)<lower(ka)`.
The deliberately selected closed target is `ke=[0.10,0.17] 1/h`.
Use this analysis question: **Do these synthetic measurements, under the stated
two-rate model and hard allowances, force ke to lie in the closed interval
[0.10,0.17] 1/h?** This is an authored deterministic question, not a statistical
claim from a real paper. A compatible strict outside witness challenges only
that question under these assumptions.

The authored data and proposed page/cell keys are available in
[synthetic-five-row.json](../fixtures/papers/synthetic-five-row.json). They are
scientific fixture content, not evidence that a PDF has been rendered or parsed.

Page 2 may offer feasible future times **8, 6 hours in that order**, future
allowance **0.20 mg/L**, and maximum horizon **8 hours**. These are separate
reviewer-selected design assumptions, not consequences of the historical
0.50 allowance. Certificate construction/extension and the design budget still
require their own explicit approval. Do not put expected candidate vectors,
selected times or successful checker labels into extraction inputs.

## Normative normalized scientific inputs

Use the existing canonical request, without modifying its archived identities:
[hero-baseline.request.json](../fixtures/decision/hero-baseline.request.json).
The scientific projection must contain:

| Row | Time | Concentration | Hard allowance | Included |
|---|---|---|---|---|
| 1 | `1/4` | `24/5` | `1/2` | true |
| 2 | `1/2` | `36/5` | `1/2` | true |
| 3 | `1/1` | `8/1` | `1/2` | true |
| 4 | `2/1` | `34/5` | `1/2` | true |
| 5 | `4/1` | `57/10` | `1/2` | true |

Model `two_rate_concentration`; initial concentration `0/1`; observable
`concentration`; units `h`, `mg/L`, `1/h`; domain `A=[1/1000,30/1]`,
`ke=[3/200,7/20]`, `ka=[2/5,8/1]`; rate order `ke_lt_ka`; closed target
`ke=[1/10,17/100]`; dataset origin `synthetic`.

Canonical mathematical equivalence compares these exact fields, ordered rows
and time-origin meaning. It does **not** require matching application record IDs,
source hashes, full projection digests, candidate IDs or native byte hashes.
The existing projection binds complete source/application metadata, so those
identities legitimately change for a paper-backed record. Execute fresh
discovery/checking and retain its actual returned identities and native anchors.

Existing references: [decision-loop explanation](DECISION_EXAMPLE.md),
[design request](../fixtures/decision/hero-design.request.json),
[changed-input request](../fixtures/decision/alternate-baseline.request.json),
and the `hero-reference-survives`, `hero-outside-survives`, `hero-both-excluded`
and `hero-own-time-recheck` families in [decision fixtures](../fixtures/decision).
The 4-hour correction control changes `5.70` to `5.30`, hence exact `53/10`.
Prior candidate IDs and the historical fixed audit pair are never production
constants for a new paper run.

## Required provenance join

Owner 2 should version additive paper contracts rather than relax existing
image-only `SourceAssetMetadata` and page-one `SourceLocator` safeguards. Current
materialization remains the authority for accepted exact values and assumptions.
The following are semantic requirements; transport field names remain theirs.

- Retain original PDF record ID, immutable SHA-256, byte size, origin and physical
  page count. Bind the parser/renderer version, processing warnings and coverage.
- Give every selected physical page its original-page number, optional printed
  label, text hash and rendered-asset hash. Define bounding-box units, coordinate
  origin and dimensions. A derived subset PDF has its own digest and an explicit
  subset-page-to-original-page mapping; subset page 1 is not original page 1.
- Bind every proposed value to the original paper and selected-page manifest
  digest, physical page, table/row/column or equation identity, original spelling,
  original unit and a short exact excerpt/locator. A citation supports traceability,
  not truth, authenticity or acceptance. Reject wrong-source/page joins.
- Retain the accepted value/unit, exact conversion operation/factor/result,
  reviewer correction/reason, and source-supplied versus human-assumed status.
  Keep model mapping, time origin, trajectory/aggregation choice, historical hard
  allowances and selected claim meaning reviewable, even when values are absent
  from the paper. Source claim and user analysis question are separate objects.
- Bind source, proposal, review, current dataset/problem revision and resulting
  materialization digests. Changed paper bytes, pages, values, units, claim,
  allowances or time-origin meaning require fresh review/authority as applicable.
  A model proposal, extraction or materialization never approves computation.

The current `source_materialization.py` preserves original proposal strings in
row `original_values` and requires exact equality with reviewed normalized
values. Conversion must therefore preserve source-unit spellings separately;
do not relabel a printed minute value as an original hour value. The immutable
conversion/provenance record must accompany the accepted solver values.

## Exact conversion and review controls

Recommended conversion fixtures for the agreed explicit unit whitelist:

| Source value/unit | Exact operation | Solver value/unit |
|---|---|---|
| `15 min` | multiply by `1/60` | `1/4 h` |
| `30 min` | multiply by `1/60` | `1/2 h` |
| `4.80 ug/mL` | multiply by `1/1` | `24/5 mg/L` |
| `500 ug/L` | multiply by `1/1000` | `1/2 mg/L` |
| `4800 ng/mL` | multiply by `1/1000` | `24/5 mg/L` |
| `500 ng/mL` | multiply by `1/1000` | `1/2 mg/L` |
| `0.002 1/min` | multiply by `60/1` | `3/25 1/h` |

The complete unit-variant table prints times `15,30,60,120,240 min`,
concentrations `4800,7200,8000,6800,5700 ng/mL` and hard allowances `500 ng/mL`.
It must normalize to the same five mathematical rows above. It is a separately
authored representation, not another collected experiment or an existing PDF.

These are exact rational conversions, not floating-point approximations. Explicit
microgram spelling aliases need an agreed whitelist. Unknown units/prefixes,
decimal separators, log axes, missing time origins and visually digitized curves
remain unresolved. SD/SEM/CI values cannot silently populate `hard_allowance`.
For a standard single-dose expression
`C(t) = (F*D/V) * ka/(ka-ke) * (exp(-ke*t)-exp(-ka*t))`, reviewed algebra gives
`A=(F*D/V)*ka/(ka-ke)` only under its stated positive-rate/single-input assumptions.
It cannot identify `F`, `D` and `V` separately. Repeated dosing, infusion or another
equation remains paper-review-only in this milestone.

Admission/acceptance controls should cover manual versus paper mathematical
equivalence; the `5.70 -> 5.30` correction reaching different exact executable
inputs with immutable old evidence; wrong page/source/unit rejection; statistical
interval and SD/SEM traps; separate design approval and changed precision/grid;
and fixed-pair follow-up outcomes including genuine unresolved checking. Download
and replay actual baseline/design/follow-up bytes with separate expected anchors.
Preserve scientific outcome, verification, binding and replay as distinct facts.

For Owner 4's later public paper, review the actual cited experiment before
claiming scientific eligibility. Until a source/page/model/data selection exists,
its scientific status is **not reviewed**. Missing observations or hard allowances
are missing requirements, never values to invent. Explicit hypothetical bounds
can support a conditional user robustness exercise, not a refutation of a paper's
statistical result. AI extraction accuracy, document authenticity, real-world
model validity and fresh checker success are four separate questions.
