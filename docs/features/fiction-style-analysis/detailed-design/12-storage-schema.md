# 12 Storage Schema 詳細設計

## 1. 目的

Style AnalysisのSQLite Schema、Migration分割、主要Column、FK、Constraint、Indexを確定する。既存Authoring Schemaを変更せず`style_` prefixのbounded contextとして追加する。

上位仕様は `../basic-design.md`。

## 2. Migration

既存`001`〜`005`は変更しない。

```text
006_style_analysis_foundation.sql
007_style_analysis_semantics.sql
008_style_analysis_analytics.sql
```

既存参照先:

```text
works(id)
episodes(id), episodes(work_id,id)
drafts(id)
characters(id), characters(work_id,id)
```

## 3. 共通ルール

- Project-local `story.db`。Style Tableへ`project_id`を重複保存しない。
- PK: `INTEGER PRIMARY KEY`。
- Timestamp: `TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`。
- Boolean: `INTEGER CHECK(value IN (0,1))`。
- JSON: `TEXT` + `json_valid` CHECK。
- SHA-256: lowercase hex 64文字。
- Text Span: Unicode Code Point半開`[start_cp,end_cp)`。
- Immutable/Historical RowはRepositoryからUpdateしない。
- Purge Cascadeを妨げるDELETE禁止Triggerは作らない。
- Generic Subject FK/Current Pointer/Cross-scope整合はServiceでValidationする。

## 4. 006 Foundation 作成順

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

## 5. Jobs

### `style_jobs`

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
error_code nullable
error_message nullable
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

CHECK: JSON valid、progress>=0、total>=0、両方非NULLならcurrent<=total、version>=1。

Index:`(status,id)`。

`style_imports`、`build_profile` Job、Source Import/Refresh Jobは作らない。

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

UNIQUE `(source_type,external_work_id)`。

### `style_source_snapshots`

```text
id
source_id INTEGER NOT NULL REFERENCES style_sources(id) ON DELETE CASCADE
filename TEXT NOT NULL
media_type TEXT NOT NULL
payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256)=64)
raw_payload BLOB NOT NULL
metadata_json TEXT NOT NULL DEFAULT '{}'
created_at
```

UNIQUE `(source_id,payload_sha256)`。

Standalone Snapshot Delete API/Repository Operationは作らない。Snapshot削除はSource Purgeだけ。

### `style_reference_works`

```text
id
source_id INTEGER NOT NULL UNIQUE REFERENCES style_sources(id) ON DELETE CASCADE
title TEXT NOT NULL
author_name TEXT nullable
metadata_json TEXT NOT NULL DEFAULT '{}'
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
metadata_json TEXT NOT NULL DEFAULT '{}'
created_at
updated_at
```

UNIQUE `(reference_work_id,external_episode_id)`。
UNIQUE `(reference_work_id,order_index)`。

ServiceはSnapshotが同Reference Work Source所属であることをValidationする。

## 7. Document / Text

### `style_documents`

```text
id
kind TEXT NOT NULL
reference_episode_id INTEGER nullable REFERENCES style_reference_episodes(id) ON DELETE CASCADE
project_work_id INTEGER nullable
project_episode_id INTEGER nullable
current_text_revision_id INTEGER nullable
current_structure_revision_id INTEGER nullable
created_at
```

Kind:`reference_episode|project_episode_draft`。

CHECK:

- Reference: reference_episode_id NOT NULL、Project Fields NULL。
- Project: reference_episode_id NULL、Project Fields NOT NULL。

Project FK:

```text
FOREIGN KEY(project_work_id,project_episode_id)
REFERENCES episodes(work_id,id)
ON DELETE CASCADE
```

UNIQUE `reference_episode_id`。
UNIQUE `(project_work_id,project_episode_id)`。

Current Pointerは循環FKを作らずService Validation:

