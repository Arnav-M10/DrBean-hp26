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
- Native details:220ms intrinsic-size transition where supported; native instant
  fallback elsewhere. Closing keeps native keyboard/visibility semantics.
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

Read Anthropic frontend-design and webapp-testing, Vercel Web Interface Guidelines,
and Impeccable4.9.1 craft-floor/Operate/animation playbooks. Use compatible plain
browser guidance; no framework migration. Impeccable context binary was not
installed/run. Apple's motion reference was requested but network policy refused
developer.apple.com; do not claim a successful retrieval.

Verification in progress: actual rendered phone/tablet/laptop/200% views, keyboard,
rapid navigation, native disclosures, reduced motion, long text, empty/error states,
ordinary launcher/science/download path, and existing web checks. Screenshots and
receipts are stored under ignored `var/design-evidence/`; final PR records exact SHA
and actual results. This design change grants no new scientific/live qualification.
