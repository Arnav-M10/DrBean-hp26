# Preview: main 9cc90e0 + codex/gemini-offline-integration c95ab28 (local merge, never pushed)

Evidence class: preview (not acceptance). Harness and tests from claude/adversarial-validation were overlaid on a
throwaway worktree of origin/main merged locally with Owner 3's branch, on macOS 26.7 arm64, backend CPython 3.13.18.

- `backend-suite.txt`: full backend suite on the combination (Owner 3's own provider/coordinator/conversation tests pass;
  failures are F-MAC-NPROC plus the Owner 2 <-> Owner 3 seam: worker controlled path and two offline-provider tests).
- `ws5-integration-pytest.txt`: Workstream 5 zero-dispatch and controlled-boundary suites. Zero-dispatch passes; the
  coordinator-level strict-xfail tests XPASS (Owner 3 fixes F-COORDINATOR-OPTIONAL-STATUS and
  F-COORDINATOR-PROVIDER-LABEL); the three worker-boundary tests fail with provider_placeholder_disabled because main's
  Worker._agent still calls check_ready() for a placeholder config instead of selecting the controlled lane.
