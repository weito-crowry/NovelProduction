DROP TRIGGER drafts_append_only_update;

DROP TRIGGER drafts_append_only_delete;

UPDATE drafts SET parent_draft_id = NULL;

DELETE FROM drafts;

DROP TABLE drafts;

CREATE TABLE drafts (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL,
    episode_id INTEGER NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    parent_draft_id INTEGER,
    document_json TEXT NOT NULL CHECK (json_valid(document_json)),
    source_agent TEXT
        CHECK (source_agent IS NULL OR length(source_agent) BETWEEN 1 AND 120),
    change_summary TEXT NOT NULL DEFAULT '' CHECK (length(change_summary) <= 1000),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (work_id, episode_id) REFERENCES episodes(work_id, id)
        ON DELETE CASCADE,
    UNIQUE (work_id, id),
    UNIQUE (episode_id, revision),
    UNIQUE (work_id, episode_id, id),
    FOREIGN KEY (work_id, episode_id, parent_draft_id)
        REFERENCES drafts(work_id, episode_id, id)
        ON DELETE RESTRICT
);

CREATE INDEX idx_drafts_episode_revision
    ON drafts(episode_id, revision);

CREATE TRIGGER drafts_append_only_update
BEFORE UPDATE ON drafts
BEGIN
    SELECT RAISE(ABORT, 'drafts are append-only');
END;

CREATE TRIGGER drafts_append_only_delete
BEFORE DELETE ON drafts
BEGIN
    SELECT RAISE(ABORT, 'drafts are append-only');
END;
