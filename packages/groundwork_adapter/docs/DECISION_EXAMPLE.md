# Controlled synthetic decision loop

The executable example discovers two historically compatible vectors from five reviewed synthetic measurements, chooses an 8-hour reading for that actual pair, and freshly checks three possible hypothetical readings. A changed 4-hour measurement produces a different pair with no separating time on the same reviewed grid. Every result has complete native bytes and separately persisted replay anchors.

These are controlled synthetic measurements, not collected experimental data or literature validation. No AI explanation, live provider, API key or network call is needed. This is a scientific engine and local bridge example; it does not establish that an HTTP worker, browser or real organization completed the task. The application owns review, revision creation, approval and authoritative persistence. Workflow IDs in these fixtures are synthetic labels, not evidence of a person's authorization.

## Reviewed inputs and actual discovered candidates

The supported model is `c(t) = A(exp(-ke*t) - exp(-ka*t))` with its fixed initial state, hours, mg/L and inverse hours. The domain is `A ∈ [0.001,30]`, `ke ∈ [0.015,0.35]`, `ka ∈ [0.4,8]`. The closed claim is `ke ∈ [0.10,0.17]`; equality with either endpoint is inside. Every historical hard allowance is 0.50 mg/L.

| Elapsed time (h) | Synthetic concentration (mg/L) | Reference prediction | Reference residual | Outside prediction | Outside residual |
|---:|---:|---:|---:|---:|---:|
| 0.25 | 4.80 | 5.051219 | 0.251219 | 5.131781 | 0.331781 |
| 0.50 | 7.20 | 6.991072 | -0.208928 | 6.985024 | -0.214976 |
| 1.00 | 8.00 | 7.763979 | -0.236021 | 7.685321 | -0.314679 |
| 2.00 | 6.80 | 7.059958 | 0.259958 | 7.128115 | 0.328115 |
| 4.00 | 5.70 | 5.467052 | -0.232948 | 5.846394 | 0.146394 |

Displayed predictions are enclosure centers and residuals are prediction minus measurement. Six-decimal rounding is for reading only. Exact interval endpoints, exact residual ranges, allowances, inclusion flags and row identities are in [hero-baseline.display.json](../fixtures/decision/hero-baseline.display.json); its native historical checker verifies whole-enclosure containment independently.

| Role | Candidate ID | A (mg/L) | ke (1/h) | ka (1/h) | Fresh historical status |
|---|---|---:|---:|---:|---|
| Reference | `search-0eccc519575b1d4c9211000a` | 9.138000 | 0.128425 | 3.511811 | Compatible; inside closed claim |
| Outside | `search-d226b3dd1f1a38698e9cc420` | 8.701219 | 0.099409 | 3.811024 | Compatible; strict counterexample |

The exact reference vector is `(913800036733/100000000000, 1631/12700, 446/127)`. The exact outside vector is `(435060970491/50000000000, 101/1016, 484/127)`; `101/1016 < 1/10`. These vectors are actual search outputs from this input, not production constants. The retained numerical reference is ranked by maximum absolute residual divided by that row's hard allowance; it does not assert a confidence interval or a global optimum.

The disclosed policy `rate-grid-amplitude-midpoint-12sig.v1` evaluates a 128×128 rate grid in ascending `ke`, then `ka`, with inclusive domain endpoints. Each rate pair screens the feasible amplitude intersection and freezes a 12-significant-digit midpoint as an exact rational. This example attempts 16,384 rate pairs, retains 32 numerical proposals from 613 numerically feasible pairs, and checks two proposals before selecting the reference and outside witness. The exact checker then constructs and independently replays the selected historical certificate. The manifest and native bundle retain the policy, caps, attempt counts, residual diagnostics and exact vectors.

## Separate measurement decision and hypothetical feedback

The example separately supplies construction and later-horizon continuation authority, a 120-second cap, two fixed-vector constructions, two allowed pair-verification passes and a 4 MiB complete-bundle limit. The reviewed application grid is `[8,6]` hours; projection restores that approved order in the application result. Future hard allowance is 0.20 mg/L. The exact criterion is `abs(p1-p2) - e1 - e2 - 2*eta > 0`; equality does not pass.

| Grid time (h) | Reference possible-reading band (mg/L) | Outside possible-reading band (mg/L) | Exact margin displayed (mg/L) | Decision |
|---:|---|---|---:|---|
| 6 | [4.028682, 4.428682] | [4.592281, 4.992281] | 0.163599 | Separating |
| 8 | [3.070818, 3.470818] | [3.728225, 4.128225] | 0.257407 | Selected |

