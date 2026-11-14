# Sponsor evidence matrix (Workstream 5, for Owner 4)

**Status at candidate `980a25a`:**
- Application code is `main` `b8c5952`, plus labelled previews of open sprint PRs.
- Every row states what was actually observed. The four lanes are separate kinds of evidence: controlled callbacks, controlled science, live Gemini and historical replay.
- **No live Gemini request has been made**. Live qualification is `not_run`. A configured key is not evidence that any integration works.
- No scoring weights, win probabilities or testimonials are implied. The [MLH Gemini page](https://www.mlh.com/partners/gemini) states no detailed rubric. LangChain's supplied category is "best use of Deep Agents". Amazon's supplied track values creativity, usefulness, implementation and UX.

## Google (Gemini)

| Feature | Actual behaviour observed | Proof artifact | Limitation | Demo step |
|---|---|---|---|---|
| Gemini reads paper text and visuals and proposes page-cited evidence | **Implemented in open PR #35, not on `main`; never run live.** In controlled mode, the metered gateway reserves exactly once before each transport call. It never retries hidden. Every failure class is recorded as one accounted outcome, and uncertain outcomes are never refunded. The paper validator refuses forged quotes, values that are not in their quote, unit-less citations and graph estimates offered as exact. | `tests/integration/test_gemini_gateway_attacks.py` (20/20 on preview `f413922`); `test_paper_proposal_validation.py` (10 pass, 6 known-defect xfails) | Not wired to any route or UI. Live mode is refused until Owner 2's atomic session accounting lands. Open defects: F-PAPER-CITATION-SUBSTRING (P1), F-PAPER-QUOTE-NORMALIZATION, F-PAPER-HARD-BOUND-CONTEXT, F-PAPER-EXPONENT-FLATTENING | none yet; after wiring: upload a paper, select pages, give explicit consent, see cited proposal fields |
| Finds a meaningful ambiguity | Controlled only. The validator attaches blocking diagnostics for statistical uncertainty, missing units, unresolved locations and graph estimates. On `main`, image-source review blocks an ambiguous decimal until a reason is given. | `test_paper_proposal_validation.py`; `test_ai_boundaries.py::test_ambiguous_decimal_blocks_until_explicitly_resolved_with_a_reason` | Not observed with a live model. The sealed holdouts (H1–H4) are reserved for after the freeze | none live yet |
| Selects a useful action through the shared agent and updates after returned scientific evidence | Controlled only, on `main`. The same objective with different evidence changes the permitted disposition (execute versus skip after a certified counterexample). This uses a scripted model and is not live adaptivity. | `test_ai_boundaries.py::test_same_objective_different_evidence_changes_the_permitted_disposition` (+ worker variant); `deepagents-adaptivity-controlled.json` with lane report `lane_1831b2bc678648fe` | Scripted branch, so it is regression evidence only | run the controlled agent lane; it is labelled controlled in the UI and API |

## LangChain (Deep Agents)

| Feature | Actual behaviour observed | Proof artifact | Limitation | Demo step |
|---|---|---|---|---|
| Actual `create_deep_agent` graph with a scoped tool inventory | On `main`, deepagents 0.7.38 `create_deep_agent` runs with exactly four permitted tools: `execute_approved_scenario`, `read_scoped_evidence`, `record_allowed_skip`, `return_grounded_explanation`. Filesystem, shell, subagents, memory and summarization are disabled, and a budget middleware is applied. A forbidden tool request fails with no side effect. | `test_ai_boundaries.py::test_actual_graph_offers_only_permitted_tools_and_records_controlled_lane`, `::test_forbidden_tool_request_fails_without_any_side_effect`. The machine-readable runtime inventory `deepagents-inventory.json` (deepagents 0.7.38, langgraph 1.2.21) is stored with lane report `lane_1831b2bc678648fe` | Controlled model only. No specialists, delegation depth 0 | controlled agent run in the app |
| Plan, tool, delegation, interrupt and resume | Not on `main`. PR #34 (Owner 2) contains interface documents only (`research-agent.v1`). Durable checkpoints, review interrupts, specialists and resume are work in progress. | `shared/contracts/RESEARCH_AGENT_HANDOFF.json` on PR #34 | Durable app jobs exist (restart recovery is proven), but durable agent state does not. Under the brief, one without the other is not a resume claim. | none yet |
| Metered agent chat model | PR #35 `GeminiChatModel` dispatches only asynchronously through the metered gateway. It refuses `stop` and other invocation overrides and synchronous calls, and it never retries. | `test_gemini_gateway_attacks.py::test_agent_chat_model_has_no_hidden_retry_and_forbids_invocation_overrides` | Not wired to the coordinator yet | none yet |

## Amazon (practical AI: useful, complete application)

| Feature | Actual behaviour observed | Proof artifact | Limitation | Demo step |
|---|---|---|---|---|
| Complete scientific loop through the ordinary HTTP API | At candidate `980a25a` (application = `main` `b8c5952`):<br>- real Counterdex discovery with a certified counterexample;<br>- changed input gives fresh identities;<br>- design needs a separate approval, and the checked fixed-pair separation is confirmed by an independent decimal oracle;<br>- candidate-specific follow-ups;<br>- native download and fresh replay, with tampering rejected;<br>- cancel and restart leave no orphan processes;<br>- verified zero external model dispatch. | `evaluation/results/integration/qualification-980a25a.md`; `gates-latest.json` (exit 0) | Scientific acceptance on this Mac only. Owner 4's G0–G4 browser workflow is not established here | Owner 4's launcher → hero investigation → design → follow-up → download → replay |
| Useful abstention | A paper outside the supported model should still be reviewable. Not yet observable on `main`. Open PR #36 (Owner 4) adds PDF admission and a page review panel with an evidence map and SD/SEM/CI and approval-text warnings. In my preview, with Owner 2's unreviewed route patch, its admission handled 19 hostile assets safely, but page rendering on macOS is not memory-bounded (F-PAPER-RENDER-MEMORY, P1). | sealed H4-class variant (after the freeze); `test_paper_trust_boundaries.py` NOT_AVAILABLE | Pending Owner 4's paper path | none yet |

## Not claimed

- Live Gemini extraction quality, latency or token use. All of it is `not_run`, and nothing was dispatched.
- Live Deep Agents adaptivity, specialists or durable agent resume.
- A Peri consultation. None was performed or arranged, and nothing was messaged on anyone's behalf.
- Any statistically established productivity claim. No user was observed, so the manual-versus-assisted comparison is `not_run`.
