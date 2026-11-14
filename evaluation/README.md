# Evaluation harness

Standard library Python. Entry point: `python3 evaluation/cli.py` (see `--help`). Protocol and rules: [docs/evaluation-protocol.md](../docs/evaluation-protocol.md).

| Path | Content |
|---|---|
| `manifest.json` | Frozen manifest: case and source digests, schedule, caps. Changing a frozen file needs `cli.py freeze`, which bumps the version and keeps ancestry. |
| `cases/C01.json` to `C12.json` | Immutable inputs, controlled boundaries and frozen expected assertions, two variants each. |
| `authoring/build_cases.py` | The script that wrote the cases. A test checks the files still match it. |
| `selftest/` | Exemplar observations that prove the grader. Harness self-test only, never product evidence. |
| `sources/` | Synthetic lab-sheet PNGs, `expected/` transcriptions with pixel regions, and the renderer in `build/`. `h01`, `h04` are sealed holdouts. |
| `drbean_eval/` | `contract` (DB-SC-1 test oracle), `oracles` (exact margins), `budget` (shared provider ledger), `assertions` (grader), `subject`, `runner`, `report`, `sanitize`, `admission`. |
| `results/` | `attempts.jsonl` (append-only), `traces/`, `REPORT.md`, `release-checklist.json`. |
| `ledger/provider_budget.jsonl` | Shared provider budget ledger. Absent until a human opens a cohort. |
| `tests/` | The harness's own unit tests. |

## Observation schema `eval-observation/v1`

A subject returns one JSON object per scheduled entry. The component that owns the behaviour emits it from its own controlled test boundary or from a real run. The harness only grades it.

Required on every observation:

| Field | Meaning |
|---|---|
| `schema` | `"eval-observation/v1"` |
| `lane` | `fixture_contract`, `live_intake`, `live_agent_controlled_tools` or `actual_full_stack`. Must equal the scheduled lane. |
| `tested_commit`, `case_sha256` | The commit the product ran at and the case digest from the manifest. Mismatches are rejected. |
| `operation` | `intake`, `agent`, `design` or `follow_up`, matching the case. |
| `provider.transport` | `controlled`, `live` or `none`. Live lanes require `live`; the fixture lane forbids it. |
| `tools.transport` | `controlled` or `real`. The full-stack lane requires `real`. |
| `provider_requests` | Integer count of provider requests in this invocation, including retries. |
| `approvals_created` | Integer. Always expected to be 0: no assistant operation creates an approval. |
| `disclosed_text` | Every string shown to the user or returned in errors, for leak checks. |
| `state` | Operation state, for example `review_ready`, `needs_clarification`, `rejected`, `unsupported`, `provider_refused`, `provider_timeout`, `completed`. |

Live lanes also report `usage.requests[]`, one item per dispatched request: `acceptance` (`known` or `unknown`), `input_tokens`, `output_tokens`, `provider_request_id`, `network_attempts`, `outcome`. Optional: `versions` (model id, SDK, framework, prompt and schema versions), `timings` (queue, provider, computation, checking, export in milliseconds), `scientific_jobs`.

By operation:

- **intake:** `proposals[]` (`field`, `value` as a canonical rational string or text or null, `status` in `proposed|ambiguous|missing|unsupported`, `unit`, `semantics` in `hard_bound|standard_deviation`, `origin`, `source_ref` with `asset_sha256`, `page`, `region_xywh_px`, `source_label` in `locator_only|needs_human_verification`), `questions[]` (`topic`, `kind`, `options`), `draft_before`, `draft_after`, `reviewed_draft`, `provenance[]`, `computation_authorized`, `repair_requests`, `plan_attempt.accepted`, `source_binding`, `fallback`, `recoverable`.
- **agent:** `tool_calls[]` (`name`, `scenario_id`, `permission` in `allowed|denied`, `reservation_id`), `reservations[]`, `mutations[]`, `effective_tools` (`enabled`, `forbidden_reachable`), `evidence_state`, `final` (`action`, `reason_code`, `claims[]`, `references[]`, `badges[]`, `labels`, `decision_basis`, `review_request`).
- **design:** `design` (`tier`, `options[]` with `option_id`, `time`, `margin`, `raw_score`, `tier`, `state`; `selected_checked`, `selection_policy`, `badges`, `claims[]`).
- **follow_up:** `revision` (`origin`, `created`, `parent_revision_ref`, `old_artifacts_byte_identical`, `requires_new_approval`, `hypothetical_label_visible`), `exclusions[]` (`candidate_id`, `basis`), `claims[]`, `explanation`.

Field names inside `proposals` follow the sheet transcriptions (`row1_time`, `row1_concentration`, `row1_allowance`, `A_min`, `ke_max`, `target_min`, `model_template`, and so on). `claims` are short tags, not prose; a claim tag such as `interval_proved` fails the overstatement assertions. Free-text explanations still need a human grader: the tag check is a screen, not a proof that every sentence is supported.

Never put raw prompts, raw provider replies, hidden reasoning, keys or personal data in an observation. The runner drops known private keys, redacts secret-shaped strings, and withholds any trace that still contains a planted sentinel.
