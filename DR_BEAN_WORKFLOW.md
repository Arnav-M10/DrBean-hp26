# Dr. Bean — practical study workspace

Status: Interactive frontend mockup completed on 2026-11-14. Confirmed product decisions are distinguished from recommended layout details below. The mockup is available at http://127.0.0.1:4190/; connection to the working scientific application remains a separate implementation step.

## 1. Goal

Help researchers open a sample or their own study, review and run a scientific check, understand the result, and plan a useful next measurement through a focused workspace with minimal routine scrolling.

This is the application **after the homepage**. Assume the user understands its purpose. Do not introduce a marketing hero, lengthy onboarding, or repeated product explanations.

## 2. Confirmed decisions

- Keep the Einstein-inspired bean logo.
- Users can select a sample study. It opens with editable, prefilled measurements and assumptions; selecting it does not execute science.
- Users may jump directly to Review. Visiting every setup tab is not required; validation and explicit approval still apply.
- Avoid routine page scrolling. Users select between views rather than navigating stacked sections. Allow scrolling when needed to prevent clutter or inaccessible content.
- The primary action after an eligible result is **Plan next measurement**.
- The secondary action is **Revise inputs**, not Edit study. It changes the data or question and leads to a newly reviewed analysis, preserving the earlier result.
- Sample studies also have editable, prefilled next-measurement settings, explicitly labeled sample assumptions.
- Keep the workflow simple: one obvious primary action, clear context, and only the relevant choices at each step.
- Make frontend changes only. Explain the necessity of any backend change to the user before proceeding with it.
- The exact appearance is not yet approved. Assess a visual mockup before committing to layout details.

## 3. Core workflow

### A. Select a study

Recommended working entry screen:

- Prominent actions to select a sample or start with the user's own inputs.
- Access to existing work without introductory marketing content.
- Sample choices show a short study description, model, and synthetic origin.
- Initially expose only samples supported by existing data and engine capabilities. One verified sample is preferable to invented variety.
- Selecting a sample creates an editable browser draft, not an approved run or a fabricated completed result.

### B. Set up the study

Recommended selectable views: **Data · Claim & assumptions · Review**.

Keep the study name, sample origin, draft status, navigation, and primary action visible on typical desktop screens. Switching views preserves draft edits.

- **Data:** editable measurements with units and hard allowances; a preview of included readings and allowances where space permits. The preview is not an analysis result.
- **Claim & assumptions:** the range being tested, model bounds, and the explanations needed to interpret the input correctly.
- **Review:** a readable summary of the exact data, claim, assumptions, and proposed work. Missing or invalid fields link back to their editors. Users can enter this view directly.

Recommended primary setup action: **Review & run**. It opens review; it does not bypass the existing frozen-plan, approval, and start semantics. Exact button grouping should follow what the API can safely support.

Keep the main controls visible. Long tables can scroll within a clearly bounded region. Do not clip content or shrink text to force a fit. On small screens and at increased text zoom, allow normal page scrolling when needed.

### C. Run and inspect results

Recommended behavior:

1. Show actual queued/running/completed state and available cancellation controls. Do not invent a progress percentage.
2. Open Results for the exact approved run when it finishes.
3. Lead with a plain-language scientific finding and a plot of actual returned evidence when available.
4. Provide selectable **Summary · Candidates · Evidence** views instead of a long stacked report.

Keep scientific outcomes distinct:

- A checked candidate outside the claim means the reviewed measurements permit an alternative under the accepted assumptions.
- No counterexample found within the search limits does **not** prove the claim.
- Incomplete or failed checking must remain visible as such; a completed job is not itself a valid scientific result.

Confirmed next actions:

- **Plan next measurement** — primary when two checked compatible candidates are available.
- **Revise inputs** — secondary; returns to an editable draft and requires a fresh review for another run.

If a comparison is unavailable, explain the specific requirement rather than presenting a dead-end button. Keep evidence accessible for useful bounded or no-separation outcomes.

### D. Plan the next measurement

Recommended focused setup view:

- Show the selected historical result and two actual checked candidates. Select the only eligible pair automatically when unambiguous; provide a choice if multiple candidates are available.
- Ask for feasible measurement times and the future hard allowance, using the study's units and concise explanations.
- For the synthetic sample, prefill editable design settings. Clearly label them as sample assumptions, not laboratory facts or computed recommendations.
- For user-provided data, obtain reviewed constraints rather than silently treating sample settings as feasible.
- Keep horizon, allowance provenance, certificate permissions, and other required constraints accessible and disclose them in review.
- **Review comparison → approve → run** uses a separate design approval. Approval of the baseline does not authorize design execution.

Show the computed selected time, the scope of the comparison, and its checked or numerical status. Preserve access to every grid outcome and the native evidence. A result may honestly report that no useful separation was established.

### E. Follow-up boundary

The existing application has follow-up functionality, but its detailed UI was not settled in this interview. Preserve it and its distinction between actual and hypothetical readings. Do not silently execute follow-up work or overwrite the original study.

## 4. MVP and acceptance criteria

| Essential feature | Observable acceptance criteria |
| --- | --- |
| Editable sample selection | Selecting the supported sample opens its actual input values; values can be changed; origin remains synthetic; no scientific work starts on selection. |
| Focused study setup | Data, claim, and review are selectable; edits survive switching; valid samples can go directly to Review; invalid inputs cannot be approved; navigation and primary action remain reachable. |
| Results-to-design handoff | Results belong to the selected approved run; eligible results offer Plan next measurement as primary and Revise inputs as secondary; sample design settings are prefilled and editable; design requires separate approval. |

