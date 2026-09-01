CREATE TABLE style_jobs (
    id INTEGER PRIMARY KEY,
    job_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(payload_json)),
    status TEXT NOT NULL,
    cancel_requested INTEGER NOT NULL DEFAULT 0
        CHECK (cancel_requested IN (0, 1)),
    progress_current INTEGER
        CHECK (progress_current IS NULL OR progress_current >= 0),
    progress_total INTEGER
        CHECK (progress_total IS NULL OR progress_total >= 0),
    result_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(result_json)),
    warning_json TEXT NOT NULL DEFAULT '[]'
        CHECK (json_valid(warning_json)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT,
    finished_at TEXT,
    error_code TEXT,
    error_message TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    CHECK (
        progress_current IS NULL
        OR progress_total IS NULL
        OR progress_current <= progress_total
    )
);

CREATE TABLE style_sources (
    id INTEGER PRIMARY KEY,
    source_type TEXT NOT NULL,
    external_work_id TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    adapter_id TEXT NOT NULL,
    adapter_version INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_type, external_work_id)
);

CREATE TABLE style_source_snapshots (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL
        REFERENCES style_sources(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    media_type TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    raw_payload BLOB NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(metadata_json)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_id, payload_sha256)
);

CREATE TABLE style_reference_works (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL UNIQUE
        REFERENCES style_sources(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    author_name TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(metadata_json)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE style_reference_episodes (
    id INTEGER PRIMARY KEY,
    reference_work_id INTEGER NOT NULL
        REFERENCES style_reference_works(id) ON DELETE CASCADE,
    external_episode_id TEXT NOT NULL,
    title TEXT NOT NULL,
    order_index INTEGER NOT NULL CHECK (order_index >= 1),
    latest_snapshot_id INTEGER NOT NULL
        REFERENCES style_source_snapshots(id) ON DELETE CASCADE,
    metadata_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(metadata_json)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (reference_work_id, external_episode_id),
    UNIQUE (reference_work_id, order_index)
);

CREATE TABLE style_documents (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('reference_episode', 'project_episode_draft')),
    reference_episode_id INTEGER
        REFERENCES style_reference_episodes(id) ON DELETE CASCADE,
    project_work_id INTEGER,
    project_episode_id INTEGER,
    current_text_revision_id INTEGER,
    current_structure_revision_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        (
            kind = 'reference_episode'
            AND reference_episode_id IS NOT NULL
            AND project_work_id IS NULL
            AND project_episode_id IS NULL
        )
        OR (
            kind = 'project_episode_draft'
            AND reference_episode_id IS NULL
            AND project_work_id IS NOT NULL
            AND project_episode_id IS NOT NULL
        )
    ),
    FOREIGN KEY (project_work_id, project_episode_id)
        REFERENCES episodes(work_id, id) ON DELETE CASCADE,
    UNIQUE (reference_episode_id),
    UNIQUE (project_work_id, project_episode_id)
);

CREATE TABLE style_text_revisions (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL
        REFERENCES style_documents(id) ON DELETE CASCADE,
    revision_no INTEGER NOT NULL CHECK (revision_no >= 1),
    source_snapshot_id INTEGER
        REFERENCES style_source_snapshots(id) ON DELETE CASCADE,
    project_draft_id INTEGER,
    raw_text TEXT NOT NULL,
    canonical_text TEXT NOT NULL,
    raw_sha256 TEXT NOT NULL CHECK (length(raw_sha256) = 64),
    canonical_sha256 TEXT NOT NULL CHECK (length(canonical_sha256) = 64),
    normalization_input_fingerprint TEXT NOT NULL
        CHECK (length(normalization_input_fingerprint) = 64),
    normalizer_id TEXT NOT NULL,
    normalizer_version INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(metadata_json)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((source_snapshot_id IS NULL) != (project_draft_id IS NULL)),
    UNIQUE (document_id, revision_no),
    UNIQUE (document_id, normalization_input_fingerprint)
);

CREATE INDEX idx_style_text_revisions_document_canonical_sha256
    ON style_text_revisions(document_id, canonical_sha256);

CREATE TABLE style_text_mappings (
    id INTEGER PRIMARY KEY,
    text_revision_id INTEGER NOT NULL
        REFERENCES style_text_revisions(id) ON DELETE CASCADE,
    segment_order INTEGER NOT NULL CHECK (segment_order >= 1),
    raw_start INTEGER NOT NULL,
    raw_end INTEGER NOT NULL,
    canonical_start INTEGER NOT NULL,
    canonical_end INTEGER NOT NULL,
    operation TEXT NOT NULL
        CHECK (operation IN ('identity', 'replace', 'delete', 'collapse')),
    UNIQUE (text_revision_id, segment_order),
    CHECK (raw_end >= raw_start),
    CHECK (canonical_end >= canonical_start),
    CHECK (raw_start != raw_end OR canonical_start != canonical_end)
);

