# 12 Storage Schema 詳細設計

## 1. 目的

Style Analysis v1のSQLite Schema、Migration分割、主要Column、FK、CHECK、UNIQUE、Indexを確定する。既存Authoring Schemaを変更せず、Project-local `story.db` に`style_` prefixのbounded contextとして追加する。

上位仕様は `../basic-design.md`。意味論は01〜11、Model Contractは15を正本とする。

## 2. Migration固定

既存`001`〜`005`はByte変更しない。

```text
006_style_analysis_foundation.sql
007_style_analysis_semantics.sql
008_style_analysis_corpus_profile.sql
009_style_analysis_external_agent.sql
```

001〜008 は既存 migration として byte/content を変更しない。External
Session/Task/Session Run Link は SA-I の 009 だけで追加する。

既存参照先:

```text
works(id)
episodes(id), episodes(work_id,id)
drafts(id)
characters(id), characters(work_id,id)
```

新ORMは導入しない。既存SQLite Repository Patternを使う。

## 3. 共通DB規則

- PK:`INTEGER PRIMARY KEY`。
- Timestamp:`TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`。
- Boolean:`INTEGER CHECK(value IN (0,1))`。
- JSON:`TEXT` + `CHECK(json_valid(column))`。
- SHA/Fingerprint:NULLまたはlowercase SHA-256 hex 64文字。文字種ValidationはService、length=64はDB CHECK。
- Text Span:Unicode Code Point半開`[start_cp,end_cp)`。
- Stable/Historical Rowは原則RepositoryからUPDATEしない。Current Pointer/Projection/Job/ReviewItem管理状態だけ更新可能。
- Generic Subject FK、Current Pointer、Cross-scope整合はService Validation。
- Project-local DBなのでStyle Tableへ`project_id`を重複保存しない。
- Purge Cascadeを妨げるDELETE禁止Triggerを追加しない。

## 4. 006 作成順

```text
style_jobs
style_sources
style_source_snapshots
style_reference_works
style_reference_episodes
style_documents
style_text_revisions
style_text_mappings
style_structure_revisions
style_scenes
style_blocks
style_sentences
style_analysis_runs
style_analysis_run_dependencies
style_structure_analysis_sources
```

## 5. `style_jobs`

```text
id
job_type TEXT NOT NULL
payload_json TEXT NOT NULL DEFAULT '{}'
status TEXT NOT NULL
cancel_requested INTEGER NOT NULL DEFAULT 0
progress_current INTEGER nullable
progress_total INTEGER nullable
result_json TEXT NOT NULL DEFAULT '{}'
warning_json TEXT NOT NULL DEFAULT '[]'
created_at
started_at nullable
finished_at nullable
error_code TEXT nullable
error_message TEXT nullable
version INTEGER NOT NULL DEFAULT 1
```

Job Type:

```text
analyze_document
analyze_reference_work
recompute_aggregate
run_lint
```

Status:

```text
queued
running
succeeded
partial
failed
cancelled
```

DB Enumは共通。09 Serviceが`partial`許可をDocument/Work解析だけに制限する。

CHECK:

- `json_valid(payload_json/result_json/warning_json)`。
- `cancel_requested IN (0,1)`。
- progress >=0。
- 両Progress non-nullなら`progress_current <= progress_total`。
- version>=1。

Index:`(status,id)`。

`style_imports`、Source Import/Refresh Job、`build_profile` Jobは作らない。

## 6. Source / Reference

### `style_sources`

```text
id
source_type TEXT NOT NULL CHECK(source_type IN ('text','html_file','epub'))
external_work_id TEXT NOT NULL
original_filename TEXT NOT NULL
adapter_id TEXT NOT NULL
adapter_version INTEGER NOT NULL
created_at
```

UNIQUE:`(source_type,external_work_id)`。

### `style_source_snapshots`

```text
id
source_id INTEGER NOT NULL REFERENCES style_sources(id) ON DELETE CASCADE
filename TEXT NOT NULL
media_type TEXT NOT NULL
payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256)=64)
raw_payload BLOB NOT NULL
metadata_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metadata_json))
created_at
```

UNIQUE:`(source_id,payload_sha256)`。

Standalone Snapshot Delete API/Repository Operationは作らない。削除はSource Purgeのみ。

### `style_reference_works`

