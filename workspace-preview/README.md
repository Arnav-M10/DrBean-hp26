# Dr. Bean workspace preview

A local, interactive frontend mockup of the workflow agreed in `../DR_BEAN_WORKFLOW.md`. No dependencies or build step.

Start from this directory:

```sh
python3 -m http.server 4190 --bind 127.0.0.1
```

Open http://127.0.0.1:4190/ and select **Use this sample**. Edit inputs, jump directly to Review, inspect the saved sample result, and select **Plan next measurement**.

## Boundaries

- This preview never calls the scientific API or changes the working app.
- Drafts persist only in memory for the current tab; reloading resets them.
- Review buttons demonstrate approval interactions but do not grant backend approval or start jobs.
- Results are explicitly labeled as a saved synthetic repository example, independent of any draft edits. Curves are approximate displays of its fixed parameter vectors.
- Next-measurement values are editable sample assumptions, not computed recommendations. No design result is fabricated.
- The source fixture path, source commit, exact candidate values, and retained artifact hash are in `reference.json` and exposed in the Evidence view.

## Validation

`node --check app.mjs` passes. A browser walkthrough verified editing and route persistence, direct Review access, invalid claim rejection, separate comparison review, and no-execution disclosures. The standard sample fits at 1366×768; the 390×844 layout permits vertical scrolling without page-width overflow. No browser console errors were observed.

The working application remains at http://127.0.0.1:4173/.
