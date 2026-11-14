# Study page

A second browser front end for the same local app, served at `/study/` by `apps/web/serve.mjs`.
The page at `/` is unchanged. Start the app as usual (`scripts/dev/launcher.py start`), then open
`http://127.0.0.1:4173/study/` (or whatever web port the launcher prints).

It uses the real API through the local proxy: the private browser session, uploaded research
assets, datasets, problems, research sessions with their review gates, the numerical model
comparison service and the signed downloads. Nothing on the page is mocked.

The start screen asks what the readings are. Each kind goes through the same four steps:

| Kind | Server work | Answer |
| --- | --- | --- |
| Drug concentration over time | Research agent plans one check; Counterdex checks it exactly | Whether the readings settle a claimed elimination rate, and which reading would |
| Electron currents at a collector | The model comparison service fits an isotropic and a bi-Maxwellian distribution (`docs/science/MODEL_COMPARISON_SERVICE.md`) | Which fits pass your χ²ν limit, and which next setting separates the two fits at each noise level |

## What a person does (concentration)

1. **Data and claim.** Drop a CSV, TSV, JSON, text, Markdown or PDF file (up to 10 pages, 5 MB),
   paste a table, type readings or use the sample. The file is saved as a research asset.
   `intake.mjs` finds the tables in it (for a PDF, in each page's text layer), guesses which
   column is time, concentration and allowance, and shows the guess for the person to correct.
   Minutes, days, ng/mL, µg/mL and µg/L convert to hours and mg/L as exact fractions. A column
   that looks like a standard deviation is pointed out and never used as an allowance.
2. **Check.** The research agent prepares one plan. The page shows it and nothing runs until the
   person approves it.
3. **Result.** The report and the native files are downloaded with their SHA-256 checked and
   shown three ways: the answer with its chart, reading by reading, and the files themselves.
   A readable HTML report can be downloaded.
4. **Next measurement.** The person gives possible times and an allowance; the agent prepares a
   separate comparison, the person approves it, and the page says which one reading can tell the
   two curves apart.

The study id is kept in `localStorage`, so a reload reopens the study.

## Electron currents

1. **Data and models.** The same intake reads angle, energy window, current and σ columns
   (A, mA, µA or nA, converted to A as exact decimal strings). The person confirms the currents
   are made up, says how, and can change the instrument, the fit grid, the noise levels and the
   settings to compare next.
2. **Comparison.** The page shows the complete `DB-MODEL-COMPARISON-1` request. Approving sends
   that exact request once through the trusted connector, `/comparison-api.mjs`.
3. **Result.** Both fits with χ²ν and whether each passes, current by current residuals, the
   numerical export (checked against its record before saving) and the service's limitations.
4. **Next measurement.** For each noise level, the setting with the widest gap between the two
   fitted bands, and how often simulated readings landed only in their own model's band.

## Limits

- Two kinds of study, one model each: the two-rate concentration curve (claim on the
  elimination rate) and the isotropic versus bi-Maxwellian electron comparison.
- The electron comparison accepts made-up currents only (the service contract), and its fits
  and simulations are numerical, not exact proofs.
- Scanned images and photos need the AI reader, which is off here; the page says so.
- Excel files are not read. Save them as CSV.
- Live model runs were not part of testing.
- Browsers share cookies across ports, so two copies of the app on 127.0.0.1 (say ports 4173 and
  28170) clear each other's private session. Open the second copy in a private window. One copy
  serving both `/` and `/study/` shares a single session and has no such problem.

## Files

| File | What it does |
| --- | --- |
| `index.html`, `styles.css` | The page and its styles (dark, one accent for the second curve) |
| `app.mjs` | Talks to the API and runs the four steps for concentration studies |
| `compare-app.mjs`, `compare.mjs` | The electron-current steps, and the request building, checks and wording behind them |
| `channel-chart.mjs` | Currents by collector setting, in the same style as the concentration chart |
| `ui.mjs` | Status lines, error wording and downloads shared by both kinds |
| `intake.mjs` | Tables from any text, column guesses, exact unit conversion |
| `results.mjs` | Reads the downloaded files into the answer, the tables and the readable report |
| `chart.mjs` | The concentration chart, shared by the page and the report |
| `math.mjs` | Symbols and formulas through KaTeX |
| `fonts/`, `vendor/katex/` | Self-hosted fonts and KaTeX; `SOURCE.txt` in each says where they came from |
| `fixtures/` | Files from a real run of the app on the sample, used by `study.test.mjs` |

`node --test` in `apps/web` runs `study.test.mjs` with the other web tests; `serve.test.mjs`
covers the `/study/` route.
