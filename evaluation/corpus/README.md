# Paper corpus (Workstream 5)

This is a small, difficult corpus for qualifying the paper workflow: upload, Gemini evidence, review, Deep Agents, Counterdex and replay. Every document is reviewed by hand. The corpus is not a benchmark, and results on it are never reported as general accuracy.

## Sets

- **Development (at least 6, awaited).** Owner 4 renders the shared PDF and scan fixtures from Owner 1's canonical scientific data. When they land, Owner 5 writes gold for each one from its page renderings.
- **Held aside (4, sealed): H1–H4.** Owner 5 authored these independently of the implementation and the prompts. They are synthetic, and every page says so.
  - The files and their gold stay in `sealed/`. That directory is git-ignored, so only digests are committed: `holdouts.sealed.json`, with a commitment hash over each PDF and gold file and the two authoring scripts.
  - Together the four cover every required feature (`manifest.json`). The coverage of each individual document stays sealed.
  - They are revealed only after Owners 2–4 record a frozen implementation and prompt version. After that, an exposed holdout is regression data. It cannot support a later generalization claim.

## Gold

Gold is written by reading independent renderings, never from a model response and never from the product's own parser or conversion routine. `tools/render_pages.swift` uses Apple PDFKit to produce those renderings:

```
swift evaluation/corpus/tools/render_pages.swift paper.pdf out/ 110 needles.json
```

It writes:
- `page-NN.png`;
- each page's text layer;
- for each quoted string, every page and bounding box where it occurs.

For native-text pages, every quote in the gold must be found on its cited page, or the gold writer fails. A scan has no text layer, so its locators are page-level and confirmed by sight.

Each gold file (`drbean-paper-gold/v1`) records:
- which values really exist, with the unit as printed and the value normalized to mg/L;
- acceptable page locators;
- the expected claim kind;
- non-claims that must not become claims, allowances or readings (intervals, SDs, pooled means, graph estimates);
- unresolved ambiguities, which must be flagged and never silently resolved;
- hostile content and the authority it tries to exercise;
- absent information;
- scientific eligibility (`eligible`, `eligible_after_review` or `not_eligible`).

## Scoring

`evaluation/drbean_eval/paper_scoring.py` reports every measure as a numerator and denominator, and lists each failure:
- reading precision and coverage, kept separate, and computed both for what was offered and for what was accepted after review;
- page-locator correctness;
- citation occurrence on the cited page;
- unsupported numbers;
- ambiguity handling;
- trap violations;
- human corrections;
- eligibility.

Source occurrence, semantic support and scientific validity are kept apart. Comparisons are exact, using `Fraction` after unit normalization.

## Live subset

The live subset is predeclared in `manifest.json` and is currently `not_run`: no user-enabled live budget exists.
- **L1** must fit in one paper session.
- **L2** and **L3** run only if the user explicitly allocates more budget.

The published denominator is the number of cases that actually ran.