```text
id
source_id INTEGER NOT NULL UNIQUE REFERENCES style_sources(id) ON DELETE CASCADE
title TEXT NOT NULL
author_name TEXT nullable
metadata_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metadata_json))
created_at
updated_at
```

1 Source = 1 Reference Work。

### `style_reference_episodes`

```text
id
reference_work_id INTEGER NOT NULL REFERENCES style_reference_works(id) ON DELETE CASCADE
external_episode_id TEXT NOT NULL
title TEXT NOT NULL
order_index INTEGER NOT NULL CHECK(order_index>=1)
latest_snapshot_id INTEGER NOT NULL REFERENCES style_source_snapshots(id) ON DELETE CASCADE
metadata_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metadata_json))
created_at
updated_at
```

UNIQUE:`(reference_work_id,external_episode_id)`。
UNIQUE:`(reference_work_id,order_index)`。

Serviceは`latest_snapshot_id`が同Work Source所属であることをValidationする。

## 7. Document / Text

### `style_documents`

```text
id
kind TEXT NOT NULL CHECK(kind IN ('reference_episode','project_episode_draft'))
reference_episode_id INTEGER nullable REFERENCES style_reference_episodes(id) ON DELETE CASCADE
project_work_id INTEGER nullable
project_episode_id INTEGER nullable
current_text_revision_id INTEGER nullable
current_structure_revision_id INTEGER nullable
created_at
```

Scope CHECK:

```text
(kind='reference_episode'
 AND reference_episode_id IS NOT NULL
 AND project_work_id IS NULL
 AND project_episode_id IS NULL)
OR
(kind='project_episode_draft'
 AND reference_episode_id IS NULL
 AND project_work_id IS NOT NULL
 AND project_episode_id IS NOT NULL)
```

Project FK:

```text
FOREIGN KEY(project_work_id,project_episode_id)
REFERENCES episodes(work_id,id)
ON DELETE CASCADE
```

UNIQUE:`reference_episode_id`。
UNIQUE:`(project_work_id,project_episode_id)`。

Current Pointerは循環FKを作らずServiceでValidation:

- Current Textは同Document TextRevision。
- Current Structureは同Document StructureRevision。
- Current StructureのTextRevision=Current Text。
- Current Text変更時Current Structure=NULL。

### `style_text_revisions`

```text
id
document_id INTEGER NOT NULL REFERENCES style_documents(id) ON DELETE CASCADE
revision_no INTEGER NOT NULL CHECK(revision_no>=1)
source_snapshot_id INTEGER nullable REFERENCES style_source_snapshots(id) ON DELETE CASCADE
project_draft_id INTEGER nullable
raw_text TEXT NOT NULL
canonical_text TEXT NOT NULL
raw_sha256 TEXT NOT NULL CHECK(length(raw_sha256)=64)
canonical_sha256 TEXT NOT NULL CHECK(length(canonical_sha256)=64)
normalization_input_fingerprint TEXT NOT NULL CHECK(length(normalization_input_fingerprint)=64)
normalizer_id TEXT NOT NULL
normalizer_version INTEGER NOT NULL
metadata_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metadata_json))
created_at
```

CHECK exactly one of`source_snapshot_id/project_draft_id` non-null。

`project_draft_id`は既存`drafts(id)`へのLogical Reference。Serviceで存在・Document Work/Episode一致をValidationする。既存Draft append-only/delete semanticsへ干渉しないためFKを追加しない。

UNIQUE:`(document_id,revision_no)`。
UNIQUE:`(document_id,normalization_input_fingerprint)`。
Index:`(document_id,canonical_sha256)`。

### `style_text_mappings`

```text
id
text_revision_id INTEGER NOT NULL REFERENCES style_text_revisions(id) ON DELETE CASCADE
segment_order INTEGER NOT NULL CHECK(segment_order>=1)
raw_start INTEGER NOT NULL
raw_end INTEGER NOT NULL
canonical_start INTEGER NOT NULL
canonical_end INTEGER NOT NULL
operation TEXT NOT NULL CHECK(operation IN ('identity','replace','delete','collapse'))
```

UNIQUE:`(text_revision_id,segment_order)`。
CHECK:end>=start、Raw/Canonical双方0長は禁止。

## 8. Structure

### `style_structure_revisions`

