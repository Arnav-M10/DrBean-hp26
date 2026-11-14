# Independent qualification of candidate `c2803a404f314392a99241808a69eefcfb8e905c` (addendum)

This candidate changes only the harness relative to `e12c512`: real paper-route attacks, development gold, and expectation updates for the hostile assets. The application code is still identical to `main` `b8c5952`. The full record, with platform, the rehearsal script and the four claims, is `qualification-e12c512.md`; everything there applies here, with the identifiers below.

| Check | Result at `c2803a4` |
|---|---|
| Acceptance lane, harness launch path | **7/7**: hero `att_10a264af8a5745a8`, changed input `att_9614785a0de849a7`, retry/concurrency `att_096ff6346a37442d`, design authority `att_3ad6b9fbaa1e4cc7`, follow-up `att_1478411e81c24101`, cancel/restart `att_e2ad482fd0aa4282`, zero dispatch `att_5fc3b732b8cd4357` |
| Engine controls | **22/22** |
| `controlled_callbacks` | passed `lane_95981c94f65a4278` {"failed": 0, "harness_pending": 0, "not_available": 36, "passed": 81, "skipped": 0, "xfailed": 4} |
| `controlled_science` | passed `lane_b533ca8eb5c94baf` {"failed": 0, "harness_pending": 0, "not_available": 11, "passed": 17, "skipped": 0, "xfailed": 1}. The single xfail is the opt-in heavy memory attack, recorded as NOT_RUN |
| `historical_replay` | passed `lane_4d51911556024747` {"incompatible_version": 1, "replayed": 128} |
| `live_gemini` | **not_run** |
| `gate --require release` | **exit 0** |

## Preview: PR #36 (Owner 4) with Owner 2's unreviewed route patch (`f063b10`; labelled preview, never acceptance)

| Check | Result |
|---|---|
| Owner 4's own paper tests on macOS | 36 passed (their PR reports only Linux) |
| `controlled_callbacks` | passed `lane_340eacd0937d4fae` {"failed": 0, "harness_pending": 0, "not_available": 36, "passed": 81, "skipped": 0, "xfailed": 4} |
| `controlled_science` | passed `lane_528c0f8cd3fa4b9a` {"failed": 0, "harness_pending": 0, "not_available": 6, "passed": 22, "skipped": 0, "xfailed": 1}, including the five paper-route attacks |
| Hostile assets through admission (library-level, under a watchdog) | 19 assets. All are refused with named codes or admitted with active content reported. Peak memory at most 327 MiB, each under 0.3 s |
| Maximum-size inflate bomb (opt-in) | **F-PAPER-RENDER-MEMORY (P1)**: a 4.2 MB PDF whose page inflates to 4 GiB drove the application's process tree to 2440 MiB (watchdog kill at 1549 MiB gives a 422 `resource_limit`) |
| Development gold versus Owner 4's manifest | 23/23, 23/23, 10/10 fields agree |
