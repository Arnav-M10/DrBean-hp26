# Source intake integration contract

Owner 2 integration branch: `backend/source-handoff`, based on main `2d2993d`.
Reuses PR #20's `c20d849` intake contract and Owner 3's existing
`ControlledSourceProposer`; proposal generation stays owned by Owner 3.
Owner 4 can consume these routes without a database edit or provider consent.

All paths below start with `/api/bean/v1`; authenticated mutations require a
stable `Idempotency-Key`. Records have `id`, `workspace_id`, `kind`, `digest`,
and `body`. Retain those returned identities rather than reconstructing them.

1. Upload PNG/JPEG bytes to `POST /workspaces/{wid}/source-assets?origin=synthetic&retention=retain`.
2. Read `/capabilities.source_intake`. Controlled intake requires server-side
   `BEAN_SOURCE_INTAKE_MODE=controlled` and an explicit
   `BEAN_CONTROLLED_SOURCE_MANIFEST` pointing to the trusted local manifest.
   Default is disabled. A request cannot supply a manifest or enable a provider.
3. `POST /workspaces/{wid}/intake-proposals` with
   `{"execution_mode":"controlled","source_id":"<asset id>","expected_source_digest":"<asset body.sha256>"}`.
   Optional `current_revision_id`, `existing_values`, and `notes` provide bounded
   review context. The additive `ControlledIntakeRequest` schema is authoritative.
   Response is an `intake_proposal` whose body follows
   `ControlledIntakeProposalRecordBody`: `authorship=controlled_fixture`,
   `execution_mode=controlled`, source/revision identity, fields, diagnostics,
   conflicts, and fixture/prompt/context/local-attempt provenance. There is no
   `provider_attempt_id`. Display its controlled-example label.
   The server also captures `input_context.current_dataset_id` and
   `input_context.current_problem_id`, including null heads. Both must still
   match at new review and materialization; clients need not supply this field.
   Older controlled proposals without a snapshot remain readable but require
   a newly prepared proposal before a new acceptance.
4. Unknown, changed/reencoded, unreadable, or unsupported bytes produce
   `status=unavailable`, empty fields, and `next_action=manual_review`. Preserve
   existing inputs and offer ordinary manual entry; do not fill fixture values.
5. Review every field through
   `POST /workspaces/{wid}/intake-proposals/{pid}/review` with
   `expected_proposal_digest`, `reviewed_fields`, and `resolved_diagnostics`.
   Each field supplies `field_path`, `value`, and `origin`; corrections,
   assumptions, and blocking diagnostics require `correction_reason`.
   Reviewed originals remain attached to each accepted field. Proposal/review
   records stay immutable and neither grants scientific approval.
6. `POST /workspaces/{wid}/intake-reviews/{rid}/materialize` with
   `expected_review_digest`, `dataset`, `problem`, and `human_assumptions`.
   See `MaterializeIntakeRequest`. Every scientific input absent from the review
   needs an explicit assumption keyed by its canonical field path. Response
   contains immutable `dataset`, `problem`, and `materialization` records with
   exact digests and field provenance; `execution_approved=false`.
7. Prepare an ordinary plan using the returned problem/dataset identities,
   separately approve that exact scope, then start it. Design and follow-up keep
   their existing separate review/approval routes. Materialization never starts
   work or consumes a scientific allowance.

Same-key identical retries return the saved result; changed payloads conflict.
Uncertain/interrupted attempts require reconciliation, never silent redispatch.
Materializing the same review under another key returns its original association;
different accepted inputs require a new review. Stale proposal/review digests,
workspace/source mismatches, and stale revision context are rejected.
Controlled sources stay synthetic; no live Gemini qualification is asserted.

Generated additive schemas live in `shared/contracts/DB-SC-1`; legacy intake
schema meanings remain unchanged. Owner 2 owns intake/config/routes/contracts
and materialization edits here. Owner 3 owns provider/coordinator logic; Owner 4
owns browser edits; Claude owns independent acceptance and findings.