```text
id
text_revision_id INTEGER NOT NULL REFERENCES style_text_revisions(id) ON DELETE CASCADE
revision_no INTEGER NOT NULL CHECK(revision_no>=1)
segmenter_id TEXT NOT NULL
segmenter_version INTEGER NOT NULL
source_kind TEXT NOT NULL CHECK(source_kind IN ('automatic','semantic','manual'))
parent_structure_revision_id INTEGER nullable REFERENCES style_structure_revisions(id) ON DELETE CASCADE
fingerprint TEXT NOT NULL CHECK(length(fingerprint)=64)
created_at
```

Automatic Parent NULL、Semantic/Manual Parent NOT NULLはService Validation。

UNIQUE:`(text_revision_id,revision_no)`。
UNIQUE:`(text_revision_id,fingerprint)`。

### `style_scenes`

```text
id
structure_revision_id INTEGER NOT NULL REFERENCES style_structure_revisions(id) ON DELETE CASCADE
order_index INTEGER NOT NULL CHECK(order_index>=1)
start_cp INTEGER NOT NULL
end_cp INTEGER NOT NULL
```

UNIQUE:`(structure_revision_id,order_index)`。

### `style_blocks`

```text
id
structure_revision_id INTEGER NOT NULL REFERENCES style_structure_revisions(id) ON DELETE CASCADE
scene_id INTEGER nullable REFERENCES style_scenes(id) ON DELETE CASCADE
order_index INTEGER NOT NULL CHECK(order_index>=1)
paragraph_index INTEGER NOT NULL CHECK(paragraph_index>=1)
block_type TEXT NOT NULL CHECK(block_type IN ('dialogue','narration','heading','separator','unknown'))
start_cp INTEGER NOT NULL
end_cp INTEGER NOT NULL
```

UNIQUE:`(structure_revision_id,order_index)`。
Index:`(structure_revision_id,scene_id,order_index)`。

### `style_sentences`

```text
id
block_id INTEGER NOT NULL REFERENCES style_blocks(id) ON DELETE CASCADE
order_index INTEGER NOT NULL CHECK(order_index>=1)
start_cp INTEGER NOT NULL
end_cp INTEGER NOT NULL
```

UNIQUE:`(block_id,order_index)`。
ServiceはDialogue/Narration BlockだけにSentenceを許可する。

## 9. Analysis Run

### `style_analysis_runs`

```text
id
document_id INTEGER NOT NULL REFERENCES style_documents(id) ON DELETE CASCADE
analyzer_id TEXT NOT NULL
analyzer_version INTEGER NOT NULL
text_revision_id INTEGER NOT NULL REFERENCES style_text_revisions(id) ON DELETE CASCADE
structure_revision_id INTEGER NOT NULL REFERENCES style_structure_revisions(id) ON DELETE CASCADE
status TEXT NOT NULL CHECK(status IN ('running','succeeded','partial','failed','cancelled'))
fingerprint TEXT NOT NULL CHECK(length(fingerprint)=64)
config_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(config_json))
analysis_policy_version INTEGER nullable
policy_input_fingerprint TEXT nullable
state_fingerprint TEXT nullable
registry_input_fingerprint TEXT nullable
model_provider TEXT nullable
model_id TEXT nullable
prompt_id TEXT nullable
prompt_version INTEGER nullable
started_at TEXT NOT NULL
finished_at TEXT nullable
error_code TEXT nullable
error_message TEXT nullable
warning_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(warning_json))
created_at
```

Fingerprint nullable列はNULLまたはlength=64 CHECK。

Index:

```text
(document_id,analyzer_id,text_revision_id,structure_revision_id,created_at)
(fingerprint,status)
```

### `style_analysis_run_dependencies`

```text
run_id INTEGER NOT NULL REFERENCES style_analysis_runs(id) ON DELETE CASCADE
dependency_run_id INTEGER NOT NULL REFERENCES style_analysis_runs(id) ON DELETE CASCADE
PRIMARY KEY(run_id,dependency_run_id)
CHECK(run_id != dependency_run_id)
```

### `style_structure_analysis_sources`

```text
structure_revision_id INTEGER NOT NULL REFERENCES style_structure_revisions(id) ON DELETE CASCADE
boundary_analysis_run_id INTEGER NOT NULL REFERENCES style_analysis_runs(id) ON DELETE CASCADE
PRIMARY KEY(structure_revision_id,boundary_analysis_run_id)
```

