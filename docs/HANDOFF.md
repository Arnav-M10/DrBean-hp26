# Owner02 backend handoff

## Baseline and provenance

- Target remote verified: `https://github.com/Arnav-M10/DrBean-hp26.git`.
- Initial branch: `work`, unborn; no commits, tracked files, local instructions, manifests or remote heads existed. No human edits were replaced.
- Working branch: `backend/gf2`. Use `git rev-parse HEAD` for the completed implementation commit; the starting commit does not exist.
- Source: uploaded `02_Backend_Agents_Data.md`, GF-2 dated November 13, 2026, with DB-SC-1 wire profile. Its embedded contract cites SHA-256 `2dc232c8f2477ed959864e039d97655c287e6cce61cc54179daa6b0569f0fe59`; this is source attribution, not a statement that this repository implements every acceptance condition.
- Implementation and synthetic packets were authored in this workspace. None of the historical PRODUCT-MAIN, PRODUCT-INTEGRATION or ENGINE-BASE implementations was imported. Organizer approval of prior-work reuse remains unresolved; no event-eligibility claim is made. No external message, account linkage, deployment or paid resource was created.

## Ownership and interfaces

`apps/api/bean_api` owns HTTP/auth/configuration, exact canonicalization, persistence, source admission/review, provider adapters, bounded orchestration, scientific-worker integration and reports. `shared/contracts/DB-SC-1` contains generated schemas and synthetic frontend exchanges. `scripts` contains schema export and offline evaluation. `fixtures/intake` contains original synthetic source PNGs and hand-authored oracles. The frontend and `packages/groundwork_adapter` remain separate owner responsibilities.

The authoritative canonicalizer is Python, with golden UTF-8 byte fixtures. Clients submit exact strings and consume generated schemas; they must not invent authoritative hashes or independent DTOs. This is an initial application schema, not migration of a historical scientific wire format. Operational policy remains GF-2. Unknown fields, duplicate JSON keys, floats in canonical input, unpaired surrogates, unsafe integer counters and oversized nesting fail closed.

Service events are explicit UTC timestamps. Experiment `time_origin` and elapsed physical time are separate. IDs are opaque; every public record lookup resolves authenticated workspace membership. API errors provide code, message, field paths, retryability, current revision, and a server request ID. No provider body or raw exception is returned.

Public routes include the document's `/api/bean/v1` investigation/design/intake/conversation routes, plus workspace creation/listing, manual datasets/problems, provider consents, intake/observation review, exact decimal conversion, scoped record reads, activity, provider-attempt inspection and report creation/download. `/openapi.json` describes the actual route bodies. `POST /runs/{r}/design-proposals` accepts **DesignRequestBody** and the server constructs DesignPlanBody and its digest.

The local auth lane maps opaque bearer secrets to stable actors from private `var/auth.json` or `BEAN_AUTH_TOKENS_JSON`. This is a local prototype identity source, not an account-registration system. No public reviewer capability, cookie session, password endpoint or tenant provisioning is implied. Hosted auth/TLS/rate controls require Owner04 review.

## Storage, restart and rollback

One explicitly selected file-backed SQLite database is authoritative for this local lane. WAL and foreign keys are enabled. Unique constraints bind one job per plan/approval and one child per run/scenario. Transactions reserve work before dispatch; no transaction waits for a provider or scientific process. Reusing an operation key with a different body conflicts. New keys cannot repeat a consumed plan; intentional reruns require a new plan with ancestry. Accepted work retains its frozen inputs after later edits.

The additive migration is `apps/api/bean_api/migrations/0001_initial.sql`, schema version 1. It is packaged in the wheel, creates tables without dropping existing data, and rejects newer schema versions. No legacy database existed to migrate. Tests open an already populated v1 database and validate consistent backup/restore.

Stop the API and worker before recovery or restore. The worker holds an exclusive OS lock per database. `uv run python -m bean_api.worker --recover` marks prior running reservations interrupted and unfinished provider attempts unknown; it does not resend them. Queued work remains durable. Recovery must run only after the previous API/provider activity has stopped: a worker lock alone cannot establish that an API intake call is finished.

`Store.backup(destination)` uses SQLite's online backup API. Back up the retained `var/sources` directory separately, preserve its permissions, restore into an isolated path, and verify source byte digests. The tests restore and query a database backup; they do not establish production disaster recovery. Roll back application code only with a compatible schema-v1 database, or restore a verified database/source snapshot. Never delete populated tables or silently fall back to a new local store. `DATABASE_URL` is rejected in this lane; Tiger Data/PostgreSQL is not implemented or qualified.

Cancellation remains `cancel_requested` until the dispatcher has observed termination. Scientific jobs run in owned spawned processes with wall/CPU/address-space/process/file limits; cancellation kills and reaps the assigned process group. Interrupted provider calls retain unknown outcomes and token reservations, since local cancellation cannot prove the remote service stopped. Completed evidence remains immutable.

## Gemini and deepagents

Pinned direct dependencies are in `pyproject.toml`, complete transitive resolution in `uv.lock`: google-genai 3.3.0, deepagents 0.7.38, langchain-google-genai 4.5.0 and langchain 1.5.0, on Python 3.12. FastAPI/Pydantic/Pillow versions reuse the observed adequate environment versions. Exact installed SDK/framework source and official provider/framework documentation informed the adapters; URLs are retained in the module docstrings.

The provider surface is Gemini Developer API `v1beta` at `generativelanguage.googleapis.com`, with Vertex mode disabled. There is **no default model**, provider switch or automatic network retry. SDK calls and coordinator calls each use one SDK attempt; the intake implementation intentionally uses one request rather than the maximum two permitted by GF-2.

