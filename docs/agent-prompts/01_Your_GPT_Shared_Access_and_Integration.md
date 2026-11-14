# Prompt 1 — your GPT — private automatic access, shared server and final integration

Work in **https://github.com/Arnav-M10/DrBean-hp26**. Implement this role to completion, test it, open/update a PR, and integrate the three owners' compatible work after the required checks pass. Preserve other people's work. Use an isolated worktree and a role branch; do not reset, force-push, discard uncommitted changes or merge every historical PR blindly.

## Goal and current state

Dr. Bean should let people bring their own research data, ask Gemini to understand it, review source-grounded interpretations and extracted values, and request mathematical checks where a compatible scientific model exists. This is a general research workspace, not a flow restricted to synthetic examples. Gemini analysis can span domains; the existing Counterdex checker currently verifies only the two-rate concentration model. Preserve that distinction in capability reporting and every result. Do not claim arbitrary datasets or model prose are mathematically verified.

`main` at `3738724` passed every GitHub CI job. The earlier live integration is on main: the owner's Gemini key lives only in private server configuration; image extraction, selected-run commentary, real science, measurement design and native replay were exercised locally. PDF and a broad general-analysis workflow are still unfinished. No live autonomous Deep Agents coordinator is integrated.

The branch **`codex/shared-access-handoff`** preserves unfinished automatic-access scaffolding in seven files: `apps/web/api.mjs`, `api.test.mjs`, `share-gateway.mjs`, `share-gateway.test.mjs`, `workflow.mjs`, and `scripts/dev/share.py`, `test_share.py`. It currently gives every public visitor the same `shared-demo` identity. **Replace that design before merging it as a general real-data product.** Its tests demonstrate a stub identity, not isolation of actual private user workspaces. Documentation on that branch still describes the preceding manual-token version.

Start by fetching origin and reading all three files in `docs/agent-prompts/`. Create a branch such as `codex/shared-server-integration` from `origin/codex/shared-access-handoff`; reuse an existing branch/worktree safely when appropriate. Claude and the UI owner start their own branches from current main. You own the final integration; coordinate using committed contracts and PR descriptions rather than simultaneous edits to shared files.

## Your exclusive ownership

- `apps/api/bean_api/auth.py`, `config.py`, session/auth modules and session persistence/migrations.
- API registration in `main.py`, capability wiring and worker registration if later needed. Claude supplies a registration function for the general routes; you wire it into the actual application.
- `apps/web/share-gateway.mjs` and its tests, `api.mjs` and transport tests.
- `scripts/dev/share.py`, `test_share.py`, launcher process ownership and shared-host setup.
- Session bootstrap in the browser. The UI owner owns `workflow.mjs` and app/DOM integration; provide a small session module/export and coordinate the narrow hook instead of both rewriting that file.
- Deployment/shared-access documentation, final cross-owner integration and end-to-end release verification.

Claude owns general file/analysis/provider modules, upload admission in `http.py`, and any explicit audit-preserving provider-budget policy extension. The UI owner owns general upload/review/result screens and browser acceptance. Do not implement their whole feature in parallel.

## Deliver automatic access without exposing private work

The user wants one shared server, one server-side Gemini key, and no long access token to copy. Provide ordinary invisible browser sessions: cryptographically random, bounded-life credentials in **Secure, HttpOnly, SameSite cookies**, with server-side identity/expiry validation and a private workspace per browser/session. Store only the appropriate secret hashes server-side. Preserve owner access locally and all existing tokens/data. A new anonymous visitor must not inherit the owner identity or another visitor's workspaces. Shared collaboration, if implemented, requires an explicit scoped invitation; it must not be a side effect of knowing the public URL.

Keep the Gemini key out of JavaScript, cookies, HTML, URLs, Git, public responses and tunnel environments. A browser session is not a Gemini credential. Cookie-based requests require coordinated `credentials: 'same-origin'` behavior in shared mode; manual local bearer requests retain their existing behavior. The current `credentials: 'omit'` and gateway cookie stripping cannot support sessions unchanged. Validate Origin/Host/HTTPS metadata at the gateway, retain a fixed loopback upstream, prevent cross-site mutations, and never allow a browser-supplied owner header to upgrade a public session.

