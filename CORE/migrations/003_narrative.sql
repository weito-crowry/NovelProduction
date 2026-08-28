CREATE TABLE chapters (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 1),
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    purpose TEXT NOT NULL DEFAULT '',
    canon_status TEXT NOT NULL DEFAULT 'draft'
        CHECK (canon_status IN ('idea', 'draft', 'canon', 'deprecated')),
    production_status TEXT NOT NULL DEFAULT 'planned'
        CHECK (production_status IN ('planned', 'outlined', 'drafting', 'revising', 'final')),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE,
    UNIQUE (work_id, id),
    UNIQUE (work_id, position)
);

CREATE TABLE episodes (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL,
    chapter_id INTEGER NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 1),
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    purpose TEXT NOT NULL DEFAULT '',
    foreshadowing_notes_json TEXT NOT NULL DEFAULT '[]'
        CHECK (json_valid(foreshadowing_notes_json)),
    canon_status TEXT NOT NULL DEFAULT 'draft'
        CHECK (canon_status IN ('idea', 'draft', 'canon', 'deprecated')),
    production_status TEXT NOT NULL DEFAULT 'planned'
        CHECK (production_status IN ('planned', 'outlined', 'drafting', 'revising', 'final')),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (work_id, chapter_id) REFERENCES chapters(work_id, id)
        ON DELETE CASCADE,
    UNIQUE (work_id, id),
    UNIQUE (chapter_id, position)
);

CREATE TABLE scenes (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL,
    episode_id INTEGER NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 1),
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    purpose TEXT NOT NULL DEFAULT '',
    canon_status TEXT NOT NULL DEFAULT 'draft'
        CHECK (canon_status IN ('idea', 'draft', 'canon', 'deprecated')),
    production_status TEXT NOT NULL DEFAULT 'planned'
        CHECK (production_status IN ('planned', 'outlined', 'drafting', 'revising', 'final')),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (work_id, episode_id) REFERENCES episodes(work_id, id)
        ON DELETE CASCADE,
    UNIQUE (work_id, id),
    UNIQUE (episode_id, position)
);

CREATE TABLE character_states (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL,
    character_id INTEGER NOT NULL,
    episode_id INTEGER NOT NULL,
    physical_state TEXT NOT NULL DEFAULT '',
    emotional_state TEXT NOT NULL DEFAULT '',
    beliefs_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(beliefs_json)),
    location_world_fact_id INTEGER,
    state_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(state_json)),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (work_id, character_id) REFERENCES characters(work_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (work_id, episode_id) REFERENCES episodes(work_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (work_id, location_world_fact_id) REFERENCES world_facts(work_id, id)
        ON DELETE SET NULL,
    UNIQUE (work_id, id),
    UNIQUE (character_id, episode_id)
);

CREATE TABLE information_items (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL,
    statement TEXT NOT NULL,
    truth_status TEXT NOT NULL DEFAULT 'uncertain'
        CHECK (truth_status IN ('true', 'false', 'uncertain', 'subjective')),
    authoring_guard TEXT NOT NULL DEFAULT '',
    notes_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(notes_json)),
    canon_status TEXT NOT NULL DEFAULT 'draft'
        CHECK (canon_status IN ('idea', 'draft', 'canon', 'deprecated')),
    importance INTEGER NOT NULL DEFAULT 0 CHECK (importance >= 0),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE,
    UNIQUE (work_id, id)
);

