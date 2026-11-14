# Counterdex

**Check a parameter claim against measurements, find a competing explanation, and
compare what to measure next.** Counterdex is a Python library and command-line
tool for bounded scientific investigation with portable, freshly replayable
evidence. It uses only the Python standard library and makes no network or model
provider calls.

Version **0.3.0** supports one model:

```text
C(t) = A · (exp(−ke · t) − exp(−ka · t))
A > 0,  0 < ke < ka
```

Time is in hours, concentration in mg/L, and rates in inverse hours. The admitted
initial conditions are `x(0)=1` and `c(0)=0`. Exact scientific execution and replay
are qualified on **CPython 3.11**.

## What Counterdex does

- **Discover competing candidates.** Search a bounded rate grid with amplitude
  screening, then independently check retained exact parameter vectors against
  every included measurement and its declared hard allowance. A compatible
  vector strictly outside a **closed** claimed interval is a counterexample;
  either endpoint is inside the claim.
- **Compare a selected pair.** Evaluate researcher-supplied feasible measurement
  times and a declared future allowance. Numerical guidance stays numerical.
  Checked separation requires two freshly compatible candidates and a strictly
  positive exact separation margin. Touching bands do not separate.
- **Review a new reading.** Recheck the original candidates using an appended
  actual, transcribed or hypothetical observation at its own declared time and
  allowance. Preserve the parent evidence and candidate vectors rather than
  silently searching for replacements.
- **Replay evidence independently of the application.** Check native bytes,
  complete lineage and exact input bindings against separately supplied expected
  identities, then recompute the scientific checks with the matching prepared
  package.

No counterexample found means **inconclusive**, never “claim proved.” Excluding
one or both selected candidates does not exclude every other model. A successful
replay confirms the recorded calculation under its declared scope; it does not
upgrade an inconclusive result or establish the truth of the physical model.

## Install

Create a CPython 3.11 environment:

```sh
python3.11 -m venv .counterdex-env
.counterdex-env/bin/python -m pip install --no-deps "counterdex==0.3.0"
.counterdex-env/bin/python -m counterdex capabilities
```

The distribution, Python import and console command are all named `counterdex`.
The package has **no runtime dependencies**. Build and publication tools are
separate development dependencies. Python 3.12/3.13 applications should invoke a
separately prepared CPython 3.11 scientific process rather than relax the
package's Python requirement.

## Try a complete native replay

This example uses synthetic measurements, a retained counterexample and its
separately stored anchors. Download the two public fixture files into a new
folder; the replay itself is offline and requires no repository checkout:

```sh
mkdir counterdex-demo
cd counterdex-demo
curl --fail --location --output hero-baseline.native.json \
  https://raw.githubusercontent.com/Arnav-M10/DrBean-hp26/b60e9d997cdc262e50107953bafc422398435297/packages/groundwork_adapter/fixtures/repro/hero-baseline.native.json
curl --fail --location --output hero-baseline.anchors.json \
  https://raw.githubusercontent.com/Arnav-M10/DrBean-hp26/b60e9d997cdc262e50107953bafc422398435297/packages/groundwork_adapter/fixtures/repro/hero-baseline.anchors.json
../.counterdex-env/bin/python -I -m counterdex replay-native \
  hero-baseline.native.json --anchors hero-baseline.anchors.json
```

For this fixture the result has `verification: "valid"`,
`expected_binding: "matches"`, `replay: "passed"`, and scientific outcome
`"certified_counterexample"`. It checks two compatible exact vectors, including
one strictly outside the reviewed closed claim. It is synthetic evidence, not an
acquired experiment or an application approval.

For real work, obtain expected anchors through the reviewer's trusted channel.
Replacing both an artifact and its anchors does not prove authorship or honest
data collection. Old evidence needs its matching prepared source; Counterdex
never installs or imports a version chosen by an evidence packet.

## Python API

After downloading the two files above, the same fresh replay is available from
Python:

```sh
../.counterdex-env/bin/python -I - <<'PY'
import json
from pathlib import Path
from counterdex import replay_packet

result = replay_packet(
    Path("hero-baseline.native.json").read_bytes(),
    expected=json.loads(Path("hero-baseline.anchors.json").read_text()),
)
print({key: result[key] for key in ("verification", "expected_binding", "replay")})
print(result["outcome"]["scientific_outcome"])
PY
```

The public API also exposes:

| Entry point | Purpose |
| --- | --- |
| `normalize_problem`, `normalize_design`, `normalize_times` | Validate exact scientific projections without changing their reviewed meaning. |
| `create_baseline` | Discover and check candidates for a reviewed historical problem. |
| `replay_baseline` | Recompute historical compatibility and outside-claim checks. |
| `create_suggestion` | Compare a frozen pair under the reviewed design scope. |
| `replay_bundle` | Replay a standalone pair-design bundle. |
| `replay_packet` | Replay an application-bound native packet and its required lineage. |
| `capabilities` | Report supported operations and runtime qualification; this is not a verdict on supplied data. |
| `ExecutionContext`, `AdapterError` | Provide cooperative execution limits and typed failures. |

