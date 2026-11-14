# Frozen shared-session integration contract

GPT 1 owns auth/sessions, `main.py`, the gateway/transport and shared-host lifecycle.
Claude owns `general_research`, upload admission and any audited budget-policy
extension. The UI owner owns workflow/app/DOM changes. This contract complements
the three prompts in `docs/agent-prompts/`; changes require a committed handoff.
Base: `296578a` (the handoff prototype is already in main). No provider request
is authorized by bootstrap, upload, session creation or reconnect.

## Browser adapter

`session.mjs` exports `bootstrapSharedSession(fetcher = fetch)`, returning
`{api, session}` from `GET /api/bean/v1/shared-session`, or `null` only when this
is a local server without shared access (404). Errors, invalid/expired cookies
and unavailable services must stay visible; they are not an owner-login fallback.
The response is exactly the nonsecret metadata:

```json
{"mode":"browser_session","authenticated":true,"workspace_id":"ws_…","credentials":"server_managed"}
```

The returned `api` is `new BeanApi(null, fetcher, {mode:'browser_session'})`:
requests use `credentials:'same-origin'` with no JavaScript bearer credential.
Existing `new BeanApi(ownerToken, fetcher)` uses `credentials:'omit'` as before.
The UI owner replaces the prototype `shared_demo` hook with this module, selects
the returned private workspace, and shares this one API context with the general
and scientific workflows. Keep explicit advanced local owner login available.
Session secrets never enter local/session storage, DOM, URLs or JSON.

Additional lifecycle routes: `POST /shared-session/rotate` rotates the cookie,
revokes the old credential and preserves the private actor/workspace;
`POST /shared-session/logout` revokes it and clears the cookie. Both require the
same authenticated cookie and exact same-origin mutation boundary. Expired,
forged and revoked credentials return 401 and clear the cookie; they cannot
recover the previous workspace. A new absent-cookie bootstrap creates a new
private workspace. Losing a cookie is not an invitation to someone else's data.

## Private server boundary

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
existing database. A missing file disables session bootstrap (404); provisioning
it needs no API restart. Existing owner tokens and data remain unchanged.

`/capabilities` adds `shared_access:{mode:'browser_session',available:boolean,
session_ttl_seconds:86400}`. Availability requires valid boundary configuration.
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
