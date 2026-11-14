# Frozen shared-session integration contract

GPT 1 owns auth/sessions, `main.py`, the gateway/transport and shared-host lifecycle.
Claude owns `general_research`, upload admission and any audited budget-policy
extension. The UI owner owns workflow/app/DOM changes. This contract complements
the three prompts in `docs/agent-prompts/`; changes require a committed handoff.
Base: `296578a` (the handoff prototype is already in main). No provider request
is authorized by bootstrap, upload, session creation or reconnect.

## Browser adapter (automatic-local amendment, 2026-11-14)

`session.mjs` exports `bootstrapSharedSession(fetcher = fetch, options = {})`,
returning `{api, session}` for both the local loopback and shared HTTPS app.
`GET /api/bean/v1/shared-session/current` is nonissuing: it returns current
metadata, 401 `browser_session_missing` for an absent cookie, or 401 for a
stale/invalid cookie. The browser issues through `GET /shared-session` only on
an absent first-visit cookie, then confirms retention with another current read.
404 and unavailable-service errors remain visible; no owner-login fallback exists.

The response is exactly the nonsecret metadata:

```json
{"mode":"browser_session","authenticated":true,"workspace_id":"ws_…","credentials":"server_managed"}
```

The returned `api` is `new BeanApi(null, fetcher, {mode:'browser_session'})`:
requests use `credentials:'same-origin'` without a JavaScript bearer credential.
Operator `new BeanApi(ownerToken, fetcher)` remains a direct-API maintenance
transport; the local and public web proxies strip browser Authorization.
The UI selects the returned workspace and shares one API context with the general
and scientific workflows. Session secrets never enter web storage, DOM, URLs or
JSON. A nonsecret local-storage marker records issuance/continuity; a first issue
requires a successful marker write. Existing valid cookies can reopen even when
storage is blocked. Web Locks serialize first visits across supporting tabs.

Only the allowlisted current-session/capabilities/workspace GET reads retry,
at most three attempts. Session issuance, rotation, science, consent and model
requests never retry automatically. Lost issuance acknowledgements remain
uncertain until a read confirms the cookie. Expired, revoked or cleared sessions
require explicit `options.startNew: true` before a new workspace can be issued;
this never recovers or transfers prior research. A previously unseen hostname or
fully cleared site storage cannot identify the earlier browser.

Additional lifecycle routes: `POST /shared-session/rotate` rotates the cookie,
revokes its old credential and preserves the actor, workspace and absolute expiry;
`POST /shared-session/logout` revokes it and clears the cookie. Both retain
authenticated-cookie and exact-origin mutation checks. Capacity counts only
active unexpired credentials; history is retained and provider accounting is
unchanged.

## Private server boundary

Local HTTP access is explicitly configured with `BEAN_LOCAL_GATEWAY_FILE`
and `BEAN_LOCAL_BROWSER_ORIGIN`. The launcher provisions the separate owner-only
`var/local-gateway.json` proof without replacing an existing file. The local
proxy strips Authorization and arbitrary forwarded/trust headers, then sends
`X-Bean-Local-Gateway` and the exact configured `X-Bean-Local-Origin`.
The API also requires the real loopback peer; the launcher disables uvicorn
forwarded-header trust. Mixed local/public boundary proofs are rejected.

Local `bean_local_session` is host-only, HttpOnly, SameSite=Strict, Path=/,
without Secure for the explicitly scoped loopback HTTP origin. It cannot select
the HTTPS lane. Public gateway and cookie requirements below remain unchanged.


The cookie is `__Host-bean_session`: 32 random bytes in 43 URL-safe characters,
`Path=/; Secure; HttpOnly; SameSite=Strict`, no Domain, absolute 24-hour lifetime.
SQLite retains only the credential SHA-256 plus random actor, private workspace,
creation/expiry and revocation. Workspace, membership and session creation are
atomic in the existing store. Rotation/revocation is durable across API restart.
A stolen unexpired credential remains a bearer until expiry/revocation; this
does not claim hardware binding or impossible replay prevention.

The gateway forwards API requests directly to fixed `127.0.0.1:8000` and static
requests to fixed `127.0.0.1:4173`. It validates the exact approved HTTPS Quick
Tunnel Host/protocol/origin, rejects cross-site API calls/subresources, and requires
exact Origin on mutations. Only GET/HEAD document navigation to the entry page
may follow an external link; it grants no API authority. It discards browser
Authorization and client trust/owner headers.
Only the named session cookie reaches the API; static requests carry no cookie.

The gateway proves its boundary using `X-Bean-Shared-Gateway` and replaces
`X-Bean-Shared-Origin` with the validated HTTPS origin. Its independent private
`var/share-gateway.json` is an owner-only regular file (0600, bounded, no symlink):
`{version:1, secret:<43 random URL-safe characters>}`. It is not an owner bearer
or a provider credential. Only the gateway receives its file path through
`BEAN_SHARE_GATEWAY_FILE`; no secret value is placed in its environment.
The API reads this configuration at request time, compares digests and validates
the shared origin again. Sharing never edits `auth.json` or creates a demo actor.
The API's `BEAN_SHARE_GATEWAY_FILE` defaults to `share-gateway.json` beside its
existing database. A missing shared file disables the shared lane (404); provisioning
it needs no API restart. The independently configured local lane is unaffected. Existing owner tokens and data remain unchanged.

`/capabilities` adds `shared_access:{mode:'browser_session',available:boolean,
session_ttl_seconds:86400}`. Availability requires valid local or shared boundary configuration.
The share launcher checks it before public activation, serializes lifecycle
changes, and never stops an unrelated process. It retains gateway configuration
through failure/restart; gateway and tunnel environments contain no provider key.

## General-research joins for Claude and the UI owner

Keep the exact raw asset and synchronous analysis routes/bodies in the prompts.
`BeanApi.uploadResearchAsset(workspace,file,operationId?)` and
`BeanApi.researchAnalysis(workspace,body)` provide bounded transport; analysis
keeps its exact operation ID/body after an uncertain response and uses a 75-second
transport deadline. Reopening is GET only, with no model redispatch.
When supplied, the upload operation ID contains 1–128 ASCII letters, digits,
underscores or hyphens and is sent unchanged as `Idempotency-Key`; an explicit
retry reuses that ID. When omitted, the transport retains an automatic ID for
the same path, media type, original bytes and optional filename metadata. A
changed filename receives a different automatic ID even when bytes match.
Optional `X-Source-Name` is printable ASCII, at most 255 bytes. Omit it for an
unrepresentable filename instead of inventing an encoding or dropping file
contents; retain local display names. A Unicode filename encoding amendment must
be agreed by both consumers. Contents, column names and values retain Unicode.

Claude supplies `register_general_routes(app)` and a capability helper with its
exact import location/signature and state requirements. Existing app state is
`settings`, `workflow` (whose `.store` is authoritative), `ledger`, `provider`,
`adapter` and `controlled_source_proposer`; sessions add `sessions`. GPT 1 wires
the implemented routes into actual startup and advertises availability only
after that integration. No competing stub will claim a completed general route.
Claude must coordinate sanitization if general asset records contain internal
storage names and are reachable through generic record/list routes.

All browser actors share the existing global provider ledger. No new session,
workspace, process restart or explicit rotation grants additional model capacity.
Preserve existing records and the owner's free-tier-only/$0 limits. Default
development and acceptance use controlled responses with zero provider calls;
a live public-data smoke is separate and may run only if the existing budget
admits its conservative reservations and the required disclosure is accepted.
