# Owner 5: native acceptance handoff

Current science base: `0543a0d` on `codex/science-next`, incorporating `main`
`9cc90e0` and its merged evaluator PR #8. Counterdex remains **0.3.0**,
CPython **3.11.17**, source
`90b42ae505c9a7c25103331f447edc2e15026d291374f6beefd0ef89c23b7bf8`.
The newer evaluator at **`219dc0c`** on
`origin/claude/adversarial-validation` is **not yet merged into that main**.
Keep these consumer states distinct. No ordinary HTTP acceptance gate was
executed or passed by this handoff.

Read [Owner 2 adoption](OWNER2_BRIDGE_ADOPTION.md), the
[result truth table](RESULT_SEMANTICS.md), [bridge contract](BRIDGE.md), and the
[portable packet](../fixtures/repro/README.md). The portable packet includes
source identity, separate anchors and its prepared CPython 3.11 command.

## Implemented proposed consumer: integrate and retest

The newer `219dc0c` already implements application packet classification,
`replay-native`, complete separately supplied application anchors, numerical-only
integrity handling and a new `hero-v2` with separately reviewed continuation
permission. It retains `hero-v1`. These changes retire the earlier native
adoption request **on the proposed branch**; do not recreate them.

A fresh read-only consumer audit used that branch's actual `native.py` against
the unchanged baseline, positive design, negative design, own-time recheck and
both-excluded review packets below. **All five** classified as
`application_bundle` and replayed `passed` / `valid` with all **eight** external
anchor fields. Recheck retained the individual `valid`/`invalid` outcomes;
both-excluded review retained `invalid`/`invalid`. This is package-to-evaluator
replay compatibility, not HTTP acceptance or an independent mathematical
implementation. The whole application still needs the proposed consumer
integrated and tested against its own downloaded run bytes/anchor records.

Current `main` still classifies these application packets as `unrecognized_json`,
calls legacy `replay`, and drops most anchor fields. Its baseline/design probes
return `invalid_input` at `bundle`; that lag does not establish a defect in the
newer proposed consumer or current scientific source. Main's old string-shaped
allowance-origin error is already fixed: it now sends the object shape, tier
and horizon. The source-artifact selection semantics remain a separate consumer
issue documented in [the current Owner 2 handoff](OWNER2_BRIDGE_ADOPTION.md).

Remaining trigger: integrate the implemented consumer and rerun ordinary
HTTP/download/replay acceptance after Owner 2 fixes the Mac process-limit
boundary and native v2 design/history mapping. The proposed follow-up flow still
launches ordinary discovery on the revised dataset; dedicated adoption of
proposal-bound **`recheck`** remains an Owner 2 seam. The existing operation
supports actual/transcription/hypothetical declarations and a reading's own
time/allowance without replacing the original fixed vectors. No new science
producer or evaluator rewrite is needed.

## Earlier findings, retained with their original scope

The earlier audit used evaluator `96aa7df` and science `b955780`, after backend
PR #6 (`cc779bf`) merged as `1f75bdc`. Its concrete requests below are historical;
items 1–3 and the continuation control are now implemented by proposed `219dc0c`.

1. In `drbean_eval/native.py`, recognize the exact application profile
   `counterdex.application-bundle.v1`. The audited `classify()` accepted only
   `groundwork.*`; all three audited application packets are consequently
   `unrecognized_json`. Classifying a profile does not validate its evidence.
2. Dispatch that profile to `counterdex replay-native PACKET --anchors ANCHORS`.
   The audited `replay()` invoked the supplied-pair `replay` command, which rejects
   the current hero design packet with `invalid_input`, field path `bundle`.
   Retain the existing command for its original inner suggestion profile.
3. Obtain the complete expected application anchor from an authenticated record
   bound to the expected artifact/run. Do not recursively select the first
   digest from nested history. Do not strip the anchor down to problem and
   suggestion digests. The audited `qualify._replay_checks` required a suggestion
   digest even for baseline/recheck, where that identity does not exist.
4. In `science_flow.Flow.design`, send the normalized request shape:
   `scientific_profile: "counterdex.v1"`, the reviewed `requested_tier`,
   `maximum_horizon`, and `allowance_origin: {"kind": "hypothetical",
   "description": REVIEWED_DESCRIPTION}` for the current hypothetical control.
   Preserve the reviewed budget and source-artifact selection. The previously
   audited string `allowance_origin: "hypothetical"` fails `DesignRequestBody` validation;
   this shape is already corrected on current main.
   Passing DTO validation alone does not qualify the narrower engine admission.
5. The original evaluator hero has `allow_continuation: false`, while requesting
   6/8 hours beyond its four-hour history. With that permission unchanged, 0.3
   returns `numerical_guidance`, `not_checked`, replay `unsupported`, and exact
   reason `unavailable_horizon`. Checked extension requires a separately reviewed
   `allow_continuation: true`; do not flip it merely to make a positive case pass.

The earlier findings reproduced using the then-fetched evaluator source and
current packet files without switching branches. Owner 2 still owns ordinary HTTP
startup, byte persistence/download and expected-anchor records. The earlier
`adac945` baseline dispatch blocker is resolved by the newly merged backend
`cc779bf`; its actual adapter has passed package 0.3 compatibility checks. Native
download and `/artifacts/{id}/anchor` routes exist. Retest the current integrated
consumer instead of repeating older unavailable-adapter or missing-route findings.

## Anchor and replay interpretation

