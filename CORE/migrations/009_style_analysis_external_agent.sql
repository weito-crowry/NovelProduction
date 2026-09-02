CREATE TABLE style_external_analysis_sessions (
    id INTEGER PRIMARY KEY,
    document_id INTEGER REFERENCES style_documents(id) ON DELETE CASCADE,
    reference_work_id INTEGER REFERENCES style_reference_works(id) ON DELETE CASCADE,
    executor_provider TEXT NOT NULL CHECK(executor_provider = 'chatgpt_mcp'),
    executor_model_id TEXT NOT NULL CHECK(length(executor_model_id) > 0),
    runtime_contract_fingerprint TEXT NOT NULL
        CHECK(length(runtime_contract_fingerprint) = 64),
    status TEXT NOT NULL
        CHECK(status IN ('active', 'succeeded', 'partial', 'failed', 'cancelled')),
    request_json TEXT NOT NULL CHECK(json_valid(request_json)),
    snapshot_json TEXT NOT NULL CHECK(json_valid(snapshot_json)),
    cursor_json TEXT NOT NULL CHECK(json_valid(cursor_json)),
    result_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(result_json)),
    warning_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(warning_json)),
    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    CHECK ((document_id IS NOT NULL) != (reference_work_id IS NOT NULL)),
    CHECK (
        (status = 'active' AND finished_at IS NULL)
        OR (status <> 'active' AND finished_at IS NOT NULL)
    )
);

CREATE INDEX idx_external_sessions_status_id
    ON style_external_analysis_sessions(status, id);
CREATE INDEX idx_external_sessions_document_status
    ON style_external_analysis_sessions(document_id, status);
CREATE INDEX idx_external_sessions_reference_work_status
    ON style_external_analysis_sessions(reference_work_id, status);

CREATE TABLE style_external_analysis_tasks (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL
        REFERENCES style_external_analysis_sessions(id) ON DELETE CASCADE,
    analysis_run_id INTEGER NOT NULL
        REFERENCES style_analysis_runs(id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL CHECK(sequence_no >= 1),
    call_key TEXT NOT NULL,
    analyzer_id TEXT NOT NULL,
    analyzer_version INTEGER NOT NULL CHECK(analyzer_version >= 1),
    prompt_id TEXT NOT NULL,
    prompt_version INTEGER NOT NULL CHECK(prompt_version >= 1),
    response_contract_id TEXT NOT NULL,
    attempt_no INTEGER NOT NULL CHECK(attempt_no IN (1, 2)),
    parent_task_id INTEGER REFERENCES style_external_analysis_tasks(id) ON DELETE CASCADE,
    request_fingerprint TEXT NOT NULL CHECK(length(request_fingerprint) = 64),
    request_json TEXT NOT NULL CHECK(json_valid(request_json)),
    response_json TEXT CHECK(response_json IS NULL OR json_valid(response_json)),
    response_fingerprint TEXT
        CHECK(response_fingerprint IS NULL OR length(response_fingerprint) = 64),
    status TEXT NOT NULL
        CHECK(status IN ('pending', 'accepted', 'repair_required', 'rejected', 'superseded')),
    error_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(error_json)),
    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    submitted_at TEXT,
    CHECK (
        (attempt_no = 1 AND parent_task_id IS NULL)
        OR (attempt_no = 2 AND parent_task_id IS NOT NULL)
    ),
    CHECK (
        status = 'pending' AND response_json IS NULL
        OR status IN ('accepted', 'repair_required', 'rejected')
            AND response_json IS NOT NULL
            AND response_fingerprint IS NOT NULL
            AND submitted_at IS NOT NULL
        OR status = 'superseded'
    ),
    UNIQUE (session_id, sequence_no),
    UNIQUE (session_id, call_key, attempt_no)
);

CREATE UNIQUE INDEX idx_external_tasks_one_pending
    ON style_external_analysis_tasks(session_id)
    WHERE status = 'pending';

CREATE TABLE style_external_analysis_session_runs (
    session_id INTEGER NOT NULL
        REFERENCES style_external_analysis_sessions(id) ON DELETE CASCADE,
    run_id INTEGER NOT NULL
        REFERENCES style_analysis_runs(id) ON DELETE CASCADE,
    run_role TEXT NOT NULL CHECK(run_role IN ('created', 'reused')),
    PRIMARY KEY (session_id, run_id)
);
