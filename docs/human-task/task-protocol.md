# Consultation and observed-task protocol

Two separate things: a five-minute consultation that can start now, and an observed task that needs the working flow. Both are formative evidence from a convenience sample, not an adoption rate or an impact study.

**Status: neither has been held.** No person has been approached by this workstream. The human team does the outreach; no message has been sent on its behalf. If nobody relevant is available, this stays pending and does not block the build.

## Five-minute consultation (can happen now)

For a relevant student science organization, methods tutor, researcher or lab group. Listen first; do not pitch. Keep the supported model narrow in your own head: a request for another model is feedback, not evidence that the tool supports it.

1. What measurement decision do you face most often?
2. When a fitted value falls in an expected range, how do you test whether that range is really justified by the data?
3. What does one more measurement cost you in time and materials?
4. What form are your data and methods in: spreadsheet, instrument export, paper sheet, photo?
5. What would make a tool like this unusable for you?

Then, in one sentence each: what Dr. Bean does today, that the AI part is currently a placeholder, and that all examples are synthetic.

Record in `consultation-record-template.md`: organization, person, role, when it happened, permission for public use, and one supporting item they allow (for example a note they confirm). Pass one actionable observation to the responsible owner the same hour.

## Observed task (after the minimal flow works)

### Before the session

- The participant is an eligible adult researcher or a member of a suitable student organization, and agrees to take part. For a Peri entry the organization must qualify; confirm lab eligibility with the organizers if the categories do not settle it.
- Ask permission separately for: notes, quoting, naming the person, naming the organization, publication.
- Use only the synthetic sheet. Do not put the person's identity or private methods into evaluation logs or model inputs.
- Teammate roleplay is rehearsal and is recorded as rehearsal.

### Task (read aloud, then stop helping)

Say first: "The AI in this build is a placeholder; the calculations are real."

1. Import the lab sheet image.
2. Find one hard allowance and say where it came from.
3. Run the baseline and explain the result in your own words.
4. Choose times at which you could really take another sample.
5. Look at the suggestion and say what it tells you.
6. Say what a later reading could and could not establish.

Record for each step: completed, completed with help (what help), abandoned, and any confusion in the person's words. Record time spent reviewing separately from time the system spent working. Do not coach an answer and then report it as independent understanding.

### Comprehension checks (ask, do not lead)

| Topic | Question | A misconception to record |
|---|---|---|
| Conditionality | "What does this result depend on?" | Treats it as a fact about nature |
| Fit versus compatibility | "The curve fits well. Does that settle the range?" | "Yes, the fit proves it" |
| Future hard allowance | "Where would the allowance for the next reading come from?" | Picks a value to turn the badge green |
| Pair-only scope | "What exactly would the next reading tell apart?" | "It finds the true value" |
| Actual versus simulated | "Is this reading real?" | Misses the hypothetical label |
| Neither fits | "What if the new value fits neither candidate?" | "The model is impossible" or "the range is proved" |

Also ask whether the proposed times are feasible and whether the required precision has a defensible source. "No useful measurement" is a legitimate outcome: record it, do not press for a positive quote.

If a screen reliably invites a false conclusion, it is unfinished: log it in the issue ledger for Owner 03 and retest when feasible.

### Afterwards

Ask the person to explain the pair-specific conclusion in their own words and write that down verbatim. Fix one observed blocker and, if practical, repeat the task. Report the actual sample size.


Fill in `consultation-record-template.md`. Keep the private copy out of the repository. Publish only what the person permitted.
