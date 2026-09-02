CREATE TABLE style_entities (
    id INTEGER PRIMARY KEY,
    reference_work_id INTEGER REFERENCES style_reference_works(id) ON DELETE CASCADE,
    document_id INTEGER REFERENCES style_documents(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    origin TEXT NOT NULL CHECK(origin IN ('inferred', 'manual')),
    created_by_run_id INTEGER REFERENCES style_analysis_runs(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((reference_work_id IS NOT NULL) != (document_id IS NOT NULL))
);

CREATE TABLE style_mentions (
    id INTEGER PRIMARY KEY,
    structure_revision_id INTEGER NOT NULL
        REFERENCES style_structure_revisions(id) ON DELETE CASCADE,
    scene_id INTEGER NOT NULL REFERENCES style_scenes(id) ON DELETE CASCADE,
    block_id INTEGER NOT NULL REFERENCES style_blocks(id) ON DELETE CASCADE,
    start_cp INTEGER NOT NULL,
    end_cp INTEGER NOT NULL,
    surface TEXT NOT NULL,
    mention_type TEXT NOT NULL,
    entity_type_candidate TEXT NOT NULL,
    canonical_name_candidate TEXT NOT NULL,
    confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
    analysis_run_id INTEGER NOT NULL
        REFERENCES style_analysis_runs(id) ON DELETE CASCADE,
    CHECK (start_cp >= 0 AND end_cp > start_cp),
    CHECK (end_cp >= start_cp)
);

CREATE TABLE style_entity_aliases (
    id INTEGER PRIMARY KEY,
    entity_id INTEGER NOT NULL REFERENCES style_entities(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    alias_kind TEXT NOT NULL,
    origin TEXT NOT NULL CHECK(origin IN ('inferred', 'manual')),
    analysis_run_id INTEGER REFERENCES style_analysis_runs(id) ON DELETE CASCADE,
    source_mention_id INTEGER REFERENCES style_mentions(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_style_entity_aliases_entity_alias
    ON style_entity_aliases(entity_id, alias);

CREATE TABLE style_entity_character_links (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES style_documents(id) ON DELETE CASCADE,
    style_entity_id INTEGER NOT NULL UNIQUE
        REFERENCES style_entities(id) ON DELETE CASCADE,
    project_character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (document_id, project_character_id)
);

CREATE TABLE style_terms (
    id INTEGER PRIMARY KEY,
    reference_work_id INTEGER REFERENCES style_reference_works(id) ON DELETE CASCADE,
    document_id INTEGER REFERENCES style_documents(id) ON DELETE CASCADE,
    canonical_label TEXT NOT NULL,
    term_type TEXT NOT NULL,
    origin TEXT NOT NULL CHECK(origin IN ('inferred', 'manual')),
    created_by_run_id INTEGER REFERENCES style_analysis_runs(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((reference_work_id IS NOT NULL) != (document_id IS NOT NULL))
);

CREATE TABLE style_term_aliases (
    id INTEGER PRIMARY KEY,
    term_id INTEGER NOT NULL REFERENCES style_terms(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    origin TEXT NOT NULL CHECK(origin IN ('inferred', 'manual')),
    analysis_run_id INTEGER REFERENCES style_analysis_runs(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_style_term_aliases_term_alias
    ON style_term_aliases(term_id, alias);

CREATE TABLE style_term_mentions (
    id INTEGER PRIMARY KEY,
    term_id INTEGER NOT NULL REFERENCES style_terms(id) ON DELETE CASCADE,
    structure_revision_id INTEGER NOT NULL
        REFERENCES style_structure_revisions(id) ON DELETE CASCADE,
    scene_id INTEGER NOT NULL REFERENCES style_scenes(id) ON DELETE CASCADE,
    block_id INTEGER NOT NULL REFERENCES style_blocks(id) ON DELETE CASCADE,
    start_cp INTEGER NOT NULL,
    end_cp INTEGER NOT NULL,
    surface TEXT NOT NULL,
    analysis_run_id INTEGER NOT NULL
        REFERENCES style_analysis_runs(id) ON DELETE CASCADE,
    CHECK (start_cp >= 0 AND end_cp > start_cp)
);

CREATE TABLE style_annotations (
    id INTEGER PRIMARY KEY,
    annotation_type TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id INTEGER NOT NULL,
    value_json TEXT NOT NULL CHECK(json_valid(value_json)),
    confidence REAL CHECK(confidence IS NULL OR confidence BETWEEN 0 AND 1),
    analysis_run_id INTEGER NOT NULL
        REFERENCES style_analysis_runs(id) ON DELETE CASCADE,
    start_cp INTEGER,
    end_cp INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        (start_cp IS NULL AND end_cp IS NULL)
        OR (start_cp IS NOT NULL AND end_cp IS NOT NULL AND start_cp >= 0 AND end_cp > start_cp)
    )
);

CREATE UNIQUE INDEX idx_style_annotations_one_per_subject
    ON style_annotations(analysis_run_id, subject_type, subject_id, annotation_type)
    WHERE annotation_type IN (
        'mention.entity_resolution',
        'speaker',
        'term.novelty',
        'term_explanation',
        'scene.pov',
        'scene.function',
        'scene.tone',
        'scene.pace',
        'scene.information_load',
        'scene.interaction',
        'block.semantic_primary'
    );

CREATE TABLE style_review_items (
    id INTEGER PRIMARY KEY,
    document_id INTEGER REFERENCES style_documents(id) ON DELETE CASCADE,
    reference_work_id INTEGER REFERENCES style_reference_works(id) ON DELETE CASCADE,
    item_type TEXT NOT NULL CHECK(item_type IN (
        'scene_boundary_proposal', 'structure_warning', 'stale_override', 'manual_review'
    )),
    subject_type TEXT NOT NULL,
    subject_id INTEGER NOT NULL,
    analysis_run_id INTEGER REFERENCES style_analysis_runs(id) ON DELETE SET NULL,
    priority TEXT NOT NULL DEFAULT 'normal' CHECK(priority IN ('normal', 'high')),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK(status IN ('open', 'resolved', 'ignored', 'superseded')),
    reason_code TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(evidence_json)),
    resolution_note TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT,
    CHECK ((document_id IS NOT NULL) != (reference_work_id IS NOT NULL))
);

CREATE INDEX idx_style_review_items_status_priority_id
    ON style_review_items(status, priority, id);
CREATE INDEX idx_style_review_items_document_status
    ON style_review_items(document_id, status);
CREATE INDEX idx_style_review_items_work_status
    ON style_review_items(reference_work_id, status);

CREATE TABLE style_inference_reviews (
    id INTEGER PRIMARY KEY,
    document_id INTEGER REFERENCES style_documents(id) ON DELETE CASCADE,
    reference_work_id INTEGER REFERENCES style_reference_works(id) ON DELETE CASCADE,
    subject_type TEXT NOT NULL,
    subject_id INTEGER NOT NULL,
    field_path TEXT NOT NULL,
    analysis_run_id INTEGER NOT NULL
        REFERENCES style_analysis_runs(id) ON DELETE CASCADE,
    review_status TEXT NOT NULL CHECK(review_status IN ('confirmed', 'rejected')),
    note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((document_id IS NOT NULL) != (reference_work_id IS NOT NULL))
);

CREATE INDEX idx_style_inference_reviews_subject
    ON style_inference_reviews(
        analysis_run_id, subject_type, subject_id, field_path, created_at, id
    );

CREATE TABLE style_manual_overrides (
    id INTEGER PRIMARY KEY,
    document_id INTEGER REFERENCES style_documents(id) ON DELETE CASCADE,
    reference_work_id INTEGER REFERENCES style_reference_works(id) ON DELETE CASCADE,
    subject_type TEXT NOT NULL,
    subject_id INTEGER NOT NULL,
    field_path TEXT NOT NULL,
    operation TEXT NOT NULL CHECK(operation IN ('set', 'clear', 'revert')),
    value_json TEXT,
    base_analysis_run_id INTEGER REFERENCES style_analysis_runs(id) ON DELETE SET NULL,
    structure_revision_id INTEGER REFERENCES style_structure_revisions(id) ON DELETE SET NULL,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((document_id IS NOT NULL) != (reference_work_id IS NOT NULL)),
    CHECK (
        (operation = 'set' AND value_json IS NOT NULL AND json_valid(value_json))
        OR (operation IN ('clear', 'revert') AND value_json IS NULL)
    )
);
