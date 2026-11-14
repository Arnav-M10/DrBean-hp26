# Independent qualification of candidate `980a25ab4c343a7a3573babacc18ca3085c56d12` (addendum)

This candidate changes only the harness relative to `e12c512`. The changes are paper-route attacks, development gold, dummy live-opt-in checks, original-checker historical replay, and Deep Agents evidence artifacts in lane reports. The application code is still identical to `main` `b8c5952`. The full record, with platform, the rehearsal script and the four claims, is `qualification-e12c512.md`.

| Check | Result at `980a25a` |
|---|---|
| Acceptance lane, harness launch path | **7/7**: hero `att_9b847ef66aab4bde`, changed input `att_67559ab59c3744b7`, retry/concurrency `att_dfdf54deaa8543e4`, design authority `att_9caebbaa1e6740a5`, follow-up `att_c32eb4fb79534826`, cancel/restart `att_730b1c4495cd40fe`, zero dispatch `att_e49345ad2d8e461e` |
| Engine controls | **22/22** |
| `controlled_callbacks` | passed `lane_1831b2bc678648fe` {"not_available": 37, "passed": 81, "xfailed": 4}; artifacts include `deepagents-inventory.json` and `deepagents-adaptivity-controlled.json` |
| `controlled_science` | passed `lane_ac4cd9ddf5024b4e` {"not_available": 12, "not_run": 1, "passed": 17} (not_run = the opt-in heavy memory attack) |
| `historical_replay` | passed `lane_6afb1071021c45fe` {"incompatible_version": 1, "replayed": 144} |
| `live_gemini` | **not_run** |
| `gate --require release` | **exit 0** |

## Previews at the previous harness `ef2e405` (labelled, never acceptance)

- **PR #36 + Owner 2's unreviewed route patch (`30ca1d7`).**
  - Lanes `controlled_callbacks` 82 passed, 4 xfail, 36 NOT_AVAILABLE. The doctor reports the dummy live opt-in without printing its key.
  - `controlled_science` 22 passed, 6 NOT_AVAILABLE, 2 not_run: the heavy memory attack, and the full launcher start, which is blocked because ports 8000/4173 are held by another instance on this Mac.
- **PR #33 (`d0148aa`).** Historical replay with original checkers: 21 replayed, 3 `replayed_original_checker` (review-evidence packets at 4f6c580, 5507519 and f713635), 1 `incompatible_version` (0.2.0 archive).
