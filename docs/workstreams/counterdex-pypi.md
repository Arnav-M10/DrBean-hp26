# Counterdex 0.3.0 publication

The user requested publication of the complete current Counterdex library and
an update to the earlier PyPI project. This release starts from main `b60e9d9`;
scientific Python files and all current/archived fixture bytes are unchanged.
The exact source identity remains
`90b42ae505c9a7c25103331f447edc2e15026d291374f6beefd0ef89c23b7bf8`.

The scientific distribution is `counterdex==0.3.0`: import and CLI `counterdex`,
CPython3.11, no runtime dependencies. Its metadata now has project links,
keywords and scientific/Python classifiers. Its public README documents current
candidate discovery, checked/numerical pair design, own-condition fixed-candidate
follow-up, native replay, actual APIs and scientific limits. Source-pinned example
URLs and the installed Python example were exercised. Application/backend/Deep
Agents components are not bundled into the scientific distribution.

`packages/groundwork_redirect` builds a separate `groundwork-adapter==0.3.0`
migration distribution depending exactly on `counterdex==0.3.0`. It installs no
old import namespace and documents the explicit import/command migration. Publish
Counterdex first, then this migration release. The version-specific0.1.0 page and
its bytes remain historical; a new release updates the old project's latest page.
No license grant was invented.

Executed distribution checks:

- Both wheel/source pairs built with CPython3.11 and passed `twine check`.
- Fresh wheel installation outside the checkout:292 engine tests ran,290 passed,
  two initially skipped for external API dependencies/installed-supervisor setup.
- The installed-supervisor lane was then explicitly configured:13/13 passed.
- The API-runtime schema check separately validated8 requests and8 results.
- Eight native baseline/design/follow-up packets freshly replayed with matching
  external anchors, retaining their scientific outcomes; README Python replay
  returned valid/matches/passed and certified_counterexample.
- All24 installed scientific source files match the repository byte-for-byte;
  Counterdex has no runtime dependencies. The migration dependency resolves to0.3.0.
- Wheel namespaces and sdist docs/tests/scripts/current+archived fixture bytes
  checked; `pip check` and Node canonical-byte control passed.

Built artifacts and retained local evidence:
`/Users/arnav/Documents/HackPrinceton/Counterdex-PyPI-Release-0.3.0/`.
Publication requires a successful authenticated PyPI upload; passing build checks
or merging this source change does not claim an upload occurred. No model-provider
calls or application credential inspection is involved.
