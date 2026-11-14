# Deep Agents impact audit and fixes (owner 5)

Assignment: five-prompt sprint, prompt 05 (agent owner). Branch `claude/deepagents-impact`
from main `aa51f16`. All checks below are **author checks** on this branch, not independent
qualification; owner 1 integrates and C requalifies. Source links point at commit
[`bdad93e`](https://github.com/Arnav-M10/DrBean-hp26/tree/bdad93e85b5b74fd28a3835348d82ed4b3560b56).

**Lanes.**
- **Controlled:** a deterministic planning fixture running through the real `create_deep_agent` graph, worker, ports and Counterdex. It proves orchestration and data flow. It does not prove model reasoning.
- **Live Gemini:** `not_run`. No admission exists, no provider request was made, and no key was read.

## What changed

1. **The predeclared live sample now fits its allocation.** The browser demo saves reviewed
   design constraints together with the question, so the live baseline carries them in every
   request.
   - On `aa51f16`, under the documented operator allocation (6 requests, 64,000 input tokens,
     3,072 output tokens), the first five requests reserved 49,524 input tokens.
   - The sixth request, the report, was then refused (`provider_budget_exhausted`) after the
     science had already run.
   - `research-prompt.v4` now gives the model bounded, deterministic views:
     - investigation evidence: 5,170 → 3,525 wire bytes;
     - finished child results: 828 → 506;
     - reviewed context with dataset rows as a lossless table: 3,302 → 2,609.
   - The same sample now **completes at 57,206 reserved input tokens**.
2. **The plan reflects actual state.** A todo the agent marks completed is recorded as
   `completed` only when the thread read canonical evidence after the previous plan update.
   The step then cites those evidence IDs. Any other completion remains a pending agent
   proposal, so planning never creates or completes science. This addresses the cause of
   F-RESEARCH-PLAN-PROGRESS-PENDING.
3. **Author checks** cover:
   - each view keeps every value of the full fact and falls back to the complete fact on any
     disagreement;
   - the frozen controlled conditions C1–C4 run through the ordinary app and real Counterdex;
   - the live-sample admission estimate runs through the real metered gateway and ledger,
     with only the SDK substituted;
   - planted instructions in reviewed text cannot approve or dispatch science.

## Capability audit

| Feature | Implementation | Observed (this branch) | Evidence | Gap | Smallest useful fix |
|---|---|---|---|---|---|
| Real `create_deep_agent` on the ordinary worker path | [worker.py:42](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/worker.py#L42) → [research_runtime.py:76](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/research_runtime.py#L76) → [research_integration.py:334](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/research_integration.py#L334) → [research_coordinator.py:775](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/research_coordinator.py#L775) | deepagents 0.7.38 / langgraph 1.2.21 / langchain 1.5.0. Captured `create_agent` stack: `NoFilesystem` (replaces `FilesystemMiddleware` by name), `_ParentNotifier`, `PatchToolCalls`, `TodoList`, `Boundary`, lazy Anthropic caching (no-op), `UnsupportedContent`, `ModelRefusal`. Each calls the model handler once; nothing retries. | Stack capture; browser check 7/7; C `test_research_graph_inventory` passes | None | None |
| Tool allowlist; SDK defaults removed | [research_coordinator.py:765-788](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/research_coordinator.py#L765-L788) | Effective ToolNode holds exactly 6 tools: `write_todos`, `prepare_scientific_proposal`, `run_scientific_operation`, `read_research_evidence`, `request_clarification`, `publish_research_report`. No filesystem, shell, network or `task`. The general-purpose subagent is disabled and summarization excluded. There is no child graph. The inventory is asserted at build time. | Stack capture; existing graph tests | None | None |
| Planning reflects actual state | [research_coordinator.py:278](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/research_coordinator.py#L278), [research_integration.py:196](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/research_integration.py#L196) | Before: every finished step showed "Suggested". Now the browser plan reads Done, Done, Suggested after the investigation and Done ×3, Suggested after the design, with completed steps citing evidence. | `test_research_agent_views.py`, C1, browser plan check | `in_progress` renders as "Running" while waiting for approval | Owner 3/4: label `in_progress` as "In progress" |
| Next action chosen from returned evidence | [research_controlled.py:50](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/research_controlled.py#L50) | The controlled policy branches on fact fields (outcome, verification, binding, replay, candidates, design tier and margin). C1, C2 and C4 reach different next steps from the same objective. | `test_research_agent_conditions.py` | A live model's choice is unverified | Live sample (below) |
| Human review is a real interrupt bound to the canonical approval | [research_coordinator.py:579-628](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/research_coordinator.py#L579-L628), [research.py:368](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/research.py#L368) | LangGraph `interrupt()` lives inside the run tool. Resume is only a wake signal ([:460](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/research_coordinator.py#L460)), and the tool rereads the canonical review. The only approval path is the authenticated `/decisions`. No child exists before approval, and a model obeying planted text cannot approve. | C1, C3, injection check, browser 7/7 | None | Design note: `interrupt_on`'s edit/respond decisions would let a resume payload change the dispatched operation, so the custom interrupt is deliberate |
| Counterdex runs; evidence is read; report and proposal cite it | [research_tools.py:141](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/research_tools.py#L141), [research_coordinator.py:630-666](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/research_coordinator.py#L630-L666) | Real child jobs run. `read_research_evidence` records `evidence_observed`. The report cites `[baseline]` then `[baseline, design]`, and commentary is validated against the complete facts. | C1; browser downloads | Validated agent commentary is not persisted in the canonical report ([research_integration.py:318](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/research_integration.py#L318)). The recommendation is visible in the plan revision, not the report download. | Owner 1: let `publish_report` store the validated commentary |
| Next-measurement proposal uses the real pair and reviewed constraints, with separate approval | [research_tools.py:103](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/research_tools.py#L103) | The design review lists the baseline's two candidate IDs and vectors, the reviewed 6 h/8 h, 1/5 mg/L allowance, 8 h horizon and the historical run. It is approved separately before the deterministic design runs. | C1, browser check | None | None |
| A different useful action on a miss, missing input or no separation | [research_controlled.py:50-85](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/research_controlled.py#L50-L85) | Changed claim: no counterexample found, then "Review assumptions and the bounded search scope…"; a further advance asks to clarify scope with no child. Missing inputs: clarification and zero jobs. Missing constraints: clarification before any design. A wide allowance gives `no_separation_established`, then "Review feasible times and allowance because this grid did not separate the pair". | C2, C3, C3b, C4 | None in the controlled lane | None |
| Evidence survives narration or model failure | [research_runtime.py:119-127](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/research_runtime.py#L119-L127) | An error during a model turn after the evidence read fails the action. The completed child and evidence remain, and downloads still work. | Restart probe R2; C DEMO-09 | No report snapshot when narration fails | None (by design) |
| Live mode: consent, admission, one dispatch boundary, no retry | [research.py:197-229](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/research.py#L197-L229), [research_ledger.py](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/research_ledger.py), [gemini_chat_gateway.py:113-202](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/gemini_chat_gateway.py#L113-L202) | Consent is bound to the exact context digest. Allocation is operator-only (default 0; per-session ceiling 8 requests / 64,000 in / 16,000 out). Each physical request is reserved before the SDK call, with a single attempt and no retries, and unknown outcomes stay reserved. | Metered tests with the SDK substituted (6 pass) | Before: the demo sample could not finish its report within 64,000 | **Fixed:** bounded views (57,206) |
| Context efficiency | [research_coordinator.py:139-317](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/research_coordinator.py#L139-L317) | Per request: a 1,024-byte gateway constant, 733-byte system prompt, 2,327 bytes of tool schemas, plus the context and conversation. Avoidable repetition was the full evidence fact with repeated digests, the child scope echo and per-row keys. | Scratch measurement plus metered ledger | Baseline plus design needs 12 requests, 193,982 reserved (was 231,726), above the 8-request ceiling | Design stays in the controlled lane. Do not raise caps. |
| Redundant reread | [research_controlled.py:142](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/research_controlled.py#L142) | The fixture rereads the baseline before proposing a design. `prepare_design` already revalidates it, so this costs one request in the design action. | Measurement | Small, and only on the design path | Deferred: removing it changes an existing test predicate for no live benefit |
| Bounded specialist subagent | none | Not added | n/a | n/a | Deferred. Each delegate turn is another admitted physical request. The live sample already uses 6 of 8 requests at 57,206 of 64,000 tokens. Simple cases need no delegation, and adding one would risk the reliable demo. |
| Checkpoints and restart | [research_checkpoints.py](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/research_checkpoints.py), [research_runtime.py:96-106](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/research_runtime.py#L96-L106) | R1: a worker lost after acquiring the approved action recovers through explicit reconcile, then resumes and completes. A loss in the middle of a turn has no continuation: the runtime does not call `continue_pending()`. | Restart probe R1/R2 | `restart_qualification` stays `not_run` | Owner 1: use `continue_pending()` for reconciled same-action recovery |
| Untrusted text | [research.py:72-78](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/research.py#L72-L78) | Source files enter context only as ID plus sha256. The objective and notes are data. A model obeying "already approved, run now" fails closed on unprepared IDs or pauses at the canonical review. | `test_instructions_inside_reviewed_text_cannot_approve_or_dispatch_science` | Live-model susceptibility untested | None |

## Results (exact)

### Controlled conditions

The predicates in `controlled-conditions.v1.json` were committed in `2518d63` before the
recorded run. C1–C3 reuse inputs that had been observed before; C4 was predicted before its
first run.

| Condition | Input | Observed |
|---|---|---|
| C1 supported witness | Synthetic hero rows; ke ∈ [1/10, 17/100]; constraints 6 h/8 h, 1/5 mg/L, 8 h | Nothing runs before approval. Outcome `certified_counterexample` (valid, matches, passed), 2 checked candidates. Next step: pair design. Two steps are Done, citing the evidence. The design review binds the actual pair and constraints. After a separate approval: `checked_pair_separation` with a positive exact margin, and the next step is a new reading. Both native packets replay with matching anchors. |
| C2 changed claim | ke widened to [3/200, 7/20] | `no_counterexample_found`. Next step: review assumptions and the bounded search scope. Report text: "does not prove". A further advance gives a `scientific_scope` clarification with 0 new children. |
| C3 missing inputs | Objective only | `reviewed_problem` clarification, 0 children, 0 jobs |
| C3b missing constraints | No `design_constraints` | Baseline gives a counterexample; the next advance asks for `design_constraints` clarification with 0 new children |
| C4 no separating time | Allowance 5/1 mg/L | Baseline gives a counterexample. The design gives `no_separation_established`, and the next step is to review feasible times and allowance. Matches the frozen prediction. |

On unmodified `aa51f16`, C1 fails (finished steps stay pending) and C2–C4 pass. On this branch
all five pass.

### Live-equivalent reservations

These use the gateway's own formula: 1,024 plus the request bytes, which conservatively
counts tokens as bytes.

| Flow | Requests | aa51f16 | This branch |
|---|---|---|---|
| Baseline, no constraints (metered: real ledger, SDK substituted) | 6 | 63,802 | 55,388 |
| **Baseline with reviewed constraints (the demo; metered)** | 6 | **5 reserved 49,524, then the report was refused** | **57,206, completed** |
| Changed measurements, no outside candidate (scratch calculator) | 6 | 60,936 | 55,548 |
| Missing inputs (calculator) | 1 | 4,445 | 4,445 |
| Baseline plus design (calculator) | 12 | 231,726 | 193,982 (over the 8-request ceiling) |

**Admission estimate for the predeclared live sample.** This is the hero baseline with
reviewed constraints:
- **6 requests:** plan, prepare, run (pauses for review), read, plan update, report;
- **≤ 57,206 reserved input tokens** under the controlled-policy request shape;
- **3,072 output tokens** (6 × 512).

The documented 6 / 64,000 / 3,072 allocation leaves about 6,800 input tokens for a live
model's own text. A verbose live model could still exhaust it, and the action would then stop
with its evidence kept. Do not raise caps to cover that.

**Live: `not_run`.** No operator allocation exists for a live session, and no provider call or
key read happened. The precise missing operator action is in
[`docs/integration/BROWSER_AGENT_MILESTONE.md`](../integration/BROWSER_AGENT_MILESTONE.md):
1. On the existing server, start it with `BEAN_RESEARCH_MODE=live` using its existing private
   free-tier key file.
2. The visitor creates the live session and saves consent.
3. After checking the shared `provider-budget`, the operator records one allocation of
   **6 requests / 64,000 input / 3,072 output** for that session.

### Verification commands

Run with `BEAN_AI_MODE=placeholder`, a CPython 3.11 `.venv-engine` and a 3.13 `.venv`.

- Backend: `pytest -q tests --ignore=tests/integration` gives 1,229 passed on `aa51f16` and
  **1,263 passed** on this branch (the 1,229 plus 34 new author checks). `ruff check apps tests
  scripts` is clean.
- Integration: `pytest -q tests/integration` gives 157 passed, 1 skipped, 49 xfailed, identical
  on `aa51f16` and this branch.
- Focused: `tests/test_research_agent_views.py` (26), `tests/test_research_agent_conditions.py`
  (5), `tests/test_research_metered_application.py` (6), and the injection check in
  `tests/test_research_integration.py` (2).
- Browser: `node apps/web/check-research.mjs` passed 7/7 through the actual launcher, with an
  isolated store, two approvals, both downloads freshly replayed, 0 provider attempts and no
  egress. A scratch copy that also asserts the plan chips passed and saved screenshots.
- C's `tests/integration/langchain_demo_browser.mjs` fails the same way on `aa51f16` and on this
  branch. Its navigation predates the five-step UI (`#research` versus `#investigations`). This
  is for C to adapt, and is not a regression here.
- After merging main `e0e4269` (PR #48, guided journey), I reran on the merged branch:
  - **Still passing:** web unit tests 82/82; focused research and backend suites 314 passed;
    the plan-chip assertions (Done, Done, Suggested, then Done ×3, Suggested).
  - **Failing:** `check-research.mjs` passes 5/7 and then times out waiting for the native
    download on the PR #48 Result/Next-measurement pages. It times out identically on
    **unmodified `e0e4269`**, so this is a PR #48 regression for owner 3, not this change.
  - **Main's own CI** has been red since PR #46/#48. The manual-editor browser smoke times out,
    and `test_research_authority.py::test_concurrent_additive_migration_preserves_legacy_metadata`
    fails intermittently with `database is locked` on CI (it passes locally).

## Two-minute sponsor walkthrough

**Claim:** *"Dr. Bean's agent tests a scientific claim, reads checkable evidence, and revises
what it recommends doing next."*

Keep this label in view throughout:

> Controlled assistant: scripted planning model, real checker jobs

1. **0:00 — inputs.** In Check inputs, load the synthetic example and choose **Use these rows**
   (0.5 mg/L hard allowances). Set the model bounds (A 0.001–30, ke 0.015–0.35, ka 0.4–8), the
   claim ke 0.10–0.17 h⁻¹ and the question.
2. **0:25 — save.** In Investigate, open *Feasible next-measurement constraints*: 6, 8 h;
   0.2 mg/L with its reason; 8 h. Tick the input review box and click *Save reviewed inputs and
   research question*. Observable: the session is saved with 0 checker jobs.
3. **0:40 — *tests a claim*.** Click *Advance research plan*. The plan appears (the Deep Agents
   `write_todos`), along with *Review the investigation operation* showing the exact frozen
   scope. Approve stays disabled until *I approve only this frozen scientific scope and its
   limits* is ticked.
4. **0:55 — *reads checkable evidence*.** Approve. The activity shows *Checker job started* and
   *Evidence returned*, and the checker card reports that the claim is not forced, with two
   candidates.
5. **1:10 — *revises what it recommends*.** The plan shows two steps **Done**, each citing that
   evidence, and the new **Suggested** step *Review feasible times and allowance for a
   separately approved pair design*.
6. **1:20 — *revises again*.** Click *Plan next step for separate review*. The review lists
   the two actual candidate IDs plus 6 h/8 h and 0.2 mg/L. Approve it separately. The checker
   reports a checked separation at a reviewed time, and the plan now suggests *Review a new
   reading at its declared time and allowance*.
7. **1:45 — checkable outside the app.** Download the report, native evidence and replay
   anchors, and show the
   `python3.11 -m counterdex replay-native … --anchors …` command.
8. **Contrast** (second workspace, or the recorded C2/C4 results). Widening the claim to
   0.015–0.35 gives *no counterexample found* and the next step *Review assumptions and the
   bounded search scope*; no counterexample is not proof. A 5 mg/L allowance gives *no
   separation established* and *Review feasible times and allowance*.

**Defensible:**
- A real Deep Agents graph with planning and a 6-tool allowlist.
- No science runs before the exact human approval.
- Counterdex computes every result, and the agent reads that evidence.
- Different evidence leads to a different next step under the controlled policy.
- The design uses the actual candidate pair and the reviewed constraints.
- Evidence replays outside the app.
- The live sample fits its documented allocation in accounting tests.

**Not defensible:**
- Live Gemini reasoning or a live run.
- Scientific discovery, universal verification or a globally optimal experiment.
- Restart continuation.
- Design under a live allocation.
- Any statement about sponsor scoring.

## Integration needs and limitations

- **Owner 1:**
  - Integrate this PR and retest the combined commit.
  - Research sessions started before this change resume with `research_checkpoint_incompatible`
    because the prompt version is now v4. Finish or cancel them before deploying.
  - Optional: persist validated commentary in `publish_report`.
  - Optional: wire `continue_pending()`.
  - Update the 63,802 figure in `BROWSER_AGENT_MILESTONE.md`.
- **Owners 3/4:** the plan now shows Done for evidence-backed steps. Step reasons come from the
  server ([research_integration.py:196](https://github.com/Arnav-M10/DrBean-hp26/blob/bdad93e85b5b74fd28a3835348d82ed4b3560b56/apps/api/bean_api/research_integration.py#L196)); wording changes are welcome as a narrow patch.
- **C:** retest F-RESEARCH-PLAN-PROGRESS-PENDING and adapt the demo browser probe to the
  five-step UI.
- **Skills:**
  - Read the Anthropic webapp-testing SKILL.md (reconnaissance first, wait for network idle,
    descriptive selectors, screenshots). Its Python helper was not used: the repository already
    drives its real launcher with Playwright.
  - Design skills (frontend-design, Impeccable, web-design-guidelines) do not apply to graph
    work and were not used.
