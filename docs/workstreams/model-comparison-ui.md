# Model-comparison interface

Owner: frontend. Branch: `codex/model-comparison-ui`; base main `af71dd6`.

Current task: extend `workspace-preview` with data/model selection, explicit
review, computed-result charts and a readable self-contained report.
Retain the existing layout and bean identity; use the app's neutral dark palette.
No numerical/physics implementation, backend routing, auth or approval changes.

Works before this task: saved two-rate synthetic mockup and the separate qualified
Counterdex application. The mockup is not a plasma-analysis service.

Dependency: numerical-service owner must supply its published branch, supported
model/data catalog, request/result contract and trusted same-origin connection.
Main/published branches and the available local Codex handoff were inspected;
no plasma comparison service is published yet. Connected acceptance is blocked
until that implementation exists. No saved example will replace a failed run.

Design: keep the study rail and Data / Assumptions / Review views; results lead
with shared fit, differences, detectability, uncertainty and feasible settings.
Use system sans, 16px body, neutral #151619 / #1c1e22 surfaces, #f0f1f3 text,
#a0a5b0 helper text and restrained #b8cdf0 focus. Charts carry model identity.
Noise controls select actual returned sweep computations, never local simulation.

Next handoff: publish the frontend consumer seam and focused PR early, then
integrate the numerical owner's exact contract and qualify the connected browser.
