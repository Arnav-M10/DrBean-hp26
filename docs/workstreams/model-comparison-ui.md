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

Verified: 14 actual launcher/browser gates at clean source `9d28103`; 123 combined
web/frontend tests. Backend source passed 1,372 tests with one optional registry
skip; that registry check subsequently passed against the numerical package on
current main. Ruff, schema export and secret scan pass.
No provider calls, new public service, ledger reset or process-limit changes.

Current task: delivered for integration in PR55. Current main `7d40d1c` is
incorporated; service and numerical owner history is preserved. Screenshots,
receipt, exact source SHAs and walkthrough are in docs/frontend/model-comparison/.
Final PR head adds qualification documentation/screenshots only after tested code
9d28103. CI and any merge decision remain visible on PR55; this is not a whole
product or live-provider release verdict.

Limits: synthetic observations only; no calibrated experimental plasma, independent
instrument detection floor, hard allowance, queue/cancel endpoint, or exact
certificate. No physical device/Safari qualification. Cloud Chromium blocks
file://; the exact downloaded HTML renders with networking disabled instead.
