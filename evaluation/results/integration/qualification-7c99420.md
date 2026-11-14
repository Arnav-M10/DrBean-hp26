# Independent qualification of candidate `7c994203ceab1013d516fcd323e088bed14cd28a` (addendum)

This candidate changes only the harness relative to `980a25a`: the lane engine precondition fails again on a stale installed engine copy. The application code is still identical to `main` `b8c5952`. The full record, with platform, the rehearsal script and the four claims, is `qualification-e12c512.md`.

| Check | Result at `7c99420` |
|---|---|
| Acceptance lane, harness launch path | **7/7**: hero `att_d6f52cfd6cae4328`, changed input `att_0111795908c74657`, retry/concurrency `att_e8c5e96c055046de`, design authority `att_ed3594301c1645b8`, follow-up `att_0fcef9e034374eb4`, cancel/restart `att_7923c04a09e9412d`, zero dispatch `att_1ea8c1627f8c4a81` |
| Engine controls | **22/22** |
| `controlled_callbacks` | passed `lane_28e854a83c5a4513` {"not_available": 37, "passed": 81, "xfailed": 4}; artifacts include the Deep Agents inventory and the controlled adaptivity contrast |
| `controlled_science` | passed `lane_9f28fcc08af24960` {"not_available": 12, "not_run": 1, "passed": 17} |
| `historical_replay` | passed `lane_a0332164932e4a9b` {"incompatible_version": 1, "replayed": 152} |
| `live_gemini` | **not_run** |
| `gate --require release` | **exit 0** |

Preview evidence since `980a25a`:
- `previews/pr36-30ca1d7/check-paper-macos.json`: Owner 4's real-browser paper check, 31/31 on this Mac.
- `previews/combined-e67c3cf/summary.md`: PRs #33 + #35 + #36 combined with no conflicts; backend 898, engine 306, integration 134 + 18 expected xfails, web 36.
