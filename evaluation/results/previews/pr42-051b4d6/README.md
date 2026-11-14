# Preview: A's PR #42 head `051b4d6` (component branch, not a candidate)

C (independent validation), 2026-11-14. This is **preview / component evidence**, never release acceptance. A's
branch is based on main `299a356` and is not merged. Neither the routes nor the worker invoke the research graph,
so no coordinator predicate can pass from this preview.

## Identity

| Item | Value |
|---|---|
| Application | A's `codex/three-owner-agent-science` at `051b4d6d985062ffd45067852ea738ed0482dce2` |
| Overlay used for the C lane | local commit `fbc08ee` = `051b4d6` + C harness `f278de6`, not pushed. Its `apps`, `packages`, `shared`, `scripts`, `fixtures`, `pyproject.toml` and `uv.lock` are identical to `051b4d6`; `evaluation` and `tests/integration` are identical to `f278de6`. |
| Backend runtime | isolated `.venv` built from the unchanged `uv.lock` (`uv sync --locked --offline`), CPython 3.13.18; deepagents 0.7.38 |
| Engine runtime | C checkout's `.venv-engine`, CPython 3.11.17, Counterdex 0.3.0. A changed only an engine test file (`packages/groundwork_adapter/tests/test_bridge.py`); engine source is identical. |
| Host | macOS 26.7 arm64 |
| Provider | none: controlled models only; the egress guard verified zero external requests; no key read |

## Results

| Run | Result |
|---|---|
| `controlled_callbacks` preview lane `lane_fec602d133ef4af0` (`lanes run --lane controlled_callbacks --app-repo <overlay> --results evaluation/results/previews/pr42-051b4d6`) | passed: 110 passed, 1 xfail (F-SESSION-CAPACITY-EXHAUSTION, B), 43 NOT_AVAILABLE, 0 failed |
| Same lane on main `299a356` at `f278de6` (for comparison, `lane_0e9bd73a317346b8`) | 102 passed, 5 xfail, 47 NOT_AVAILABLE |
| Difference | 4 narration cases now pass (F-NARRATION-OVERSUPPRESSION fixed by policy v3); 4 inventory probes run instead of NOT_AVAILABLE |
| Backend suite at pure `051b4d6` (`pytest -q tests --ignore=tests/integration`, CI's command) | 1029 passed, 1 skipped (B research runtime absent in an A-only checkout); `ruff check apps tests scripts` clean. These are A's author checks and the existing suite, re-run by C for reproducibility; they are not independent evidence. |

## Compiled graph inventory (C probe and exploration)

`tests/integration/test_research_graph_inventory.py` passes 4/4 here and reports NOT_AVAILABLE on main. The listing
below comes from `inventory_exploration.py` (in this folder; output in `inventory_exploration.txt`), run from pure
`051b4d6` with the isolated `.venv`.

- **Compiled parent:** a single tool node with exactly `prepare_scientific_proposal`, `publish_research_report`,
  `read_research_evidence`, `request_clarification`, `run_scientific_operation` and `write_todos`. This matches
  the allowlist A declared in `docs/integration/RESEARCH_GRAPH_HANDOFF.md`.
- **Planning:** `write_todos` comes from langchain's own `TodoListMiddleware`; it is not among the five explicit
  tools.
- **What one model turn sees:** exactly those six tools. There was one model call and one admitted turn, so no
  hidden model request. Plain prose ends with `research_completion_unaccepted`, and no side-effect port is called.
- **Middleware passed to `create_agent`:** `FilesystemMiddleware` (A's tool-less replacement), the SDK's
  `_ParentNotifierMiddleware`, `PatchToolCallsMiddleware`, `TodoListMiddleware`, A's `Boundary`, the lazy
  `AnthropicPromptCachingMiddleware`, `UnsupportedContentMiddleware` and `ModelRefusalMiddleware`.
- **Excluded SDK defaults:** a default deep agent of the same pinned SDK adds `SubAgentMiddleware` and
  `SummarizationMiddleware`, plus the tools `delete`, `edit_file`, `execute`, `glob`, `grep`, `ls`, `read_file`,
  `task` and `write_file`. All are absent from the product parent. There are no specialists, so no delegation is
  possible.
- **Checkpointer:** the supplied one is passed through unchanged. `checkpointer=None` is refused before any model is
  constructed.
- **The probe catches regressions.** Two mutations of A's graph were each caught:
  - restoring the default filesystem middleware, with the factory's own self-check disabled (3 probe failures);
  - no longer excluding summarization (1 failure).
- **Note for integration:** the SDK's `_ParentNotifierMiddleware` stays in the stack. It does nothing unless the
  run config carries an async-subagent parent reference (the `configurable` parent key or
  `metadata.parent_thread_id`); with one, it would contact an Agent Server. B's server-built run config should never
  carry those keys. C will check the actual integrated config. The egress guard would refuse such a call in the
  offline lanes.

## Narration retest (F-NARRATION-OVERSUPPRESSION, A)

Policy `evidence-bound-statements.v3` keeps the four correct limiting statements: the strict xfails become
XPASS(strict), and `--runxfail` gives 37/37. C's 14 new converse cases are all withheld on v3 (51 passed) and on
main's v2 (47 passed, 4 strict xfails). The finding is `fixed_pending_retest`. It closes only on B's integrated
candidate.

## What this preview does not establish

- the actual app or worker invoking the factory;
- a disk-backed checkpointer that survives a process restart;
- any DB-RESEARCH-1 route or browser path, or a real Counterdex child dispatched by the graph;
- A's combined A+B claim (141 passed with B `0c69912`), which C has not reproduced;
- live Gemini, which is `not_run`.

These are Gate 1-3 integration properties and await B's integrated commit.
