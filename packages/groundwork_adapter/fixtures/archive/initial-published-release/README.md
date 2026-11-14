# Immutable initial published fixture archive

These JSON files are exact copies of the fixture packets, trust anchors, replay
reports and ledger distributed in the initial published release. Their bytes
were preserved before the public package rename to Counterdex. They are retained
as historical evidence and must not be edited, reformatted or regenerated.

The archived source-manifest digest is
`d51ab1750dc4eddd7389ea61b019d32763f74d6a181d4b6979f6967a6c65d525`.
Fresh replay of these packets requires the original prepared source matching
that manifest. The current Counterdex source must report a source mismatch
rather than borrow an archived verification result. An archived replay report
records its original execution; opening it is not a new replay.

Current Counterdex fixtures live in the package's `fixtures/` directory and are
generated separately by `scripts/generate_fixtures.py`. Public names and import
paths changed; normative scientific schema identifiers, hash domains, model and
proof-policy meanings did not. The rename task does not upload Counterdex to
PyPI or claim qualification of the backend's Python 3.12/3.13 environment.
