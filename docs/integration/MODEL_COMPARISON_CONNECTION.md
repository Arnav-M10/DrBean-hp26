# Private numerical comparison connection

The numerical service works without model-provider calls. It serves reviewed,
newly generated synthetic data through the application's existing private
browser session. Numerical fits and Monte Carlo frequencies are not exact
Counterdex certificates.

## Connected mode

Use the ordinary application server and its configured private-session proxy.
Open `/workspace-preview/` on the **same origin** as the working application,
including the trailing slash. For an already running local application, this
means appending `workspace-preview/` to the web address printed by the launcher.
For a configured shared link, append the same path to that HTTPS origin.
The normal setup/start instructions remain in the repository README. No second
port, bearer token, model-provider consent, or alternate owner is needed by this
workflow. The comparison route itself never calls a provider.

The trusted web server provides:

```json
{
  "schema_version": "DB-MODEL-COMPARISON-CONNECTION-1",
  "available": true,
  "mode": "private_session",
  "module": "/comparison-api.mjs",
  "request_schema": "DB-MODEL-COMPARISON-1",
  "result_schema": "DB-MODEL-COMPARISON-RESULT-1"
}
```

at `/workspace-preview/comparison-service.json`. `available` declares that this
server supplies the trusted connection module; it is not a service health check,
scientific result or proof of authorization. The module must still confirm the
private cookie/session and the current backend's offline-comparison capability.
An unavailable/incompatible backend fails closed. Merely copying this manifest
to a static server does not create a trusted proxy or backend authority.

The UI owner controls the page's review, approval and stale-result presentation.
The transport supplied here does not itself replace that interface. Until that
consumer is integrated, the retained workspace-preview page remains a labelled
static mockup even when these connection routes exist.

## Consumer interface

The UI checks the fixed manifest and imports the fixed same-origin module only
in connected mode. It must not accept a visitor-supplied module or API URL.

```js
import { connectComparison } from '/comparison-api.mjs'

const comparison = await connectComparison()
// Called only after review and explicit approval of this complete request:
const record = await comparison.submit(reviewedRequest)
const result = record.body
// Returned bytes have been checked against the selected immutable record:
const { bytes, filename, digest } = await comparison.download(record)
```

The request is the executable `DB-MODEL-COMPARISON-1` contract in
`apps/api/bean_api/model_comparison/contract.py`. Scientific scalars are decimal
strings; seeds and counts are safe nonnegative integers. A complete request
includes `review.reviewed: true` and `approval: "approved_for_this_request"`.
Absent instrument assumptions are normalized to explicit `instrument: null`
and produce the backend's honest unsupported response.

| Member | Behavior |
| --- | --- |
| `workspaceId`, `session` | Current private browser session metadata; no credential value. |
| `capabilities` | Confirmed backend numerical capability, frozen for this connection. |
| `submit(request, { operationKey } = {})` | One explicit POST. Copies the request before sending and checks the returned request/input digest/result digest. Optional bounded operation key supports a UI-managed pending operation. |
| `list()` | Reads this workspace's retained comparison records. No computation starts. |
| `get(id)` | Reopens one immutable comparison and checks identity, workspace and digests. |
| `download(record)` | Returns `{ bytes, filename, digest, record }` for the selected immutable record. Checks the actual download hash, export schema and exact record/input binding. |
| `setConnectionFailureHandler(handler)` | Reports session/transport failures to presentation code without retrying a mutation. |

`connectComparison({ startNew: true })` is reserved for the person's explicit
new-workspace choice after a session-recovery state. Ordinary connection retries
must use the default `false`. Existing private-session code retains continuity
markers and requires a deliberate choice when the previous cookie is lost.
No model comparison call silently transfers history to a replacement identity.

The API prefix is `/api/bean/v1`; comparison routes are
`/workspaces/{workspaceId}/model-comparisons`, `/{comparisonId}`, and
`/{comparisonId}/download`. All ordinary comparison requests remain same-origin
and cookie-authenticated. The server validates workspace membership. The fixed
proxy strips client-supplied Authorization, owner identities and gateway proofs.

## Results, errors and retry

