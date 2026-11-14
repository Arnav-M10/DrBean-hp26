# Preview: backend/restart-recovery (PR #14) at c231be4 on macOS 26.7 (Darwin 25.6.0)

Diagnostic previews only (never acceptance). All runs use this branch's harness against a scratch checkout.

| Directory | Diagnostics | Result |
|---|---|---|
| `relax_nproc+science_barrier/` | relax_nproc, science_barrier | RS-CANCEL-RESTART passes: the lifeline guard stops the held child when the worker is SIGKILLed (F-ORPHAN-WORKER-KILL fixed by the PR). Cancelled/killed jobs never reach the normal-completion cleanup. |
| `relax_nproc/` | relax_nproc | Hero and changed input **fail** (`worker_failed` / `scientific_attempt_failed`); cancel without the barrier leaves **1 live child** after cancellation. Root cause: F-RESTART-EPERM. |
| `LOCAL-PATCH-killpg-eperm/` | relax_nproc (+ science_barrier) | Same lane against a **local, unpushed** copy of c231be4 with one line changed in `run_bounded`'s `finally`: `except (ProcessLookupError, PermissionError)`. 6/7 pass (as on main), cancel/restart with the barrier passes. Confirms the single cause. This patch is not a proposed implementation and was not pushed anywhere. |

`killpg-eperm-repro.py` (standard library only): a spawn child calls `setsid()` and exits; before
`join()`, `os.killpg(pid, SIGKILL)` raises `PermissionError` (errno 1) on Darwin; after `join()` it is
`ProcessLookupError` (errno 3). Linux returns ESRCH in the first case, which is why the PR's Linux
validation passed. Output here, under CPython 3.11.17 and 3.13.18:

```
before join (zombie leader): PermissionError errno 1
after join (reaped): ProcessLookupError errno 3
```
