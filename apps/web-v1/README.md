# Dr. Bean front end v1 — "Research notebook"

An alternative presentation of the Dr. Bean browser app. It sits beside `apps/web` and does not replace it.
Its behaviour is the same: the server serves the shared workflow modules (`app.mjs`, `workflow.mjs`,
`research.mjs`, …) unchanged from `../web/`, so there is no second copy of the logic. v1 owns only
its presentation files: `index.html`, `styles.css`, `motion.mjs`, `story.mjs` and `figure.mjs`.

```bash
node apps/web-v1/serve.mjs            # http://127.0.0.1:4173, proxies /api to the local API like apps/web
node apps/web-v1/serve.mjs 4199       # any other port
```

Start the API and worker the usual way (`scripts/dev`). The page keeps every element ID that
`apps/web` uses, so the shared modules work without changes. If a shared module renames an ID,
update `index.html` here to match.

## Theme

The page looks like a lab notebook:
- **Paper and ink.** The background is graph paper. Each card is a ruled notebook page with a red margin line. Asides are margin notes, errors are written in red pen, and tables look like ledgers.
- **Two inks with fixed meanings.** Blue is the reference / inside the claim; red is the counterexample / outside the claim. The worked example and your own results figure use them the same way, and every curve also has a written label, so colour is never the only cue. Both inks pass the dataviz palette validator in light and dark mode.
- **Light and dark.** The page follows the system setting. Dark mode is its own set of colours, not a colour inversion.

## Motion

Motion tells the story and keeps you oriented. It is not decoration.
- **A worked example told by scrolling** (`story.mjs`). As you scroll, the readings appear on the figure, then their allowances, then two curves that both fit, then where each curve says the next reading should fall. Finally a new reading rules one curve out. The data is the engine's documented synthetic example (`DECISION_EXAMPLE.md`), and the caption says so.
- **Page turns** (`motion.mjs`). Moving between notebook pages uses the View Transitions API, and the current tab slides between positions.
- **Content appearing.** New cards and panels appear as they scroll into view, including ones the shared modules add later (found with a MutationObserver).
- **Your results figure** (`motion.mjs` + `figure.mjs`). After a run, each computed candidate's curve is drawn under the candidate table. The figure is for display only: the caption says the exact table and the evidence record are authoritative.
- **Reduced motion.** With `prefers-reduced-motion`, nothing animates: the whole worked example is shown at once and page changes are instant.

## Check

```bash
BEAN_COUNTERDEX_PYTHON=/abs/path/python3.11 node apps/web-v1/check-v1.mjs [--screens DIR]
```

The check starts the real API, worker and engine and runs Chromium against them. It covers:
- the story building step by step
- page turns using view transitions
- a real baseline run drawing one curve per candidate, with colours that follow the claim
- no horizontal overflow at 390 px
- reduced motion and dark mode
- no outside requests, and zero model-provider attempts

Exit codes: 0 passed, 1 failed, 3 unrun.