The complete application anchor has exactly these eight fields:

```text
artifact_sha256, dataset_digest, problem_digest, projection_digest,
app_request_digest, design_digest, scenario_id, run_id
```

`problem_digest` is the application problem identity; `projection_digest` is the
scientific problem identity. Baseline, `review` and `recheck` anchors retain
`app_request_digest: null` and `design_digest: null`. Design fills both. The
separate `result.native_suggestion_digest` names its inner suggestion; it cannot
replace the raw packet hash. Current design results also retain it in fresh
native replay. Baseline/recheck use the historical profile, not a suggestion.

| Packet/operation | Required interpretation of fresh replay |
|---|---|
| `hero-baseline`, `investigate` | `replay: passed`, `verification: valid`, outcome `certified_counterexample`; at least one individually compatible strict outside vector; two compatible vectors make this pair eligible. |
| `hero-design`, `design` | `passed`, `valid`, `fresh_checked.tier: checked_pair_separation`; selected time `8/1` and strictly positive exact selected margin. Compare the same bound candidate IDs/vectors. |
| `alternate-design`, `design` | `passed`, `valid`, `fresh_checked.tier: no_separation_established`, selected time null; both candidates still compatible. A useful negative design result. |
| `hero-own-time-recheck`, `recheck` | `passed`, certificate `valid`; individual results contain one `valid` and one `invalid`; outcome `inconclusive`. The full hypothetical proposal retains time `79/10`, allowance `7/20` and generating choices; aggregate origin remains hypothetical. |
| `hero-both-excluded`, legacy `review` | `passed`, certificate `valid`; both candidate results `invalid`, outcome `inconclusive`. Successfully computed exclusion is not corruption. |
| Numerical-only or incomplete evidence | Exact replay `unsupported`; numerical-record integrity may pass. Never promote this to checked separation. |

The inner `groundwork.analytic-pair.v1` proposition differs: if either candidate
is incompatible, pair verification is invalid and pair replay fails. Historical
certificates can replay successfully while reporting exclusions. Qualify the
operation's proposition and individual results; never grade only `completed`,
`ok`, hashes or a stored `valid` field. Keep Owner 5's decimal/predicate oracle
independent; neither producer decisions nor package test assertions are its oracle.

## Minimal local reproduction

From the repository root with the matching source and CPython 3.11, replay these
unchanged bytes against their separately retained fixture anchors:

```sh
for packet in hero-baseline hero-design alternate-design hero-own-time-recheck hero-both-excluded; do
  PYTHONPATH=packages/groundwork_adapter python3.11 -m counterdex replay-native \
    "packages/groundwork_adapter/fixtures/decision/$packet.native.json" \
    --anchors "packages/groundwork_adapter/fixtures/decision/$packet.anchors.json"
done
```

To execute the actual bounded producer rather than only replay its packet:

```sh
PYTHONPATH=packages/groundwork_adapter python3.11 -m counterdex.bridge \
  < packages/groundwork_adapter/fixtures/decision/hero-baseline.request.json
```

This must return `ok: true`, `scientific_outcome: certified_counterexample`,
individual compatible outside evidence, and complete bytes matching its manifest.
HTTP acceptance must instead download its own run's bytes and expected anchors.

These negative controls distinguish wrong expected identity, changed raw bytes,
and false mathematics even after deliberately resealing diagnostic hashes:

```sh
PYTHONPATH=packages/groundwork_adapter python3.11 - <<'PY'
import base64, json
from pathlib import Path
from counterdex.errors import AdapterError
from counterdex.exact import artifact_digest, canonical_bytes, semantic_digest
from counterdex.native_packet import replay_packet
root = Path('packages/groundwork_adapter/fixtures/decision')
raw = (root / 'hero-baseline.native.json').read_bytes()
expected = json.loads((root / 'hero-baseline.anchors.json').read_text())
def reject(data, anchor, code):
    try:
        replay_packet(data, expected=anchor)
    except AdapterError as error:
        assert error.code == code, error.to_dict()
        print(code)
    else:
        raise AssertionError('Altered evidence was accepted')
reject(raw, dict(expected, projection_digest='0' * 64), 'wrong_specification_binding')
reject(raw + b' ', expected, 'artifact_mismatch')
packet = json.loads(raw)
native = json.loads(base64.b64decode(packet['scientific']['bytes_base64']))
certificate = json.loads(base64.b64decode(native['certificate']['bytes_base64']))
certificate['candidates'][0]['samples'][1]['lower'] = '0/1'
def encoded(value):
    data = canonical_bytes(value)
    return {'sha256': artifact_digest(data), 'bytes_base64': base64.b64encode(data).decode()}
native['certificate'] = encoded(certificate)
native['baseline_digest'] = semantic_digest('report', {k: v for k, v in native.items() if k != 'baseline_digest'})
packet['scientific'] = encoded(native)
changed = canonical_bytes(packet)
reject(changed, expected, 'artifact_mismatch')
diagnostic = dict(expected, artifact_sha256=artifact_digest(changed))
reject(changed, diagnostic, 'exact_check_failure')
PY
```

Only the explicitly altered diagnostic anchor permits the false enclosure to
reach mathematical checking. It is not trusted identity or authentication. Retain
the original-anchor rejection alongside it. Runtime/source mismatch is a separate
unsupported-environment result; use the recorded matching source instead of
rewriting archived packets. Package reproduction does not establish HTTP gates,
physical truth, independent formal certification or provider qualification.
