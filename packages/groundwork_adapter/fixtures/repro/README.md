# Portable Counterdex baseline replay

This folder copies the exact controlled hero baseline request, native packet and
separately retained anchors from the decision fixtures. It does not run discovery
again or constitute an HTTP evaluation. Inputs are synthetic, with no acquired
measurements or provider calls.

The recorded package is Counterdex **0.3.0**, with source
digest `90b42ae505c9a7c25103331f447edc2e15026d291374f6beefd0ef89c23b7bf8`. `implementation.json` retains the full
implementation identity. Replay checks that identity and independently supplied
anchors; a different source build cannot silently accept this packet.

From this directory, prepare an isolated CPython 3.11 environment and install the
matching released package when it is available:

```sh
python3.11 -m venv .replay-env
.replay-env/bin/python -m pip install --no-deps counterdex==0.3.0
.replay-env/bin/python replay.py
```

Before publication, install the matching reviewed wheel into that environment
instead. The replay script never installs dependencies or selects a different
executable: it invokes the caller's interpreter with `-I -m counterdex.bridge`.
It reads `hero-baseline.native.json` unchanged and supplies
`hero-baseline.anchors.json` independently. Keep both files; recomputing an
expected anchor from changed bytes would discard the original identity check.

Equivalent package CLI replay from this folder is:

```sh
.replay-env/bin/python -I -m counterdex replay-native \
  hero-baseline.native.json --anchors hero-baseline.anchors.json
```

The scoped claim is an exact outside witness to the reviewed closed `ke` interval
under the retained two-rate model, complete parameter domain and per-row hard
bounds. Two fixed candidate vectors freshly satisfy those historical bounds;
one lies outside the closed claim. This does not establish search completeness,
whole-model impossibility, a confidence interval, a global experiment optimum,
an actual measurement or independent formal certification. Read the native
packet for the exact rational inputs and scientific checks.
