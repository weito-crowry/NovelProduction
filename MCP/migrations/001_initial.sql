CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    checksum TEXT NOT NULL
);

CREATE TABLE works (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE world_facts (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL,
    fact_key TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    canon_status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE,
    UNIQUE (work_id, fact_key)
);

CREATE TABLE timeline_events (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL,
    event_key TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    chronology_sort_key TEXT NOT NULL,
    canon_status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE,
    UNIQUE (work_id, event_key)
);

CREATE TABLE timeline_event_participants (
    id INTEGER PRIMARY KEY,
    timeline_event_id INTEGER NOT NULL,
    participant_label TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (timeline_event_id) REFERENCES timeline_events(id) ON DELETE CASCADE,
    UNIQUE (timeline_event_id, participant_label, role)
);

CREATE TABLE timeline_event_relations (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL,
    source_event_id INTEGER NOT NULL,
    target_event_id INTEGER NOT NULL,
    relation_type TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE,
    FOREIGN KEY (source_event_id) REFERENCES timeline_events(id) ON DELETE CASCADE,
    FOREIGN KEY (target_event_id) REFERENCES timeline_events(id) ON DELETE CASCADE,
    UNIQUE (source_event_id, target_event_id, relation_type)
);

CREATE TABLE characters (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL,
    character_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    summary TEXT NOT NULL,
    canon_status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE,
    UNIQUE (work_id, character_key)
);

CREATE TABLE relationships (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL,
    source_character_id INTEGER NOT NULL,
    target_character_id INTEGER NOT NULL,
    relationship_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    canon_status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version INTEGER NOT NULL DEFAULT 1,
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
    version INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE,
    UNIQUE (work_id, decision_key)
);

CREATE TABLE canon_decision_changes (
    id INTEGER PRIMARY KEY,
    canon_decision_id INTEGER NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    before_payload TEXT,
    after_payload TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (canon_decision_id) REFERENCES canon_decisions(id) ON DELETE CASCADE
);

CREATE INDEX idx_world_facts_work_id ON world_facts(work_id);
CREATE INDEX idx_timeline_events_work_id_sort_key ON timeline_events(work_id, chronology_sort_key);
CREATE INDEX idx_timeline_event_relations_work_id ON timeline_event_relations(work_id);
CREATE INDEX idx_characters_work_id ON characters(work_id);
CREATE INDEX idx_relationships_work_id ON relationships(work_id);
CREATE INDEX idx_canon_decisions_work_id ON canon_decisions(work_id);
