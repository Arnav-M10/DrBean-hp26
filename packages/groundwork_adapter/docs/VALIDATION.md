# Counterdex validation and release handoff

Implementation is confined to `packages/groundwork_adapter/` on branch
`codex/counterdex`. The checkout remote was verified as the requested
repository. No application, web, infrastructure or root manifest files changed.
All runtime code uses the Python standard library. Build/publishing utilities
are isolated development tools, not scientific runtime dependencies.
The user confirmed permission for the work and requested an independent
implementation; all supplied example measurements are newly constructed fixtures.

## Initial published release: executed checks

Environment: CPython **3.11.17**, macOS 26.7, arm64. The initial release's complete
source suite passed **138 tests**. Command:

```sh
PYTHONPATH=packages/groundwork_adapter python3 -m unittest discover \
  -s packages/groundwork_adapter/tests -q
node packages/groundwork_adapter/tests/check_canonical.mjs
```

The Node check matches the Python DB-SC-1 golden bytes and semantic digest,
including Unicode, control escapes, array order and a large rational. It is a
fixture check, not a production browser canonicalizer. Replay tests also run a
fresh subprocess with numerical, provider and network imports blocked.

Seven complete synthetic packets and actual native replay outcomes are retained
in [the archived fixture ledger](../fixtures/archive/initial-published-release/manifest.json): numerical success, cancelled
partial grid, numerical range failure, zero-usefulness grid, checked separation,
valid checked pair without separation, and a hypothetical new datum excluding
both chosen candidates. The last case deliberately has invalid pair
compatibility and failed scientific replay; it makes no global emptiness claim.
Numerical-only records deliberately have unsupported scientific replay while
their recorded integrity is checked. None of these fixtures is a real acquired
dataset or live provider result.

Initial published release source-manifest digest:
`d51ab1750dc4eddd7389ea61b019d32763f74d6a181d4b6979f6967a6c65d525`.
Its checked-success packet is 12,255 bytes, selects exact time `6/1` hours, and
has suggestion digest
`1206270927fba493e809c7587695867b0ba46a6e3fefb002d831e947038a3206`.
Its recorded construction time was about 0.006 seconds on this synthetic input;
this is not a general latency or throughput claim. All per-case timings and
artifact digests are in the ledger.

The validation history includes corrected failures: a replay test was initially
run while its record-validator module was still being implemented; rerun passed.
Automated review found vector truncation, scope/budget bypasses and a source
association attack; their fixes have persistent regressions. A whitespace check
found and removed an extra blank line. These failures are retained here rather
than presented as an uninterrupted green run. See [REVIEW.md](REVIEW.md) for
the argument and automated second-reader scope.

Initial distribution checks also passed: wheel and source distribution built,
`twine check` accepted both, and a clean wheel install ran all **138 tests** with
`python -I` outside the checkout (1.379 seconds). `pip check` reported no broken
requirements. The installed CLI freshly replayed the separating and
nonseparating compatible pairs successfully, preserved the intentionally
invalid new-datum pair as invalid, and kept the numerical partial record
unverified. Package imports resolved to the clean environment's `site-packages`.
The whitespace check passed for all new text files.

## Counterdex rename qualification

The renamed source suite passed **138 tests** in 1.312 seconds. Regeneration
produced seven current fixture packets, and the Node canonical-byte check
passed. Raw artifact hashes for all seven archived packets were checked and
remained unchanged. Both Counterdex distributions passed `twine check`. A clean
wheel installation ran all **138 tests** with `python -I` outside the checkout
(1.310 seconds), and `pip check` found no broken requirements. The installed
`counterdex` console command reported the new package name, and fresh native
replay passed with selected time `6/1`. The wheel contains only the `counterdex`
import namespace, has no runtime dependencies, and matches the recorded source
manifest byte hashes.

Current Counterdex source-manifest digest:
`028808d68d0ccfe28a08cbc867ccec6f91e9669e2f53d3972f7655dba5cf30a0`.
The current checked-success packet is 12,255 bytes and has suggestion digest
`5ad07ce07b60ed58e0394645114649a38972ffa93377b8a9076a98472a532d90`.
The current per-case results and identities are in
[the generated fixture ledger](../fixtures/manifest.json). The initial release's
hashes above remain historical records and are not reused for Counterdex.

The distribution, import package and console command are now named `counterdex`.
The ownership folder stays `packages/groundwork_adapter/`. Normative
`groundwork.*.v1` schemas, DB-SC-1, `dr-bean` hash domains, the model, exact proof
rule and selection policies remain unchanged. Archived JSON evidence stays
byte-for-byte intact and requires the original prepared source for fresh replay.
New current fixtures are generated separately under `fixtures/`.

Counterdex remains qualified only for standalone CPython 3.11. The backend's
Python 3.12/3.13 runtime and application integration are pending separate work;
this rename does not expand scientific runtime support. Browser replay remains
unavailable.

## Reproduce distribution checks

Build tooling used: setuptools 84.0.0, wheel 0.48.0, build 1.6.1, twine 7.0.0.
The release directory is ignored by git and contains local build outputs only.

```sh
python3 -m build --no-isolation packages/groundwork_adapter
python3 -m twine check \
  packages/groundwork_adapter/dist/counterdex-0.1.0-py3-none-any.whl \
  packages/groundwork_adapter/dist/counterdex-0.1.0.tar.gz
python3 -m venv /tmp/counterdex-clean
/tmp/counterdex-clean/bin/python -m pip install --no-index --no-deps \
  packages/groundwork_adapter/dist/counterdex-0.1.0-py3-none-any.whl
/tmp/counterdex-clean/bin/python -I -m unittest discover \
  -s packages/groundwork_adapter/tests -q
/tmp/counterdex-clean/bin/python -m pip check
```

Run the README's CLI example with this clean interpreter as well. Relative
paths above assume the repository root. Using `-I` and a fresh environment tests
the installed wheel rather than relying on an editable checkout. Exact replay
needs the prepared matching source and a separately supplied expected problem
and suggestion identity. It never installs a dependency named by a bundle.

## Publishing

The intended standalone release is **counterdex 0.1.0**. Counterdex is not
published to PyPI by this rename/Git-push task. Once the distribution checks pass,
a separate explicit upload would be:

```sh
python3 -m twine upload \
  packages/groundwork_adapter/dist/counterdex-0.1.0-py3-none-any.whl \
  packages/groundwork_adapter/dist/counterdex-0.1.0.tar.gz
```

Use your publishing account locally. The package's native scope is documented;
browser replay, backend approval/supervision, shared transport adoption and
deployment remain separate integration gates. Scientific interpretation does not
expand when the package is uploaded. A code change requires fixture regeneration
and a new prepared source identity; a published version must never be overwritten.
