# Owner 3 metered Gemini implementation and integration handoff

Working branch: `codex/gemini-metered-adapter`, initially from main `cbfa5ef`.
During validation, PR32 merged; current main `b8c5952` was merged normally at
`2b510d22df74a27765d25c85b042816499eda173`. The only conflict was an import
in the owned ai_prompts.py. All current-main coordinator/tests were retained.
The latest Owner 3 brief supersedes historical placeholder-only instructions in
the workstream log. This branch implements the owned adapter; application startup
and the combined live paper workflow are pending the integrations below.
This is an internal Python adapter contract, not a second public DTO or ledger.
Owner 2 owns coordinator/tests, main/config wiring, canonical contracts and the
single durable ledger. Owner 4 owns paper parsing/page identity, launcher and UI.
Owner 3 owns providers, GeminiChatModel, paper prompts and grounded narration.

## Physical request boundary

`MeteredGeminiGateway(config, ledger)` is shared by direct structured calls and
`GeminiChatModel(gateway=..., context=...)`. Each physical `dispatch` reserves
exactly once with the EXISTING `begin_attempt(context, metadata)` and reconciles
with `finish_attempt`. No adapter-local session allowance, retries, provider file
uploads, polling, token counting, caching or automatic function execution exists.
Those auxiliary operations require Owner 2's separate durable accounting first.

For live admission Owner 2's injected ledger must advertise
`session_accounting_version = "research-session.v1"`; without that capability the
transport refuses before client construction. This marker is a server integration
contract, not a request option or proof by itself. Its `begin_attempt` MUST
atomically resolve owned session/action/operation/consent/model/source/page/review
identities and enforce allocated generation/action/session/token budgets (zero by
default; proposed ceilings 12/action and 24/session never relax lower caps).
The existing main ledger lacks this enforcement and is deliberately NOT accepted
for live dispatch. Unknown outcomes retain conservative reservations.

`SessionCallContext` carries actor_id, workspace_id, operation_id, consent_id,
research_session_id, action_id, model, review_revision_id, source_digests,
selected_page_manifest_digest, selected_page_ids, optional
selected_page_subset_digest and optional parent_action_id/specialist_id.
It is constructed by the server; values from paper/model output cannot grant
permissions. Both direct calls and child models retain these bindings. Owner 2
must NOT reserve a second physical attempt in coordinator middleware: retain
logical turn/tool admission there, physical metering here. Existing four-turn /
six-tool plan limits remain unchanged; new action types require versioned review.
Specialist identity is only a reference: Owner 2 must enforce at most two
specialists, depth one, admitted parent/action relationships and the same session
budget. The gateway does not implement delegation or grant its own allowance.

Modes: ProviderConfig.mode disabled (default), controlled (trusted local transport),
live (real SDK after admission). No code reads a secret file or environment key.
Owner 2/4 alone load explicitly selected server config. Proposed startup mapping:
BEAN_PROVIDER_MODE -> mode; BEAN_GEMINI_MODEL -> exact reviewed model;
BEAN_GEMINI_API_KEY -> server-only api_key;
BEAN_GEMINI_ACCOUNT_DECISION_ID -> server-only account_decision_id, resolved by
Owner 2 to account_gate_passed rather than trusting presence. Operation budgets
also map to ProviderConfig. These names are a proposed startup contract, not
implemented environment readers in the application. Owner 4 passes them only to
the backend process after explicit selection; existing launcher sanitization must
remain until it supports this contract. No dependency changes are requested:
all required packages already occur in the unchanged lockfile.
Never send keys to the browser. `capabilities()` reports mode/configured separately
from reachable/qualification (not_run), and never makes a diagnostic request.
Do not wire a live-start button until session/consent allocation is durable.

Diagnostic command: `python scripts/ai/provider_status.py`. It reports only field
presence, a bounded mode name, `application_wiring: pending_owner_2_and_4`, and
reachability/qualification `not_run`. It imports no SDK and performs no probes.
It never loads dotenv or a secret file. Presence is not proof the running server
uses that configuration. The retained diagnostic was run in a cleared environment.

Gateway status fields are `provider`, `execution_mode`, `configured`,
`session_accounting_ready`, `dispatch_enabled`, `dispatch_requires`, `reachable`,
`live_qualification`, `sdk_version`. Configured means key/model fields exist;
`dispatch_enabled: false` means there is no globally armed transport: every call
requires atomic admission. These are internal status fields; Owner 2 publishes
the authoritative capability DTO. They never certify account access.

