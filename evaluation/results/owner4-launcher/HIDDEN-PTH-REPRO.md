# F-LAUNCHER-HIDDEN-PTH reproduction (Owner 4)

Host: macOS 26.7 (Darwin 25.6.0) arm64; backend CPython 3.13.18 (`.venv`, `uv sync --locked`, uv 0.13.8);
engine CPython 3.11.17 (`.venv-engine` from `scripts/dev/launcher.py setup`). Launcher
`scripts/dev/launcher.py` at `a516943`. Paths below are shortened: `<repo>` is the checkout under
`~/Documents/...`, `<tmp>` is a private scratch directory under `/private/tmp`.

## 1. `<repo>` is inside an iCloud Drive File Provider domain

```
$ xattr -l ~/Documents
com.apple.file-provider-domain-id: com.apple.CloudDocs.iCloudDriveFileProvider/<id>
```

## 2. Dot-named directories there become hidden, recursively, within seconds

```
$ uv venv var/probe-uv-venv;  uv venv var/.probe-dot-venv;  mkdir var/.probe-dot-dir; touch var/.probe-dot-dir/file
# ~6 s later (ls -lO / stat -f %Sf)
var/probe-uv-venv           -        (birth 23:50:32, ctime 23:51:09)
var/.probe-dot-venv         hidden   (birth 23:51:13, ctime 23:51:19)
var/.probe-dot-dir          hidden   (birth 23:51:13, ctime 23:51:19)
var/.probe-dot-dir/file     hidden   (birth 23:51:13, ctime 23:51:19)
<tmp>/.probe-dot-tmp        -        (same commands outside ~/Documents, 11 s later: still visible)
<repo>/.venv/lib/python3.13/site-packages/_editable_impl_dr_bean_backend.pth   hidden (birth 21:58:46, ctime 22:06:02)
<repo>/.venv-engine/...                                                        hidden (birth 23:49:30, ctime 23:49:39)
```

Fresh venvs from uv and from `python -m venv` are not hidden at creation; only the dot-named
location triggers the flag. uv and Python are not the cause.

## 3. CPython skips a hidden `.pth`

```
$ <repo>/.venv/bin/python -I -c 'site.addsitedir(<tmp>/pthprobe/site); find_spec("probe_pkg")'
visible .pth -> True
$ chflags hidden <tmp>/pthprobe/site/visible.pth
hidden .pth (3.13.18) -> False
hidden .pth (3.11.17) -> False
```

## 4. Effect on the one-command launcher

```
$ DRBEAN_VAR_DIR=<tmp>/o4var python3 scripts/dev/launcher.py setup
== local auth (existing file is preserved)
   <repo>/.venv/bin/python: Error while finding module specification for 'bean_api.bootstrap'
   (ModuleNotFoundError: No module named 'bean_api')

$ DRBEAN_VAR_DIR=<tmp>/o4start/var python3 scripts/dev/launcher.py start      # auth.json pre-written
--- last lines of var/run/worker.log ---
<repo>/.venv/bin/python: Error while finding module specification for 'bean_api.worker'
(ModuleNotFoundError: No module named 'bean_api')
Start failed; everything this launcher started was stopped. See the log lines above.
$ ... launcher.py status        -> api/worker/web not running; ports 8000 and 4173 free
$ ... launcher.py doctor        -> "ok  backend runtime (.venv)  ... dr-bean-backend 0.1.0 ..."
```

The doctor row is a false positive: it checks package metadata, not whether the services can
import `bean_api`.

## 5. Same launcher, unmodified, with `apps/api` on `PYTHONPATH`

The harness subject `--subject http-owner4-launcher` records the unmodified attempt (exit 1,
`bean_api` not importable) and then one labelled retry with `apps/api` on `PYTHONPATH`, which the
launcher passes through. That retry starts in under a second; API, worker and science readiness are
reported separately; the egress guard in the API and worker records no provider credential names,
although dummy `GEMINI_API_KEY`, `GOOGLE_API_KEY` and `LANGSMITH_API_KEY` were present in the
launcher's own environment.

Suggested fix (Owner 4): pass `--app-dir apps/api` to uvicorn and add `apps/api` to `PYTHONPATH` in
`child_env()` (as `shared/contracts/BACKEND_INTEGRATION.md` documents), and let doctor import
`bean_api` with the services' environment. Operator workaround: keep the checkout outside
iCloud-synced folders.
