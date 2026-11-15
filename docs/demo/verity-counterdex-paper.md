# Dr. Verity numerical-premise example

This fictional paper claims to prove the Riemann hypothesis. Its argument explicitly requires a false, finite numerical proposition on page 3. Dr. Bean can genuinely check that proposition with its existing concentration-model adapter. It does not check complex analysis or disprove the Riemann hypothesis.

## The document

The exact example is [`verity-riemann-study.pdf`](../../apps/web/study/fixtures/verity-riemann-study.pdf), four pages, 95,608 bytes. Its SHA-256 is `63bb064732d25880228e360d2657f0e1bfdc374f6905020d9f6a914011282c47`.

Proposition 3.1 states that every compatible parameter assignment has `ke` in the closed interval `[0.10, 0.17]` per hour. The model is

```text
C(t) = A (exp(-ke t) - exp(-ka t)), with 0 < ke < ka
A in [0.001, 30] mg/L
ke in [0.015, 0.35] per hour
ka in [0.4, 8] per hour
```

The paper declares these readings **synthetic**, with an author-chosen deterministic hard allowance of ±0.50 mg/L for each row. The allowances are neither standard deviations nor confidence intervals.

| Elapsed hours | Concentration, mg/L | Hard allowance, mg/L |
| --- | --- | --- |
| 0.25 | 4.80 | 0.50 |
| 0.50 | 7.20 | 0.50 |
| 1.00 | 8.00 | 0.50 |
| 2.00 | 6.80 | 0.50 |
| 4.00 | 5.70 | 0.50 |

The proposed transfer step and theorem explicitly require Proposition 3.1. Finding one admitted compatible assignment outside the interval refutes this numerical premise, so that proposed proof fails. The paper's separate complex-analysis claims are outside the supported checker.

## Run it

1. Open the study app and start a new study.
2. Upload this PDF **alone**. Its filename may change; its bytes must match.
3. Choose **Check the proof’s premise**.
4. The paper review opens on Proposition 3.1 and its role in the proposed proof. Expand **Review the source values and assumptions** to compare the five readings, hard allowances, claim, origin and search limits with the PDF. **Edit the numerical inputs** opens the editable model details; edits are flagged as a different study.
5. Prepare the check, then approve the real maintained plan.
6. Read the counterexample, graph and per-reading checks. The Files view contains the readable report, native evidence and replay anchors.

The displayed explanation has three parts: what the paper requires, the actual outside witness, and why the necessary premise fails. **Next step** stays within the paper review: inspect the checked assignment, download and replay evidence, and revisit the failed premise. It does not offer measurement planning or dispatch new scientific jobs. The experimental next-measurement workflow remains available for ordinary concentration studies. Uploading an ordinary document leaves the user at its overview, with no experiment selected. The concentration editor is reached by an explicit concentration check or sample choice; this paper has its own review presentation. Paper graphs use calibration time, and general concentration graphs use elapsed time without assuming a dose.

## What is prepared and what is computed

Only the input transcription and paper-context explanation are prepared. Recognition requires one PDF with the exact hash, byte count and media type. Changed files, other papers and multiple-file selections follow the ordinary workflow. This is not a claim of automatic mathematical understanding or Gemini extraction.

The prepared transcription creates the ordinary editable dataset and problem. The existing research-session routes, controlled Deep Agents coordinator, approval, worker, Counterdex discovery, exact fixed-vector verification and native replay execute normally. There is no stored successful verdict, witness or substituted scientific response in the frontend profile.

The paper-specific conclusion appears only for the original reviewed rows, domain, claim and source identity, with a valid matching counterexample and successful native replay. It uses the witness actually returned by the current worker. Editing the scientific inputs removes that paper-specific interpretation; the ordinary result still applies to the edited study.

One actual run returned `ke = 101/1016`, approximately `0.0994094` per hour, below `0.10`, while respecting every included hard bound. This is an observed result, not a fixture used to decide future outcomes. A failed, unavailable or inconclusive computation must retain its ordinary meaning.

The readable HTML report carries the paper identity, proposition, scope and actual witness. Raw scientific JSON remains the standard backend report and evidence, without an invented theorem-verification badge. Reopening this study fetches the retained PDF identity and real saved evidence.

## Verification

Run unit and web regression tests:

```sh
node --test apps/web/*.test.mjs apps/web/study/*.test.mjs
```

Run the real browser/API/worker lane against a local controlled deployment with the installed matching CPython 3.11 Counterdex environment:

```sh
PLAYWRIGHT_MODULE=/absolute/path/to/node_modules/playwright \
BEAN_VERITY_URL=http://127.0.0.1:28170/study/app \
BEAN_VERITY_ENGINE_PYTHON=/absolute/path/to/.venv-engine/bin/python \
node tests/integration/verity-counterdex-browser.mjs
```

For an uninstalled frontend development preview, `BEAN_VERITY_OVERLAY=1` serves the modified frontend modules from the current checkout while retaining the actual running API and worker. The test records whether it used an overlay or served product files.

This lane creates a private synthetic study, waits for approval, runs actual science, downloads and independently replays native evidence with the same checker implementation, verifies the saved explanation and readable report, checks desktop and phone layouts, and confirms a changed PDF with the same filename does not select the example. General assistant analysis endpoints are blocked. The coordinator must be configured as controlled, and the test requires zero physical model calls. No live Gemini qualification is implied.

Artifacts are written locally under `var/test-evidence/verity-counterdex/` and are not committed.
