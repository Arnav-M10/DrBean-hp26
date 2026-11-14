# Owner2 — dark design and motion

Delivered for integration in PR49, `codex/dark-minimal-motion`, base mainaa51f16.
Works: neutral dark tokens, system type, horizontal existing step index, flatter
grouping, high-contrast controls/plots, bounded page/disclosure/event/download
motion, reduced/static fallback. No framework, model, backend or authority change.

Verified:81 web checks;10 presentation groups across320/390/834/1440px and200%
reflow; real agent/browser baseline+separate design+two native replays; preserved
manual scientific flow;16 actual private-browser checks. No provider calls.
Immediate keyboard focus exclusion after closing a disclosure is regression-tested;
preference-change cancellation is distinguished from natural animation completion.
Screenshots, contrast, exact commands and limitations: docs/design/.

Current task: Owner1 combines PR49 with access/PR47 and journey/PR48, preserving
Owner3's structure/copy and the narrow registration hooks, then tests that exact
combined commit. Safari, physical devices and live-provider qualification remain
unrun. Separate branch checks do not qualify the combined release.