Boundary Run IDはUNIQUEにしない。

Service Validation:Structure kind=semantic、Parent automatic、Run analyzer=`scene-boundary-detector`、Run input Structure=Parent。

## 10. 007 作成順

```text
style_entities
style_mentions
style_entity_aliases
style_entity_character_links
style_terms
style_term_aliases
style_term_mentions
style_annotations
style_review_items
style_inference_reviews
style_manual_overrides
```

## 11. Entity

### `style_entities`

```text
id
reference_work_id INTEGER nullable REFERENCES style_reference_works(id) ON DELETE CASCADE
document_id INTEGER nullable REFERENCES style_documents(id) ON DELETE CASCADE
entity_type TEXT NOT NULL
canonical_name TEXT NOT NULL
origin TEXT NOT NULL CHECK(origin IN ('inferred','manual'))
created_by_run_id INTEGER nullable REFERENCES style_analysis_runs(id) ON DELETE SET NULL
created_at
```

CHECK exactly one Scope。

### `style_mentions`

```text
id
structure_revision_id INTEGER NOT NULL REFERENCES style_structure_revisions(id) ON DELETE CASCADE
scene_id INTEGER NOT NULL REFERENCES style_scenes(id) ON DELETE CASCADE
block_id INTEGER NOT NULL REFERENCES style_blocks(id) ON DELETE CASCADE
start_cp INTEGER NOT NULL
end_cp INTEGER NOT NULL
surface TEXT NOT NULL
mention_type TEXT NOT NULL
entity_type_candidate TEXT NOT NULL
canonical_name_candidate TEXT NOT NULL
confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1)
analysis_run_id INTEGER NOT NULL REFERENCES style_analysis_runs(id) ON DELETE CASCADE
```

Entity ID列なし。

### `style_entity_aliases`

```text
id
entity_id INTEGER NOT NULL REFERENCES style_entities(id) ON DELETE CASCADE
alias TEXT NOT NULL
alias_kind TEXT NOT NULL
origin TEXT NOT NULL CHECK(origin IN ('inferred','manual'))
analysis_run_id INTEGER nullable REFERENCES style_analysis_runs(id) ON DELETE CASCADE
source_mention_id INTEGER nullable REFERENCES style_mentions(id) ON DELETE SET NULL
created_at
```

Manual AliasはRun NULL、Inferred AliasはRun必須をService Validation。
Index:`(entity_id,alias)`。

### `style_entity_character_links`

```text
id
document_id INTEGER NOT NULL REFERENCES style_documents(id) ON DELETE CASCADE
style_entity_id INTEGER NOT NULL UNIQUE REFERENCES style_entities(id) ON DELETE CASCADE
project_character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE
created_at
```

UNIQUE:`(document_id,project_character_id)`。
ServiceでEntity Document Scope一致、person、Enabled、Character Work一致をValidation。

Entity Relation Tableは作らない。

## 12. Term

### `style_terms`

```text
id
reference_work_id INTEGER nullable REFERENCES style_reference_works(id) ON DELETE CASCADE
document_id INTEGER nullable REFERENCES style_documents(id) ON DELETE CASCADE
canonical_label TEXT NOT NULL
term_type TEXT NOT NULL
origin TEXT NOT NULL CHECK(origin IN ('inferred','manual'))
created_by_run_id INTEGER nullable REFERENCES style_analysis_runs(id) ON DELETE SET NULL
created_at
```

CHECK exactly one Scope。

### `style_term_aliases`

```text
id
term_id INTEGER NOT NULL REFERENCES style_terms(id) ON DELETE CASCADE
alias TEXT NOT NULL
origin TEXT NOT NULL CHECK(origin IN ('inferred','manual'))
analysis_run_id INTEGER nullable REFERENCES style_analysis_runs(id) ON DELETE CASCADE
created_at
```

Index:`(term_id,alias)`。

### `style_term_mentions`

