# Coordinator sprint qualification (role C, DB-COORDINATOR-3OWNER-1)

C (Claude) independently evaluates the three-owner coordinator sprint. A (the user's Codex) owns Counterdex and
the Deep Agents graph, prompts and model adapters; B (the teammate's Codex) owns backend authority, contracts,
durability, sessions, ledger, UI, general-file services and main integration. C owns `evaluation/**`, the
independent tests under `tests/integration/test_*` that it authored, findings and qualification reports. C does
not fix production behaviour to satisfy its own oracle; it files a reproducer for A or B and retests the repair.

## Frozen predicates

- [`predicates.v1.json`](predicates.v1.json): 54 predicates (43 release-blocking) in eight groups: scientific
  (SCI), coordinator journey and graph (LOOP), authority and privacy (AUTH), durability crash matrix (CRASH),
  metering (METER), general files and papers (FILE), release (REL).
- [`FROZEN.json`](FROZEN.json): canonical SHA-256 commitment, frozen against main `299a356`. The self-test
  `evaluation/tests/test_coordinator_predicates.py` fails on any edit; a correction is a new `predicates.v2.json`
  with its own commitment, and v1 stays.
- Statuses: `passed`, `failed`, `not_available` (feature absent), `not_run` (with reason), `historical_only`,
  `author_check` (checked component authored by Claude, needs A/B cross-review). A missing producer is never a
  pass.
- Adaptivity is graded as acceptable sets of permitted next actions per tool-return condition, not one sentence
  or tool order.

## Baseline

[`../results/coordinator/baseline-299a356.json`](../results/coordinator/baseline-299a356.json) records each predicate's status on main `299a356`
(application tree identical on the C branch), the basis and the evidence path. The human-readable record is
[`../results/integration/baseline-299a356.md`](../results/integration/baseline-299a356.md).

## Probes

| File | Predicates | At baseline |
|---|---|---|
| `tests/integration/test_private_sessions_independent.py` | AUTH-01, AUTH-02, AUTH-03; availability probe for F-SESSION-CAPACITY-EXHAUSTION | 3 passed; 1 strict xfail (the finding) |
| `tests/integration/test_research_session_probes.py` | LOOP-01, LOOP-08, AUTH-01, AUTH-04, AUTH-06 through DB-RESEARCH-1 routes | 7 NOT_AVAILABLE (routes not registered) |
| `tests/integration/test_native_download_scope.py` | SCI-09 and AUTH-01 for a completed run's native bytes, anchors, evidence and report | passes (actual Counterdex) |
| `tests/integration/test_provider_accounting_independent.py` | CRASH-08, METER-02, METER-03 on main's provider boundary and shared ledger | passes |
| the earlier independent suite and engine controls | mapped predicate by predicate in the baseline observation file | see the lane reports |

The probes rely only on HTTP status codes, published DB-RESEARCH-1 DTO fields and side-effect counts read from
the store, so they run unchanged once B registers the routes. When a probe meets the real routes, an observation
that contradicts a predicate becomes a finding with a reproducer for its owner.

## Lanes

The four lanes and their permitted conclusions are in `docs/evaluation-protocol.md`; this sprint uses them
unchanged: controlled callbacks, controlled model with actual Counterdex, separately admitted live Gemini
(`not_run` unless the user enables disclosure, mode, model and an admitted allocation) and fresh native replay.

## Holdouts

The sealed paper holdouts H1-H4 (commitment in `../corpus/holdouts.sealed.json`) stay sealed: no prompt has
been frozen by A, so they have not been revealed or used. They become development evidence once they inform a
repair. The supplied public papers (zolleral_26, 9,848,487 bytes, 12 pages; sokolowskial_25, 19,073,679 bytes,
11 pages) are measured locally and are not committed; see FILE-02 in the baseline.
