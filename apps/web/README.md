# Dr. Bean web workspace

This local frontend is the first slice of the researcher workflow. It supports CSV and manual measurement entry, exact rational validation, review of a two-rate model question, and JSON draft download.

## Run locally

From `apps/web`, run `node serve.mjs` and open `http://127.0.0.1:4173`. Run `node --test` for parser, measurement, and question validation tests. The preview has no install step.

To exercise the draft workflow, load the synthetic example, review the measurements, then enter the bounds and origin of the hard allowances. For a local UI exercise, use scale `[1, 12]` mg/L, elimination rate `[1/10, 0.3]` h⁻¹, absorption rate `[1/2, 2]` h⁻¹, and target interval `[0.10, 17/100]` h⁻¹. The example uses a team-chosen hard allowance of `0.1` mg/L. Open the exact values disclosure in Review and download the draft if you want to keep the input strings and source provenance. Draft editing is tab-local. The JSON download is a record of the inputs and the editor currently has no JSON reopen action.

## Integration handoff

The verified `Arnav-M10/DrBean-hp26` remote had no branches or tags when cloned. The frontend is dependency-free and lives entirely under `apps/web`. The supplied work order included the shared GF-2 and DB-SC-1 contract. The separate planning documents and inspected source baselines were unavailable locally.

Owner 02 can unblock the first end-to-end slice by making the selected backend and runtime-validated client available for capabilities, manual input, plan, approval, and run retrieval. Owner 01 can then supply a real scenario artifact for the provider-free end-to-end test. This preview creates no approval, run, evidence, design job, or report records. Once those interfaces exist, the separate design approval and Gemini integration can bind to the actual investigation identities.
