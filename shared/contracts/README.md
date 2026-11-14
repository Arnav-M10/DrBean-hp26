# Shared application contract

The authoritative models are `apps/api/bean_api/contracts.py`, with incomplete conversation output models in `apps/api/bean_api/conversation.py`. Generate the browser-facing Draft 2020-12 JSON Schemas and synthetic examples with:

```sh
.venv/bin/python scripts/export_contracts.py
```

`DB-SC-1` names the wire and canonical identity profile. `GF-2` names the separately enforced operational policy. All objects reject unknown fields. JSON Schema consumers must also send requests to the server for ownership, exact arithmetic, source locator, and transaction validation; passing a schema does not confer approval or verification.

The API owner owns application DTOs, provider consent, source provenance and lifecycle records. Scientific domain, candidate, horizon, verification and design fields are a proposed integration boundary for Owner01 review. The default adapter is explicitly unavailable. These schemas do not constitute a qualified scientific checker or a promise of live Gemini access.

Provider output and persisted client records have separate schemas. `IntakeProposalBody` is the structured Gemini output and rejects server metadata. The returned immutable record's `body` uses `IntakeProposalRecordBody`, which adds the server-bound `provider_attempt_id` and `review_state: "unaccepted"`. `AssistantOutput` is the model's explanation and optional incomplete draft; the actual returned record's `body` uses `AssistantResponseRecordBody`, including server-owned facts, critical statements, source references, authorship, proposal links, and failure information. Its nested proposal is an `AssistantProposalRecord` with an `AssistantProposalRecordBody`. The service validates these persisted bodies before writing them. Optional fields remain omitted when that response branch does not use them; metadata never becomes model authority.

## Exact bytes and identities

Scientific scalars are reduced rational **strings**, including integer values such as `1/1`. Historical per-row allowances and inclusion flags remain independent fields. An excluded row is preserved and validated. The explicit decimal parser retains conversion precision; callers retain the original spelling separately. Binary floats and booleans are rejected in rational fields.

The server is the sole identity authority. `canonical.py` validates ASCII object keys, Unicode scalar strings, sorted object keys, ordered arrays, minimal escaping and UTF-8. It rejects duplicate keys, floats, nonfinite numbers, negative integer counters including `-0`, unpaired surrogates, and counters above `9007199254740991`. Raw JSON is limited to 1 MiB and 32 nested levels; rational numerator/denominator lengths are limited to 256 digits and decimal exponents to magnitude 128. These are application admission limits.

Every field in the fully validated `model_dump(mode="json")` semantic body, including explicit defaults and null values, participates in its identity. Envelope IDs, workspace authorization and service timestamps live outside that body. Dataset row ordering, original spellings, notes, origins and ancestry are therefore preserved by dataset identities; changing any creates a distinct revision. Problem bodies bind both the immutable dataset ID and digest. Plans bind reviewed problem and scenario identities, budget, tools, provider disclosure and ancestry. Design requests bind selected historical evidence, exact candidate vectors, feasible times, allowance and construction limits. Do not add the identity's own digest to its hashed body.

The hash input is `dr-bean:<kind>:v1`, one LF byte, then canonical bytes. Admitted kinds are `dataset`, `problem`, `plan`, `design-request`, `suggestion`, and `report`. Other opaque entities use separate operational identifiers and byte digests. Existing historical engine identities are neither imported nor rewritten. Source and downloadable artifact SHA-256 values hash the exact file bytes separately.

`DB-SC-1/fixtures/canonical-golden.json` contains literal expected bytes, including astral Unicode, combining characters, control escapes, U+2028/U+2029, large rational text and array-order controls. The server implementation is tested against these bytes. A browser must not create an alternative authoritative canonicalizer or embed raw canonical JSON directly into HTML script source.

## Review and evidence boundaries

Source upload supports one PNG/JPEG, at most 5 MiB and 12 megapixels. Upload alone never authorizes provider transmission. `ProviderConsent` identifies the exact image, notes and existing field context; `AgentProviderConsent` separately identifies a reviewed problem and scientific context. Scientific `ApprovalRequest` is yet another explicit transition. An intake candidate, conversation interpretation or typed "yes" cannot create an approval.

Intake fields preserve original spellings, candidate exact values, source locators and unresolved issues. Visual transcription defaults to `unreviewed_visual`; a quote matching the model's own text does not authenticate pixels. Review corrections preserve their reason and source category. Unresolved fields block scientific plan construction.

`ScientificResult` separates outcome, verification, expected binding and replay. A valid flag requires a named `VerificationRecord` attached to an artifact digest; the workflow additionally checks the externally expected scenario identity. Only the trusted adapter may supply these records. A well-formed imported record cannot authenticate itself. Checked pair separation additionally requires a positive exact margin, a named pair, an explicit positive future allowance and passed native replay. Zero margin does not qualify.

`synthetic-workflow.json` is a transcription/schema fixture only: its proposed domain and candidate vectors assert no fit, witness, compatibility, proof or separating measurement. `http-exchanges.json` illustrates success, idempotent retries and recoverable errors without credentials or real approval capabilities. Replace synthetic envelope IDs with actual creation responses when exercising the API.
