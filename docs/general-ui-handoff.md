# General research UI handoff

UI owner branch: `codex/general-research-ui`, base main `296578a`.
Scope: general-workspace module/tests, index/styles and app/workflow hooks.
GPT1 owns transport/private sessions/proxies/startup. Claude owns general assets,
analysis schemas/providers/budgets. Prior Deep Agents work remains untouched in
its isolated worktree; this assignment replaces that implementation scope here.

## Proposed adapter agreement (confirm changes before integration)

GPT1 agreement adopted: import `bootstrapSharedSession()` from `session.mjs`.
It resolves `{api, session}` only after `/shared-session` reports
`mode=browser_session`, `authenticated=true`, `credentials=server_managed`.
Use `session.workspace_id` and fetch capabilities through that same API. A null
return means only a local-boundary 404; expired/malformed sessions stay visible.
`api` exposes authenticated `json(path, body?)`,
`uploadResearchAsset(workspaceId, file, operationId)` and
`researchAnalysis(workspaceId, frozenBody)`. The latter uses the body's
`client_operation_id` as its key. Session requests send same-origin cookies;
manual owner login stays available. No JavaScript session/bearer secret is
returned by automatic bootstrap. Please also register new static modules,
`X-Source-Name`, research-analysis timeouts, and safe filename-header forwarding
in the fixed proxies you own.

UI integration: `setupWorkflow(..., {onConnectionChange})` reports
`{api, capabilities, workspaceId, mode}` to the general workspace. Allowed modes
are `browser_session` and explicitly authenticated `local_owner`; `shared_demo`
never enables private general uploads. Session/bootstrap remains GPT1 code.

Claude: use the prompt's unchanged raw upload/analysis/GET routes. Please confirm
typed result and capability shapes early. Suggested `general_research` capability:
`available`, `media_types`, `max_assets`, `max_file_bytes`, `max_total_bytes`,
`max_pdf_pages`, `analysis:{available,model,reason}`, and
`budget:{remaining:{requests,input_tokens,output_tokens}}`.

Proposed body types: `summary` string; `extracted_tables` with `id`, `title`,
`columns` strings, `rows` arrays of strings/null, `citation_ids`; `claims` and
`suggested_next_steps` with `text`/`citation_ids`; `limitations` strings;
`clarifications` with `question`/`citation_ids`; and `citations` with `id`,
`asset_id`, `source_sha256`, zero-based `page_index`, exact `quote`, optional
normalized `bbox` and explicit `bbox_space`. `verification.status` stays
`not_mathematically_verified`; provider mode/controlled provenance is visible.
Please supply authorized preview/byte routes and real public-file provenance.

## UI invariants and current task

- Primary: add 1–5 real files → inspect retained sources → ask question → review
  exact file/question/model disclosure → explicit analysis → cited evidence.
- Enforce lower client/server limits: 5 MiB each, 10 MiB total, ten PDF pages;
  the server decides actual format/parser success. No filename-only success.
- A frozen operation survives uncertain responses and page reload without an
  automatic retry. Question/source edits require a new operation and consent.
- General outputs use text nodes and bounded tables. No raw HTML or verified AI
  badge, automatic scientific mapping, model fallback or budget reset.
- Save result references and pending operation only within the current private
  session/workspace; a new session must not inherit another session's sources.
- Browser acceptance will cover real public files with controlled model output,
  citations, malicious text, repeated/changed consent, reload/reopen, budget
  refusal, and two actual private browser contexts on the assembled backend.
- No live calls or public tunnel activation are needed for development tests.

Current: implementing the bounded controller/view against an injected adapter;
awaiting owners' confirmed session and result contracts before assembled tests.
