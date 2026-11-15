# Independent validator: acceptance checklist (written before any candidate was seen)

Sprint start 2026-11-15T05:38:06Z. Starting main `d7abf3b33476cdecae3d4ec5779794255eff1941`.
Roles: Codex 1 backend repair, Codex 2 classic live UI (`apps/web`), Codex 3 integration.
Validator: Claude (independent; owns harness changes, retained evidence and this report only).

## Ground rules

- Live tests run only on Codex 3's exact combined commit, checked out clean. Harness files may be
  layered uncommitted; application files (`apps`, `packages`, `scripts`, `workspace-preview`) must
  match that commit exactly, and the record states it.
- Budget: at most **8 physical Gemini requests in total** for this sprint, failed and uncertain
  attempts included. They are recorded as a new, separately authorized extension in
  `evaluation/results/sprint/live-budget.json`. No ledger reset, refund, release of unknown usage or
  replenishment. A new store never adds quota.
- One live workflow is the target: **one run, one grant of at most 8**. No automatic retry. A second
  run happens only if the first made zero provider requests because of a harness fault.
- Existing server-side free-tier configuration only (`gemini-3.5-flash-lite`, free-tier assertion,
  recorded account decision). No billing, paid model or new key. The key is copied as a 0600 file
  into the temporary store by the harness and never read, printed or committed.
- Inputs: the documented public synthetic fixture only. Consent and approvals go through the
  ordinary routes and UI.
- Missing configuration, a refused grant or an unavailable candidate: live testing is **NOT RUN**.

## Live acceptance (all required for "live workflow passed")

| # | Predicate | Evidence that counts |
|---|---|---|
| L1 | A real Gemini response drives the actual Deep Agents plan and tool flow | Provider attempt rows (`provider=gemini`, `execution_mode=live`) before the first plan step or tool call; capabilities report `deepagents.execution_mode=live` |
| L2 | Provider consent is recorded before any provider dispatch | Consent record time earlier than the first provider attempt; zero attempts before consent |
| L3 | A proposed scientific operation pauses for separate scope approval | Session waits on a pending review of kind `plan` (or the scientific-scope kind); no scientific child exists before approval |
| L4 | Approval triggers real Counterdex computation | After approval a scientific child job completes with Counterdex native evidence (artifact sha256, engine version) |
| L5 | The agent reads the returned evidence and produces an appropriate next action | A tool call reading the evidence after the child, then a plan revision, report or next-action step grounded in that evidence |
| L6 | Scientific results and downloads remain available even if commentary fails | Report and native downloads available with commentary absent or withheld; checked live if commentary fails, otherwise offline (O4) |
| L7 | Reload keeps the session; downloaded native evidence freshly replays | Page reload shows the same session and results; the downloaded native file plus anchors replay with `counterdex replay-native` (passed) |
| L8 | Accounting holds | Physical requests at most the grant and at most 8 for the sprint, all attempts terminal, no retries |

A run that stops early is reported with its exact stopping code, usage and how far it got. It is
never called a qualified autonomous release.

## Offline checks (on the same candidate; no provider requests)

| # | Predicate | Test |
|---|---|---|
| O1 | Declining approval dispatches no scientific job | Existing or added backend test: reject the pending plan review, then assert zero jobs and zero scientific children |
| O2 | Changed input invalidates a stale approval | Existing or added test: approve against an old input revision or digest and expect refusal (stale) with no job |
| O3 | Exhausted allocation stops rather than silently retrying | Existing or added test: allocation used up, then the action stops with an exhausted state and exactly the allowed attempts, no extra dispatch |
| O4 | Narration failure does not hide or invalidate valid scientific evidence | Existing or added test: commentary or narration fails, yet the report, evidence and downloads stay available and valid |

Also: the backend unit suite and web suites on the candidate, and the strict offline release gate
(`scripts/release/checklist.py --strict-offline`) if it fits the window on isolated resources. If it
does not run, it is recorded as **NOT RUN**, and focused tests are never relabelled as the full gate.

## Verdict format (to Codex 3)

What may merge, what may be demonstrated, the exact tested commit, the physical request count, the
scientific and replay results, and the remaining limitations.
