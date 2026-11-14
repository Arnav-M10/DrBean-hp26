# Counterdex scientific integration handoff

The 0.2.0 application/runtime seam is specified in [BRIDGE.md](BRIDGE.md),
with the exact application projection in [APPLICATION_MAPPING.md](APPLICATION_MAPPING.md).
It adds bounded baseline discovery, one/two-candidate historical certificates,
application-bound native bytes and hypothetical follow-up replay. The existing
fixed-pair scientific contracts below remain supported. See
[DECISION_EXAMPLE.md](DECISION_EXAMPLE.md) for executed synthetic controls.

This package supplies exact-input numerical guidance and a bounded exact checker
for `two_rate_kinetics_v1`, revision 1. It has no third-party runtime dependencies.
The native qualification target is CPython 3.11. Browser replay, provider access,
deployment and application authorization are separate, unqualified boundaries.
The distribution, Python import and console entry point are named `counterdex`.
The ownership path remains `packages/groundwork_adapter/`; the implementation
module inside it is `counterdex/`.

The standalone CPython 3.11 runtime differs from the backend's Python 3.12/3.13
environment. Direct backend adoption is still pending. This rename does not
qualify a broader interpreter range or an integrated scientific worker.

All contracts added here are package-local scientific projections. They are not
another definition of the application's `DesignRequest`, approvals, revisions or
HTTP DTOs. Owner 2 owns those schemas and must adopt an explicit mapping before
integrating the adapter. No route, authorization authority, root dependency
manifest or provider implementation is added by this package. Owner 3 consumes
the resulting distinctions; Owner 4 qualifies the installed release and browser
path separately.

## Operations and supplied authority

`normalize_problem(payload)` and `normalize_design(payload, problem)` validate
complete scientific inputs and return immutable objects. `compare_grid(problem,
design, context)` returns numerical diagnostics. `construct_pair(...)`,
`verify_pair(...)`, and `checked_design(...)` construct or freshly verify the
named analytic pair profile. `capabilities()` exposes granular support and caps.

The bundle integration entry points are:

```python
create_suggestion(
    problem_payload, design_payload,
    expected_problem_digest=expected_problem_digest,
    expected_design_digest=expected_design_digest,
    workflow=workflow,
    context=context,
    artifacts=artifacts,
)  # immutable bounded bundle bytes

replay_bundle(
    bundle_bytes,
    expected_problem_digest=expected_problem_digest,
    expected_suggestion_digest=expected_suggestion_digest,
    context=context,
)  # fresh replay report
```

These entry points consume an already accepted frozen operation. Supplying IDs
or a digest does not grant approval. Owner 2 must validate workspace ownership,
scenario and revision binding, design-specific scope, idempotent reservation and
remaining budget before invocation. Workflow identity is retained in the bundle;
its transport schema and persistence remain Owner 2's responsibility. Lower-level
checker calls are useful native scientific operations, not alternate web routes.

`ExecutionContext` starts its clock once and cooperatively reports cancellation
or resource exhaustion before further bounded work. A smaller supplied budget
wins; reusing a context cannot reset elapsed time or an observed stop. The API
worker must still enforce its hard wall limit. Never convert a stopped worker
into a scientific negative result or silently allocate another attempt.

## Scientific field mapping

