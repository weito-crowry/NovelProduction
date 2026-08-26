CREATE INDEX idx_world_facts_work_topic_key
ON world_facts(work_id, topic_key, id);

CREATE INDEX idx_world_facts_work_statement
ON world_facts(work_id, statement, id);

CREATE INDEX idx_world_facts_work_category
ON world_facts(work_id, category, id);

CREATE INDEX idx_timeline_events_work_time
ON timeline_events(work_id, time_start, time_end, id);

CREATE INDEX idx_timeline_events_work_title
ON timeline_events(work_id, title, id);

CREATE INDEX idx_timeline_events_work_description
ON timeline_events(work_id, description, id);

CREATE INDEX idx_characters_work_name
ON characters(work_id, display_name, id);

CREATE INDEX idx_characters_work_description
ON characters(work_id, description, id);

CREATE INDEX idx_relationships_work_type
ON relationships(work_id, relationship_type, id);
