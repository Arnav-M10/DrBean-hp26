# 120-second demo script

One script for both the in-person presentation and the optional video. No sponsor scene follows it. The timing is narrative, not a latency claim.

**Readiness today: only the first twelve seconds can be shown live.** Every later scene depends on components that do not exist yet. Do not record or present a scene until its "needs" column is met by a real run. Never splice a mock into a sequence described as live.

| Time | Show | Say | Needs before it can be shown | Ready |
|---|---|---|---|---|
| 0–12 s | The web workspace with the synthetic series and the two-rate model. A fit curve that looks fine. | "A good-looking fit does not tell you what your data actually pin down. This researcher wants to know whether the elimination rate must lie in a claimed range, and what to measure next." | `apps/web` | yes |
| 12–32 s | Upload `c04a.png`. Gemini's proposals beside the image, each with its region. The stained allowance flagged as ambiguous. The person types 0.2 and accepts. | "Gemini reads the sheet and proposes each value with its location. It will not guess the smudged allowance. A person confirms the meaning; nothing enters the analysis unreviewed." | Source admission, live Gemini intake, review view (Owners 02, 03). A real recorded run of C04. | no |
| 32–55 s | The frozen plan, the approval click, then the actual tool trace. | "The researcher approves one bounded computation for exactly this reviewed problem. The agent can only call the tools this plan permits." | Plans, approvals, runs, deepagents tools, Groundwork baseline (Owners 01, 02). | no |
| 55–75 s | The result card from typed backend fields, the grounded explanation, and two recorded traces side by side: C08 and C09. | "Here a checked alternative outside the range exists, so the claim is not forced by the data. When the same request met an inconclusive result, the agent stopped instead. Same permissions, different evidence, different action." | Real result; live-agent traces for C08 and C09 labelled "live model, controlled tools". | no |
| 75–100 s | Feasible times and a future hard allowance entered; a separate approval; the suggestion with its tier. | "The next measurement is a new request with its own approval. This is numerical guidance for two named candidates at the times the lab can actually sample. It is not a global optimum and not a checked separation." | Design routes and job (Owners 01, 02, 03). | no |
| 100–120 s | A reading added and labelled HYPOTHETICAL in the banner and the row; the new investigation beside the unchanged old one; the reviewer export. | "A new reading starts a new investigation. This one is hypothetical and says so everywhere. It could rule out either candidate or both. It would never prove the range. The earlier evidence stays inspectable." | Observation proposals, revisions, export (Owners 02, 03). | no |

## What to disclose on screen and aloud

- Every source is synthetic. The banner on each sheet says so.
- Any previously completed run shows its real time, mode and commit. A pending live call stays pending.
- Controlled-tool traces are labelled as such and never described as real science.
- If the exact tier is unavailable, say "numerical guidance" and show no stronger badge.
- If a real result is inconclusive, present it as unresolved. Do not change allowances to get a better scene.

## Questions judges may ask, and where the answer is

| Question | Answer source |
|---|---|
| What predates the event? | `docs/provenance-and-eligibility.md` |
| Which tests use controlled tools? | `evaluation/results/REPORT.md`, lane column |
| What did Gemini actually choose? | sanitized traces under `evaluation/results/traces/` |
| What did the checker establish? | the run's verification record; today: nothing has run |
| What is unsupported? | README "What does not exist yet"; runbook "Omitted integrations" |

## Rehearsal checklist (presentation device)

- [ ] Timer run on the presentation device: at or under 120 seconds, twice.
- [ ] Sheet readable at the chosen browser zoom; long fractions do not overflow.
- [ ] Whole path works by keyboard alone.
- [ ] Network disconnected: the page still loads (the smoke confirms no external request) and the saved-results fallback opens.
- [ ] A no-useful-suggestion result has a prepared, honest line.
- [ ] Hypothetical data is identified visually and verbally.
- [ ] Only synthetic content and authorized people appear in any recording.
- [ ] Local saved-results fallback and the cleared source packet are on the device.

None of these has been done.