POST returns a retained record, not a queue job or synthetic progress sequence.
The request is in flight while the actual bounded computation executes. The
record's `body.status` is `completed`, `unsupported`, `fit_failed`, or
`budget_exceeded`; scientific failure states still have retained input-bound
records. Transport/execution failures produce API errors and must not be
rendered as scientific findings. There is no cancellation or operation-status
endpoint in this initial service.

The module never automatically retries a mutation. Within one connection,
explicitly resubmitting identical request bytes reuses the existing operation
key; a changed request gets a different key. If the UI supplies its own key, it
must preserve it with the exact pending request, including across refreshes if
recovery is offered. Reusing that key with changed bytes is refused by the
backend. A completed same-key operation returns its retained record; pending or
interrupted operations are refused rather than re-executed. After an uncertain
response, read retained history before offering another deliberate operation.

The transport verifies byte and identity binding only. Successful download
integrity does not upgrade `fit_failed`, an ambiguous result, numerical
sensitivity, or Monte Carlo frequency to an exact guarantee. This is a numerical
JSON export, not a native Counterdex exact-replay packet. Reports must retain
the result's limitations and distinguish the current reviewed input from a
historical record.

## Static mode and examples

Directly serving `workspace-preview` with a generic static server remains static
preview mode. A missing manifest or `available: false` means no service; it must
not trigger an API request or fall back to a saved result as though computed.
The UI owner maintains its static manifest and labels. The trusted server's
manifest is generated in memory, independently of that file.

The fixed public synthetic example/schema routes are:

- `/workspace-preview/examples/synthetic.request.json`
- `/workspace-preview/examples/synthetic.response.json`
- `/workspace-preview/examples/request.schema.json`
- `/workspace-preview/examples/result.schema.json`

The response is a retained generated fixture, not a new browser run. No private
research material is exposed. The server serves an explicit path allowlist;
arbitrary repository paths, dotfiles and directory traversal are not accepted.
The shared gateway's cross-site navigation exception permits only the two exact
preview entry documents. The manifest, modules and API still require the
existing origin boundary.

## Retained connection checks

```sh
node --test apps/web/comparison-api.test.mjs \
  apps/web/comparison-serving.test.mjs apps/web/session.test.mjs \
  apps/web/serve.test.mjs apps/web/share-gateway.test.mjs
```

Result during implementation: **36 tests passed**. Eight new tests cover the
actual connector/serving implementation: capability refusal, private session
reuse, review gates, explicit same-key retry, changed requests, substitution
refusal, bound downloads, numerical-status preservation, fixed static routes,
unconfigured access refusal and shared-link origin restrictions. They combine
actual server processes on temporary ports with deterministic transport
fixtures. They are transport component tests; qualification of the combined UI
and real scientific service is a separate integration check.

The actual connected transport can be checked without depending on unfinished
UI presentation code:

```sh
BEAN_TEST_PYTHON=/absolute/path/to/backend/python \
PLAYWRIGHT_MODULE=/absolute/path/to/playwright \
node tests/integration/model_comparison_browser.mjs --results /tmp/comparison-evidence
```

This harness starts its own API and web server on temporary ports, creates only
temporary stores and dummy gateway records, and opens two real Chromium
contexts. It imports the production connector from the actual preview origin
and uses the production numerical subprocess. Seven checks passed during
implementation: distinct private workspaces; one immutable computation with
same-key repeat/read/history/download agreement; doubled observations changing
fitted density; second-visitor read/download/submit denial; missing instrument
remaining unsupported after export; reload reopening the original identity;
and zero provider attempts, provider jobs, external page requests or guarded API
egress attempts. It retains `evidence.json` and the actual `original-export.json`
in the requested results directory. Git HEAD, tracked working-tree changes,
source/input digests and the exact numerical backend are recorded so a working
tree run cannot be mistaken for acceptance of a later commit.

The API and evidence-query Python processes run with the evaluation egress
guard. The production compute subprocess receives its normal credential-free
environment rather than a modified test runner; that distinction is retained
in the evidence. The page's controls, charts and report flow are explicitly
`not_run_transport_only` in this harness, and require the UI owner's separate
combined workflow qualification.
