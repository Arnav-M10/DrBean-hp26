# Dr. Bean preferred research workspace

The preferred entry now connects to the existing Deep Agents coordinator through
the ordinary trusted same-origin server. Private cookie access, reviewed exact
inputs, canonical scientific approvals, worker execution and retained evidence
reuse the existing application modules. No browser keys or bearer-token fields.

## Connected research walkthrough (controlled mode)

From a clean checkout with uv and Node 20+:

```sh
scripts/dev/setup.sh
BEAN_AI_MODE=placeholder BEAN_RESEARCH_MODE=controlled scripts/dev/start.sh
```

Open **http://127.0.0.1:4173/workspace-preview/** (or append `/workspace-preview/`
to the printed web origin). Keep the trailing slash. The qualified manual UI stays
at `/`; numerical plasma comparison stays available through its own rail link.

1. Import your CSV with the exact header `time,concentration,epsilon`, or type
   readings. Specify the experiment, elapsed-time origin and actual/transcribed/
   synthetic origin. Imported originals remain alongside corrected values. Units
   are hours and mg/L; epsilon is a deterministic hard allowance, not a noise SD.
   The optional synthetic example only fills inputs; it never supplies candidates.
2. In **Research question**, review the question, model/parameter bounds, closed
   elimination-rate claim and allowance assumptions. Optional future times and
   bounds can be supplied for later design. Tick the input review and choose
   **Start reviewed investigation**. This requests the real maintained agent plan.
3. In **Plan & review**, inspect the persisted plan, public activity and exact
   proposed scientific scope. Tick that separate review and approve. This queues
   the actual Counterdex worker. Results open automatically when retained evidence
   is ready. No percentage progress or hidden reasoning is invented.
4. Read the question, finding, conditional meaning, uncertainty and next step.
   Decimal summaries carry units; exact records are in details. Download the
   standalone readable HTML, canonical research JSON, native packet and matching
   anchors. Native replay uses CPython 3.11 and the installed checker:
   `python -m counterdex replay-native packet.json --anchors anchors.json`.
5. **Plan next measurement for separate review** asks the agent to use the retained
   evidence. A supported pair gets its own canonical design approval. An unresolved
   outcome asks for clarification instead. Investigation approval never approves design.
6. Refresh/reopen restores the same private session and its evidence. Read-only
   polling never redispatches. An uncertain mutation exposes an explicit retry of
   the frozen body/key. Expired private access requires recovery or an explicitly
   different workspace; histories and approvals are not transferred.

Controlled mode is an offline policy driving the real Deep Agents/worker path.
It is **not live Gemini qualification**. A configured live server shows its exact
provider disclosure and existing capacity; consent does not grant an allocation.
Unknown attempts/quota stop safely. No browser refill or credential controls exist.
Claude owns all live calls. No backend restart/recovery qualification is claimed
from these frontend checks. New recovery/report additions are owned by PR60;
older servers honestly show unavailable commentary or operator recovery.

The current science path is the maintained two-rate concentration investigation
and separate checked pair design. Observation ingestion, arbitrary file/model
registration and unsupported operations remain unavailable. Numerical model fits
are a separate workflow, never exact Counterdex certificates.

The preserved numerical plasma comparison is `/workspace-preview/comparison.html`
on the same web origin. It uses the numerical owner's private-session transport
and exact `DB-MODEL-COMPARISON-1` request/result contracts. No provider calls.

## Numerical plasma comparison walkthrough

From a clean checkout with uv and Node 20+:

```sh
scripts/dev/setup.sh
scripts/dev/start.sh
```

Open `http://127.0.0.1:4173/workspace-preview/comparison.html` (or the web origin
printed by the launcher plus `/workspace-preview/comparison.html`).

1. Choose **Use synthetic plasma example**. Review the newly generated currents,
   units, selected channel geometry and the two model-family explanations.
2. Open **Assumptions**: instrument area/efficiency, density bounds, discrete
   temperature grid, fit cap, per-observation Gaussian noise, sweep σ/z, Monte
   Carlo scope and feasible measurement settings. Inputs persist across views.
3. Open **Review**, inspect the exact request and tick the explicit approval.
   **Approve and compare** performs the one permitted request. The actual bounded
   computation runs synchronously; Results opens automatically on return.
4. Inspect Summary, Residuals, Sensitivity, and Noise & next measurement. The noise
   control selects actual returned cases and starts no new computation. High noise
   may make the fitted predictions indistinguishable. It never proves model truth.
5. **Download readable report** produces standalone HTML containing the question,
   origin, assumptions, plots/tables, every returned noise/MC case, limitations,
   methods and provenance. **Server JSON** downloads the byte/binding-checked
   immutable export. Provenance is also available separately.
6. Revise a current and compare again after a fresh review. Earlier evidence is
   retained in the private-workspace result selector. Identical retained requests
   reopen without computation. Failed/unsupported/budget outcomes stay honest.

CSV input supports `channel_id,current_A,sigma_A`, up to 64 rows / 128 KiB, on
explicitly reviewed channel geometry. Origin is cleared on import; a person must
confirm newly generated synthetic data. Experimental/acquired observations are
unsupported in v1 and cannot be silently relabelled or processed.

The service is an idealized planar normal-energy synthetic response, not a real
instrument calibration. σ is Gaussian noise; the band-separation threshold is
2zσ. No independent instrument detection floor or hard allowance is modelled.
No queue, percentage-progress or cancellation endpoint is advertised. Closing the
page is not cancellation. Numerical JSON is not an exact Counterdex native packet.

## Standalone static draft and saved mockup

```sh
python3 -m http.server 4190 --bind 127.0.0.1 --directory workspace-preview
```

The direct static research page is visibly **Static sample / draft mode** and
cannot compute. `/comparison.html` retains the numerical draft. Its committed
manifest is unavailable. Only the ordinary trusted server supplies the fixed
private-session connection module. The public request fixture is input only.

`saved-example.html` retains the earlier concentration mockup with its original
explicit saved-result labels, app/style and reference provenance. It opens in a
separate tab and is never used as a failed-calculation fallback.

## Checks and evidence

```sh
node --test workspace-preview/tests/*.test.mjs
node --test apps/web/*.test.mjs
PLAYWRIGHT_MODULE=/absolute/path/to/pinned/playwright \
  CHROMIUM_PATH=/path/to/chromium node workspace-preview/check-connected.mjs
PLAYWRIGHT_MODULE=/absolute/path/to/pinned/playwright \
  CHROMIUM_PATH=/path/to/chromium node workspace-preview/check-static-research.mjs
PLAYWRIGHT_MODULE=/absolute/path/to/pinned/playwright \
  CHROMIUM_PATH=/path/to/chromium node workspace-preview/check-research.mjs
```

The browser runner starts its own ordinary launcher, API, worker, private proxy
and actual numerical subprocess on dynamic ports with temporary stores. It
separates static drafting, real computation and the deliberately injected
transport-failure control. Existing services/credentials/data are untouched.
Receipts and full saved reports are under ignored `var/model-comparison/`.
Selected screenshots/qualification notes are in `docs/frontend/model-comparison/`.

The preferred-research runner uses its own temporary stores and dynamic ports.
The ordinary controlled launcher lane is distinct from the explicitly injected
post-science model-failure deployment. Both use real scientific children and fresh
native replay. No provider is contacted. Receipts are written under ignored
`var/test-evidence/preferred-research/`; selected evidence and exact tested commits
are recorded in `docs/frontend/preferred-research/`.