```text
id
term_id INTEGER NOT NULL REFERENCES style_terms(id) ON DELETE CASCADE
structure_revision_id INTEGER NOT NULL REFERENCES style_structure_revisions(id) ON DELETE CASCADE
scene_id INTEGER NOT NULL REFERENCES style_scenes(id) ON DELETE CASCADE
block_id INTEGER NOT NULL REFERENCES style_blocks(id) ON DELETE CASCADE
start_cp INTEGER NOT NULL
end_cp INTEGER NOT NULL
surface TEXT NOT NULL
analysis_run_id INTEGER NOT NULL REFERENCES style_analysis_runs(id) ON DELETE CASCADE
```

Occurrence Indexなし。Term↔Entity Linkなし。

## 13. Annotation

### `style_annotations`

```text
id
annotation_type TEXT NOT NULL
subject_type TEXT NOT NULL
subject_id INTEGER NOT NULL
value_json TEXT NOT NULL CHECK(json_valid(value_json))
confidence REAL nullable CHECK(confidence IS NULL OR confidence BETWEEN 0 AND 1)
analysis_run_id INTEGER NOT NULL REFERENCES style_analysis_runs(id) ON DELETE CASCADE
start_cp INTEGER nullable
end_cp INTEGER nullable
created_at
```

用途:

```text
mention.entity_resolution
speaker
scene.function
scene.tone
scene.pace
scene.information_load
scene.interaction
scene.pov
block.semantic_primary
scene_boundary_candidate
term_candidate
term.novelty
term_explanation
```

Generic SubjectはService Validation。Spanは両方NULLまたは両方non-null。

次のAnnotationは`(analysis_run_id,subject_type,subject_id,annotation_type)`で最大1件になるPartial Unique Indexを作る。

```text
mention.entity_resolution
speaker
scene.function
scene.tone
scene.pace
scene.information_load
scene.interaction
scene.pov
block.semantic_primary
term.novelty
term_explanation
```

`term_explanation`は05どおり1 Run×1 TermMention最大1件。

`term_candidate`と`scene_boundary_candidate`だけ複数可。

## 14. Review / Override

Generic Review/Override RowはPurge/Isolation用Scope Pairを持つ。

```text
document_id nullable REFERENCES style_documents(id) ON DELETE CASCADE
reference_work_id nullable REFERENCES style_reference_works(id) ON DELETE CASCADE
```

CHECK exactly one Scope。

Scope解決は10を正本とする。

- Structure/Scene/Block/Mention/TermMention -> Document。
- Project Entity/Term -> Document。
- Reference Entity/Term -> Reference Work。
- Entity Alias/Term Alias InferenceReview -> Parent Identity Scope。

### `style_review_items`

```text
id
document_id nullable
reference_work_id nullable
item_type TEXT NOT NULL CHECK(item_type IN ('scene_boundary_proposal','structure_warning','stale_override','manual_review'))
subject_type TEXT NOT NULL
subject_id INTEGER NOT NULL
analysis_run_id INTEGER nullable REFERENCES style_analysis_runs(id) ON DELETE SET NULL
priority TEXT NOT NULL DEFAULT 'normal' CHECK(priority IN ('normal','high'))
status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','resolved','ignored','superseded'))
reason_code TEXT NOT NULL
evidence_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(evidence_json))
resolution_note TEXT nullable
version INTEGER NOT NULL DEFAULT 1 CHECK(version>=1)
created_at
resolved_at nullable
```

Manual ReviewItem `subject_type`は10 ReviewItem Subject RegistryだけをServiceで許可する。

ReviewItemのstatus/version/resolution_note/resolved_atだけ管理Update可。

Index:`(status,priority,id)`、`(document_id,status)`、`(reference_work_id,status)`。

### `style_inference_reviews`

```text
id
document_id nullable
reference_work_id nullable
subject_type TEXT NOT NULL
subject_id INTEGER NOT NULL
field_path TEXT NOT NULL
analysis_run_id INTEGER NOT NULL REFERENCES style_analysis_runs(id) ON DELETE CASCADE
review_status TEXT NOT NULL CHECK(review_status IN ('confirmed','rejected'))
note TEXT nullable
created_at
```

10 Inference Review Registryの`subject_type + field_path + Raw Source`組合せだけをServiceで許可する。

Index:`(analysis_run_id,subject_type,subject_id,field_path,created_at,id)`。

### `style_manual_overrides`