The native checker freshly verifies both candidates against history before deriving the finite-grid margins. This is a recommendation for these selected vectors, this grid and this allowance. [hero-design.display.json](../fixtures/decision/hero-design.display.json) contains exact centers, errors, bands and margins. [decision-summary.json](../fixtures/decision/decision-summary.json) includes both candidates' historical and future curve points, with exact values and six-decimal display values; connecting those points is only a display aid.

Each following case appends one hypothetical observation at the actual selected 8-hour time with the reviewed 0.20 mg/L allowance. A new dataset and problem ID/digest preserve the original rows and bind the original design bytes. The checker keeps the original candidate IDs and parameter vectors and rebinds them to the revised problem.

| Hypothetical reading (mg/L) | Reference | Outside | Scoped result |
|---:|---|---|---|
| 3.270818 | Compatible | Excluded | The selected outside candidate is excluded; the original interval is not proved |
| 3.928225 | Excluded | Compatible | A selected compatible outside witness remains |
| 3.599521 | Excluded | Excluded | Neither selected vector explains the revision; whole-model impossibility is not established |

All three evidence packets freshly replay successfully. Correctly checked exclusion is valid evidence with an incompatible candidate; it is different from a corrupt certificate or a false stored enclosure. Pair design is unavailable when fewer than two selected candidates remain compatible. See the `hero-reference-survives`, `hero-outside-survives` and `hero-both-excluded` file families in [fixtures/decision](../fixtures/decision).

## Changed-input result and fixed-pair constraints

The alternate reviewed dataset changes only the 4-hour concentration from 5.70 to 5.30 mg/L, updates its original spelling and revision identity, and keeps the same domain, claim and hard allowances. Actual search discovers a new reference `(A≈9.603985, ke≈0.157441, ka≈3.272441)` and outside candidate `(A≈9.945597, ke≈0.170630, ka≈3.033071)`. Both freshly fit the revised history. With the same grid and 0.20 mg/L future allowance, exact margins are approximately -0.238607 at 6 hours and -0.214317 at 8 hours: **no separation established** and no selected time. [alternate-design.display.json](../fixtures/decision/alternate-design.display.json) records this outcome; no demonstration pair or time is substituted.

Separate regression controls use the supplied fixed audit vectors `(9.041075603155,0.122,3.54)` and `(8.267973235218,0.074,4.17)`. These constants occur only in the fixture generator and tests. They are not used by the production discovery operation.

| Fixed-pair control | Reviewed times (h) | Future allowance (mg/L) | Checked result |
|---|---|---:|---|
| `fixed-pair-8h` | 6, 8 | 0.20 | Select 8; margin 0.767190 |
| `fixed-pair-6h-only` | 6 | 0.20 | Select 6; margin 0.555349 |
| `fixed-pair-wide-allowance` | 6, 8 | 0.60 | No separation; margins -0.244651 and -0.032810 |

Each control preserves the full exact engine input, problem/design/result identities, raw bundle and fresh replay. The generator also checks each margin against an independent narrow audit interval. Historical compatibility and replay stay valid in the no-separation control.

## Contribution from the same reviewed data

| Component | Concrete output | What it adds |
|---|---|---|
| Numerical reference fit | Inside-claim vector and per-row residuals | An explicit explanation of these measurements, without an interval guarantee |
| Separately checked outside candidate | Compatible exact vector with `ke < 0.10` | This closed claim is not forced by the reviewed hard bounds under the model |
| Reviewed finite-grid decision | 8 hours; strict positive margin 0.257407 mg/L | A pair-specific measurement decision using the reviewed grid and precision |
| Candidate-specific follow-up | Reference-only, outside-only and both-excluded cases | New feedback with preserved history, exact checking and offline replay |

This is a controlled feature comparison, not a comparative study of scientific software. A finite search finding no witness would establish only that bounded search outcome. A fit alone makes no confidence-interval claim to refute. All conclusions remain conditional on the reviewed model and hard bounds.

## Run, inspect and replay

Run from the repository root with a qualified CPython 3.11. This example machine uses `/opt/homebrew/bin/python3.11`; use the prepared interpreter selected by your deployment. Generation writes only the separate decision-fixture directory. It leaves the frozen archive and other fixture families untouched.

```sh
ENGINE_PYTHON=/opt/homebrew/bin/python3.11
"$ENGINE_PYTHON" packages/groundwork_adapter/scripts/generate_decision_fixtures.py
```

