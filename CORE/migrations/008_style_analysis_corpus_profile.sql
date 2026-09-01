CREATE TABLE style_measurements (
    id INTEGER PRIMARY KEY,
    analysis_run_id INTEGER NOT NULL
        REFERENCES style_analysis_runs(id) ON DELETE CASCADE,
    structure_revision_id INTEGER NOT NULL
        REFERENCES style_structure_revisions(id) ON DELETE CASCADE,
    target_type TEXT NOT NULL CHECK(target_type IN ('document','scene','character')),
    target_id INTEGER NOT NULL,
    metric_name TEXT NOT NULL,
    metric_version INTEGER NOT NULL,
    value_real REAL,
    value_int INTEGER,
    sample_count INTEGER NOT NULL CHECK(sample_count >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((value_real IS NOT NULL) != (value_int IS NOT NULL)),
    UNIQUE (analysis_run_id, target_type, target_id, metric_name, metric_version)
);

CREATE TABLE style_corpora (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE style_corpus_work_memberships (
    id INTEGER PRIMARY KEY,
    corpus_id INTEGER NOT NULL REFERENCES style_corpora(id) ON DELETE CASCADE,
    reference_work_id INTEGER NOT NULL
        REFERENCES style_reference_works(id) ON DELETE CASCADE,
    include_all_episodes INTEGER NOT NULL CHECK(include_all_episodes IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (corpus_id, reference_work_id)
);

CREATE TABLE style_corpus_episode_memberships (
    id INTEGER PRIMARY KEY,
    work_membership_id INTEGER NOT NULL
        REFERENCES style_corpus_work_memberships(id) ON DELETE CASCADE,
    reference_episode_id INTEGER NOT NULL
        REFERENCES style_reference_episodes(id) ON DELETE CASCADE,
    mode TEXT NOT NULL CHECK(mode IN ('include', 'exclude')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (work_membership_id, reference_episode_id)
);

CREATE TABLE style_aggregates (
    id INTEGER PRIMARY KEY,
    container_type TEXT NOT NULL CHECK(container_type IN ('reference_work', 'corpus')),
    container_id INTEGER NOT NULL,
    measurement_target_type TEXT NOT NULL CHECK(measurement_target_type IN ('document', 'scene')),
    filter_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(filter_json)),
    metric_name TEXT NOT NULL,
    metric_version INTEGER NOT NULL,
    statistic TEXT NOT NULL CHECK(statistic IN ('mean', 'median', 'p10', 'p25', 'p75', 'p90', 'stddev', 'min', 'max')),
    aggregate_policy_version INTEGER NOT NULL,
    value_real REAL NOT NULL,
    source_measurement_count INTEGER NOT NULL CHECK(source_measurement_count >= 0),
    sample_count INTEGER NOT NULL CHECK(sample_count >= 0),
    work_count INTEGER NOT NULL CHECK(work_count >= 0),
    skipped_target_count INTEGER NOT NULL CHECK(skipped_target_count >= 0),
    filter_state_fingerprint TEXT,
    input_fingerprint TEXT NOT NULL CHECK(length(input_fingerprint) = 64),
    warning_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(warning_json)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE style_aggregate_measurements (
    aggregate_id INTEGER NOT NULL REFERENCES style_aggregates(id) ON DELETE CASCADE,
    measurement_id INTEGER NOT NULL REFERENCES style_measurements(id) ON DELETE CASCADE,
    PRIMARY KEY (aggregate_id, measurement_id)
);

CREATE TABLE style_profiles (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    source_corpus_id INTEGER REFERENCES style_corpora(id) ON DELETE SET NULL,
    status TEXT NOT NULL CHECK(status IN ('draft', 'active', 'archived')),
    active_version_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE style_profile_versions (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES style_profiles(id) ON DELETE CASCADE,
    version_no INTEGER NOT NULL CHECK(version_no >= 1),
    parent_version_id INTEGER REFERENCES style_profile_versions(id) ON DELETE SET NULL,
    profile_generation_policy_version INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (profile_id, version_no)
);

CREATE TABLE style_rules (
    id INTEGER PRIMARY KEY,
    profile_version_id INTEGER NOT NULL REFERENCES style_profile_versions(id) ON DELETE CASCADE,
    target_scope TEXT NOT NULL CHECK(target_scope IN ('document', 'scene', 'character')),
    scope_selector_json TEXT NOT NULL CHECK(json_valid(scope_selector_json)),
    metric_name TEXT NOT NULL,
    metric_version INTEGER NOT NULL,
    preferred_value REAL,
    min_value REAL,
    max_value REAL,
    weight REAL NOT NULL DEFAULT 1.0,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
    severity_policy TEXT NOT NULL DEFAULT 'standard' CHECK(severity_policy = 'standard'),
    source_kind TEXT NOT NULL CHECK(source_kind IN ('corpus', 'manual')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        enabled = 0
        OR (
            min_value IS NOT NULL
            AND max_value IS NOT NULL
            AND min_value <= max_value
            AND (preferred_value IS NULL OR (min_value <= preferred_value AND preferred_value <= max_value))
        )
    )
);

CREATE TABLE style_rule_aggregate_sources (
    rule_id INTEGER NOT NULL REFERENCES style_rules(id) ON DELETE CASCADE,
    aggregate_id INTEGER NOT NULL REFERENCES style_aggregates(id) ON DELETE RESTRICT,
    role TEXT NOT NULL CHECK(role IN ('preferred', 'min', 'max')),
    PRIMARY KEY (rule_id, role)
);

CREATE TABLE style_lint_runs (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL
        REFERENCES style_documents(id) ON DELETE CASCADE,
    text_revision_id INTEGER NOT NULL
        REFERENCES style_text_revisions(id) ON DELETE CASCADE,
    structure_revision_id INTEGER NOT NULL
        REFERENCES style_structure_revisions(id) ON DELETE CASCADE,
    profile_id INTEGER NOT NULL REFERENCES style_profiles(id) ON DELETE RESTRICT,
    profile_version_id INTEGER NOT NULL
        REFERENCES style_profile_versions(id) ON DELETE RESTRICT,
    scene_id INTEGER REFERENCES style_scenes(id) ON DELETE CASCADE,
    basic_metric_run_id INTEGER REFERENCES style_analysis_runs(id) ON DELETE SET NULL,
    semantic_metric_run_id INTEGER REFERENCES style_analysis_runs(id) ON DELETE SET NULL,
    input_fingerprint TEXT NOT NULL CHECK(length(input_fingerprint) = 64),
    status TEXT NOT NULL CHECK(status IN ('running','succeeded','failed','cancelled')),
    warning_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(warning_json)),
    enabled_rule_count INTEGER NOT NULL CHECK(enabled_rule_count >= 0),
    applicable_rule_count INTEGER NOT NULL CHECK(applicable_rule_count >= 0),
    missing_rule_count INTEGER NOT NULL CHECK(missing_rule_count >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT
);

CREATE TABLE style_findings (
    id INTEGER PRIMARY KEY,
    lint_run_id INTEGER NOT NULL REFERENCES style_lint_runs(id) ON DELETE CASCADE,
    rule_id INTEGER NOT NULL REFERENCES style_rules(id) ON DELETE RESTRICT,
    target_type TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    metric_name TEXT NOT NULL,
    observed_value REAL NOT NULL,
    expected_min REAL NOT NULL,
    expected_max REAL NOT NULL,
    preferred_value REAL,
    deviation REAL NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('info','warning','strong_warning')),
    sort_score REAL NOT NULL,
    explanation_code TEXT NOT NULL,
    evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE style_finding_reviews (
    id INTEGER PRIMARY KEY,
    finding_id INTEGER NOT NULL REFERENCES style_findings(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK(status IN ('acknowledged','ignored')),
    note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