To configure a permitted live run, the responsible owner must first record the account, adult audience, region, data-use, paid/unpaid treatment, selected model/modality, quota, conservative token bound and approved spend decision. Only public/synthetic nonconfidential data is admitted in this prototype. The decision must be substantive; an environment flag alone is not account or audience qualification. Then export server-side values:

```text
GEMINI_API_KEY=<server secret>
GEMINI_MODEL=<actually available selected model>
BEAN_GEMINI_ACCOUNT_GATE=approved
BEAN_GEMINI_ACCOUNT_DECISION_ID=<recorded account/data/budget decision>
BEAN_GEMINI_IMAGE_TOKEN_BOUND=<documented conservative model-specific image tokens>
BEAN_GEMINI_MAX_INPUT_TOKENS=16000
BEAN_GEMINI_MAX_OUTPUT_TOKENS=2048
```

Never paste the key into the chat, browser, fixture, trace or repository. Network access to the actual provider host must be admitted in the environment; the inspected environment only allowed package-manager hosts, and no provider access was tested. Per-operation provider consent separately binds selected payload/model; scientific approval does not substitute for it. Agent plans use their own durable provider-consent record and disclose `problem` and `dataset` context.

Provider attempts are durably reserved before dispatch, with prompt/source digests, SDK/model/prompt/schema versions, sanitized outcome and reported usage when available. Shared conservative caps are 32 requests, 64,000 input tokens, 16,000 output tokens; unknown usage does not refund a reservation. These token limits are not a verified monetary quote. Approved spend/quota must justify the chosen allocation before enabling calls. Missing actual usage/cost remains unknown.

Deepagents is the actual installed framework. Runtime graph inspection verifies the final allowed tool inventory. Filesystem middleware is explicitly replaced with inert middleware, default subagents and summarization are disabled, and memory/checkpoints/store/cache and LangSmith tracing are disabled. Server wrappers enforce the frozen tool allowlist, baseline-first ordering, ownership, one child per approved scenario, expiry/cancellation, four model turns/six attempted tools/two scientific reservations/300-second invocation caps, including waits. Rejected attempts count. A user can approve smaller budgets. The model never receives approval credentials and cannot select paths, URLs, SQL, shell commands or arbitrary parameter vectors.

Known explanation controls catch invalid references, unsupported numbers and enumerated overclaims; they **cannot prove arbitrary prose true**. Critical factual cards come from persisted typed evidence, with model commentary visibly separate and suppressible. Controlled framework tests show different later choices after different returned evidence; these are controlled model/tool tests, not live Gemini or real scientific computations.

## Scientific adapter and review limits

`ScienceAdapter` in `science.py` is the explicit Owner01 integration seam. `UnavailableAdapter` returns unsupported investigation evidence and unavailable design options for every approved grid time. It never constructs a numerical candidate or a certificate. Worker result schemas and independently supplied problem identities block mismatched/structurally unsupported evidence. A checked badge requires a qualified adapter, verification record and matching artifacts; checked design additionally requires exact positive margin and fresh native replay. Browser replay is not implemented.

Owner01 must review the proposed two-rate scientific admission fields and implement the typed adapter. The current schema uses positive finite domain bounds, feasible `ke<ka`, closed target `ke` interval, nonnegative concentration/time, explicit included/excluded rows and strictly positive per-row historical allowance. Whether zero historical allowance should be admitted is an outstanding scientific contract decision; future allowance remains strictly positive. No historical default is copied into future allowance.

Design proposals only use two exact candidates from a selected completed historical scenario. This release's design dispatcher is deterministic adapter execution under separate approval; Gemini interpretation/explanation is supported as separately disclosed conversation operations. A Gemini-backed **design coordinator invocation** remains unqualified/unavailable and is not silently replaced under the same provider approval. Every requested time is preserved with evaluated/skipped/failed/unavailable status. No geometric/arithmetic checker was reimplemented in the backend.

Source intake supports retained PNG/JPEG with normal orientation only. PDF, animation, digest-only retention, preprocessing transforms and CSV import are not implemented. Visual transcriptions remain unreviewed even when rational parsing succeeds. Every acceptance records exact proposal digest, reviewed values and correction provenance. Conversation-generated design/observation drafts remain unaccepted; dedicated validated scientific routes construct their execution scopes. Review of a new observation preserves the old dataset/result and hypothetical lineage; it never reruns science automatically.

Reports preserve selected historic records and exact JSON byte hashes. Hash integrity is not scientific replay. Native scientific bundles, reviewer share capabilities, browser replay and advanced time-series features are pending the corresponding owners. Activity uses ordinary SQLite queries; no scale/performance or Tiger Data feature claim is made. Photon has only a future seam: an independently authorized adapter could call existing authenticated proposal commands. No channel/account-link/outbox/notification infrastructure was added.

## Qualification and next owners

Actual live provider calls: **0**. Live Gemini model/modality/framework success samples: **0**. Live latency/token/cost samples: **0/unknown**. No fabricated extraction accuracy, consultation, sponsor eligibility, replay or hosted performance claim exists. The eight source packets are synthetic and independently sanity-checked for text/rational consistency; they are a small finite control corpus, not an OCR benchmark. The evaluation runner retains all supplied attempts and starts unrun portfolio cases at `not_run`.

Owner01 next: review scientific schemas, supply the qualified adapter and prepared replay artifacts without importing disputed historical code until the reuse decision permits it. Owner03 next: consume the generated schemas and build source/value review, dedicated exact approval, durable conversation and evidence cards. Owner04 next: review reproducibility/auth/storage decisions, obtain the service/reuse decisions, authorize and execute the bounded live portfolio, then assess hosted deployment and the demo. See `docs/EVALUATION.md` for the acceptance mapping.
