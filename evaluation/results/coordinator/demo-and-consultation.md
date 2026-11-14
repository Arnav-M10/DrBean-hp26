# Evidence-bound demonstration plan and consultation record (role C)

Prepared for B, who owns the operational demo script (`docs/demo/demo-script.md`) and the consultation template
(`docs/human-task/consultation-record-template.md`). C does not edit those; this file states what current evidence
can and cannot support. Status is for main `299a356` (observed on C commit `bb503a7`).

## Demonstration rules

- Show only what the build renders. Each scene cites the predicate and the evidence reference behind it.
- A saved run is shown as "saved run" with its commit and time, never as fresh. Controlled model decisions are
  labelled controlled; live Gemini has not run and is not shown.
- Coordinator scenes stay out of the demo until their Gate 3 evidence exists on the exact candidate.

## The target loop, scene by scene

| Scene | Predicates | Status on 299a356 | Evidence now |
|---|---|---|---|
| Question and sources; reviewed meanings and assumptions | LOOP-01, SCI-03 | manual source review and reviewed inputs available; no research session | RS-HERO-FULL, `check-backend.mjs` (browser review) |
| Agent-maintained research plan | LOOP-02 | not available | none |
| Canonical investigation approval, actual Counterdex child | LOOP-03, LOOP-04, SCI-01 | manual plan approval and actual child available; agent dispatch not available | RS-HERO-FULL; `check-backend.mjs` |
| Evidence-dependent next action | LOOP-05 | not available as an agent decision | controlled-graph adaptivity artifact only (`deepagents-adaptivity-controlled.json`, controlled model) |
| Separately approved pair design (positive and no-separation) | SCI-04, SCI-05 | available (manual) | RS-DESIGN-AUTHORITY; `check-backend.mjs`; control `fixed_pair:grid-6-8-allowance-0.6` |
| Pause, restart, reopen at a pending review | CRASH-05 | not available for research reviews; run and design history reopen after reload | `check-backend.mjs` (reopened design history) |
| Separately reviewed new reading and recheck | SCI-06 | available (manual, hypothetical readings) | RS-FOLLOWUP; controls `followup:3.4`, `followup:4.57`, `followup:4.0` |
| Report, native bytes, fresh replay | SCI-09 | available | `historical_replay` lane `lane_583ed42dc383477e`; download-scope probe |
| A meaningful non-positive branch | LOOP-07 | manual no-separation design available; agent branch not available | control `fixed_pair:grid-6-8-allowance-0.6` |

**Honest two-minute demo today:** B's existing manual-loop script, scenes 3-6, is backed by current evidence on
this baseline (RS-HERO-FULL, RS-DESIGN-AUTHORITY, RS-FOLLOWUP and the passing `check-backend.mjs` browser run). It
must not be narrated as agent-coordinated. The general-file screen cannot be shown working: no producer is
registered on main.

## Consultation record: what C can attest

| Item | Entry |
|---|---|
| Source of the information | the DB-COORDINATOR-3OWNER-1 brief supplied by the user on 2026-11-14 |
| Content | Professor Gregor's feedback, as relayed in the brief: specimen preparation, measurement and data analysis consume time, while model fitting generally does not |
| Form | relayed paraphrase, not a verbatim quote |
| Date, attendees, permissions (notes, quote, naming, publishing), build tested | not recorded in any file available to C; B's template is the place to record them, and C does not fill it from memory |
| Supports | an observed workflow need: prioritise source preparation and review, the analysis handoff and feasible measurement decisions |
| Does not support | adoption, endorsement, a lab request, quote permission, customer status, eligibility, time saved or any prize outcome |
| Measured task utility | none observed by C (sample size 0); preparation, review and analysis times will be reported only when observed |

The two public papers named in the brief (zolleral_26 and sokolowskial_25, Princeton tglab) were downloaded only
to measure size and page count locally. They were not committed or sent to any provider; see FILE-02.