CREATE TABLE reader_disclosures (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL,
    information_item_id INTEGER NOT NULL,
    episode_id INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (work_id, information_item_id) REFERENCES information_items(work_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (work_id, episode_id) REFERENCES episodes(work_id, id)
        ON DELETE CASCADE,
    UNIQUE (work_id, id),
    UNIQUE (work_id, information_item_id)
);

CREATE TABLE character_knowledge_events (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL,
    character_id INTEGER NOT NULL,
    information_item_id INTEGER NOT NULL,
    episode_id INTEGER NOT NULL,
    knowledge_state TEXT NOT NULL
        CHECK (knowledge_state IN ('suspects', 'believes', 'knows', 'confirmed', 'doubts', 'rejected')),
    note TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (work_id, character_id) REFERENCES characters(work_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (work_id, information_item_id) REFERENCES information_items(work_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (work_id, episode_id) REFERENCES episodes(work_id, id)
        ON DELETE CASCADE,
    UNIQUE (work_id, id),
    UNIQUE (character_id, information_item_id, episode_id)
);

CREATE TABLE episode_characters (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL,
    episode_id INTEGER NOT NULL,
    character_id INTEGER NOT NULL,
    role TEXT NOT NULL DEFAULT 'participant'
        CHECK (length(role) BETWEEN 1 AND 120),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (work_id, episode_id) REFERENCES episodes(work_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (work_id, character_id) REFERENCES characters(work_id, id)
        ON DELETE CASCADE,
    UNIQUE (work_id, id),
    UNIQUE (episode_id, character_id)
);

CREATE TABLE episode_world_facts (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL,
    episode_id INTEGER NOT NULL,
    world_fact_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (work_id, episode_id) REFERENCES episodes(work_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (work_id, world_fact_id) REFERENCES world_facts(work_id, id)
        ON DELETE CASCADE,
    UNIQUE (work_id, id),
    UNIQUE (episode_id, world_fact_id)
);

CREATE TABLE episode_timeline_events (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL,
    episode_id INTEGER NOT NULL,
    timeline_event_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (work_id, episode_id) REFERENCES episodes(work_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (work_id, timeline_event_id) REFERENCES timeline_events(work_id, id)
        ON DELETE CASCADE,
    UNIQUE (work_id, id),
    UNIQUE (episode_id, timeline_event_id)
);

CREATE TABLE episode_information (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL,
    episode_id INTEGER NOT NULL,
    information_item_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (work_id, episode_id) REFERENCES episodes(work_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (work_id, information_item_id) REFERENCES information_items(work_id, id)
        ON DELETE CASCADE,
    UNIQUE (work_id, id),
    UNIQUE (episode_id, information_item_id)
);

CREATE INDEX idx_chapters_work_position ON chapters(work_id, position, id);
CREATE INDEX idx_episodes_chapter_position ON episodes(chapter_id, position, id);
CREATE INDEX idx_scenes_episode_position ON scenes(episode_id, position, id);
CREATE INDEX idx_character_states_work_character ON character_states(work_id, character_id, id);
CREATE INDEX idx_character_states_work_episode ON character_states(work_id, episode_id, id);
CREATE INDEX idx_reader_disclosures_work_episode ON reader_disclosures(work_id, episode_id, id);
CREATE INDEX idx_knowledge_events_work_character ON character_knowledge_events(work_id, character_id, id);
CREATE INDEX idx_knowledge_events_work_episode ON character_knowledge_events(work_id, episode_id, id);

CREATE TABLE relationships_phase2 (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL,
    source_character_id INTEGER NOT NULL,
    target_character_id INTEGER NOT NULL,
    relationship_type TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    canon_status TEXT NOT NULL DEFAULT 'draft'
        CHECK (canon_status IN ('idea', 'draft', 'canon', 'deprecated')),
    valid_from_episode_id INTEGER,
    valid_to_episode_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE,
    FOREIGN KEY (work_id, source_character_id) REFERENCES characters(work_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (work_id, target_character_id) REFERENCES characters(work_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (work_id, valid_from_episode_id) REFERENCES episodes(work_id, id),
    FOREIGN KEY (work_id, valid_to_episode_id) REFERENCES episodes(work_id, id),
    UNIQUE (work_id, id),
    CHECK (valid_from_episode_id IS NULL OR valid_from_episode_id >= 1),
    CHECK (valid_to_episode_id IS NULL OR valid_to_episode_id >= 1)
);

INSERT INTO relationships_phase2
    (id, work_id, source_character_id, target_character_id, relationship_type,
     description, canon_status, valid_from_episode_id, valid_to_episode_id,
     created_at, updated_at, version)
SELECT id, work_id, source_character_id, target_character_id, relationship_type,
       description, canon_status, NULL, NULL, created_at, updated_at, version
FROM relationships;

DROP TABLE relationships;
ALTER TABLE relationships_phase2 RENAME TO relationships;

CREATE INDEX idx_relationships_work_id ON relationships(work_id);
CREATE INDEX idx_relationships_work_type ON relationships(work_id, relationship_type, id);
CREATE INDEX idx_relationships_work_interval
    ON relationships(work_id, source_character_id, target_character_id, relationship_type, id);

CREATE TABLE canon_decision_changes_phase2 (
    id INTEGER PRIMARY KEY,
    canon_decision_id INTEGER NOT NULL,
    entity_type TEXT NOT NULL
        CHECK (entity_type IN (
            'world_fact', 'timeline_event', 'character', 'relationship',
            'chapter', 'episode', 'scene', 'information_item'
        )),
    entity_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    before_payload TEXT,
    after_payload TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (canon_decision_id) REFERENCES canon_decisions(id) ON DELETE CASCADE
);

INSERT INTO canon_decision_changes_phase2
    (id, canon_decision_id, entity_type, entity_id, action,
     before_payload, after_payload, created_at)
SELECT id, canon_decision_id, entity_type, entity_id, action,
       before_payload, after_payload, created_at
FROM canon_decision_changes;

DROP TABLE canon_decision_changes;
ALTER TABLE canon_decision_changes_phase2 RENAME TO canon_decision_changes;