```text
id
document_id nullable
reference_work_id nullable
subject_type TEXT NOT NULL
subject_id INTEGER NOT NULL
field_path TEXT NOT NULL
operation TEXT NOT NULL CHECK(operation IN ('set','clear','revert'))
value_json TEXT nullable
base_analysis_run_id INTEGER nullable REFERENCES style_analysis_runs(id) ON DELETE SET NULL
structure_revision_id INTEGER nullable REFERENCES style_structure_revisions(id) ON DELETE SET NULL
note TEXT nullable
created_at
```

CHECK:

```text
(operation='set' AND value_json IS NOT NULL AND json_valid(value_json))
OR
(operation IN ('clear','revert') AND value_json IS NULL)
```

Active Unique/Supersede Pointerなし。Effective Event=`created_at DESC,id DESC`。Append-onlyはRepository APIで守る。

## 15. 008 作成順

```text
style_measurements
style_corpora
style_corpus_work_memberships
style_corpus_episode_memberships
style_aggregates
style_aggregate_measurements
style_profiles
style_profile_versions
style_rules
style_rule_aggregate_sources
style_lint_runs
style_findings
style_finding_reviews
```

## 16. Measurement

### `style_measurements`

```text
id
analysis_run_id INTEGER NOT NULL REFERENCES style_analysis_runs(id) ON DELETE CASCADE
structure_revision_id INTEGER NOT NULL REFERENCES style_structure_revisions(id) ON DELETE CASCADE
target_type TEXT NOT NULL CHECK(target_type IN ('document','scene','character'))
target_id INTEGER NOT NULL
metric_name TEXT NOT NULL
metric_version INTEGER NOT NULL
value_real REAL nullable
value_int INTEGER nullable
sample_count INTEGER NOT NULL CHECK(sample_count>=0)
created_at
```

CHECK exactly one Value列 non-null。
UNIQUE:`(analysis_run_id,target_type,target_id,metric_name,metric_version)`。

Metric Name/Version/Value Column/Scope整合は07 RegistryでService Validationする。

## 17. Corpus Membership

### `style_corpora`

```text
id
name TEXT NOT NULL
description TEXT NOT NULL DEFAULT ''
created_at
updated_at
```

### `style_corpus_work_memberships`

```text
id
corpus_id INTEGER NOT NULL REFERENCES style_corpora(id) ON DELETE CASCADE
reference_work_id INTEGER NOT NULL REFERENCES style_reference_works(id) ON DELETE CASCADE
include_all_episodes INTEGER NOT NULL CHECK(include_all_episodes IN (0,1))
created_at
```

UNIQUE:`(corpus_id,reference_work_id)`。

### `style_corpus_episode_memberships`

```text
id
work_membership_id INTEGER NOT NULL REFERENCES style_corpus_work_memberships(id) ON DELETE CASCADE
reference_episode_id INTEGER NOT NULL REFERENCES style_reference_episodes(id) ON DELETE CASCADE
mode TEXT NOT NULL CHECK(mode IN ('include','exclude'))
created_at
```

UNIQUE:`(work_membership_id,reference_episode_id)`。
ServiceでEpisode Work一致をValidation。

## 18. Aggregate

### `style_aggregates`

```text
id
container_type TEXT NOT NULL CHECK(container_type IN ('reference_work','corpus'))
container_id INTEGER NOT NULL
measurement_target_type TEXT NOT NULL CHECK(measurement_target_type IN ('document','scene'))
filter_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(filter_json))
metric_name TEXT NOT NULL
metric_version INTEGER NOT NULL
statistic TEXT NOT NULL CHECK(statistic IN ('mean','median','p10','p25','p75','p90','stddev','min','max'))
aggregate_policy_version INTEGER NOT NULL
value_real REAL NOT NULL
source_measurement_count INTEGER NOT NULL CHECK(source_measurement_count>=0)
sample_count INTEGER NOT NULL CHECK(sample_count>=0)
work_count INTEGER NOT NULL CHECK(work_count>=0)
skipped_target_count INTEGER NOT NULL CHECK(skipped_target_count>=0)
filter_state_fingerprint TEXT nullable
input_fingerprint TEXT NOT NULL CHECK(length(input_fingerprint)=64)
warning_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(warning_json))
created_at
```

Aggregate値は元Measurement Typeに関係なくREAL。Immutable Historical Snapshot。

`container_id`はHistorical保持のためLogical ReferenceとしFKを張らない。

