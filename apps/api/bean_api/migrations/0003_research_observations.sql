CREATE TABLE IF NOT EXISTS research_event_observations (
    session_id TEXT NOT NULL REFERENCES research_sessions(id),
    observation_key TEXT NOT NULL,
    event_id TEXT NOT NULL REFERENCES research_events(id),
    PRIMARY KEY(session_id,observation_key)
);