The installed combination is google-genai 3.3.0 / LangChain core 1.8.0, using
models.generate_content, schema output for direct requests, tool declarations for
chat requests, automatic_function_calling disabled and HTTP retry attempts=1.
A deployment candidate is gemini-3.5-flash-lite, subject to account access and
explicit user-enabled qualification. No account capability, free entitlement or
model performance was probed. There is no default model or automatic fallback.
Official references: https://ai.google.dev/gemini-api/docs/models ,
https://ai.google.dev/gemini-api/docs/pricing ,
https://ai.google.dev/gemini-api/docs/rate-limits ,
https://ai.google.dev/gemini-api/docs/document-processing ,
https://ai.google.dev/gemini-api/docs/structured-output ,
https://ai.google.dev/gemini-api/docs/function-calling .
Specific deployment candidate documentation:
https://aistudio.google.com/docs/models/gemini-3.5-flash-lite .
Public documentation and installed SDK shapes were inspected; account access,
applicable price/rate tier and actual remote generate_content compatibility remain
unqueried. Model selection must be reviewed during authorized live qualification.

Operation profile `gemini-operation-budgets.v1` reserves at most the lower of
configured output cap and: agent 512, explanation 768, design/observation proposal
1024, intake/paper understanding 2048 tokens. Per-call overrides can only lower
that profile. Text/schema/tool/system UTF-8 bytes plus 1024 overhead form a local
conservative estimate, not observed tokens. Inline media additionally requires an
explicit measured model-specific `image_token_upper_bound` per part. Unknown media
cost blocks dispatch. Requests have the configured 1–60 second timeout, plus at
most one second of cooperative async transport cleanup grace. The unused SDK
sync pool closes locally too. Arbitrary injected Python is trusted, not sandboxed.

## Python consumers

```python
# Server constructs these references after resolving ownership/disclosure.
context = SessionCallContext(
    actor_id=actor_id, workspace_id=workspace_id, operation_id=operation_id,
    consent_id=consent_id, research_session_id=research_session_id,
    action_id=action_id, model=exact_model, review_revision_id=review_revision_id,
    source_digests=(original_sha256, subset_sha256),
    selected_page_manifest_digest=manifest_sha256,
    selected_page_ids=tuple(selected_page_ids),
    selected_page_subset_digest=subset_sha256,
)
gateway = MeteredGeminiGateway(config, session_ledger)
proposal_exchange = await gateway.understand_paper(
    retained_paper_context, context=context, subset_bytes=admitted_pdf_subset,
)
model = GeminiChatModel(gateway=gateway, context=context)
# bind_tools and with_structured_output retain exactly this gateway/context.
```

`GeminiExchange` returns `value`, `attempt_id`, `usage`, `execution_mode`,
`provider_request_id`, `model_version`, `simulated_usage`. Structured generate
returns the compatible ProviderResult. All paper outputs stay unaccepted and
scientifically unassessed. Missing/partial usage remains unknown; malformed usage
fails closed and no retry/refund occurs. Controlled metadata is simulated, never
billing or evidence of Gemini success. Transport failures expose sanitized codes.

`GeminiChatModel` is async-only. Its bind_tools accepts the tested bounded JSON
Schema subset; unsupported keywords/tool-choice/overrides refuse. Tool-call IDs
and opaque thought signatures survive round trips; private thought text is
rejected. It creates no clients/ledgers and disables environment-enabled tracing.
Owner 2 must remove the current coordinator's SDK-specific per-invocation kwargs
(`automatic_function_calling`, `max_retries`, `max_output_tokens`, `timeout`) when
using this model. Physical policy belongs to the gateway. The existing system
policy's JSON-only clause also needs the tool-turn wording used by this gateway.
The restricted inventory and explicit scientific approval gates stay in force.

## Integration dependencies

Owner 4 supplies retained original paper and bounded admitted selected-page
material; Owner 2 validates ownership/consent and binds the manifest to the call.
Original PDF, derived subset and physical page numbers must not be conflated.
The durable ledger MUST authenticate selected_page_subset_digest against exactly
the selected physical-page manifest. A generic disclosed digest is insufficient.
The gateway verifies that named subset digest against actual inline bytes and
rejects sending the full original PDF for a narrowed selection. It does not parse
PDFs or establish which pages arbitrary bytes contain: the trusted Owner 4 parser
and Owner 2 admission record must supply that attestation before live use.
Owner 3 validates proposed citations and explicit coverage before human review.
Paper proposal schemas here are internal until Owner 2 publishes the authoritative
application types; no persistence/materialization/approval shortcut is added.

