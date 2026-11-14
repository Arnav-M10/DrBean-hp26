# Numerical comparison frontend handoff

Frontend: PR55 / `codex/model-comparison-ui`; numerical owner: merged PR57.
Use the authoritative [private connection](MODEL_COMPARISON_CONNECTION.md),
[service contract](../science/MODEL_COMPARISON_SERVICE.md) and
[physics/scope](../science/MODEL_COMPARISON_PHYSICS.md).

The UI checks `DB-MODEL-COMPARISON-CONNECTION-1` at its fixed same-origin manifest,
requires the exact `/comparison-api.mjs` module and `private_session` mode, then
uses the production `connectComparison()`. No visitor-entered host, token, key,
identity, permissive proxy, duplicate API or model implementation is introduced.
Default connection retries retain private continuity. New-workspace recovery is
an explicit person choice and clears retained client history/operation keys.

The exact `DB-MODEL-COMPARISON-1` request is snapshotted after input validation and
fresh review. Only the person's checked approval submits it. Changes clear that
review and immediately mark earlier results historical. The synchronous request
shows in-flight status only; no fake queue, percentage or cancellation is added.
A late response retains its own input binding and cannot overwrite a changed draft.
Identical retained requests use checked `get()` instead of computing again.
After an uncertain reply the interface requires a read of retained history;
no mutation is retried automatically and same-request operation keys are retained.

The production connector checks workspace/record/input/body/download binding.
The UI does no fitting, current prediction, derivative, Monte Carlo or grid ranking.
Plot coordinates use returned observations/predictions/residuals/derivatives;
observation/setting indices are labelled as indices, never seconds or energy.
Lines only guide the eye between sampled channels, not continuous response curves.
2zσ is display arithmetic on the returned noise assumptions, not a new simulation
or an independent instrument detection floor. Returned counts/Wilson intervals
are conditional sampling statistics, never model-truth confidence percentages.

HTML includes every returned noise case, feasible-grid and conditional-simulation
result, methods, limitations and original reviewed inputs. Server JSON remains
the canonical supporting download; it is numerical evidence, not an exact native
Counterdex packet. Missing/unsupported/budget/failure outcomes cannot be replaced
by the saved mockup. Experimental input is blocked honestly; supported user CSV
requires an explicit newly generated synthetic origin before fresh approval.

The numerical service and scientific engine stay with their owners. The frontend
adds only its exact static files to the trusted server allowlist; proxy/session
boundaries and the original qualified application remain intact.
