# Two-minute demo script

One script for the in-person presentation and the optional video. The timings are narrative targets, not promised runtimes. This is the only current demo script.

**The story:** "Several explanations fit these measurements. Dr. Bean exposes the ambiguity and helps choose a measurement that distinguishes this pair, with evidence you can rerun."

**Software rehearsal path:** source review, actual discovery, separate design, hypothetical follow-up and native replay now have a passing local browser check. Presentation-device rehearsal and measured presentation timing remain pending. Use a controlled source proposal and identify it explicitly; arbitrary-image extraction is disabled.

Every AI element on screen carries a visible **placeholder AI** label until the user authorizes live testing. Say it aloud once: "Gemini is wired in but switched off for this demo; these proposals are controlled placeholder output."

| Scene | Time | Show (only what the release actually renders) | Say | Needs | Ready |
|---|---|---|---|---|---|
| 1 Problem | 12 s | The five-row measurement table and the claimed range for the elimination rate. | "A fit looks fine, but do the data really force this rate into the claimed range? And if not, what should we measure next?" | web workspace | yes |
| 2 Source and value review | 20 s | The lab-sheet image beside the proposed values, labelled placeholder AI; one unresolved field; the person corrects and accepts. | "Values are proposed with their location on the sheet. Nothing enters the analysis until a person reviews it." | source review control (I-017); controlled proposals | software implemented; rehearsal pending |
| 3 Approved investigation, checked result | 23 s | The frozen plan, the approval click, then the result table: a reference candidate inside the claim and an outside candidate, both within every hard allowance. | "The researcher approves one bounded computation. The engine finds another explanation that fits every reading but has a rate outside the claimed range, and checks it exactly." | G1 (I-013) | software implemented; rehearsal pending |
| 4 Interpretation | 20 s | Execution, scientific outcome, binding and replay shown as separate states; the exact values in an expandable detail. | "So these data do not force the claim. That is all it says: it does not tell us the true rate, and other explanations may also fit." | G1 | software implemented; rehearsal pending |
| 5 Next-measurement constraints and design | 25 s | Feasible times 6 and 8 h and future allowance 0.2 mg/L reviewed; a separate approval; a table with the selected time and the two possible-reading bands. Then one changed constraint giving a different answer. | "Choosing the next measurement is a separate request with its own approval. For this pair, at the times the lab can sample, one time separates them: no single reading can fit both. Loosen the precision and it no longer does." | G2 | software implemented; rehearsal pending |
| 6 Follow-up and replay | 20 s | A reading entered and labelled HYPOTHETICAL; a new revision beside the unchanged original; which candidate survives; the native download and the replay command printing `replay: passed`. | "A hypothetical reading keeps one candidate and excludes the other. A different reading could exclude both. It never proves the range. Anyone can rerun the exact check; that is a fresh run of the same checker, not a second proof system." | G2; native export through the API | software implemented; rehearsal pending |

No curve is shown: the web workspace renders tables, not plots. If a basic curve lands after the tables work, add it then.

Say what the run on screen actually produced; do not recite expected numbers. For orientation only, the engine's own synthetic decision example (`packages/groundwork_adapter/docs/DECISION_EXAMPLE.md`, engine level, not an application run) discovers on these five rows a reference with ke about 0.1284 and an outside candidate with ke about 0.0994, selects 8 hours with a margin of about 0.257 mg/L at allowance 0.2, and shows hypothetical readings of about 3.27, 3.93 and 3.60 mg/L keeping the reference, keeping the outside candidate, and excluding both. A changed 4-hour measurement yields a different pair and no separating time. The earlier audit pair (margin about 0.767 at 8 hours) is a separate fixed regression control and is not what discovery returns.

A short answer to keep ready: "These two fixed parameter assignments both fit the reviewed hard bounds; the second lies outside the claimed interval. At this reviewed time and precision their possible-reading bands do not overlap. The next datum can distinguish them, but it may exclude both, and other assignments can remain."

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
| What did the checker establish? | The run's verification record and native bundle |
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
