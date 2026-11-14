# Dr. Bean model-comparison workspace

The preferred researcher interface is `/workspace-preview/` on the ordinary
application's web origin. It uses the numerical owner's private-session transport
and exact `DB-MODEL-COMPARISON-1` request/result contracts. No provider calls.

## Connected walkthrough

From a clean checkout with uv and Node 20+:

```sh
scripts/dev/setup.sh
scripts/dev/start.sh
```

Append `/workspace-preview/` to the printed web address (normally
`http://127.0.0.1:4173/workspace-preview/`). Keep the trailing slash.

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

The direct static page is visibly **Draft-only** and cannot compute. Its committed
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
```

The browser runner starts its own ordinary launcher, API, worker, private proxy
and actual numerical subprocess on dynamic ports with temporary stores. It
separates static drafting, real computation and the deliberately injected
transport-failure control. Existing services/credentials/data are untouched.
Receipts and full saved reports are under ignored `var/model-comparison/`.
Selected screenshots/qualification notes are in `docs/frontend/model-comparison/`.
