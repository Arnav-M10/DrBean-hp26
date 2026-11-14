CREATE TABLE IF NOT EXISTS research_sessions (
    id TEXT PRIMARY KEY REFERENCES entities(id),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    actor_id TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('controlled','live')),
    state TEXT NOT NULL DEFAULT 'ready',
    revision INTEGER NOT NULL DEFAULT 0,
    thread_id TEXT NOT NULL UNIQUE,
    graph_version TEXT NOT NULL,
    checkpoint_version TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    problem_id TEXT REFERENCES entities(id),
    problem_digest TEXT,
    input_heads TEXT NOT NULL,
    source_refs TEXT NOT NULL,
    plan_revision_id TEXT REFERENCES entities(id),
    pending_review_id TEXT REFERENCES entities(id),
    pending_review_digest TEXT,
    last_decision_id TEXT REFERENCES entities(id),
    active_action_id TEXT,
    consent_id TEXT REFERENCES entities(id),
    logical_turns INTEGER NOT NULL DEFAULT 0 CHECK(logical_turns>=0),
    tool_calls INTEGER NOT NULL DEFAULT 0 CHECK(tool_calls>=0),
    child_count INTEGER NOT NULL DEFAULT 0 CHECK(child_count>=0),
    physical_calls INTEGER NOT NULL DEFAULT 0 CHECK(physical_calls>=0),
    physical_allocation INTEGER NOT NULL DEFAULT 0 CHECK(physical_allocation>=0),
    input_allocation INTEGER NOT NULL DEFAULT 0 CHECK(input_allocation>=0),
    output_allocation INTEGER NOT NULL DEFAULT 0 CHECK(output_allocation>=0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_actions (
    id TEXT PRIMARY KEY REFERENCES entities(id),
    session_id TEXT NOT NULL REFERENCES research_sessions(id),
    operation_id TEXT NOT NULL UNIQUE REFERENCES operations(id),
    request_digest TEXT NOT NULL,
    state TEXT NOT NULL,
    budget TEXT NOT NULL,
    logical_turns INTEGER NOT NULL DEFAULT 0 CHECK(logical_turns>=0),
    tool_calls INTEGER NOT NULL DEFAULT 0 CHECK(tool_calls>=0),
    child_count INTEGER NOT NULL DEFAULT 0 CHECK(child_count>=0),
    physical_calls INTEGER NOT NULL DEFAULT 0 CHECK(physical_calls>=0),
    active_seconds REAL NOT NULL DEFAULT 0,
    lease_owner TEXT,
    lease_epoch INTEGER NOT NULL DEFAULT 0,
    lease_until REAL,
    acquired_at REAL,
    resume_required INTEGER NOT NULL DEFAULT 0,
    waiting_job_id TEXT REFERENCES jobs(id),
    error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS research_actions_queued ON research_actions(state,updated_at);
CREATE TABLE IF NOT EXISTS research_effects (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES research_sessions(id),
    action_id TEXT NOT NULL REFERENCES research_actions(id),
    effect_key TEXT NOT NULL,
    kind TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    plan_id TEXT REFERENCES entities(id),
    approval_id TEXT REFERENCES approvals(id),
    job_id TEXT REFERENCES jobs(id),
    result_id TEXT REFERENCES entities(id),
    state TEXT NOT NULL,
    response TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(session_id,effect_key)
);
CREATE TABLE IF NOT EXISTS research_events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES research_sessions(id),
    action_id TEXT REFERENCES research_actions(id),
    sequence INTEGER NOT NULL,
    body TEXT NOT NULL,
    UNIQUE(session_id,sequence)
);
CREATE TRIGGER IF NOT EXISTS research_events_no_update BEFORE UPDATE ON research_events
BEGIN SELECT RAISE(ABORT, 'immutable research event'); END;
CREATE TRIGGER IF NOT EXISTS research_events_no_delete BEFORE DELETE ON research_events
BEGIN SELECT RAISE(ABORT, 'immutable research event'); END;
CREATE TABLE IF NOT EXISTS research_checkpoint_blobs (
    thread_id TEXT NOT NULL REFERENCES research_sessions(thread_id),
    namespace TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    parent_id TEXT,
    codec_version TEXT NOT NULL,
    checkpoint BLOB NOT NULL,
    metadata BLOB NOT NULL,
    PRIMARY KEY(thread_id,namespace,checkpoint_id)
);
CREATE TABLE IF NOT EXISTS research_checkpoint_writes (
    thread_id TEXT NOT NULL REFERENCES research_sessions(thread_id),
    namespace TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    write_index INTEGER NOT NULL,
    channel TEXT NOT NULL,
    value BLOB NOT NULL,
    PRIMARY KEY(thread_id,namespace,checkpoint_id,task_id,write_index)
);
CREATE TABLE IF NOT EXISTS research_attempt_bindings (
    attempt_id TEXT PRIMARY KEY REFERENCES provider_attempts(id),
    session_id TEXT NOT NULL REFERENCES research_sessions(id),
    action_id TEXT NOT NULL REFERENCES research_actions(id),
    lease_epoch INTEGER NOT NULL
);
