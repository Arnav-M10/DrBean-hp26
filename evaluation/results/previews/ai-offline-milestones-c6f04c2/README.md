# Preview: codex/ai-offline-milestones c6f04c2 (based on main 9cc90e0), harness overlaid

Evidence class: preview, never acceptance. macOS 26.7 arm64.

- `ws5-integration-pytest.txt`: zero-dispatch and controlled-boundary suites: 36 passed; the two strict-xfail
  coordinator tests XPASS (F-COORDINATOR-OPTIONAL-STATUS and F-COORDINATOR-PROVIDER-LABEL fixed on this branch);
  the three worker-boundary tests pass (F-AI-INTEGRATION-SEAM resolved on this branch).
- `backend-suite.txt`: 319 passed, 5 failed; every failure is the Mac process-limit defect (F-MAC-NPROC), including
  Owner 3's new real-Counterdex coordinator test (error_code scientific_runtime_unavailable).