- Current Textは同Document TextRevision。
- Current Structureは同Document StructureRevision。
- Current Structure TextRevision = Current Text。
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
raw_sha256 TEXT NOT NULL
canonical_sha256 TEXT NOT NULL
normalization_input_fingerprint TEXT NOT NULL
normalizer_id TEXT NOT NULL
normalizer_version INTEGER NOT NULL
metadata_json TEXT NOT NULL DEFAULT '{}'
created_at
```

CHECK exactly one of`source_snapshot_id/project_draft_id` non-null。

`project_draft_id`は`drafts(id)`へのLogical Reference。Serviceで存在・Document Work/Episode一致をValidationする。既存Draft append-only/delete semanticsへ干渉しないため新FKは追加しない。

UNIQUE `(document_id,revision_no)`。
UNIQUE `(document_id,normalization_input_fingerprint)`。
Index `(document_id,canonical_sha256)`。

Reference Snapshot削除はSource Purge時だけであり、TextRevisionもCASCADE DeleteされるためExactly-one CHECKと競合しない。

### `style_text_mappings`

```text
id
text_revision_id INTEGER NOT NULL REFERENCES style_text_revisions(id) ON DELETE CASCADE
segment_order INTEGER NOT NULL
raw_start INTEGER NOT NULL
raw_end INTEGER NOT NULL
canonical_start INTEGER NOT NULL
canonical_end INTEGER NOT NULL
operation TEXT NOT NULL
```

Operation:`identity|replace|delete|collapse`。

UNIQUE `(text_revision_id,segment_order)`。

CHECK: order>=1、each end>=start、raw/canonical双方0長は不可。

## 8. Structure

### `style_structure_revisions`

```text
id
text_revision_id INTEGER NOT NULL REFERENCES style_text_revisions(id) ON DELETE CASCADE
revision_no INTEGER NOT NULL
segmenter_id TEXT NOT NULL
segmenter_version INTEGER NOT NULL
source_kind TEXT NOT NULL
parent_structure_revision_id INTEGER nullable REFERENCES style_structure_revisions(id) ON DELETE CASCADE
fingerprint TEXT NOT NULL
created_at
```

`source_kind IN ('automatic','semantic','manual')`。

Automatic Parent NULL、Semantic/Manual Parent NOT NULLをService Validation。

UNIQUE `(text_revision_id,revision_no)`。
UNIQUE `(text_revision_id,fingerprint)`。

### `style_scenes`

```text
id
structure_revision_id INTEGER NOT NULL REFERENCES style_structure_revisions(id) ON DELETE CASCADE
order_index INTEGER NOT NULL
start_cp INTEGER NOT NULL
end_cp INTEGER NOT NULL
```

UNIQUE `(structure_revision_id,order_index)`。

### `style_blocks`

```text
id
structure_revision_id INTEGER NOT NULL REFERENCES style_structure_revisions(id) ON DELETE CASCADE
scene_id INTEGER nullable REFERENCES style_scenes(id) ON DELETE CASCADE
order_index INTEGER NOT NULL
paragraph_index INTEGER NOT NULL
block_type TEXT NOT NULL
start_cp INTEGER NOT NULL
end_cp INTEGER NOT NULL
```

Block Type:`dialogue|narration|heading|separator|unknown`。

UNIQUE `(structure_revision_id,order_index)`。
Index `(structure_revision_id,scene_id,order_index)`。

### `style_sentences`

```text
id
block_id INTEGER NOT NULL REFERENCES style_blocks(id) ON DELETE CASCADE
order_index INTEGER NOT NULL
start_cp INTEGER NOT NULL
end_cp INTEGER NOT NULL
```

UNIQUE `(block_id,order_index)`。

ServiceはDialogue/Narration BlockだけにSentenceを許可する。

## 9. AnalysisRun

### `style_analysis_runs`

```text
id
document_id INTEGER NOT NULL REFERENCES style_documents(id) ON DELETE CASCADE
analyzer_id TEXT NOT NULL
analyzer_version INTEGER NOT NULL
text_revision_id INTEGER NOT NULL REFERENCES style_text_revisions(id) ON DELETE CASCADE
structure_revision_id INTEGER NOT NULL REFERENCES style_structure_revisions(id) ON DELETE CASCADE
status TEXT NOT NULL
fingerprint TEXT NOT NULL
config_json TEXT NOT NULL DEFAULT '{}'
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
warning_json TEXT NOT NULL DEFAULT '[]'
created_at
```

Status:`running|succeeded|partial|failed|cancelled`。

Fingerprint列はNULLまたは64文字CHECK。

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

Service Validation:

- Structure Kind=semantic。
- Parent Kind=automatic。
- Run Analyzer=`scene-boundary-detector`。
- Run input Structure=Parent Automatic。

## 10. 007 Semantics 作成順

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

Index `(entity_id,alias)`。

### `style_entity_character_links`

```text
id
document_id INTEGER NOT NULL REFERENCES style_documents(id) ON DELETE CASCADE
style_entity_id INTEGER NOT NULL UNIQUE REFERENCES style_entities(id) ON DELETE CASCADE
project_character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE
created_at
```

UNIQUE `(document_id,project_character_id)`。

ServiceでEntity Document Scope一致、person、Enabled、Character Work一致をValidation。

Relation Tableは作らない。

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

Index `(term_id,alias)`。

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

## 13. `style_annotations`

```text
id
annotation_type TEXT NOT NULL
subject_type TEXT NOT NULL
subject_id INTEGER NOT NULL
value_json TEXT NOT NULL
confidence REAL nullable
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

