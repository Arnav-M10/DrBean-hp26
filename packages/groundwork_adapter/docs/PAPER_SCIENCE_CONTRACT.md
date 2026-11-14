# Paper scientific compatibility and integration checklist

Owner 1, paper sprint; base main `cbfa5ef`. This is the scientific handoff for
Owners 2–4, not a replacement API schema. Owner 2 owns `contracts.py`, admission,
materialization, persistence and now the coordinator and its tests. Owner 3 owns
the shared metered Gemini adapter, extraction and narration. Owner 4 owns PDF
parsing/page modules, rendering shared fixtures, browser/release integration and
the ownership document. Owner 1 changes only the adapter and its progress log.

## First compatibility checklist

| Requirement | Mechanical check | Retained human/source decision |
|---|---|---|
| Model | Fixed two-rate template; `C(0)=0`; positive-width positive domain; whole-box `upper(ke)<lower(ka)` | Selected experiment, single initial event, same trajectory, applicability, physical meaning of each rate; never swap rate names |
| Measurements | 3–128 retained rows; at least three distinct included nonnegative times; nonnegative concentrations; positive per-row hard bounds | Exact table/cell transcription; included/excluded rows; elapsed-time origin; no invented readings |
| Units | Allowlisted exact conversion to h, mg/L, 1/h; finite decimal/rational arithmetic | Original unit and accepted correction; no inferred prefixes, log-axis coordinates or decimal-separator guessing |
| Question | Closed interval for `ke`, exactly retained | Paper claim type and user's separate analysis question; CI/SD/SEM/estimate is not a universal deterministic statement |
| Uncertainty | Each included row has a positive hard absolute allowance | Justified bound or explicitly hypothetical sensitivity assumption; source SD/SEM/CI/resolution/detection limits never automatically supply it |
| Source identity | Owner 2 checks source/page/selected-manifest/proposal/review identities and stale input heads atomically | Selected study/cohort/table and correction reasons; software hashes establish identity, not document authenticity |
| Execution | Existing exact projection and native runtime; existing separate approvals | Baseline approval does not authorize design or follow-up |

`counterdex.paper_mapping.assess_paper_scope` returns one of
`eligible_supported_problem`, `needs_measurements_or_assumptions`,
`unsupported_model`, `unsupported_claim_semantics`, with field-specific issues.
It takes existing normalized dataset/problem records and source-review facts;
its eligible result binds their current IDs/digests and projection digest.
It always returns `execution_approved=false`, `source_authenticity_verified=false`
and `mathematical_verification=not_run`. The function does not authenticate the
reviewed assumptions it receives. Derive them from authoritative accepted
records; **never pass a Gemini eligibility flag or model-authored approval**.
Existing `project_application` remains the engine's numerical admission path.

The helper's keyword facts are an internal scientific interface, not a second
transport DTO. Owner 2 must publish the versioned application fields and map
accepted records to these predicates. Do not silently route unaccepted paper
proposals through the manual-input endpoint to evade paper review.
In particular, compare the actual selected claim/user-question parameter,
endpoints, closure and converted units to `problem.target`. Claim-kind strings
alone do not establish that join, and this helper cannot authenticate it.

## Model meaning and safe amplitude mapping

For a reviewed single-dose first-order oral expression,

`C(t) = F*D*ka/(V*(ka-ke)) * (exp(-ke*t) - exp(-ka*t))`,

the algebraic amplitude is `A = F*D*ka/(V*(ka-ke))`. The exact helper
`oral_amplitude` checks supplied positive normalized values, `F<=1`, `ke<ka`
and the rational arithmetic. It does not parse equations or infer applicability.
At given rates, amplitude identifies only `F*D/V=A*(ka-ke)/ka`; many different
F, D and V give the same amplitude. No bioavailability, dose or volume estimate
may be inferred from fitted A alone.

Fixed or bounded F/D/V impose a **coupled** A/ke/ka domain. The current independent
native box does not preserve that constraint automatically. The initial oral
paper lane therefore requires an explicitly reviewed independent-amplitude
relaxation and a separate user deterministic robustness question. It does not
claim equivalence of the paper's whole physical parameter domain or refutation
of the paper. Arbitrary equations, repeated dosing, infusions, nonzero initial
concentration and reversed/relabeled physical rates remain paper-review-only.