The generator executes seven actual bridge subprocesses and seven separate offline replay subprocesses, plus three exact fixed-pair regression controls. It aborts if source identity changes during generation. After any scientific source edit, regenerate these current examples with the final source version; never relabel archived bytes. [manifest.json](../fixtures/decision/manifest.json) records the source manifest, qualified runtime, actual attempt counts, raw artifact sizes/hashes and observed operation/replay latencies. Timings are local diagnostics, not performance guarantees.

Integration example 1 runs the complete historical request through the prepared stdin/stdout bridge:

```sh
PYTHONPATH=packages/groundwork_adapter "$ENGINE_PYTHON" -m counterdex.bridge \
  < packages/groundwork_adapter/fixtures/decision/hero-baseline.request.json \
  > /tmp/counterdex-hero-baseline.response.json
```

Integration example 2 supplies the actual historical candidate IDs/vectors, full original source bodies, matching raw baseline bytes and separately bound design request:

```sh
PYTHONPATH=packages/groundwork_adapter "$ENGINE_PYTHON" -m counterdex.bridge \
  < packages/groundwork_adapter/fixtures/decision/hero-design.request.json \
  > /tmp/counterdex-hero-design.response.json
```

The stored design request embeds its exact original baseline, so the command is self-contained. When constructing a new design after a newly executed baseline, bind that new response's artifact/hash/anchors and candidate outputs. The generator's `design_request` helper demonstrates that transition. Historical references alone are insufficient.

Offline replay has no application server or search dependency. This request contains the exact native bytes and the separately persisted expected anchors:

```sh
PYTHONPATH=packages/groundwork_adapter "$ENGINE_PYTHON" -m counterdex.bridge \
  < packages/groundwork_adapter/fixtures/decision/hero-design.replay-request.json
PYTHONPATH=packages/groundwork_adapter "$ENGINE_PYTHON" -m counterdex.bridge \
  < packages/groundwork_adapter/fixtures/decision/hero-both-excluded.replay-request.json
```

Every operation has `.request.json`, `.response.json`, `.native.json`, `.anchors.json`, `.replay-request.json`, `.replay.json` and `.display.json` files. Native artifacts are exact bytes without an appended newline. Application/native identities are different, explicitly retained anchors. They are content bindings, not signatures or proof of authorization.

Validate the seven application requests and results with the authoritative DTOs in a prepared API environment. On this machine the isolated contract-check environment is `/tmp/counterdex-contracts-check/bin/python`; deployment can use its prepared API interpreter:

```sh
/tmp/counterdex-contracts-check/bin/python \
  packages/groundwork_adapter/scripts/check_application_schema.py \
  --fixtures packages/groundwork_adapter/fixtures/decision
```

The observed schema check passes 7 requests and 7 results. The fixed-pair controls use native engine input shapes and can be replayed with:

```sh
PYTHONPATH=packages/groundwork_adapter "$ENGINE_PYTHON" -m counterdex replay \
  packages/groundwork_adapter/fixtures/decision/fixed-pair-6h-only.bundle.json \
  --anchors packages/groundwork_adapter/fixtures/decision/fixed-pair-6h-only.anchors.json
```

Owner 2 can use these paired request/response/native examples to wire the real worker and atomic artifact publication. Owner 4 can render the display records without reconstructing scientific verdicts. Owner 5 can replay the bytes independently and use the existing evaluation harness to test the actual HTTP route, cancellation and orphan-process behavior. Browser replay remains unavailable.

<!-- decision-run:start -->
## Recorded local execution

The current fixtures were generated with Counterdex 0.3.0 on CPython 3.11.17. The engine source digest is `510580863d6dbb13a569f7f28ad9822111a50356981208e08608827fcef4ee69`. 8 scientific bridge subprocesses and 8 separate replay subprocesses completed; all replayed successfully. Three separately labeled fixed-pair controls also freshly replayed.

| Operation | Observed bridge seconds | Observed separate replay seconds | Native bytes |
|---|---:|---:|---:|
| `hero-baseline` | 0.299753 | 0.072867 | 53950 |
| `hero-design` | 0.148657 | 0.108617 | 110479 |
| `hero-reference-survives` | 0.241014 | 0.181843 | 177459 |
| `hero-outside-survives` | 0.237166 | 0.161284 | 177475 |
| `hero-both-excluded` | 0.250072 | 0.146210 | 177419 |
| `hero-own-time-recheck` | 0.237018 | 0.133656 | 179187 |
| `alternate-baseline` | 0.284482 | 0.066284 | 54181 |
| `alternate-design` | 0.129358 | 0.096051 | 110991 |

These are measured local runs with no provider requests. The complete per-operation counters, source manifest and exact artifact hashes are retained in `fixtures/decision/manifest.json`; latencies are not an HTTP result or a general performance guarantee.
<!-- decision-run:end -->