Partial Unique Index:

- `term.novelty`。
- `mention.entity_resolution`。
- `speaker`。
- Scene各Axis。
- `scene.pov`。
- `block.semantic_primary`。

について `(analysis_run_id,subject_type,subject_id,annotation_type)` を1件にする。

`term_candidate`/`term_explanation`は複数可。

## 14. Review / Override Scope

Generic Review/Override RowにはPurge/Isolation用Scope Pairを持たせる。

```text
document_id nullable REFERENCES style_documents(id) ON DELETE CASCADE
reference_work_id nullable REFERENCES style_reference_works(id) ON DELETE CASCADE
```

Exactly One Scope。

- Structure/Mention/Block/Scene/Project Entity/Project Term -> document。
- Reference Entity/Term -> reference_work。

### `style_review_items`

10契約 + Scope Pair。`analysis_run_id`はON DELETE SET NULL。

### `style_inference_reviews`

```text
id
scope pair
subject_type
subject_id
field_path
analysis_run_id INTEGER NOT NULL REFERENCES style_analysis_runs(id) ON DELETE CASCADE
review_status TEXT NOT NULL CHECK(review_status IN ('confirmed','rejected'))
note TEXT nullable
created_at
```

### `style_manual_overrides`

```text
id
scope pair
subject_type
subject_id
field_path
operation TEXT NOT NULL
value_json TEXT nullable
base_analysis_run_id INTEGER nullable REFERENCES style_analysis_runs(id) ON DELETE SET NULL
structure_revision_id INTEGER nullable REFERENCES style_structure_revisions(id) ON DELETE SET NULL
note TEXT nullable
created_at
```

Operation:`set|clear|revert`。

- Set: value_json必須 + valid JSON。
- Clear/Revert: value_json NULL。
- Active Unique/Supersede Pointerなし。
- Effective Event=`created_at DESC,id DESC`。

Append-onlyはRepository APIで守る。

## 15. 008 Analytics 作成順

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

