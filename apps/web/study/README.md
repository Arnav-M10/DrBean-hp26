# Study page

A second browser front end for the same local app, served at `/study/` by `apps/web/serve.mjs`.
The page at `/` is unchanged. Start the app as usual (`scripts/dev/launcher.py start`), then open
`http://127.0.0.1:4173/study/` (or whatever web port the launcher prints).

It uses the real API through the local proxy: the private browser session, uploaded research
assets, datasets, problems, research sessions with their review gates, and the signed artifact
downloads. Nothing on the page is mocked.

## What a person does

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

## Limits

- One model: the two-rate concentration curve, with the claim on the elimination rate.
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
| `app.mjs` | Talks to the API and runs the four steps |
| `intake.mjs` | Tables from any text, column guesses, exact unit conversion |
| `results.mjs` | Reads the downloaded files into the answer, the tables and the readable report |
| `chart.mjs` | The concentration chart, shared by the page and the report |
| `math.mjs` | Symbols and formulas through KaTeX |
| `fonts/`, `vendor/katex/` | Self-hosted fonts and KaTeX; `SOURCE.txt` in each says where they came from |
| `fixtures/` | Files from a real run of the app on the sample, used by `study.test.mjs` |

`node --test` in `apps/web` runs `study.test.mjs` with the other web tests; `serve.test.mjs`
covers the `/study/` route.
