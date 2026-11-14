# Reviewed numerical comparison — frontend qualification

The preferred `workspace-preview` now consumes the merged numerical service through
its existing private-session transport. No scientific equations, fitting, API,
authority, ledger or trusted proxy implementation was independently recreated.
The pre-existing qualified application remains at `/`; this interface is at
`/workspace-preview/comparison.html` on that same origin. Frontend ownership is PR55.

## Exact candidate and scope

Clean, tested application/frontend source:
`9d28103618f16fbfa6a70f4db001da2510ea4af2`, incorporating main `7d40d1c`
and the numerical owner's merged PR57. Subsequent qualification changes contain
only this documentation, selected captures, receipt and progress note.

[Machine-readable receipt](receipt.json) records 14 passing gates, exact Git HEAD,
empty tracked changes, input/source digests and actual operation counts. Backend
`drbean_bounded_grid_reference.v1`, source digest
`8ed3094b5e1e4bbe6850839f5b155dd1adc8c0a53b3d24e7015ed6587fce61ac`.
The optional Counterdex numerical registry adapter is separately tested; the
reference backend remains the returned production implementation, not a claim
that all numerical operations were dispatched through that adapter.

| Validation | Actual result |
| --- | --- |
| Ordinary launcher → private browser UI → API → production numerical subprocess | 14 grouped checks passed on clean 9d28103 |
| Frontend state/report tests and existing web tests | 123 passed (15 new + 108 retained); new tests rerun after final presentation changes |
| Full backend, excluding independent integration | 1,372 passed, one optional numerical-registry skip, two third-party SyntaxWarnings |
| Previously skipped registry adapter, with current main's package | One passed separately |
| Ruff / generated schema drift / secret scan / whitespace | Passed; zero secret findings |

Full backend execution used the service-integrated backend source at `01f1997`.
The final backend and its existing tests are unchanged from that run. The optional
package arrived with main afterward and its real registry bridge was exercised
separately; its skip is not silently counted as a pass. Provider calls were zero.
This frontend pass is not a new independent-evaluator or entire-release verdict.

## What the actual browser proved

- Static serving remains draft-only, with zero comparison POSTs and no saved-result
  fallback. The public sample is an input fixture, not a result cache.
- A person loads the newly generated plasma example, reviews channel geometry,
  response/fit/noise/measurement scope, and explicitly approves one request.
  The actual response opens Results without Save/Prepare/Advance/Open chores.
- Both fits, returned residuals, five numerical parameter-sensitivity series,
  actual conditional Monte Carlo tables and feasible-setting comparisons render.
  Noise selection reads returned cases only. The highest declared noise case
  reports the actual ambiguous outcome; no model-truth confidence is invented.
- Doubling the reviewed observations changes the real fitted densities by a
  factor of two. The input digest changes and earlier evidence remains retained.
- An identical completed request is reopened without another computation.
- Real `budget_exceeded` remains bounded and honest. A separately injected HTTP
  failure preserves prior evidence with a historical-input label. That fault
  injection is a UI transport diagnostic, not a fabricated scientific outcome.
- CSV input remains local until origin confirmation and fresh explicit review.
  Experimental origin is refused honestly. No synthetic substitution occurs.
- Two private browsers remain isolated. Reload restores retained results without
  computation. Lost cookies block downloads; explicitly starting a replacement
  workspace clears prior client evidence/approval keys and transfers no history.
- 320/390/834/1440px layouts, 200% CSS reflow, native keyboard scrolling of narrow
  plots, a keyboard noise selector, focus and reduced motion pass in Chromium.

The isolated run retained four immutable numerical records / four operations,
three private workspaces after explicit recovery, and zero provider attempts,
Counterdex jobs or separate Counterdex approvals. Numerical approval is the
service's reviewed request; these counts do not mean its approval was bypassed.
API/worker/query Python processes are egress-guarded. The numerical child uses its
normal production credential-free environment. No external page requests or
client JavaScript errors were observed. Existing services/stores were untouched.

## Short walkthrough

Check out PR55's `codex/model-comparison-ui`, run `scripts/dev/setup.sh`, then
`scripts/dev/start.sh`. Open the printed web origin plus `/workspace-preview/comparison.html`.

1. **Use synthetic plasma example** → inspect observations and both model families.
2. **Assumptions** → inspect instrument, density/temperature grid, Gaussian noise,
   band multiplier, simulation scope and feasible settings.
3. **Review** → tick explicit approval → **Approve and compare**.
4. Inspect Summary / Residuals / Sensitivity / Noise & next measurement. Use the
   keyboard or pointer to select the highest returned noise case.
5. **Download readable report**, supporting **Server JSON**, and provenance.
   Change observations and repeat review to obtain a fresh, bound computation.

Reproduction commands and static-mode instructions: [workspace README](../../../workspace-preview/README.md).
Run `node workspace-preview/check-connected.mjs` with the pinned Playwright module
and browser selected as described there. CI runs this exact interface runner and
retains its report, screenshots and JSON evidence as a separate artifact.

## Captures and readable evidence

- [Computed result, desktop](computed-result-desktop.png): real first comparison,
  original reviewed inputs, no injected error.
- [High-noise outcome](computed-noise-desktop.png): actual returned ambiguous case
  and conditional simulation frequencies.
- [Retained evidence, phone](computed-result-phone.png): earlier computed result
  after a separately injected transport failure, correctly labelled historical.
- [Standalone readable report](readable-report.png): exact downloaded HTML rendered
  with networking offline, including actual computed plots/tables.

Full HTML and bound JSON are retained locally under ignored
`var/model-comparison/`; CI's separate artifact retains those files. Managed cloud
Chromium refused `file://` with `ERR_BLOCKED_BY_ADMINISTRATOR`; the runner closes
that blocked page and renders the exact saved HTML bytes in a fresh offline page.
It records the actual file-open/fallback outcome per environment. No network or
API dependency is needed by the report. Direct file opening on a normal desktop
was not established by this cloud fallback. Initial policy/harness/overflow
failures were preserved in local logs and corrected; no frozen predicate changed.

## Boundaries

Only newly generated synthetic observations are admitted by this service version.
No experimental plasma details or personal attribution/quotation were added.
The idealized response does not calibrate or imply endorsement by a researcher,
institution or instrument. Temperatures mean kBT/e in eV, not kelvin. Observation
index is not seconds or energy; connecting lines only guide the eye between
sampled predictions. No continuous fitted curve was returned.

Gaussian σ, the derived 2zσ band-separation threshold, an independent instrument
floor and a deterministic hard allowance are distinct. The latter two are not
modelled. Monte Carlo conditions on fitted vectors without refitting or propagating
parameter uncertainty; Wilson intervals concern sampling frequencies only.
No queue, percentage-progress or cancellation endpoint is invented. Missing,
unsupported, ambiguous and bounded results do not acquire verified badges or
exact native certificates. Safari/WebKit, physical touch, a screen-reader session,
live providers and public deployment remain unqualified.

Frontend-design, Impeccable Operate/harden/adapt/craft-floor, current Vercel interface
accessibility guidance and Playwright testing guidance were applied to the retained
layout. Impeccable's context launcher was unavailable; context was read directly.
No detector binary, framework, font download or component library was introduced.
