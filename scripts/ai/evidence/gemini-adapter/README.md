# Metered Gemini candidate: offline evidence

Branch `codex/gemini-metered-adapter`; current-main integration code SHA
`2b510d22df74a27765d25c85b042816499eda173` (main `b8c5952`).
Later handoff commits contain documentation/output only.

| Current-main check | Actual result | Retained output |
|---|---|---|
| Full backend excluding independent integration directory | **862 passed**, no skips, 144.57 seconds | [backend.txt](backend.txt) |
| Independent AI boundaries and zero dispatch, unchanged | **38 passed**, 14.68 seconds | [independent.txt](independent.txt) |
| New Gemini-focused tests (included in full backend) | **158 passed**, 2.88 seconds | [focused.txt](focused.txt) |
| Controlled graph preflight | Passed; both branches; zero observed socket attempts | [offline-preflight.json](offline-preflight.json) |
| Presence-only diagnostic in cleared environment | Disabled; no fields present; no probes | [configuration-presence.json](configuration-presence.json) |
| Ruff on owned files; git diff --check | Passed | [validation.json](validation.json) |
| Live Gemini qualification | **not_run**, allocation zero | No fabricated live trace |

| Capability | Implemented | Offline evidence | Live evidence / dependency |
|---|---|---|---|
| Direct SDK generation via shared reserve boundary | Yes | Admission before construction; zero-allocation refusal; sanitized failures/usage | not_run; Owner 2 durable session ledger/config |
| Async LangChain chat model and tools | Yes | Bound schemas/args, IDs/signatures, direct plus chat shared allowance, cancellation | not_run; Owner 2 coordinator/worker wiring |
| Page-cited unaccepted paper proposal | Yes | Positive extraction, quotes/pages/units/coverage, ambiguity/unsupported/statistical controls | not_run; Owner 4 parser, Owner 2 authoritative records/consent |
| Grounded explanation and manual fallback | Existing guard reused | Actual HTTP/native positive and adversarial/known-bad evidence controls | No live prose quality claims |
| Real complete live paper-to-evidence UI | Pending integration | Existing source/science flow regression checked; new adapter tested separately | Blocked by named backend/browser/scientific mapping dependencies |
| Bounded live qualification | Scope predeclared in handoff | No generation allocation, no calls | not_run, not a pass |

The new Gemini-focused suite contains **158 passing cases**: 42 gateway,
49 adapter, 67 paper cases. The retained focused run was at code SHA `6a50474`
before main was merged; the full integrated backend run includes these same
cases. The independent tests were not edited. No provider credentials were read,
no keys validated, and no hosted requests/account probes were made. Public Google
documentation lookup is separate from application-provider use.

## Exact environment and commands

Linux, backend CPython 3.12.14, google-genai 3.3.0, langchain-core 1.8.0,
Deep Agents 0.7.38. Existing lockfile/dependencies unchanged. Prepared engine
runtime `/tmp/drbean-counterdex-runtime/bin/python` is CPython 3.11.18 with the
repository's Counterdex 0.3.0. Actual Counterdex operations/native replay execute
in the full backend's conversation/scientific regressions. These do not turn a
synthetic model response into Gemini or mathematical evidence. macOS was not run
here; no limits were relaxed.

From repository root (substitute your prepared backend and engine interpreters):

```sh
export BEAN_COUNTERDEX_PYTHON=/tmp/drbean-counterdex-runtime/bin/python
export BEAN_COUNTERDEX_REPLAY_PYTHON=/tmp/drbean-counterdex-runtime/bin/python
export PATH=/tmp/drbean-counterdex-runtime/bin:/tmp/drbean-python/cpython-3.11-linux-x86_64-gnu/bin:$PATH
/workspace/DrBean-ai/.venv/bin/python scripts/ai/offline_pytest.py -q tests --ignore=tests/integration
/workspace/DrBean-ai/.venv/bin/python scripts/ai/offline_pytest.py -q tests/test_gemini_gateway.py tests/test_gemini_chat_model.py tests/test_gemini_papers.py
/workspace/DrBean-ai/.venv/bin/python -m pytest -q --runxfail tests/integration/test_ai_boundaries.py tests/integration/test_zero_dispatch.py
/workspace/DrBean-ai/.venv/bin/python scripts/ai/probe.py
env -i BEAN_PROVIDER_MODE=disabled /workspace/DrBean-ai/.venv/bin/python scripts/ai/provider_status.py
/workspace/DrBean-ai/.venv/bin/ruff check apps/api/bean_api/providers.py apps/api/bean_api/gemini_chat_model.py apps/api/bean_api/ai_prompts.py apps/api/bean_api/conversation.py tests/test_provider.py tests/test_conversation.py tests/test_explanation_guards.py tests/test_gemini_gateway.py tests/test_gemini_chat_model.py tests/test_gemini_papers.py scripts/ai/provider_status.py scripts/ai/offline_pytest.py
git diff --check
```

The file-backed runner rejects socket.connect/connect_ex in that Python process
and Python-spawn imports. Independent integration uses its existing guard, which
allows loopback HTTP and blocks/logs non-loopback traffic and hosted client
construction. This is not an OS firewall or a sandbox for arbitrary injected
Python/native subprocesses. An initial integration invocation incorrectly used
the all-socket runner, blocking localhost; it was corrected to the existing
integration guard. The initial explicit-controlled config credential requirement
was also fixed and independently retested.

Controlled transports and the isolated test admission ledger are authored test
code. They prove shared context/reservation behavior, not durable production
session authority. Live-policy fixtures are explicitly synthetic, including any
request IDs, usage and timings they supply. Missing usage never becomes zero-cost
success. The default real application ledger deliberately lacks the required
session admission marker and cannot admit live calls.

## Review findings fixed before final testing

- SDK mixed payload parts could hide text behind media accounting: payload unions
  now reject, ancillary signatures count, and a 60,000-byte regression refuses.
- SDK async cleanup could hang: cooperative cleanup gets one second of grace,
  a second cancellation does not abandon the owned task, and the unused sync pool
  closes locally. Arbitrary blocking injected Python is not forcibly killable.
- Tool-turn prompt digest hashed a different default instruction: one effective
  instruction is now counted, hashed and sent, with an exact regression.
- Generic PDF disclosure did not identify the selected-page subset: a specific
  server-attested digest is now required. Owner 2/4 must still prove physical-page
  content/mapping before admission; this adapter is no parser.
- A phrase such as “No hard bound is justified” could appear to assert a bound:
  clear negations refuse and every proposed allowance receives a blocking
  scientific-modeling review diagnostic. Unaccepted schema validation is no proof.
- Pydantic nested context mutation was challenged during an awaited response:
  revalidation copies the context, and the new regression preserves original
  response bindings after caller lists are cleared.

Before the main merge, the broad run was **853 passed, one failed** at
`6a50474`: an old Owner 2 coordinator free-prose positive expected acceptance.
That original output is retained in [backend-before-main-merge.txt](backend-before-main-merge.txt).
Main's own PR32 merge already reconciled this assertion; this branch does not
edit Owner 2's test. The current-main retest is recorded separately below.