See the [scientific input contract](https://github.com/Arnav-M10/DrBean-hp26/blob/b60e9d997cdc262e50107953bafc422398435297/packages/groundwork_adapter/docs/INTEGRATION.md)
for complete input shapes and identities. Scientific scalar inputs use exact
rational strings, not JSON floating-point numbers. Row order, excluded rows,
notes and provenance participate in the problem identity. Candidate vectors,
feasible times, allowance provenance, policies and limits participate in the
design identity.

## Command line and application integration

```sh
.counterdex-env/bin/python -m counterdex --help
```

Run the command above from the directory where the environment was created.
Commands include `capabilities`, `baseline`, `replay-baseline`, `run`, `replay`,
`bridge`, and `replay-native`; each command has `--help`. Evidence-producing CLI
commands require an explicit output path and refuse to overwrite an existing
file.

The bounded JSON subprocess bridge offers `handshake`, `admission`,
`investigate`, `design`, `review`, `recheck`, and `replay` operations. In
particular, `recheck` binds a separately reviewed observation proposal and its
revised inputs to the original baseline or design packet. Read the
[bridge contract](https://github.com/Arnav-M10/DrBean-hp26/blob/b60e9d997cdc262e50107953bafc422398435297/packages/groundwork_adapter/docs/BRIDGE.md)
and [exact application mapping](https://github.com/Arnav-M10/DrBean-hp26/blob/b60e9d997cdc262e50107953bafc422398435297/packages/groundwork_adapter/docs/APPLICATION_MAPPING.md)
for request schemas, approved limits, lineage and the POSIX parent-supervision
example. Those technical documents retain dated integration notes; the library
scope and release information on this page describe this distribution.

Counterdex checks mathematics and scope bindings. The calling application owns
authentication, human review, approval, durable storage, provider consent and hard
process supervision. Workflow IDs alone confer no authority. A new measurement
design or changed assumptions need fresh application review and approval. Native
bytes and the accepted report should be published together after checking their
exact bindings.

The Dr. Bean application coordinates this workflow using its own backend and
Deep Agents integration. They are separate from the Counterdex distribution;
installing this library does not start a server, configure an AI provider or
supply a browser verifier.

## Scientific limits

This release does not establish global identifiability, search completeness,
physical truth, model adequacy, instrument precision, a global design optimum,
or a confidence interval. Hard allowances are reviewed bounds, not automatically
inferred statistical uncertainties. The exact checker uses a fixed rational
exponential-enclosure rule for the admitted analytic template. An unresolved
enclosure is not evidence of incompatibility.

Generic ODE families, interventions, resets, shared offsets, correlated errors
and nonlinear observables are unsupported. Native replay is qualified on
CPython 3.11; in-browser mathematical replay is not qualified. Pair separation
concerns only the two named candidates and approved feasible times. Numerical
scores cannot be promoted to checked guarantees.

The public package preserves existing schema identifiers, hash domains and
proof/selection-policy identifiers as compatibility data. Archived evidence
retains its original bytes and source requirements.

## Documentation and source

- [Counterdex 0.3.0 release notes](https://github.com/Arnav-M10/DrBean-hp26/blob/main/packages/groundwork_adapter/docs/RELEASE_0_3_0.md)
- [Result semantics and permitted claims](https://github.com/Arnav-M10/DrBean-hp26/blob/b60e9d997cdc262e50107953bafc422398435297/packages/groundwork_adapter/docs/RESULT_SEMANTICS.md)
- [Exact analytic argument](https://github.com/Arnav-M10/DrBean-hp26/blob/b60e9d997cdc262e50107953bafc422398435297/packages/groundwork_adapter/docs/ANALYTIC_ARGUMENT.md)
- [Synthetic discovery, design and follow-up examples](https://github.com/Arnav-M10/DrBean-hp26/tree/b60e9d997cdc262e50107953bafc422398435297/packages/groundwork_adapter/fixtures/decision)
- [Portable replay packet](https://github.com/Arnav-M10/DrBean-hp26/tree/b60e9d997cdc262e50107953bafc422398435297/packages/groundwork_adapter/fixtures/repro)
- [Repository and issue tracker](https://github.com/Arnav-M10/DrBean-hp26)

The source distribution includes tests, technical documentation, synthetic
fixtures and the parent-supervision example. The wheel supplies the scientific
runtime. The repository package directory is `packages/groundwork_adapter/`.
