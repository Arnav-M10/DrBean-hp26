# Dark workspace and interaction motion — Owner 2

Branch `codex/dark-minimal-motion`, based on current main `aa51f16`.
Owner 2 writes global CSS, chart colors and the motion module. Owner 3 retains
shell/navigation/form composition; Owner 4 retains copy; Owner 1 integrates.
Registration changes are a separate, narrow patch: dark meta, motion module
script and its existing static-server allowlist entry. No application/authority
behavior changes, new dependency, external font or provider request.

## Direction

A quiet working document, with a compact horizontal step index and a clear
reading column. Replace the light lab-notebook/serif/colored-rail treatment with
neutral dark surfaces and one system sans family. Actual tables and scientific
plots carry the visual interest. Use separators instead of nested outlined cards.
Preserve the task sequence, exact values, controls and all scientific caveats.

| Token | Value / purpose |
|---|---|
| `--paper` | `#151619`, page |
| `--surface` | `#1c1e22`, selected/raised context |
| `--sunken` | `#23262b`, editable/data surfaces |
| `--ink`, `--ink-2`, `--ink-3` | `#f0f1f3`, `#c2c5cc`, `#a0a5b0` |
| `--rule`, `--rule-strong` | `#363a42`, `#737984`; controls use the stronger rule |
| `--act`, `--focus` | `#b8cdf0`, `#b8cdf0`; links/selection/focus |
| Type | platform system sans; 16px body, 20px section, 32px page; data tabular |
| Plots | blue, amber, teal, violet; solid/dashed identity and text labels retained |

## Motion contract

The focal interaction is moving through a reviewed study: the incoming page
moves a few pixels in the direction of travel while the old page is hidden
immediately. Focus stays with the application's existing heading logic. No
outgoing clone, screenshot overlay or focusable ghost page.

- Controls:120ms color/press feedback, no delayed hit targets.
- Pages:220ms, `cubic-bezier(.2,.8,.2,1)`, cancel on another navigation.
- Native details:220ms intrinsic-size opening transition where supported; native
  instant fallback elsewhere. Closing is immediate: delaying native content
  visibility keeps controls keyboard-focusable, so no closing transition is used.
- Real result charts:one restrained opacity reveal per distinct result geometry;
  no interpolation of scientific values or animated counters.
- Activity:optional `data-motion-stream="session-id"` and
  `data-motion-event="event-id"` hooks. Only newly observed real events animate;
  rebuilding/polling the same list does not replay it.
- Confirmed downloads:optional `bean:download-ready` event with
  `detail.target` equal to the originating button, emitted only after a successful
  authenticated download. It is visual acknowledgement, never scientific authority.
- Reduced motion:instant state changes, retained focus/selection/status feedback.
  Preference changes cancel running animations; no scroll/page-load choreography.

Motion observes DOM only. It cannot fetch, poll, approve, dispatch, retry,
read credentials or change application/scientific state.

## References and verification