### `style_aggregate_measurements`

```text
aggregate_id INTEGER NOT NULL REFERENCES style_aggregates(id) ON DELETE CASCADE
measurement_id INTEGER NOT NULL REFERENCES style_measurements(id) ON DELETE CASCADE
PRIMARY KEY(aggregate_id,measurement_id)
```

Measurement PurgeでLinkが消えてもAggregate Rowは残す。

## 19. Profile

### `style_profiles`

```text
id
name TEXT NOT NULL
description TEXT NOT NULL DEFAULT ''
source_corpus_id INTEGER nullable REFERENCES style_corpora(id) ON DELETE SET NULL
status TEXT NOT NULL CHECK(status IN ('draft','active','archived'))
active_version_id INTEGER nullable
created_at
updated_at
```

`active_version_id`は循環FKを作らず同Profile VersionをService Validation。

### `style_profile_versions`

```text
id
profile_id INTEGER NOT NULL REFERENCES style_profiles(id) ON DELETE CASCADE
version_no INTEGER NOT NULL CHECK(version_no>=1)
parent_version_id INTEGER nullable REFERENCES style_profile_versions(id) ON DELETE SET NULL
profile_generation_policy_version INTEGER nullable
created_at
```

UNIQUE:`(profile_id,version_no)`。

### `style_rules`

```text
id
profile_version_id INTEGER NOT NULL REFERENCES style_profile_versions(id) ON DELETE CASCADE
target_scope TEXT NOT NULL CHECK(target_scope IN ('document','scene','character'))
scope_selector_json TEXT NOT NULL CHECK(json_valid(scope_selector_json))
metric_name TEXT NOT NULL
metric_version INTEGER NOT NULL
preferred_value REAL nullable
min_value REAL nullable
max_value REAL nullable
weight REAL NOT NULL DEFAULT 1.0
enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1))
severity_policy TEXT NOT NULL DEFAULT 'standard' CHECK(severity_policy='standard')
source_kind TEXT NOT NULL CHECK(source_kind IN ('corpus','manual'))
created_at
```

CHECK:

```text
enabled = 0
OR (
  min_value IS NOT NULL
  AND max_value IS NOT NULL
  AND min_value <= max_value
  AND (preferred_value IS NULL OR (min_value <= preferred_value AND preferred_value <= max_value))
)
```

Rule数値は08どおりfinite REALとしてService Validationし、Count Metricでも整数性を要求しない。

Exact Enabled DuplicateはCanonical Selector比較でService拒否。

### `style_rule_aggregate_sources`

```text
rule_id INTEGER NOT NULL REFERENCES style_rules(id) ON DELETE CASCADE
aggregate_id INTEGER NOT NULL REFERENCES style_aggregates(id) ON DELETE RESTRICT
role TEXT NOT NULL CHECK(role IN ('preferred','min','max'))
PRIMARY KEY(rule_id,role)
```

Corpus Ruleは3 Link。Manual Ruleは0 Link。

## 20. Lint

### `style_lint_runs`

```text
id
document_id INTEGER NOT NULL REFERENCES style_documents(id) ON DELETE CASCADE
text_revision_id INTEGER NOT NULL REFERENCES style_text_revisions(id) ON DELETE CASCADE
structure_revision_id INTEGER NOT NULL REFERENCES style_structure_revisions(id) ON DELETE CASCADE
profile_id INTEGER NOT NULL REFERENCES style_profiles(id) ON DELETE RESTRICT
profile_version_id INTEGER NOT NULL REFERENCES style_profile_versions(id) ON DELETE RESTRICT
scene_id INTEGER nullable REFERENCES style_scenes(id) ON DELETE CASCADE
basic_metric_run_id INTEGER nullable REFERENCES style_analysis_runs(id) ON DELETE SET NULL
semantic_metric_run_id INTEGER nullable REFERENCES style_analysis_runs(id) ON DELETE SET NULL
input_fingerprint TEXT NOT NULL CHECK(length(input_fingerprint)=64)
status TEXT NOT NULL CHECK(status IN ('running','succeeded','failed','cancelled'))
warning_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(warning_json))
enabled_rule_count INTEGER NOT NULL CHECK(enabled_rule_count>=0)
applicable_rule_count INTEGER NOT NULL CHECK(applicable_rule_count>=0)
missing_rule_count INTEGER NOT NULL CHECK(missing_rule_count>=0)
created_at
finished_at nullable
```