UNIQUE `(analysis_run_id,target_type,target_id,metric_name,metric_version)`。

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
include_all_episodes INTEGER NOT NULL
created_at
```

UNIQUE `(corpus_id,reference_work_id)`。

### `style_corpus_episode_memberships`

```text
id
work_membership_id INTEGER NOT NULL REFERENCES style_corpus_work_memberships(id) ON DELETE CASCADE
reference_episode_id INTEGER NOT NULL REFERENCES style_reference_episodes(id) ON DELETE CASCADE
mode TEXT NOT NULL CHECK(mode IN ('include','exclude'))
created_at
```

UNIQUE `(work_membership_id,reference_episode_id)`。

ServiceでEpisodeのWork一致をValidation。

## 18. Aggregate

### `style_aggregates`

```text
id
container_type TEXT NOT NULL
container_id INTEGER NOT NULL
measurement_target_type TEXT NOT NULL
filter_json TEXT NOT NULL DEFAULT '{}'
metric_name TEXT NOT NULL
metric_version INTEGER NOT NULL
statistic TEXT NOT NULL
aggregate_policy_version INTEGER NOT NULL
value_real REAL NOT NULL
source_measurement_count INTEGER NOT NULL
sample_count INTEGER NOT NULL
work_count INTEGER NOT NULL
skipped_target_count INTEGER NOT NULL
filter_state_fingerprint TEXT nullable
input_fingerprint TEXT NOT NULL
warning_json TEXT NOT NULL DEFAULT '[]'
created_at
```

Enum:

```text
container_type=reference_work|corpus
measurement_target_type=document|scene
statistic=mean|median|p10|p25|p75|p90|stddev|min|max
```

Countは0以上。Aggregate RowはImmutable Historical Snapshot。

`container_id`はHistorical保持のためLogical ReferenceとしFKを張らない。

### `style_aggregate_measurements`

```text
aggregate_id INTEGER NOT NULL REFERENCES style_aggregates(id) ON DELETE CASCADE
measurement_id INTEGER NOT NULL REFERENCES style_measurements(id) ON DELETE CASCADE
PRIMARY KEY(aggregate_id,measurement_id)
```

Measurement PurgeでLinkが消えてもAggregate Rowは残る。

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

`active_version_id`は循環FKを作らずServiceで同Profile VersionをValidation。

### `style_profile_versions`

```text
id
profile_id INTEGER NOT NULL REFERENCES style_profiles(id) ON DELETE CASCADE
version_no INTEGER NOT NULL
parent_version_id INTEGER nullable REFERENCES style_profile_versions(id) ON DELETE SET NULL
profile_generation_policy_version INTEGER nullable
created_at
```

UNIQUE `(profile_id,version_no)`。

### `style_rules`

```text
id
profile_version_id INTEGER NOT NULL REFERENCES style_profile_versions(id) ON DELETE CASCADE
target_scope TEXT NOT NULL
scope_selector_json TEXT NOT NULL
metric_name TEXT NOT NULL
metric_version INTEGER NOT NULL
preferred_value REAL nullable
min_value REAL nullable
max_value REAL nullable
weight REAL NOT NULL DEFAULT 1.0
enabled INTEGER NOT NULL DEFAULT 1
severity_policy TEXT NOT NULL DEFAULT 'standard'
source_kind TEXT NOT NULL
created_at
```

`target_scope IN ('document','scene','character')`。
`source_kind IN ('corpus','manual')`。
weight 0..5。

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

Exact Enabled DuplicateはServiceでCanonical Selector比較して拒否する。

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
input_fingerprint TEXT NOT NULL
status TEXT NOT NULL
warning_json TEXT NOT NULL DEFAULT '[]'
enabled_rule_count INTEGER NOT NULL
applicable_rule_count INTEGER NOT NULL
missing_rule_count INTEGER NOT NULL
created_at
finished_at nullable
```

Status:`running|succeeded|failed|cancelled`。

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
severity TEXT NOT NULL
sort_score REAL NOT NULL
explanation_code TEXT NOT NULL
evidence_json TEXT NOT NULL
created_at
```

Severity:`info|warning|strong_warning`。

### `style_finding_reviews`

```text
id
finding_id INTEGER NOT NULL REFERENCES style_findings(id) ON DELETE CASCADE
status TEXT NOT NULL CHECK(status IN ('acknowledged','ignored'))
note TEXT nullable
created_at
```

Append-only。

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
- `PRAGMA foreign_key_check` / `integrity_check`。
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
- Term Explanation subject=TermMention。
- ManualOverride Scope Cascade/Append-only Repository。
- Project Character Link Document uniqueness。
- Measurement Unique。
- Aggregate Policy Version/Input Fingerprint/Measurement Link。
- Rule enabled時min/max必須、preferred範囲、target_scope/source_kind/Aggregate Source。
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
- SourceSnapshot FKをSET NULLへ戻してExactly-one制約と競合させる。
- Standalone Snapshot Delete API追加。
- Draft Tableへ新FK/Column追加。
- Run削除でStable Entity/TermをCascade Delete。
- Mention RowへEntity ID追加。
- Relation/Term Entity Link追加。
- ManualOverride Supersede Pointer再導入。
- Aggregate Policy Versionを保存しない。
- Boundary Analysis RunをStructure SourceでUNIQUEにする。
- Character Aggregate追加。
- AggregateをReference Work Purgeで物理削除。
- Profile Identity/Version統合。
- `analysis_stale`等bool Column追加。
