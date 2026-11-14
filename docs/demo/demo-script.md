# Two-minute demo script

One script for the in-person presentation and the optional video. The timings are narrative targets, not promised runtimes. This is the only current demo script.

**The story:** "Several explanations fit these measurements. Dr. Bean exposes the ambiguity and helps choose a measurement that distinguishes this pair, with evidence you can rerun."

**Readiness today: scenes 3 to 6 cannot be shown.** They need a real scientific result through the application (gate G1, then G2). Show a scene only when its "needs" column is met by a real run. Never splice a mock into a sequence described as live, and never show the engine's prepared fixture as if the application produced it.

Every AI element on screen carries a visible **placeholder AI** label until the user authorizes live testing. Say it aloud once: "Gemini is wired in but switched off for this demo; these proposals are controlled placeholder output."

| Scene | Time | Show (only what the release actually renders) | Say | Needs | Ready |
|---|---|---|---|---|---|
| 1 Problem | 15 s | The five-row measurement table and the claimed range for the elimination rate. | "A fit looks fine, but does the data really force this rate into the claimed range? And if not, what should we measure next?" | web workspace | yes |
| 2 Source review | 20 s | The lab-sheet image beside the proposed values, labelled placeholder AI; one unresolved field; the person corrects and accepts. | "Values are proposed with their location on the sheet. Nothing enters the analysis until a person reviews it." | source review control (I-017); controlled proposals | no |
| 3 Counterevidence | 30 s | The frozen plan, the approval click, then the result table: a reference candidate and an outside candidate, both within every hard allowance. | "The researcher approves one bounded computation. The engine finds another explanation that fits every reading but has a rate outside the claimed range. It is exactly checked. So these data do not force the claim." | G1 (I-013) | no |
| 4 Next measurement | 30 s | Feasible times 6 and 8 h and future allowance 0.2 mg/L reviewed; a separate approval; a table with the selected time and the two possible-reading bands. | "Choosing the next measurement is a separate request with its own approval. For this pair, at the times the lab can sample, 8 hours separates them: no reading can fit both." | G2 | no |
| 5 Follow-up | 15 s | A reading entered and labelled HYPOTHETICAL; a new revision beside the unchanged original; which candidate survives. | "A hypothetical 3.4 keeps the reference and excludes the outside candidate. A different reading could exclude the other, or both. It never proves the range." | G2 | no |
| 6 Replay and insight | 10 s | Download of the native evidence and the replay command printing `replay: passed`. | "Anyone can rerun the exact check. That is a fresh run of the same checker, not a second proof system." | native export through the API | no |

No curve is shown: the web workspace renders tables, not plots. If a basic curve lands after the tables work, add it then.

The numbers in scenes 4 and 5 are regression oracles for one audited pair on the shared synthetic example. A real search may choose another pair and another time. Say what the run on screen actually produced.

## If real computation is slow on the day

Use a saved real scientific run from this build, shown with its real time and commit and the words "saved run". Never call it fresh. If no real run exists, show scenes 1 and the manual plan and approval path only, and say plainly that the engine is not yet connected.

## Disclose

- All data are synthetic.
- AI output is placeholder; live Gemini has not been run.
- The result is conditional on the reviewed model, measurements and hard allowances.
- The suggestion is specific to two named candidates, the reviewed times and the stated allowance. It is not a global optimum.

## Questions judges may ask

| Question | Answer source |
|---|---|
| What predates the event? | `docs/provenance-and-eligibility.md` |
| Is the AI real? | Placeholder now. Real deepagents graph, controlled model. Live Gemini: not run. `docs/INTEGRATION_STATUS.md` |
| Change an input and show me | New immutable revision, new plan, new approval, real recomputation. Works for the manual path today. |
| What did the checker establish? | The run's verification record and native bundle; today, nothing through the application |
| Which tests are controlled? | `docs/handoff-owner04.md`, results by lane |

## Rehearsal checklist (presentation device)

- [ ] `scripts/dev/setup.sh` and `start.sh` succeed on the device; doctor shows Gemini live disabled.
- [ ] Timed run at or under 120 seconds, twice.
- [ ] Model APIs unreachable (network off or blocked): everything still works.
- [ ] Tables readable at the chosen zoom; long fractions stay inside details.
- [ ] Whole path works by keyboard.
- [ ] A prepared honest line for "no separation established".
- [ ] Hypothetical data labelled on screen and aloud.
- [ ] Saved-run fallback and recovery commands on the device.

None of these has been done.
