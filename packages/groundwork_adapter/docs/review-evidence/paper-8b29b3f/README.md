# Paper sprint retained scientific evidence

Clean tested commit: **8b29b3fa802c8c10e9bb5d8bd0cd6a88a4289bcc**.
These are Owner 1 executions, not Claude's independent acceptance or a PDF/Gemini
accuracy evaluation. [Scope and handoff](../../PAPER_SCIENCE_QUALIFICATION.md).

`engine-tests.txt` and `backend-tests.txt` retain exact commands, prepared
runtime paths, sanitized environment, source identity and results. The backend
log explains its initial PATH-discovery skips and successful supplementary run;
all 619 unique cases passed across two runs. Its socket guard is parent-only.

The ordinary HTTP lane ran on an unchanged detached checkout with fresh stores,
no diagnostic overrides, explicit backend/science/replay interpreters, and
placeholder mode:

```sh
python3.11 evaluation/cli.py run --lane offline_real_science --subject http-launch --results /tmp/fresh-results
python3.11 evaluation/cli.py controls --results /tmp/fresh-results
python3.11 evaluation/cli.py gate --require release --output /tmp/science-gate.json --results /tmp/fresh-results
```

The environment must supply `DRBEAN_BACKEND_PYTHON`, `DRBEAN_SCIENCE_PYTHON`,
`BEAN_COUNTERDEX_PYTHON` and `BEAN_COUNTERDEX_REPLAY_PYTHON` pointing at prepared
interpreters, `BEAN_AI_MODE=placeholder`, and no provider credentials. The
summary retains all seven attempt/record identities, exact SHA and 214-predicate
count. The unmodified controls record contains 22 successful controls. The gate
is the existing offline scientific gate, not combined-paper release approval.

`artifacts.json` retains the three downloaded packet SHA-256 values and separate
eight-field anchors. Replay each unchanged file using the matching installed
source digest `510580863d6dbb13a569f7f28ad9822111a50356981208e08608827fcef4ee69`:

```sh
python3.11 -I -m counterdex replay-native baseline.native.json --anchors baseline.anchors.json
python3.11 -I -m counterdex replay-native design.native.json --anchors design.anchors.json
python3.11 -I -m counterdex replay-native followup-actual-own-time.native.json --anchors followup-actual-own-time.anchors.json
```

The follow-up's actual-origin declaration is retained over synthetic data; it is
not evidence of acquisition. Its valid replay retains an inconclusive scientific
outcome. All `.replay.json` files are actual fresh checker output.

No database, authentication file, source image or credential is retained.
Historical receipt directories and archived fixture bytes remain unchanged.
`SHA256SUMS.json` hashes each retained file except itself.
