CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    checksum TEXT NOT NULL
);

CREATE TABLE works (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    working_title TEXT NOT NULL,
    genre TEXT NOT NULL DEFAULT '',
    premise TEXT NOT NULL DEFAULT '',
    themes_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(themes_json)),
    description TEXT NOT NULL DEFAULT '',
    production_status TEXT NOT NULL DEFAULT 'planned'
        CHECK (production_status IN ('planned', 'outlined', 'drafting', 'revising', 'final')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1)
);

CREATE TABLE world_facts (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL,
    topic_key TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    title TEXT NOT NULL,
    statement TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    valid_from TEXT,
    valid_to TEXT,
    canon_status TEXT NOT NULL DEFAULT 'draft'
        CHECK (canon_status IN ('idea', 'draft', 'canon', 'deprecated')),
    importance INTEGER NOT NULL DEFAULT 0 CHECK (importance >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE,
    UNIQUE (work_id, id),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_from <= valid_to)
);

CREATE TABLE timeline_events (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL,
    event_key TEXT NOT NULL,
    time_start TEXT,
    time_end TEXT,
    date_precision TEXT NOT NULL DEFAULT 'unknown'
        CHECK (date_precision IN ('unknown', 'year', 'season', 'month', 'day')),
    date_display TEXT NOT NULL DEFAULT '正確な日付不明',
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'general',
    location_world_fact_id INTEGER,
    cause_summary TEXT NOT NULL DEFAULT '',
    consequence_summary TEXT NOT NULL DEFAULT '',
    canon_status TEXT NOT NULL DEFAULT 'draft'
        CHECK (canon_status IN ('idea', 'draft', 'canon', 'deprecated')),
    importance INTEGER NOT NULL DEFAULT 0 CHECK (importance >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE,
    FOREIGN KEY (location_world_fact_id) REFERENCES world_facts(id)
        ON DELETE SET NULL,
    UNIQUE (work_id, event_key),
    UNIQUE (work_id, id),
    CHECK (
        (time_start IS NULL AND time_end IS NULL)
        OR (time_start IS NOT NULL AND time_end IS NOT NULL AND time_start <= time_end)
    )
);

CREATE TABLE characters (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL,
    character_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    entity_type TEXT NOT NULL DEFAULT 'human'
        CHECK (entity_type IN ('human', 'ai', 'organization')),
    description TEXT NOT NULL DEFAULT '',
    birth_date TEXT,
    death_date TEXT,
    physical_description TEXT NOT NULL DEFAULT '',
    occupation TEXT NOT NULL DEFAULT '',
    core_beliefs TEXT NOT NULL DEFAULT '',
    goals TEXT NOT NULL DEFAULT '',
    fears TEXT NOT NULL DEFAULT '',
    personality TEXT NOT NULL DEFAULT '',
    speech_style TEXT NOT NULL DEFAULT '',
    ai_attitude TEXT NOT NULL DEFAULT '',
    genetic_modification_attitude TEXT NOT NULL DEFAULT '',
    private_notes TEXT NOT NULL DEFAULT '',
    profile_json TEXT NOT NULL DEFAULT '{}',
    canon_status TEXT NOT NULL DEFAULT 'draft'
        CHECK (canon_status IN ('idea', 'draft', 'canon', 'deprecated')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE,
    UNIQUE (work_id, character_key),
    UNIQUE (work_id, id)
);

CREATE TABLE timeline_event_participants (
    id INTEGER PRIMARY KEY,
    event_id INTEGER NOT NULL,
    character_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (event_id) REFERENCES timeline_events(id) ON DELETE CASCADE,
    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE,
    UNIQUE (event_id, character_id, role)
);

CREATE TABLE timeline_event_relations (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL,
    source_event_id INTEGER NOT NULL,
    target_event_id INTEGER NOT NULL,
    relation_type TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE,
    FOREIGN KEY (source_event_id) REFERENCES timeline_events(id) ON DELETE CASCADE,
    FOREIGN KEY (target_event_id) REFERENCES timeline_events(id) ON DELETE CASCADE,
    UNIQUE (source_event_id, target_event_id, relation_type)
);

CREATE TABLE relationships (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL,
    source_character_id INTEGER NOT NULL,
    target_character_id INTEGER NOT NULL,
    relationship_type TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    canon_status TEXT NOT NULL DEFAULT 'draft'
        CHECK (canon_status IN ('idea', 'draft', 'canon', 'deprecated')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE,
    FOREIGN KEY (source_character_id) REFERENCES characters(id) ON DELETE CASCADE,
    FOREIGN KEY (target_character_id) REFERENCES characters(id) ON DELETE CASCADE,
    UNIQUE (source_character_id, target_character_id, relationship_type)
);

CREATE TABLE canon_decisions (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL,
    decision_key TEXT NOT NULL,
    summary TEXT NOT NULL,
    reason TEXT,
    decided_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE,
    UNIQUE (work_id, decision_key)
);

CREATE TABLE canon_decision_changes (
    id INTEGER PRIMARY KEY,
    canon_decision_id INTEGER NOT NULL,
    entity_type TEXT NOT NULL
        CHECK (entity_type IN ('world_fact', 'timeline_event', 'character', 'relationship')),
    entity_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    before_payload TEXT,
    after_payload TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (canon_decision_id) REFERENCES canon_decisions(id) ON DELETE CASCADE
);

CREATE INDEX idx_world_facts_work_id ON world_facts(work_id);
CREATE INDEX idx_timeline_events_work_id ON timeline_events(work_id, id);
CREATE INDEX idx_timeline_event_relations_work_id ON timeline_event_relations(work_id);
CREATE INDEX idx_characters_work_id ON characters(work_id);
CREATE INDEX idx_relationships_work_id ON relationships(work_id);
CREATE INDEX idx_canon_decisions_work_id ON canon_decisions(work_id);