### `style_findings`

```text
id
lint_run_id INTEGER NOT NULL REFERENCES style_lint_runs(id) ON DELETE CASCADE
rule_id INTEGER NOT NULL REFERENCES style_rules(id) ON DELETE RESTRICT
target_type TEXT NOT NULL
target_id INTEGER NOT NULL
metric_name TEXT NOT NULL
observed_value REAL NOT NULL
expected_min REAL NOT NULL
expected_max REAL NOT NULL
preferred_value REAL nullable
deviation REAL NOT NULL
severity TEXT NOT NULL CHECK(severity IN ('info','warning','strong_warning'))
sort_score REAL NOT NULL
explanation_code TEXT NOT NULL
evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json))
created_at
```

### `style_finding_reviews`

```text
id
finding_id INTEGER NOT NULL REFERENCES style_findings(id) ON DELETE CASCADE
status TEXT NOT NULL CHECK(status IN ('acknowledged','ignored'))
note TEXT nullable
created_at
```

Append-only。11 Effective Reviewは最新Eventを使う。

## 21. Purge

Reference Work PurgeはSource RowをDELETEする。

Cascadeで:

```text
Snapshot
Reference Work/Episode
Document/Text/Structure
AnalysisRun/Semantic Output
Entity/Term
Review/Override
Measurement
Corpus Membership
```

を削除する。

Aggregate Measurement LinkはMeasurement削除でCascadeするがAggregate RowはHistorical Snapshotとして残す。

Profileは通常物理削除せずArchiveを使用する。

## 22. Migration / Integration Test

- Fresh001→008 / Existing005→008。
- Existing001〜005 Checksum不変。
- `PRAGMA foreign_key_check` / `PRAGMA integrity_check`。
- Job Type4種のみ。
- `style_imports`/Upload Staging Tableなし。
- Source Identity / 1 Source=1 Work。
- Snapshot Delete/PurgeでTextRevision Exactly-one CHECK違反なし。
- Project Document Composite Episode FK。
- Current Pointer Logical FK。
- TextRevision normalization_input_fingerprint Unique。
- Structure fingerprint Unique/Reuse。
- Semantic Structure Source LinkはBoundary Run非Unique。
- SentenceはDialogue/Narrationだけ。
- Run Output Cascade vs Stable Identity `created_by_run_id SET NULL`。
- Mention Entity IDなし / Relation/Term-Linkなし。
- `term_explanation` 1 Run×1 TermMention Unique。
- ReviewItem Subject Registry/Scope/Status/Version/Resolution Note。
- InferenceReview Registry/Scope/Alias Parent Scope。
- ManualOverride Scope Cascade/Append-only Repository。
- Project Character Link Document uniqueness。
- Measurement Value Column/Unique/Metric Registry validation。
- Aggregate REAL/Policy Version/Input Fingerprint/Measurement Link。
- Rule REAL/enabled min-max/preferred/target_scope/source_kind/Aggregate Source。
- Lint scene_id/Input Fingerprint。
- `analysis_stale`等永続bool不存在。

## 23. Codex禁止事項

- 001〜005変更。
- ORM追加。
- `style_imports`/Network Source用Column追加。
- `build_profile`/Source Import Job追加。
- Local Upload Staging Table追加。
- Current PointerをLatest Queryで代替。
- TextRevision Reuseをraw hashだけで判定。
- SourceSnapshot FKをSET NULLへ戻す。
- Standalone Snapshot Delete API追加。
- Draft Tableへ新FK/Column追加。
- Run削除でStable Entity/TermをCascade Delete。
- Mention RowへEntity ID追加。
- Relation/Term Entity Link追加。
- `term_explanation`複数Row化。
- Review/Inference subject typeを10 Registry外へ拡張。
- ManualOverride Supersede Pointer再導入。
- Aggregateを元Measurement int型へ丸める。
- Aggregate Policy Versionを保存しない。
- Boundary Analysis RunをStructure SourceでUNIQUEにする。
- Character Aggregate追加。
- AggregateをReference Work Purgeで物理削除。
- Profile Identity/Version統合。
- `analysis_stale`等bool Column追加。