| Projection/field | Meaning and integration rule |
|---|---|
| `schema_version` | Exact package-local profile: `groundwork.problem.v1` or `groundwork.design.v1`; unknown versions and fields fail. |
| `model`, `model_revision` | Only `two_rate_kinetics_v1`, revision `1`; fixed equations, concentration observable, units and initial state are normative. |
| `units`, `initial_conditions` | Hours, mg/L, inverse hours; exact `x(0)=1`, `c(0)=0`. Unit relabeling, resets and new doses require another model. |
| `time_origin` | Explicit elapsed-time origin for this experiment, identical in problem and design. It is not a wall-clock appointment. |
| `domain` | Ordered `A,ke,ka` meaning; finite positive strict intervals, with `upper(ke)<lower(ka)`. Candidates lie inside these closed domains. |
| `claim.interval` | Closed interval for `ke`, permitted to be degenerate. Exact equality with either endpoint is inside the claim. |
| `observations` | Stable IDs, exact time/value/positive hard allowance, inclusion, allowance origin, observation origin, notes and provenance. At least three distinct included nonnegative times. Duplicate times may represent different rows and are preserved. |
| `dataset_kind`, `origin` | Actual and hypothetical histories remain distinct. An actual problem refuses hypothetical rows; a hypothetical fork may retain its real ancestors explicitly. |
| `problem_digest` | New full scientific-projection identity. Row order, excluded rows, notes and provenance all remain in this projection. No note-only equivalence is promised. |
| `scenario_id` | Opaque supplied historical-scenario reference; authorization is checked by the backend. |
| `candidates[].id` | Stable one-to-one identity, never inferred from display position. IDs use bounded printable ASCII; Unicode remains allowed in ordinary text. |
| `candidates[].parameters` | Two distinct exact fixed vectors. No refitting or parameter substitution occurs during checking. |
| `candidates[].source_artifact_digest` | `null` for new construction, or a raw-byte SHA-256 reference. Exact reuse currently requires both candidates to reference the same complete matching pair artifact. |
| `grid` | One to 64 unique exact times with explicit feasibility and reason; canonical order is ascending exact time. Deduplicate a preview before approval with `normalize_times`, retaining source spellings separately. |
| `future_allowance`, `allowance_origin` | Explicit positive hard allowance and `hypothetical` or `reviewed_hard_bound` origin. No historical/default allowance is inherited; standard deviation is not an admitted substitute. |
| `horizon_policy` | Explicit maximum horizon and construction/extension flags. The historical horizon must be covered; checked feasible times cannot exceed the permitted horizon. Numerical plotting does not extend checked scope. |
| `requested_tier` | `numerical_guidance` or `checked_pair_separation`. Numerical execution cannot consume exact-construction scope. |
| `numerical_policy`, `checked_policy` | Versioned distinct selection rules; never rank checked rows by rounded numerical scores. |
| `limits` | At most 120 seconds, 64 times, two fixed-vector constructions, two pair verification passes, 2 MiB per certificate and 4 MiB aggregate bundle. Smaller reviewed values remain authoritative. |

The new exact proof rule is `alternating32-dyadic128.v1`. It fixes Taylor degree
32/33, outward dyadic rounding at 128 fractional bits, and at most ten range
reductions. Each admitted input and each rate/time product is a rational with
numerator and denominator of at most 256 bits; exponential arguments are at most
`1024/1`. There is no hidden precision, segment, degree or retry search. The
explicit analytic solution establishes continuation for this template. Stored
enclosures cover the listed historical and feasible future points; they are not
a universal forecast for all compatible assignments. See
[ANALYTIC_ARGUMENT.md](ANALYTIC_ARGUMENT.md) for the narrow argument.

## Identity and artifact rules

Public branding and Python imports are Counterdex. The existing
`groundwork.*.v1` schema strings, DB-SC-1 profile, `dr-bean` hash domains, model
identity and proof/selection policy identifiers stay unchanged. They are
normative compatibility values, not display labels.

The adapter implements DB-SC-1: normalized scientific scalars are reduced `n/d`
strings with positive denominator, integer `/1`, and zero `0/1`. Canonical JSON
uses sorted ASCII keys, preserved arrays and Unicode scalar text, UTF-8 and
minimal escapes. Floating JSON numbers, duplicate keys, unpaired surrogates,
unknown fields and excessive structures fail before scientific evaluation.

Typed semantic identities use SHA-256 of UTF-8 `dr-bean:<kind>:v1`, LF, and the
complete named canonical body. `problem` and `design-request` identities include
their entire normalized projections; a suggestion's own digest is outside its
hashed body. Artifact digests identify exact supplied bytes separately. Never
remove arbitrary nested fields named `digest` or `hash`, substitute transport
IDs for semantic identities, or calculate scientific inputs through floats.

Artifacts are supplied bounded bytes keyed by their digest. They are never
instructions to read a local path, import a module, fetch a URL or install a
package. Every supplied reference counts toward the aggregate byte budget.
Missing dependencies make replay incomplete. Pair replay parses serialized
bytes, binds exact candidate identities and parameters, freshly recomputes each
enclosure, checks historical allowances and recomputes strict margins and
selection. Cached badges do not authorize any of those conclusions.
The immutable initial published fixture packets are retained under
`fixtures/archive/initial-published-release/`. Their recorded source digests
require their original prepared source for fresh replay. Current Counterdex
fixtures are generated separately with current source identities; never edit an
archived JSON packet to apply a name change.

## Result semantics

Execution, numerical guidance, pair verification, binding and fresh replay are
separate fields. A completed numerical grid is not a compatibility certificate.
Failed or skipped rows remain in the grid; ranking covers only evaluated rows.
The numerical policy stores twelve-significant-digit half-even decimal scores,
orders descending stored score and then ascending exact time, and marks ties.
This reproduces selection from recorded diagnostics without claiming identical
transcendental bits across platforms.

Historical exact compatibility requires each whole concentration enclosure to
lie inside its row's `[value-allowance,value+allowance]` interval. A disjoint
enclosure establishes that selected candidate's measurement incompatibility.
Overlapping but insufficient containment remains inconclusive. A construction
failure does not establish incompatibility.