Read [Anthropic frontend-design](https://github.com/anthropics/skills/tree/main/skills/frontend-design)
and [webapp-testing](https://github.com/anthropics/skills/tree/main/skills/webapp-testing),
[Vercel Web Interface Guidelines](https://github.com/vercel-labs/web-interface-guidelines),
and [Impeccable4.9.1](https://github.com/pbakaus/impeccable) craft-floor, Operate,
animate, adapt, typeset, quieter, harden, polish, audit and optimize guidance.
Use compatible plain-browser guidance; no framework migration. Impeccable's
context/detector binary was not installed/run. The [Apple motion reference](https://developer.apple.com/design/human-interface-guidelines/motion)
was requested but network policy refused its host; retrieval is not claimed.

## Observed verification and reproduction

[PR49](https://github.com/Arnav-M10/DrBean-hp26/pull/49) records exact tested SHA
and CI. Local prepared runtimes: backend3.12.14, engine3.11.18, Chromium and pinned
Playwright1.63. No model requests. Existing test predicates remain unchanged.

```sh
node --test apps/web/*.test.mjs
NODE_PATH="$PWD/tests/integration/node_modules" CHROMIUM_PATH=/usr/bin/chromium \
  node apps/web/check-motion.mjs
BEAN_DESIGN_CAPTURE_DIR="$PWD/var/design-evidence/science" \
  NODE_PATH="$PWD/tests/integration/node_modules" CHROMIUM_PATH=/usr/bin/chromium \
  node apps/web/check-research.mjs
BEAN_DESIGN_CAPTURE_DIR="$PWD/var/design-evidence/science" \
  NODE_PATH="$PWD/tests/integration/node_modules" CHROMIUM_PATH=/usr/bin/chromium \
  BEAN_COUNTERDEX_PYTHON="$PWD/.venv-engine/bin/python" \
  BEAN_COUNTERDEX_REPLAY_PYTHON="$PWD/.venv-engine/bin/python" \
  node apps/web/check-backend.mjs
NODE_PATH="$PWD/tests/integration/node_modules" CHROMIUM_PATH=/usr/bin/chromium \
  node tests/integration/shared-session-browser.mjs
```

-81 web checks pass. Design runner10 grouped checks pass at320/390/834/1440px:
  keyboard focus, validation, long CSV names/values, native disclosures, rapid
  navigation and Back/Forward,200% CSS zoom/reflow, empty/unavailable states,
  preference changes, activity deduplication and response-only download feedback.
  The immediate-Tab close regression explicitly checks a focusable child with no
  post-close delay, including repeated rapid reopening/closing.
  Its API failure and hook probes are explicitly labelled presentation fixtures.
- Real launcher/browser agent path7 checks passes: two separate approvals,
  actual baseline/design, both native downloads and fresh installed-engine replay.
- Preserved manual browser path passes: changed input, real discoveries,
  separately approved positive/no-separation designs, follow-up, retained native
  evidence and fresh replay. Optional screenshots run only after existing assertions.
- Actual private HTTPS/browser path16 checks passes; zero provider attempts and
  API/browser outbound requests. No session/proxy/approval/ledger changes.
- Rendered token contrast:body16.01:1; secondary9.66; helper6.76;
  placeholder/disabled6.15; semantic text6.94–8.69; focus11.23;
  control borders3.81; plot lines8.47–9.98 on raised surfaces.
- Chromium layout CPU across each scripted viewport's interactions/captures:
  totals are recorded per viewport in the presentation receipt. These are local
  observations, not a cross-device frame-rate or Core Web Vitals claim. Motion module is5.7KB source,
  no request/dependency/font imports and no permanent animation loop.

The checks found and fixed a genuinely overflowing absolutely positioned screen
reader label inside the narrow table, and preserved secondary step links needed
by the manual path. They do not hide overflowing scientific data or weaken tests.
Owner1's review also caught focusable children during the native closing transition;
the final opening-only rule and immediate-Tab regression resolve that defect.

Selected before/after/real-result captures and receipts: [evidence](evidence/README.md).
Other captures remain under ignored `var/design-evidence/`. Screenshots are review
evidence, not pixel-locked regression goldens. No live/scientific release claim.

## Integration boundary and limits

Owner1 integrates this design PR with automatic access/PR47 and journey/PR48,
preserving Owner3's copy/structure and the small registered hooks. Retest the
actual resulting tree; separate branch passes are not combined acceptance.
Only study/result appearance and motion are owned here. No unrelated branches
were merged. No physical phone, Safari/WebKit, screen-reader session or live
Gemini qualification was run. Engines without intrinsic-size disclosure animation
use normal instant details; missing WAAPI leaves navigation/content operational.
Optional `BEAN_DESIGN_RECORD_VIDEO=1` needs the pinned Playwright ffmpeg binary;
normal design acceptance and screenshots do not require it.
