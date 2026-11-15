# Study page

A second browser front end for the same local app, served by `apps/web/serve.mjs`: a front page at
`/study/` and the study itself at `/study/app`. The page at `/` is unchanged. Start the app as usual
(`scripts/dev/launcher.py start`), then open `http://127.0.0.1:4173/study/` (or whatever web port the
launcher prints). Links to a study step, such as `/study/#data`, open the study directly.

The study uses the real API through the local proxy: the private browser session, research assets,
the general research service, datasets, problems, research sessions with their review gates, the
numerical model comparison service and the signed downloads. Nothing in the study is mocked.

## Front page

`index.html` is two screens. The first plays a saved run on the study's own chart (`chart.mjs`),
once: the readings, the curve inside the claim, the curve outside it with its exact rate set by
KaTeX, then the times to measure and the one that decides. The second shows the steps a study takes,
from your files to the report, and sends one dot of data through them the first time it is seen.
Reduced motion shows the finished picture with no movement. `home.mjs` draws both; the values come
from `home-data.mjs`, a copy of the run in `fixtures/` that `study.test.mjs` checks against those
files. The front page sends nothing to the server and opens no workspace; its buttons lead to
`/study/app`, which reopens a study saved in the browser. `logos/` holds the Gemini and LangChain
marks (CC0, see `logos/SOURCE.txt`).

## One flow for any files

1. **Data.** The person writes a question and adds up to 5 files of any field: CSV, TSV, JSON,
   text, Markdown, PDF (up to 20 pages and 25 MB) or PNG/JPEG, or pastes a table. Each file is saved as a
   research asset. `intake.mjs` reads the tables in its text, and `general.mjs` decides from the
   column names which checks fit. The overview then shows what Dr. Bean can do with the files:

   | Offered when | Path | Answer |
   | --- | --- | --- |
   | Always (needs a question) | The assistant: the general research service sends the files and question to Gemini, or to its local test responder | A summary, claims with exact quotes the server compares against the files, copied tables and next steps. Never shown as checked. |
   | A table has time and concentration columns | Exact check: the research agent plans one check and Counterdex proves it | Whether the readings settle a claimed elimination rate, and which reading would |
   | A table has angle and current columns | Numerical comparison: the model comparison service fits an isotropic and a bi-Maxwellian distribution | Which fits pass the χ²ν limit, and which next setting separates them at each noise level |

   A table with unnamed columns can still be sent to a check by hand ("Use a table for a check
   anyway"). A table the assistant copied, for example from a photo or a scanned page, can start a
   check from its answer. The check page then asks for every value to be compared with the file.
2. **Approval.** Each path shows exactly what will run. The assistant's page lists the question,
   the files, the model and the size, and sends nothing until the person ticks the consent box.
3. **Answer.** The assistant's answer, the checked result or the comparison, each with its files.
4. **Next step.** The assistant's suggestions and the checks its files allow, the next
   measurement for a check, or the best setting at each noise level for a comparison.

The study id is kept in `localStorage`, so a reload reopens it.

## Limits

- The assistant answers in any field, but only when the server owner has enabled Gemini (or the
  test responder, `BEAN_GENERAL_ANALYSIS_MODE=controlled_demo`, which restates files and never
  calls a provider). Its answers are AI readings, not checks.
- Checked answers exist for two models so far: the two-rate concentration curve (claim on the
  elimination rate, exact) and the isotropic versus bi-Maxwellian electron comparison (numerical,
  made-up currents only, per the service contract).
- Excel files are not read. Save them as CSV.
- Live model runs were not part of testing.
- Browsers share cookies across ports, so two copies of the app on 127.0.0.1 (say ports 4173 and
  28170) clear each other's private session. Open the second copy in a private window. One copy
  serving both `/` and `/study/` shares a single session and has no such problem.

## Files

| File | What it does |
| --- | --- |
| `app.html`, `styles.css` | The study page and its styles (dark, one accent) |
| `index.html`, `home.css`, `home.mjs`, `home-data.mjs`, `logos/` | The front page, its layout and motion, the saved run it plays, and two service logos |
| `app.mjs` | Files and question, the overview, routing, and the exact-check steps |
| `general-app.mjs`, `general.mjs` | The assistant's steps, and which checks a table fits |
| `compare-app.mjs`, `compare.mjs` | The electron-current steps, and the request, checks and wording behind them |
| `intake.mjs` | Tables from any text, column guesses, exact unit conversion |
| `results.mjs`, `chart.mjs` | The exact check's files read into answers, tables, charts and the readable report |
| `channel-chart.mjs` | Currents by collector setting, in the same style |
| `math.mjs` | Symbols and formulas through KaTeX |
| `ui.mjs` | Status lines, error wording and downloads shared by every path |
| `fonts/`, `vendor/katex/` | Self-hosted fonts and KaTeX; `SOURCE.txt` in each says where they came from |
| `fixtures/` | Files from a real run of the app on the sample, used by `study.test.mjs` |

`node --test` in `apps/web` runs `study.test.mjs` with the other web tests; `serve.test.mjs` and
`share-gateway.test.mjs` cover the `/study/` and `/study/app` routes.
