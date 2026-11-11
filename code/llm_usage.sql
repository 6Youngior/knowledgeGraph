CREATE TABLE IF NOT EXISTS llm_requests (
    request_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    model TEXT NOT NULL,
    purpose TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    reserved_tokens INTEGER NOT NULL CHECK (reserved_tokens >= 0),
    input_tokens INTEGER,
    output_tokens INTEGER,
    total_tokens INTEGER CHECK (total_tokens >= 0),
    status TEXT NOT NULL DEFAULT 'pending'
);
