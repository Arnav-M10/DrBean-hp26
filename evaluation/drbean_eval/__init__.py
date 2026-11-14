"""Dr. Bean integration and evaluation harness (Workstream 5 owns it since the five-workstream split).

Standard library only. This package observes and grades the product; it never
produces scientific verdicts, provider responses or approvals itself. It launches
local test stacks only in isolated temporary state and never dispatches a model
request: live lanes are disabled until a new explicit user instruction.
"""

HARNESS_VERSION = "0.2.0"
CONTRACT_REVISION = "GF-2"
WIRE_PROFILE = "DB-SC-1"
CONTRACT_SOURCE_SHA256 = "2dc232c8f2477ed959864e039d97655c287e6cce61cc54179daa6b0569f0fe59"
API_PREFIX = "/api/bean/v1"
