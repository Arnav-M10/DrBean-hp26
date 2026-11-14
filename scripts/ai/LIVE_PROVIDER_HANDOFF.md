# Owner 3 provider interface proposal v1

Working branch: `codex/gemini-metered-adapter`, from main `cbfa5ef`.
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
selected_page_manifest_digest and optional parent_action_id/specialist_id.
It is constructed by the server; values from paper/model output cannot grant
permissions. Both direct calls and child models retain these bindings. Owner 2
must NOT reserve a second physical attempt in coordinator middleware: retain
logical turn/tool admission there, physical metering here. Existing four-turn /
six-tool plan limits remain unchanged; new action types require versioned review.

Modes: ProviderConfig.mode disabled (default), controlled (trusted local transport),
live (real SDK after admission). No code reads a secret file or environment key.
Owner 2/4 alone load explicitly selected server config. Proposed startup mapping:
BEAN_PROVIDER_MODE -> mode; BEAN_GEMINI_MODEL -> exact reviewed model;
server-only api_key/account_decision_id and operation budgets -> ProviderConfig.
Never send keys to the browser. `capabilities()` reports mode/configured separately
from reachable/qualification (not_run), and never makes a diagnostic request.
Do not wire a live-start button until session/consent allocation is durable.

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

## Integration dependencies

Owner 4 supplies retained original paper and bounded admitted selected-page
material; Owner 2 validates ownership/consent and binds the manifest to the call.
Original PDF, derived subset and physical page numbers must not be conflated.
Owner 3 validates proposed citations and explicit coverage before human review.
Paper proposal schemas here are internal until Owner 2 publishes the authoritative
application types; no persistence/materialization/approval shortcut is added.

Earlier PR28 guard changes are reused only in owned files. The coordinator is now
Owner 2's: its old opaque-ID free-prose positive expects acceptance and must be
reconciled to the bounded narration policy by that owner (retain nonnumeric
classification and every scientific negative control). No coordinator edit is
included here. Existing controlled conversation provenance/horizon DTO needs also
remain Owner 2's; manual factual fallback remains available.