Across all three: preserve working sessions, existing authorization, exact scientific values, approvals, evidence downloads, and prior results. Use the existing backend contracts.

## 5. Deferred features

- Additional scientific models or unsupported sample studies.
- A marketing homepage or mandatory tutorial.
- Accounts, collaboration, provider activation, and new external services.
- A general redesign of follow-up acquisition and advanced evidence inspection.
- A large sample catalogue before its data and expected behavior are verified.

## 6. Technical approach

Existing stack: buildless HTML/CSS/JavaScript in `apps/web`; FastAPI and a durable worker; Counterdex scientific engine; SQLite storage.

Active local checkout: `/Users/bluestareesh/DrBean-hp26`.
Local app: `http://127.0.0.1:4173/`.

Reuse:

- Existing editable table, CSV parsing, input validation, and preview plot.
- Existing five-reading synthetic sample and its prefilled claim/model bounds.
- Current immutable plan/review/approval/run interfaces.
- Existing result rendering, pair selection, design, follow-up, and evidence downloads.
- Existing session and history interfaces; do not replace authentication.

Recommended changes are frontend routing, layout, labels, sample configuration, and presentation of current state. Do not put sample results into the UI as substitutes for computed science.

Before adding sample design presets, inspect the current verified fixtures and browser design flow to choose supported times, allowance, horizon, and provenance. The interview did not approve specific numerical defaults. Defaults remain editable and must appear in review.

The first pass requires no planned backend changes. If a desired transition cannot be supported by the existing contracts, document the missing interface and explain it to the user before changing the backend.

## 7. Risks and fallbacks

- **Limited scientific scope:** the current engine supports one two-rate concentration model. Use a single valid sample initially; do not suggest arbitrary datasets can receive the same checks.
- **Unknown sample outcome after edits:** compute from the user's actual draft. Do not promise a counterexample or two candidates for every input.
- **Prefilled settings mistaken for facts:** explicitly identify synthetic origin and sample assumptions at editing and review.
- **No-scroll layout harms usability:** validate at typical laptop and phone sizes and with enlarged text. Prefer readable scrolling to clipped controls or tiny text.
- **Missing runtime/provider capability:** preserve the manual science path and truthful capability/error messages. Do not enable live AI as part of a frontend task.
- **Review simplification hides consent:** retain the exact frozen input and separate approvals, even when presenting a compact flow.

## 8. Build sequence and validation

1. **Visual mockup:** show sample selection, a study setup view, and a result-to-design view. Validate hierarchy and scrolling behavior with the user before implementing a broad layout change.
2. **Setup implementation:** connect the selected sample to existing draft state; add selectable Data / Claim & assumptions / Review views with direct review access.
3. **Result handoff:** present concise actual findings, preserve candidate/evidence access, and establish the confirmed primary and secondary actions.
4. **Design setup:** reuse actual pair context and existing design controls; prefill reviewed sample settings and preserve separate approval.
5. **Verification:** run existing frontend tests and a focused browser walkthrough. Verify real scientific execution only in the prepared offline environment; label anything not executed as unverified.

Demonstration:

- Select the synthetic sample and inspect/edit a measurement.
- Jump directly to Review, confirm the frozen inputs, approve, and run.
- Inspect the actual result and candidate evidence.
- When eligible, choose Plan next measurement, adjust a prefilled setting, review, separately approve, and inspect the real design result.
- Revise inputs and confirm the old result remains available and the new draft cannot reuse its approval.

Also check an invalid input, unavailable pair comparison, no-counterexample/no-separation presentation, route switching, session persistence, keyboard navigation, narrow screens, and long-table scrolling. Do not invent pass counts or computed outcomes.

No deadline, ownership split, or implementation estimate was agreed in this interview.

## 9. Remaining decisions

Nonblocking for mockups:

- Exact visual arrangement and responsive behavior.
- Whether the initial selector exposes only the existing sample or additional independently verified variants.
- Exact sample design defaults, to be derived from current verified application examples.
- Detailed follow-up interaction after a design result.

**Concrete first task:** create a compact visual mockup of sample selection and the Data / Claim & assumptions / Review workspace, keeping the bean logo and the main controls visible without routine page scrolling.

## 10. Completed interactive mockup

Files: `workspace-preview/index.html`, `workspace-preview/styles.css`, `workspace-preview/app.mjs`, and `workspace-preview/reference.json`.

- Retained the Einstein bean logo and used a restrained ivory/green workspace with a study list, editable table, plot, and contextual inspector.
- Implemented sample selection, editable measurements and assumptions, direct Review access, visible primary actions, and input validation.
- Added selectable Summary / Candidates / Evidence views for an explicitly labeled saved repository example. Edited inputs are never presented as its source.
- Made **Plan next measurement** primary and **Revise inputs** secondary. Comparison settings start with editable synthetic assumptions and require a separate review.
- No API calls, scientific execution, backend changes, or modifications to the running app. Mockup edits exist only in the current tab and reset on reload.

Verified in the browser at 1366×768: the sample selector, five-reading data view, claim view, review, reference summary, and comparison settings fit their available panels without routine scrolling. At 390×844, the page has no horizontal overflow and keeps the primary action reachable while allowing vertical scrolling. Also checked retained draft edits across routes, direct review, invalid claim rejection, separate comparison approval, and the explicit no-execution dialogs. JavaScript syntax check passed; no browser console errors were observed during the walkthrough.

The preview demonstrates layout and interaction only. Live run status, session/history integration, uploads, scientific execution, and existing follow-up functionality still belong to the working app at http://127.0.0.1:4173/.
