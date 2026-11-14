# Validation record

Validation performed in the selected workspace on Python 3.12.14 against the pinned `uv.lock` environment. All application inputs are synthetic; provider transports/models used by tests are explicitly controlled.

| Check | Observed result |
|---|---|
| `python -m pytest -q` | **164 passed**, 13.20 seconds |
| `ruff check apps tests scripts` | All checks passed |
| Schema export | 32 schemas and 3 synthetic fixture files generated |
| Offline corpus evaluation | 8 source-integrity checks passed; 24 portfolio variants remain `not_run` without imported evidence |
| Wheel build | `dr_bean_backend-0.1.0-py3-none-any.whl` built; packaged migration and bounded decoder inspected |
| Running HTTP service | Health/capabilities 200; unauthenticated workspace read 401; authenticated workspace read 200 |
| Live Gemini | 0 requests; not qualified |
| Groundwork / native replay / browser replay | Not installed or qualified; capabilities report unsupported |

The test suite includes real SQLite concurrent reservation races, immutable revisions, stale scope, separate design authority, source corruption and parser resource controls, cancellation with actual spawned-process termination, restart/unknown-outcome records, backup restore, exact JSON and rational controls, HTTP auth/export, provider failure controls, and the actual deepagents framework with controlled models. Worker integration records controlled framework attempts in the durable ledger and confirms completed work is not dispatched again.

These results establish bounded backend behavior under the tested conditions. They do not establish live Gemini extraction accuracy, scientific correctness, provider cost/latency, frontend usability, PostgreSQL behavior, production deployment, event eligibility or sponsor qualification. See `HANDOFF.md` for the remaining gates and owner actions.