Earlier PR28 guard changes were reused only in owned files; these are now also
on main through PR32. The coordinator is now Owner 2's. Before PR32 merged, one
old opaque-ID free-prose positive conflicted with bounded narration. Current
main already reconciles that expectation; no owned coordinator edit is included
here. Existing controlled conversation provenance/horizon DTO needs also
remain Owner 2's; manual factual fallback remains available.

PaperContext includes original ID/SHA, selected-manifest identity, byte size,
total_pages, full page metadata (page ID/SHA, physical_page, retained text and
optional rendered dimensions), and selected_page_ids. Proposed limits are 20 MiB,
50 admitted pages, eight selected pages per batch. Only selected text is sent;
oversized prompts refuse instead of truncating. The internal PaperProposal repeats
bindings, inspected/omitted pages, located findings, diagnostics and limitations.
Findings preserve original text/raw numeric spelling, optional exact candidate,
unit status, extraction method and uncertainty separately. Exact retained quotes
and visual bounds are checked, but a visual box remains proposed and human-review
blocking. Every hard allowance has a blocking scientific-modeling review note;
SD/SE/CI/error bars and clear negated bound claims cannot become deterministic
allowances. This is no proof of arbitrary prose or mathematical eligibility.

| Dependency | Owner | Required before combined live acceptance |
|---|---|---|
| Canonical paper/proposal/session DTOs and routes | 2 | Authenticate and persist original values/corrections; reject stale revisions; no approval from extraction |
| Durable research session/action consent ledger | 2 | Atomic 12/action, 24/session proposed ceilings, lower caps retained, zero initial allocation; unknown reservations retained across restart/retry |
| Coordinator/model and worker wiring | 2 | One physical attempt per gateway call, logical four-turn/six-tool caps, events/review references, no hosted model bypass |
| Parser/page subset, launcher and review UI | 4 | Bounded immutable physical-page mapping; consent disclosure; original/proposal/correction distinction; no raw key in browser |
| Scientific eligibility/projection fixtures | 1 | Explicit model and uncertainty interpretation; accepted exact values reach normal approved science |
| Independent combined qualification | Claude | Challenge the exact assembled commit, unchanged holdouts and bounded live sample after user allocation |

Relative to current main, no server-owned file, independent evaluator, web module,
launcher, dependency or lockfile is changed. PR32 is now merged at b8c5952. PR28's
owned guard/conversation implementation is present there, so its overlapping code
is superseded; compare any residual documentation before closing it. PR22 remains
independently owned. This candidate adds only the newer Gemini layer. No PR is
automatically merged or closed by this delivery.

## Evidence and limits

See [qualification record](evidence/gemini-adapter/README.md) for exact commands,
results, retained output and tested SHA. Offline tests include positive extraction,
real native scientific narration/replay, citation and uncertainty negatives,
malicious tool arguments, reserve-before-construction, shared parent/specialist
admission, retries/exhaustion, missing/malformed usage, cancellation and cleanup.
Synthetic ledger tests establish the adapter's behavior against a supplied
admission authority, not implementation of the missing production session ledger.
No live accuracy, usefulness, latency or billing score is claimed.

### Predeclared live sample: not_run, allocation zero

After Owner 4 provides the shared synthetic/public PDF fixture and Owner 1 its
canonical expected projection, Claude can qualify one complete session on the
assembled commit. Proposed sample: one selected-page extraction (one call), a
baseline action (at most three calls), separately reviewed design (at most two),
then one follow-up explanation after separately reviewed real science (one).
Maximum seven generation calls in the same research_session_id; zero specialists,
zero automatic retries, zero auxiliary provider operations. This is a proposed
qualification scope, not user consent or allocated credits. If it cannot fit the
existing four-turn/six-tool action caps, stop and report that limit. Source or
disclosure changes require a fresh review without resetting the session allowance.
Record exact emitted/located/correct citation denominators, exact-value/unit
matches, abstentions, human correction count, request latency, observed tokens,
unknown outcomes and retrieved/replayed downstream evidence. Include uncertainty
misuse and unsupported-model cases offline before live qualification. Report
unexecuted cases as not_run. No model-generated scientific success score is used.

Two-minute feature explanation: Gemini can propose a page-cited reading of a
paper while retaining the original spelling, proposed exact value, source page,
uncertainty and unresolved assumptions. A person still checks/corrects those
values. The shared model adapter lets the approved agent select only the tools
the backend exposes; every physical model request goes through one reservation
boundary. Counterdex supplies the mathematical evidence, and narration can state
only supported bounded facts. A next measurement and follow-up each need their
own review. Manual science works when Gemini is disabled or unavailable. This
branch supplies that Gemini layer and its offline evidence; the ordinary live
paper-to-evidence experience awaits the backend and browser integrations above.
