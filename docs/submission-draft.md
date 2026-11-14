# Submission draft (for human review; not submitted)

Nothing here has been published, posted or submitted. Publication, enrolment and submission need the team's specific authorization. Every bracketed item must be replaced with a fact before use. Remove any sentence whose evidence does not exist at submission time.

## Project

**Name:** Dr. Bean (powered by Groundwork)

**One line:** Dr. Bean helps a researcher see what their measurements actually constrain and choose a defensible next measurement, with a person reviewing every value and approving every computation.

**Main track (one only):** Science and Discovery (proposed; team to confirm). Overall consideration is automatic; a main-track winner cannot also win Best Overall.

**Team:** [name 1, Discord username] · [name 2, Discord username] · [name 3, Discord username] · [name 4, Discord username]. Rookie eligibility: [per organizer definition].

**Repository:** https://github.com/Arnav-M10/DrBean-hp26 [confirm it is public and created 13–15 November]

**Video:** [link, only once processing has finished and the link opens signed out]

## What it does (write from the accepted build only)

Draft text that is true today:

> Dr. Bean's web workspace takes a concentration time series, by CSV or by hand, checks every number exactly as a fraction, and walks the researcher through stating a two-rate model, parameter bounds and a claimed range for the elimination rate. It keeps the original spelling and source of every value and exports the reviewed draft.

Draft text that becomes true only when the listed evidence exists:

| Sentence | Evidence required first |
|---|---|
| "Gemini reads a lab-sheet image and proposes each value with its location; a person confirms or corrects it." | Live intake attempts for C01 and C04 in `evaluation/results/attempts.jsonl` |
| "A real deepagents agent chose different actions for different evidence under the same permissions." | Live-agent attempts for C08 and C09 |
| "A bounded, approved computation found a checked alternative outside the claimed range" (or the honest unresolved result) | The actual full-stack record |
| "It suggests when to measure next" with the tier named | The design job's suggestion and tier |

## Sponsor and special entries

Describe only what the accepted build does. No weights, required models or win probabilities are known or claimed.

| Entry | Claim allowed now | What would substantiate it |
|---|---|---|
| Gemini | none | Actual admitted image assistance, source-linked proposals, a useful correction or abstention, an explanation grounded in returned evidence |
| Amazon Practical AI (creativity, usefulness, technical implementation, user experience, 25% each per H1) | user experience of the manual workspace only | Usefulness: an observed real task. Technical: bounded actions and recovery. Creativity: ambiguity connected to a next measurement. No AWS is used or needed. |
| LangChain (deepagents) | none | Real deepagents use in the same flow |
| Peri | none | A real event-time consultation with a qualifying organization, with name, role and permitted evidence |
| Others (Tiger Data, MongoDB, Solana, Vultr, Photon) | none; omitted | not pursued |

## Limitations to state

- Narrow scope: one model family, one image, one claim type.
- A result is conditional on the reviewed model, measurements and hard allowances. It does not identify the true parameter, validate the model or support clinical decisions.
- Gemini proposes and explains. It does not approve or decide validity.
- The evaluation is a small feasibility portfolio with every failure and unrun case retained.
- All data shown are synthetic.

## What predates the event

See `docs/provenance-and-eligibility.md`. Planning documents and the shared contract predate the event. The organizer ruling on reusing earlier implementation is [pending / recorded as: ...]. No earlier implementation is in the repository.

## Before submitting

- [ ] Clean-checkout run passes on the submitted commit.
- [ ] Repository link opens signed out.
- [ ] Video finished processing and plays signed out; at most 120 seconds.
- [ ] Names and Discord usernames are the real ones.
- [ ] Every claim above has its evidence; unsupported sentences removed.
- [ ] A human submits. A saved local file is not a completed entry.
