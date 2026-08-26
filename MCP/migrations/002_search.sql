ALTER TABLE world_facts ADD COLUMN valid_from TEXT;

ALTER TABLE world_facts ADD COLUMN valid_to TEXT;

CREATE INDEX idx_world_facts_work_valid_from
ON world_facts(work_id, valid_from, id);

CREATE INDEX idx_world_facts_work_valid_to
ON world_facts(work_id, valid_to, id);

CREATE INDEX idx_world_facts_work_title
ON world_facts(work_id, title, id);

CREATE INDEX idx_world_facts_work_body
ON world_facts(work_id, body, id);
