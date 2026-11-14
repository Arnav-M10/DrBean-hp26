# Numerical comparison — frontend handoff

Working frontend: `codex/model-comparison-ui`, based on main `af71dd6`.
Frontend owns `workspace-preview`; numerical owner retains computation, public
API/DTO authority, persistence, approval and trusted connection setup.

## Required numerical-owner handoff

Supply the branch/commit, supported public synthetic plasma example and user-data
format, units/channel, model descriptions/parameter bounds, response assumptions,
noise/detection/hard-allowance semantics, and an executable request/result example.
The UI must also know the approved submit/review boundary, real queued/running/
terminal states, result identity/input binding, safe retry/idempotency/reuse rules,
optional cancellation and same-origin session/bootstrap setup.

Returned scientific data must include predictions for both models, residuals,
parameter sensitivity, approved noise-sweep cases, signal differences and detection
threshold, feasible-setting comparison, numerical limitations and provenance.
Omitted analyses will read unavailable; the browser will not generate physics.

## Frontend consumer seam (provisional, not a backend API declaration)

The UI uses a same-origin service manifest at `./comparison-service.json`.
The committed manifest is explicitly unavailable. Only the numerical owner may
enable it after supplying trusted same-origin routes and the agreed adapter.
No user-entered URL, bearer token, provider credential or cross-origin proxy is
introduced. Standalone Python static serving cannot become a trusted API proxy.

The frontend view model separates the immutable reviewed input, job state and
returned result. A generation fence rejects late responses; edits immediately
mark earlier results stale and clear review. A failed run keeps the prior result
and its original inputs/downloads labelled historical. No submission retry is
automatic. Noise-level selection reads only actual returned sweep cases; a new
noise request requires the service's explicit scoped approval contract.

The old saved example remains a separately labelled static mockup. It has no
submission authority and is never used as a fallback result. Reports carry the
same result/input binding and numerical limitations as the displayed evidence.