CREATE TABLE style_structure_revisions (
    id INTEGER PRIMARY KEY,
    text_revision_id INTEGER NOT NULL
        REFERENCES style_text_revisions(id) ON DELETE CASCADE,
    revision_no INTEGER NOT NULL CHECK (revision_no >= 1),
    segmenter_id TEXT NOT NULL,
    segmenter_version INTEGER NOT NULL,
    source_kind TEXT NOT NULL
        CHECK (source_kind IN ('automatic', 'semantic', 'manual')),
    parent_structure_revision_id INTEGER
        REFERENCES style_structure_revisions(id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL CHECK (length(fingerprint) = 64),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (text_revision_id, revision_no),
    UNIQUE (text_revision_id, fingerprint)
);

CREATE TABLE style_scenes (
    id INTEGER PRIMARY KEY,
    structure_revision_id INTEGER NOT NULL
        REFERENCES style_structure_revisions(id) ON DELETE CASCADE,
    order_index INTEGER NOT NULL CHECK (order_index >= 1),
    start_cp INTEGER NOT NULL,
    end_cp INTEGER NOT NULL,
    UNIQUE (structure_revision_id, order_index)
);

CREATE TABLE style_blocks (
    id INTEGER PRIMARY KEY,
    structure_revision_id INTEGER NOT NULL
        REFERENCES style_structure_revisions(id) ON DELETE CASCADE,
    scene_id INTEGER
        REFERENCES style_scenes(id) ON DELETE CASCADE,
    order_index INTEGER NOT NULL CHECK (order_index >= 1),
    paragraph_index INTEGER NOT NULL CHECK (paragraph_index >= 1),
    block_type TEXT NOT NULL
        CHECK (block_type IN ('dialogue', 'narration', 'heading', 'separator', 'unknown')),
    start_cp INTEGER NOT NULL,
    end_cp INTEGER NOT NULL,
    UNIQUE (structure_revision_id, order_index)
);

CREATE INDEX idx_style_blocks_structure_scene_order
    ON style_blocks(structure_revision_id, scene_id, order_index);

CREATE TABLE style_sentences (
    id INTEGER PRIMARY KEY,
    block_id INTEGER NOT NULL
        REFERENCES style_blocks(id) ON DELETE CASCADE,
    order_index INTEGER NOT NULL CHECK (order_index >= 1),
    start_cp INTEGER NOT NULL,
    end_cp INTEGER NOT NULL,
    UNIQUE (block_id, order_index)
);

CREATE TABLE style_analysis_runs (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL
        REFERENCES style_documents(id) ON DELETE CASCADE,
    analyzer_id TEXT NOT NULL,
    analyzer_version INTEGER NOT NULL,
    text_revision_id INTEGER NOT NULL
        REFERENCES style_text_revisions(id) ON DELETE CASCADE,
    structure_revision_id INTEGER NOT NULL
        REFERENCES style_structure_revisions(id) ON DELETE CASCADE,
    status TEXT NOT NULL
        CHECK (status IN ('running', 'succeeded', 'partial', 'failed', 'cancelled')),
    fingerprint TEXT NOT NULL CHECK (length(fingerprint) = 64),
    config_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(config_json)),
    analysis_policy_version INTEGER,
    policy_input_fingerprint TEXT
        CHECK (
            policy_input_fingerprint IS NULL
            OR length(policy_input_fingerprint) = 64
        ),
    state_fingerprint TEXT
        CHECK (state_fingerprint IS NULL OR length(state_fingerprint) = 64),
    registry_input_fingerprint TEXT
        CHECK (
            registry_input_fingerprint IS NULL
            OR length(registry_input_fingerprint) = 64
        ),
    model_provider TEXT,
    model_id TEXT,
    prompt_id TEXT,
    prompt_version INTEGER,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error_code TEXT,
    error_message TEXT,
    warning_json TEXT NOT NULL DEFAULT '[]'
        CHECK (json_valid(warning_json)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_style_analysis_runs_document_input
    ON style_analysis_runs(
        document_id,
        analyzer_id,
        text_revision_id,
        structure_revision_id,
        created_at
    );

CREATE INDEX idx_style_analysis_runs_fingerprint_status
    ON style_analysis_runs(fingerprint, status);

CREATE TABLE style_analysis_run_dependencies (
    run_id INTEGER NOT NULL
        REFERENCES style_analysis_runs(id) ON DELETE CASCADE,
    dependency_run_id INTEGER NOT NULL
        REFERENCES style_analysis_runs(id) ON DELETE CASCADE,
    PRIMARY KEY (run_id, dependency_run_id),
    CHECK (run_id != dependency_run_id)
);

CREATE TABLE style_structure_analysis_sources (
    structure_revision_id INTEGER NOT NULL
        REFERENCES style_structure_revisions(id) ON DELETE CASCADE,
    boundary_analysis_run_id INTEGER NOT NULL
        REFERENCES style_analysis_runs(id) ON DELETE CASCADE,
    PRIMARY KEY (structure_revision_id, boundary_analysis_run_id)
);
