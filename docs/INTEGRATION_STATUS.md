# Integration status

Product candidate: [PR #27](https://github.com/Arnav-M10/DrBean-hp26/pull/27), code `31a8ed3c9b66ed721cf2f37179ab3fe62ebe0d09`, incorporating Owner 2's `42f92b1` controlled-intake handoff. Local clean-checkout equivalent: `c4d1ad63713c9fb00b2baab5aa758f3a4c505952`; both have tree `9ed03fb5bc828117f33ca015ad44a0ec6f9d3703`.

- Ordinary browser source flow: upload or select the packaged synthetic image, request controlled values, inspect/correct/accept, copy reviewed rows into the draft, review assumptions, materialize, then separately approve science. No database helper or copied proposal ID.
- Unknown or changed image bytes preserve existing work and offer manual entry. Controlled output is explicitly not Gemini transcription.
- Real discovery, separately approved positive/no-separation design, hypothetical and declared actual follow-up, automatic follow-up result navigation, and native evidence downloads are implemented.
- Declared actual acquisition requires its own time, hard allowance and acquisition provenance. Declaration does not authenticate an instrument; synthetic dataset ancestry remains synthetic.
- Source selection/origin survive action rendering. Changed drafts invalidate source previews. Owner 2 enforces stale accepted-revision boundaries.
- Clean setup/start/stop/restart, selected-checkout import and provider-variable filtering are exercised by the release checks. The explicit source-example start option does not enable Gemini.
- Fresh clean candidate c4d1ad6 (tree-identical to published 31a8ed3) passed all 5 offline gates and 12 boundaries on Darwin arm64. All six CI jobs passed. See release-evidence/offline-c4d1ad6-macos.json and product-candidate.json; prior reports remain historical.
- Independent evaluator acceptance is Claude's responsibility. Owner 4 consumes unchanged tests without manufacturing findings.
- Consultation, observed user task and presentation-device rehearsal have not happened. The user requested software completion first.

Start after setup: `scripts/dev/start.sh --controlled-source-examples`. See [release runbook](release-runbook.md) and [demo script](demo/demo-script.md). Live Gemini, hosting and visual expansion remain deferred.
