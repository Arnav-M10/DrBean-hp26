# Counterdex 0.3.0

Publication preparation: **November 14, 2026**. This page describes the
Counterdex **0.3.0** scientific distribution prepared from repository commit
[`b60e9d997cdc262e50107953bafc422398435297`](https://github.com/Arnav-M10/DrBean-hp26/tree/b60e9d997cdc262e50107953bafc422398435297).
Publication metadata and documentation updates preserve the scientific Python
source and existing fixture bytes. An upload is complete only when the release
is available from the package index; this document alone is not an upload
receipt.

## Package identity

The distribution, import namespace and console command are all `counterdex`.
Install with CPython 3.11:

```sh
python3.11 -m pip install --no-deps "counterdex==0.3.0"
python3.11 -m counterdex capabilities
```

There are no runtime dependencies or model-provider calls. The qualified source
identity is
`90b42ae505c9a7c25103331f447edc2e15026d291374f6beefd0ef89c23b7bf8`.
Package version and source identity both matter for fresh replay. Exact
execution remains restricted to CPython 3.11; the host application's runtime
must not broaden that qualification.

## Included scientific operations

- Bounded candidate discovery for
  `C(t) = A·(exp(−ke·t) − exp(−ka·t))`, with `A > 0` and `0 < ke < ka`.
- Independent exact checks against every included historical hard allowance,
  with strict outside tests against a closed claimed interval.
- Numerical fixed-pair guidance and checked fixed-pair separation on the
  approved finite feasible-time grid. Checked separation requires a strictly
  positive margin; numerical guidance cannot acquire a checked label.
- Explicit design mapping that retains the reviewed tier, allowance provenance
  and maximum horizon. Unsupported prospective certificate reuse is rejected.
- Proposal-bound `recheck` of the original candidates with one appended actual,
  transcribed or hypothetical observation at that reading's own declared time
  and allowance. Parent bytes, original vectors and historical lineage remain
  bound; the operation does not search for replacement candidates.
- Portable native evidence and fresh replay against separately supplied
  external anchors, including input/projection/run/scenario binding checks and
  required parent evidence.
- A bounded JSON subprocess bridge and a POSIX parent-supervision example for
  applications using a separate prepared CPython 3.11 engine.

The CLI includes `capabilities`, `baseline`, `replay-baseline`, `run`, `replay`,
`bridge` and `replay-native`. The Python API exports normalization helpers,
`create_baseline`, `replay_baseline`, `create_suggestion`, `replay_bundle`,
`replay_packet`, `capabilities`, `ExecutionContext` and `AdapterError`.

## Evidence and interpretation

The checked model is intentionally narrow: hours, mg/L, inverse-hour rates,
`x(0)=1`, and `c(0)=0`. No new model family or runtime is introduced by this
publication. A bounded search without an outside witness remains inconclusive.
A new reading that excludes the outside candidate does not prove the interval;
excluding both selected candidates does not eliminate all models. Replay,
verification, binding, integrity and scientific outcome are separate results.

The source archive retains the current synthetic decision examples, portable
replay packet, tests, exact analytic argument, technical contracts and immutable
historical archives. Archived packets require their original matching prepared
source. Public scientific schema identifiers, digest domains and policy names
remain unchanged compatibility data.

Use the [public quick start](https://github.com/Arnav-M10/DrBean-hp26/blob/main/packages/groundwork_adapter/README.md)
for an installed-package replay that needs no repository checkout. The
[retained technical evidence](https://github.com/Arnav-M10/DrBean-hp26/tree/b60e9d997cdc262e50107953bafc422398435297/packages/groundwork_adapter/fixtures)
identifies synthetic examples explicitly. Historical handoffs elsewhere in the
source archive describe their dated integration checkpoints, not the state of
every current application deployment.

## Application boundary

Counterdex does not grant approval, infer consent, allocate provider budgets,
operate equipment or start a server. An application must separately review
measurements and assumptions, approve the precise operation, enforce workspace
and storage authority, supervise the process, and publish matching result/native
bytes. Changed assumptions require a new plan and approval.

Dr. Bean's backend, browser and Deep Agents coordinator are separate application
components. Their integration checks do not turn this library into a browser
verifier or establish live-model reasoning. Scientific claims remain grounded
in Counterdex's returned evidence and explicit limitations.