For two freshly compatible fixed candidates, exact center/error values give
`M = abs(p1-p2)-e1-e2-2*eta`. Only `M>0` separates their possible future data
bands; `M=0` does not pass. Checked selection prefers positive margins, larger
exact margin and earlier exact time, with IDs preserving candidate association.
No positive row produces `no_separation_established`, never a claim that no useful
experiment exists. The only guaranteed separation statement is that no one
datum at that time can fit both selected assignments under these assumptions.
The datum may exclude either candidate or both; other assignments can remain.

An actual follow-up uses its actual time, allowance and reviewed experiment
context in a new problem revision, then a new plan and approval. A suggested
time does not append an observation. A hypothetical value stays in a separate
hypothetical problem. Preserve the original problem, design and evidence bytes
when creating either branch. Eliminating an outside candidate does not establish
the original interval claim, and eliminating both candidates does not establish
global emptiness.

## Schema-owner adoption proposal

Owner 2 should review these proposed transport additions before generating
application clients. They are not adopted by merely importing this package.

| Proposed field | Purpose/type | Identity and failure behavior | Migration and examples |
|---|---|---|---|
| `proof_rule` | Versioned string identifying the exact analytic arithmetic policy. | Included in pair evidence and its raw digest; an unknown value is `unsupported_model`. | New evidence profile only. Valid: `alternating32-dyadic128.v1`. Invalid: an unspecified `auto` policy. |
| `source_artifact_digest` | Nullable lowercase 64-hex string associating each candidate with supplied bytes. | Included in design identity; wrong bytes give `artifact_mismatch`, absent bytes `incomplete_export`, unmatched pair association `missing_second_witness`. | New optional-by-explicit-null association. Valid: `artifact_digest(pair_bytes)` for both members of that pair. Invalid: one member references an unrelated or absent artifact. |
| `allowance_origin` | Object with `kind` and nonempty `description`. | Included in design identity; missing/unsupported kind is `invalid_input`. | Required explicit review for new designs. Valid: `{"kind":"hypothetical","description":"sensitivity control"}`. Invalid: `{"kind":"standard_deviation","description":"estimated"}`. |
| `horizon_policy` | Object with boolean construction/extension flags and exact rational maximum horizon. | Included in design identity; inadequate scope is `unavailable_horizon`. | New design approval must enumerate scope. Valid: a maximum covering history and all feasible checked times. Invalid: extension enabled while construction is disabled. |
| Numerical row status and rank scope | Each grid row retains status, reason, ID-keyed predictions and approximate string diagnostics. | Numerical report is immutable; partial results rank only evaluated rows. | New numerical projection, no forged exact badge. Valid: cancelled tail rows remain `skipped`. Invalid: omitted unevaluated rows shown as a complete-grid optimum. |

Owner 2 must retain the application-specific request, plan, approval, operation
and execution identities alongside these projections. Provider configuration
does not change the mathematical model, but belongs in the application execution
record. No fixture's transport ID is authority; fixture IDs are labeled as such.

## Stable failure families

`AdapterError.to_dict()` gives `code`, safe `message`, `field_paths` and `retryable`.
The backend adds its own request/current-revision fields. Do not expose stack
traces, source bytes or provider payloads in public errors.

| Code/family | Meaning |
|---|---|
| `invalid_input`, `unsupported_model` | Malformed/unknown fields or scientific scope outside this template. |
| `wrong_specification_binding`, `candidate_mismatch`, `artifact_mismatch` | Supplied evidence or exact vectors cannot attach to the expected problem/design. |
| `missing_second_witness`, `unavailable_horizon`, `incomplete_export` | Required matching evidence, authorized horizon or portable dependency is absent. |
| `construction_range`, `numerical_range_limitation` | Input is outside the fixed exact arithmetic or numerical evaluator policy. |
| `invalid_certificate`, `exact_check_failure` | Malformed evidence or a stored enclosure differing from fresh exact computation. |
| `measurement_incompatible`, `insufficient_enclosure` | Exact candidate-specific historical exclusion, or inconclusive enclosure containment, respectively. |
| `no_separating_time` | Checked finite-grid sufficient separation test found no positive margin. |
| `cancelled`, `resource_exhaustion` | Operational stop, never an empty compatible set. |

No provider calls, browser executions or deployment checks are represented by
the scientific test suite. Native installed-package and complete-bundle commands,
observed results and source/artifact identities belong in the release validation
ledger. Publishing the standalone package is a separate release action; shared
application transport adoption remains an integration task for Owner 2. This
package does not publish itself.
