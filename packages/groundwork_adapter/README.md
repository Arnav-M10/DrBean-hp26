# Counterdex

A dependency-free scientific package for one admitted kinetics template:
`C(t) = A * (exp(-ke*t) - exp(-ka*t))`, with hours, mg/L, positive ordered
rates, `x(0)=1`, and `c(0)=0`. Qualified native runtime: **CPython 3.11**.
The Python import and command-line module are `counterdex`; the console command
is also `counterdex`. The repository ownership directory remains
`packages/groundwork_adapter/`.

It discovers candidate vectors from reviewed observations with a deterministic
bounded rate grid and amplitude screening. Every retained exact vector is
independently checked against the historical hard allowances. One compatible
vector strictly outside the closed claim is a checked counterexample; failure
to find one says only what this bounded search found.

It then compares two frozen parameter vectors on a reviewed finite grid. The
numerical tier provides finite binary64 diagnostics with an exact-input boundary.
The exact tier uses a fixed rational exponential enclosure rule, freshly checks
both candidates against every included historical hard bound, and applies the
strict margin `abs(p1-p2)-e1-e2-2*eta > 0`. Its certificate is specific to this
analytic template. It is not a general ODE checker or a global design optimizer.

Pair design requires two checked candidates and an explicit positive future hard
allowance. A single historical witness remains useful with pair design disabled.
A checked time can rule out fitting **both selected choices**; a datum
can exclude either or both. None of this establishes physical truth, instrument
precision, the entire compatible parameter set, or the original interval claim.

## Install and check

From the repository root, using CPython 3.11:

```sh
python3.11 -m pip install --no-deps ./packages/groundwork_adapter
python3.11 -m unittest discover -s packages/groundwork_adapter/tests -v
python3.11 -m counterdex capabilities
```

For the complete application-shaped discovery → design → hypothetical reading
→ replay loop, use [the prepared runtime bridge](docs/BRIDGE.md),
[exact application mapping](docs/APPLICATION_MAPPING.md), and
[the executed synthetic decision example](docs/DECISION_EXAMPLE.md).
The standalone commands also include `baseline`, `replay-baseline`, `bridge`,
and `replay-native`; run `python3.11 -m counterdex --help` for their inputs.

For source-only development, prefix commands with
`PYTHONPATH=packages/groundwork_adapter`. Build tooling is separate from the
zero-dependency runtime. No network, account, numerical solver, or provider SDK
is required for scientific work or replay.

## Run and replay the complete synthetic example

All supplied examples are synthetic. Their workflow IDs are fixture IDs, not
real approvals. The backend must validate real approval and operation scope.

```sh
python3.11 -m counterdex run \
  packages/groundwork_adapter/fixtures/checked_success.request.json \
  --anchors packages/groundwork_adapter/fixtures/checked_success.anchors.json \
  --output /tmp/counterdex-example.bundle.json
python3.11 -m counterdex replay /tmp/counterdex-example.bundle.json \
  --anchors packages/groundwork_adapter/fixtures/checked_success.anchors.json
```

The output destination must not already exist. Anchors are separate expected
identities supplied by the caller; for real review, obtain them through a trusted
channel. Replacing both a packet and its anchor does not prove authorship or
honest data collection. A source-version mismatch returns `unsupported_runtime`:
prepare the recorded package version, rather than importing anything named by
the artifact. Missing evidence returns `incomplete_export`.

`run` supports fresh candidate construction from a request file. Python callers
can also supply bounded artifact bytes to reuse an existing matching pair. A
numerical-only bundle can pass record-integrity checks but returns scientific
replay `unsupported`; it never receives an exact badge.

## Python integration

```python
from counterdex import create_suggestion, normalize_problem, normalize_design

problem = normalize_problem(reviewed_problem_projection)
design = normalize_design(frozen_design_projection, problem)
bundle_bytes = create_suggestion(
    problem.to_payload(), design.to_payload(),
    expected_problem_digest=approved_problem_digest,
    expected_design_digest=approved_design_digest,
    workflow={"plan_id": plan_id, "approval_id": approval_id,
              "operation_id": operation_id, "execution_id": execution_id},
)
```

These are **package-local scientific projections**, not competing application
transport DTOs. Owner 2 maintains the shared transport schema, authorization,
durable records and hard process supervision. The adapter supplies cooperative
cancellation and cannot authorize work. Publish a checked report and its complete
bytes atomically. Owner 3 consumes typed tiers and the fixed interpretation
selector; browser replay remains unavailable. Owner 4 qualifies deployment.
Counterdex's standalone CPython 3.11 qualification differs from the backend's
Python 3.12/3.13 environment. The prepared subprocess bridge and parent example
connect those runtimes without widening exact runtime qualification. Ordinary
API/worker wiring and independent HTTP acceptance remain separate integration
work; passing package tests does not establish that gate.

The problem identity includes row order, excluded rows, notes and provenance.
The design identity includes candidate vectors/IDs/artifact associations, grid,
allowance and origin, policies and limits. New values normalize to reduced `n/d`.
The bundle identity excludes only its named top-level `suggestion_digest` field.
Raw artifact SHA-256 hashes remain separate from DB-SC-1 semantic identities.
The existing `groundwork.*.v1` schema identifiers, `dr-bean` hash domains, and
model/proof/selection policy identifiers remain compatibility data. The public
package preserves those normative values.

## Evidence and release

- [Scientific integration contract](docs/INTEGRATION.md)
- [Result semantics and permitted claims](docs/RESULT_SEMANTICS.md)
- [Current backend adoption handoff](docs/OWNER2_BRIDGE_ADOPTION.md)
- [Portable offline replay packet](fixtures/repro/README.md)
- [Exact analytic argument](docs/ANALYTIC_ARGUMENT.md)
- [Automated second-reader review](docs/REVIEW.md)
- [Executed fixture ledger](fixtures/manifest.json)
- [Validation and publishing handoff](docs/VALIDATION.md)
- [Immutable initial-release archive](fixtures/archive/initial-published-release/README.md)

Regenerate fixtures after any package code change:

```sh
python3.11 packages/groundwork_adapter/scripts/generate_fixtures.py
python3.11 packages/groundwork_adapter/scripts/generate_decision_fixtures.py
```

The generator writes current fixtures only. The initial published fixture
archive retains its original bytes and requires its original prepared source
for fresh replay. The original 0.2.0 bridge evidence is also retained under
`fixtures/archive/0.2.0-bridge/`. This sprint prepares version 0.3.0; it does not
upload to PyPI. Explicit design requests preserve their reviewed tier, horizon
and allowance provenance. The additive `recheck` operation binds an appended
observation proposal and rechecks the original candidates at the reading's own
time and allowance. See [the bridge contract](docs/BRIDGE.md).

The partial fixture uses a deterministic cancellation callback; rerunning its
request through the CLI without that callback produces a new completed result.
Timing strings in the fixture ledger are observations, not latency guarantees.
The release is intentionally narrow: no provider calls, browser verification,
application routes, equipment control, or hosting are included.
