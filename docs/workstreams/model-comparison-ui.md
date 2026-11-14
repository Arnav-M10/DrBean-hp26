# Model-comparison interface

Owner: frontend. Branch / review: `codex/model-comparison-ui`, PR55.

Built: preferred `workspace-preview` researcher journey, current-channel CSV,
synthetic source and explicit-review controls, response/fit/noise/setting editors,
actual bound numerical results, residual/sensitivity/noise/MC views, immutable
history, stale-draft labels, result reuse and readable HTML + server JSON +
provenance. Existing saved concentration mockup remains visibly separate.

Integrated the numerical owner's published PR57 and production private transport;
no physics, computation, auth or API implementation was independently rebuilt.
Initial missing-service dependency was resolved by its subsequent publication.
Only five fixed static allowlist entries/tests change outside the frontend.

Verified so far: 13 actual launcher/browser gates; 15 frontend tests; 108 existing
web tests. Backend source at the service integration passed 1,372 tests with one
optional numerical-package skip (to be covered against latest main's package).
No provider calls, new public service, ledger reset or process-limit changes.

Current task: merge current main, rerun the final assembled browser candidate,
retain screenshots/receipts, push the focused PR for integration. Exact SHA and
final CI status belong in PR55; separate branch results are not release acceptance.

Limits: synthetic observations only; no calibrated experimental plasma, independent
instrument detection floor, hard allowance, queue/cancel endpoint, or exact
certificate. No physical device/Safari qualification. Cloud Chromium blocks
file://; the exact downloaded HTML renders with networking disabled instead.