One explicitly identified trajectory is supported. Pooled subjects, dose cohorts
or incompatible time origins are not one trajectory. Aggregate means remain in
paper review in this initial interface: the application must first retain and
expose an explicit effective-mean-curve assumption, cohort/time alignment and
per-mean bounds. Native effective coefficients must never be described as
individual or population pharmacokinetic estimates. Do not hide this distinction
only in generated commentary.

## Exact values, conversions and authority

For every accepted scientific field Owner 2 must retain:

- Original retained paper ID/SHA, selected-page manifest digest, physical page
  number and page asset identity, printed page label where present, table/row/cell
  locator and original source spelling/unit. A subset's page 1 is not necessarily
  original physical page 1; retain the mapping and both byte identities.
- Accepted spelling/unit, exact normalized rational and unit, conversion policy,
  multiplicative rational factor, any human correction/reason and assumption
  category. `convert_scalar` converts the **accepted** value; it does not invent
  or overwrite the original spelling. An edited value is not an original reading.
- Selected paper claim/type, separate user question when applicable, source and
  proposal/review digests, current dataset/problem revision heads and the exact
  normalized inputs that will enter `project_application`.

Supported exact conversions are explicit and case-sensitive: h/min/s to h;
mg/L, ug/mL (also the two explicit micro-symbol spellings), ng/mL, ug/L, mg/dL
and g/L to mg/L; 1/h, 1/min and 1/s to 1/h. The factors and retained input appear
in the helper result. No floating-point intermediary or rounded display value is
admitted. Unknown prefixes and ambiguous numbers remain unresolved. Figure
digitization is not exact table transcription; discuss/cite plots, but do not
materialize estimated coordinates as original measured observations this sprint.

Current image materialization compares exact accepted values but has no paper
page/conversion fields, and overwrites `original_values` from its intake proposal.
Owner 2 must extend that authority path rather than treating a converted value
as the original paper text. Owner 4 must preserve the source/page identities.
Changed source bytes, accepted value/unit, claim, allowance, origin or input
revision require a new review/plan/approval as applicable. Saved identical retries
return their old immutable association; historical evidence stays readable.

Statistical uncertainty is kept separate. An explicitly accepted hypothetical
hard bound can support a conditional sensitivity analysis of retained observations,
but it is not converted statistical uncertainty and requires the separate reviewed
user robustness question. Future design allowance is a
separately reviewed choice, never copied from source error bars by default.

## Executable fixture and downstream facts

[Synthetic scientific content](PAPER_FIXTURE_SPEC.md) and
[authored JSON](../fixtures/papers/synthetic-five-row.json) define the existing
five-row experiment and an exact min/ng-per-mL variant. Owner 4 alone creates PDF,
scan, page and manifest bytes. No PDF hash, page image or parser/Gemini success is
fabricated here. Owner 1 tests the controlled reviewed-mapping seam through actual
discovery/checking and fresh native replay; actual PDF extraction/materialization
acceptance waits for the parser and Owner 2's application interface.

Equivalence means equal mathematical inputs, not equal provenance hashes:
paper and manual records retain different source/record/projection identities.
Compare units, initial state, time-origin meaning, domain/claim and every ordered
row's time/value/allowance/inclusion. Discover/check both; never copy an old pair
or claim a parsed public paper was refuted because a synthetic fixture passes.

Preserve compact-evidence axes independently: scientific outcome, verification,
expected binding, replay, candidate-specific statuses and design tier. Numerical
discovery is not a certificate. No outside witness found does not prove an
interval. Pair separation addresses exactly the named vectors at the evaluated
approved times; "best" means only the implemented objective on that finite grid.
Return exact selected time, both predicted enclosures, allowance, margin/tier,
evaluated alternatives and an honest reason when no separation is established.

Grounded narration examples for Owner 3:

- Allowed after checked outside compatibility: "This assignment challenges the
  user's deterministic question under the reviewed assumptions; it does not
  refute the paper's statistical confidence interval."
- Allowed: "Verification is valid and replay passed; this candidate remains
  unresolved, so the scientific outcome is inconclusive."
- Allowed for numerical tier: "Numerical guidance suggests a time; checked
  separation was not established."
- Forbidden: "The true model is identified," "every outside model is excluded,"
  "the paper is disproved," "globally optimal sampling," or "SD became a
  guaranteed measurement bound."

All reachable follow-up branches retain original vectors: either survivor,
both excluded, both compatible and unresolved. Both compatible can retain a
certified outside witness while neither vector is distinguished. Both excluded
does not establish the interval. Reading time/allowance/origin belong to that
separately reviewed reading; declared actual is not instrument authentication.
No branch silently starts new discovery under old approval.
