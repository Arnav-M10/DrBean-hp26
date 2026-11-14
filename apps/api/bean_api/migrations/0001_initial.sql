-- DB-SC-1 application storage, explicit isolated local SQLite lane.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    current_dataset_id TEXT,
    current_problem_id TEXT,
    conversation_revision INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS memberships (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    actor_id TEXT NOT NULL,
    PRIMARY KEY (workspace_id, actor_id)
);
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    kind TEXT NOT NULL,
    body TEXT NOT NULL,
    digest TEXT NOT NULL,
    parent_id TEXT REFERENCES entities(id),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS entities_workspace_kind ON entities(workspace_id, kind, created_at);
CREATE TRIGGER IF NOT EXISTS entities_immutable_update BEFORE UPDATE ON entities
BEGIN SELECT RAISE(ABORT, 'immutable entity'); END;
CREATE TRIGGER IF NOT EXISTS entities_immutable_delete BEFORE DELETE ON entities
BEGIN SELECT RAISE(ABORT, 'immutable entity'); END;
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    plan_id TEXT NOT NULL REFERENCES entities(id),
    plan_digest TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    scope TEXT NOT NULL CHECK(scope IN ('investigation', 'design')),
    expected_revision_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    UNIQUE(plan_id, actor_id)
);
CREATE TRIGGER IF NOT EXISTS approvals_immutable_update BEFORE UPDATE ON approvals
BEGIN SELECT RAISE(ABORT, 'immutable approval'); END;
CREATE TRIGGER IF NOT EXISTS approvals_immutable_delete BEFORE DELETE ON approvals
BEGIN SELECT RAISE(ABORT, 'immutable approval'); END;
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    plan_id TEXT NOT NULL UNIQUE REFERENCES entities(id),
    approval_id TEXT NOT NULL UNIQUE REFERENCES approvals(id),
    actor_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('run', 'design_job')),
    state TEXT NOT NULL CHECK(state IN ('queued', 'running', 'completed', 'cancel_requested', 'cancelled', 'failed', 'interrupted')),
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    worker_id TEXT,
    result_id TEXT REFERENCES entities(id),
    error_code TEXT,
    tool_calls INTEGER NOT NULL DEFAULT 0 CHECK(tool_calls >= 0),
    provider_turns INTEGER NOT NULL DEFAULT 0 CHECK(provider_turns >= 0),
    scientific_reservations INTEGER NOT NULL DEFAULT 0 CHECK(scientific_reservations >= 0)
);
CREATE INDEX IF NOT EXISTS jobs_workspace_state ON jobs(workspace_id, state, created_at);
CREATE TABLE IF NOT EXISTS scenario_reservations (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES jobs(id),
    scenario_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('reserved', 'running', 'completed', 'skipped', 'failed', 'interrupted')),
    created_at TEXT NOT NULL,
    finished_at TEXT,
    result_id TEXT REFERENCES entities(id),
    reason_code TEXT,
    UNIQUE(run_id, scenario_id)
);
CREATE TABLE IF NOT EXISTS operations (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    actor_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    operation_key TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('reserved', 'completed', 'failed', 'interrupted')),
    response TEXT,
    error_code TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    UNIQUE(workspace_id, actor_id, operation, operation_key)
);
CREATE TABLE IF NOT EXISTS provider_attempts (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    operation_id TEXT NOT NULL REFERENCES operations(id),
    metadata TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('reserved', 'completed', 'failed', 'unknown_outcome')),
    response_metadata TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT
);