Make session/provisioning restart-safe. The WIP writes an actor before restarting the API and can strand it after a failed restart. Concurrent starts can also race. Add ownership locking and idempotent recovery; never restart or kill unrelated processes. Keep credentials out of logs and error messages. If the launcher reads private Gemini configuration solely to restart the owned API, document that accurately; the gateway/tunnel must remain key-free.

The owner chose Cloudflare HTTPS sharing and subsequently asked for a friendlier token-free flow. `cloudflared` is installed on the owner's Mac. **No public tunnel has yet been started or verified.** An earlier automatic review rejected public Cloudflare exposure before the user was asked specifically about it. Carry the later authorization and its exact scope forward; if an action is rejected again, report the stated reason and ask for the precise missing approval. Do not bypass a rejection by indirect execution. Finish local checks before public activation. Keep the Mac/network dependency and temporary hostname honest.

## Shared interface to implement and integrate

Use `/api/bean/v1` throughout. Coordinate any necessary contract amendment with both other owners before coding against different shapes.

- `GET /shared-session` establishes/reopens the browser session at the shared boundary and returns nonsecret metadata: `{mode:"browser_session", authenticated:true, workspace_id, credentials:"server_managed"}`. Never return the session secret in JSON.
- Claude supplies raw-byte `POST /workspaces/{workspace_id}/research-assets`, with a bounded `Content-Type` and optional bounded `X-Source-Name`. Response: asset `id`, `sha256`, `media_type`, `byte_size`, `filename`, provenance and page descriptors. Authenticated asset retrieval uses `GET /research-assets/{id}`. Update the fixed proxies' header allowlists for that filename header if adopted; do not permit arbitrary upstream destinations.
- `POST /workspaces/{workspace_id}/research-analyses` takes `{client_operation_id, question, assets:[{id,sha256}], consent:{accepted,provider:"gemini",model,asset_ids,include_question:true}}`. The idempotency header equals `client_operation_id`. Prefer a bounded synchronous POST returning a durable record; do not claim asynchronous durable resume unless built. `GET /research-analyses/{id}` reopens it without dispatch.
- Result body: `summary`, `extracted_tables`, `claims`, `limitations`, `clarifications`, `suggested_next_steps`, `citations`, `verification:{status:"not_mathematically_verified",supported_adapter:null|id}`, and `provider_attempt_id`. Actual checker evidence is attached separately by trusted server code.
- Citations use original source SHA, zero-based `page_index`, exact quote, and optional top-left normalized `[0,1]` bbox with explicit `bbox_space`. Display page numbers as one-based. Never mix coordinate systems or accept numeric substring matches.

Wire Claude's `register_general_routes(app)` and capability helper into real startup, not only a test fixture. Report the general feature available only when routes/services are reachable. The UI must receive actual server availability, selected model and budget status.

## Budget and validation

The owner permits **free-tier Gemini only, $0**. One key is shared server-side, not one key per person. Existing local reservations are nearly exhausted: five calls were made; the last observed remaining allowance was three requests but only 4,568 input and 4,736 output tokens. These are application reservations, not Google's quota or a verified billing statement. Never erase attempts, refund them silently, replace the store, reset history or create a new actor to bypass the shared budget. Coordinate any explicit auditable budget grants with Claude; preserve default limits and require trusted owner configuration to activate additional capacity. Most development/tests must make zero provider calls.

Prove two independent browser contexts cannot list/open/modify each other's workspaces, assets, analyses, science results or owner data. Test forged/expired/replayed sessions, foreign Origin, missing cookies, client-supplied owner credentials, restart/reopen, parallel startup and shutdown ownership. Run the existing supported scientific loop and native replay after integration. Exercise a real general-file workflow through the assembled UI using controlled responses first, then one explicitly permitted bounded public-data live smoke only if budget admits it. Record unrun lanes honestly.

Relevant commands include `node --test` in `apps/web`, launcher/sharing unit tests, backend pytest with the prepared CPython 3.11 engine, Ruff, schema export/diff and `python3 scripts/release/secret_scan.py`. Use the prepared `.venv` for backend code and `.venv-engine` for science; default system Python is not the backend runtime. Commit real code and tests, wait for GitHub CI, then merge compatible reviewed PRs without force-pushing. Return the final main SHA, working shared URL, what was actually tested, remaining limitations and teammate startup instructions. If the public link is blocked, finish/push everything else and state that exact blocker.
