# Owner 1 retained acceptance evidence

Actual clean application source: `f71363589ad5370cabbf99bfaf96c8a2d11e57db`
([PR #27](https://github.com/Arnav-M10/DrBean-hp26/pull/27)).
These are Owner 1 executions, not a newly authored Claude acceptance. See
[qualification and limitations](../../DECISION_LOOP_QUALIFICATION.md).

- `engine-tests.txt` and `backend-focused.txt`: exact sanitized commands,
  runtime identities, cases and results.
- `ordinary-http-summary.json`: seven executed cases with required predicates,
  exact source, immutable record identities, guard results and no diagnostics.
- `native-controls.json`: all 22 control results, with interpreter/source scope.
- `science-gate.json`: integrated harness verdict on those fresh results.
  The ordinary HTTP text summary has trailing display padding removed; numerical
  artifacts and JSON receipts preserve their recorded contents.
- `unresolved-receipt.json`, `unresolved.native.json`, `unresolved.anchors.json`:
  synthetic own-time actual-declaration control, exact discovered vectors and
  rational inputs, authenticated downloaded packet and all eight external
  anchors. The candidate stays unresolved although verification/replay pass.
- `clean-checkout.json`: unmodified retained strict-checklist JSON from a clean
  clone. `clean-checkout.txt` is the checklist portion of its stdout; dependency
  download progress is omitted. Its configured-gate verdict does not cover the
  additional review findings documented above.
- `SHA256SUMS.json`: file hashes for this evidence directory, excluding itself.

Prepare the pinned backend and matching installed Counterdex 0.3.0 under CPython
3.11.17. The HTTP harness uses `DRBEAN_BACKEND_PYTHON` and
`DRBEAN_SCIENCE_PYTHON` to select them. It was run in a sanitized environment with
new temporary results/stores, with these commands from the exact checkout:

```sh
python3.11 evaluation/cli.py run --lane offline_real_science --subject http-launch --results /path/to/new-results
python3.11 evaluation/cli.py controls --results /path/to/new-results
python3.11 evaluation/cli.py gate --require release --output /path/to/science-gate.json --results /path/to/new-results
bash scripts/release/clean_checkout.sh --strict-offline
```

The clean-clone run used `DRBEAN_RELEASE_EVIDENCE_DIR` to retain its report before
the disposable clone was removed. It installed from lock files and used pinned
Playwright 1.63 with its matching Chromium 153, not a preconfigured application
store. No real model-provider credentials entered the checks. No databases,
auth files, credential values or source images are retained here.
