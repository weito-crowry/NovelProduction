# 12 Storage Schema 詳細設計

## 1. 目的

Style AnalysisのSQLite永続化Schema、Migration分割、主要Constraint/Indexを確定する。既存NovelProduction Authoring Schemaを変更せず、`style_` prefixのbounded contextとして追加する。

上位仕様は `../basic-design.md`。

## 2. Migration方針

既存 `001_initial.sql`〜`005_structured_drafts.sql` は変更しない。新規Migrationは以下3本に固定する。

```text
006_style_analysis_foundation.sql
007_style_analysis_semantics.sql
008_style_analysis_analytics.sql
```

mainへMerge済みMigrationはByte変更しない。

## 3. Project Scope

Style AnalysisはProject Registryが解決したProject-local `story.db` へ保存する。`style_*` Tableに `project_id` を重複保持しない。Reference CorpusもProject-local。

## 4. 共通ルール

- PK: `INTEGER PRIMARY KEY`
- Timestamp: `TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`
- Boolean: `INTEGER NOT NULL CHECK (... IN (0,1))`
- Enum: TEXT + CHECK
- JSON: TEXT + `CHECK (json_valid(column))`
- SHA-256: lowercase hex 64文字
- Text span: `[start_cp,end_cp)`, `end_cp > start_cp`
- Mapping Segmentは片側長0可、両側長0不可
- Order Indexは1-based
- Immutable RowだけUPDATE禁止Trigger
- Purgeを妨げるDELETE禁止Triggerは追加しない

## 5. 006 Foundation

### style_imports

Initial Importの受付状態。

```text
id
source_type TEXT NOT NULL
locator TEXT NOT NULL
status TEXT NOT NULL
job_id INTEGER
error_code TEXT
error_message TEXT
created_at
finished_at
```

Status: `queued | running | succeeded | failed | cancelled`。Refreshでは新しいImport Rowを作らない。

### style_sources

```text
id
source_type TEXT NOT NULL
external_work_id TEXT
canonical_url TEXT
adapter_id TEXT NOT NULL
adapter_version INTEGER NOT NULL
created_at
```

External ID非NULLならPartial Unique Index `(source_type,external_work_id)`。

### style_source_snapshots

```text
id
source_id INTEGER NOT NULL REFERENCES style_sources(id) ON DELETE CASCADE
resource_kind TEXT NOT NULL
external_key TEXT NOT NULL
canonical_url TEXT
fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
status_code INTEGER
etag TEXT
last_modified TEXT
media_type TEXT NOT NULL
payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256)=64)
raw_payload BLOB NOT NULL
adapter_id TEXT NOT NULL
adapter_version INTEGER NOT NULL
metadata_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metadata_json))
```

- INDEX `(source_id,external_key,fetched_at)`
- UNIQUE `(source_id,external_key,payload_sha256)`
- UPDATE禁止

HTML/TXT/EPUBの元Bytesを同じSchemaで保持する。

### style_reference_works

```text
id
source_id INTEGER REFERENCES style_sources(id) ON DELETE SET NULL
external_work_id TEXT
source_url TEXT
title TEXT NOT NULL
author_name TEXT
metadata_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metadata_json))
import_state TEXT NOT NULL
created_at
updated_at
```

`import_state = complete | deleted_source`。Current Catalog ProjectionなのでMetadata Update可。

### style_reference_episodes

```text
id
reference_work_id INTEGER NOT NULL REFERENCES style_reference_works(id) ON DELETE CASCADE
external_episode_id TEXT NOT NULL
title TEXT NOT NULL
order_index INTEGER NOT NULL CHECK(order_index >= 1)
source_url TEXT
latest_snapshot_id INTEGER REFERENCES style_source_snapshots(id) ON DELETE SET NULL
current_text_revision_id INTEGER
created_at
updated_at
```

- UNIQUE `(reference_work_id,external_episode_id)`
- UNIQUE `(reference_work_id,order_index)`
- INDEX `(reference_work_id,order_index)`

`current_text_revision_id` はLogical FK。IngestionServiceが、そのEpisodeのStyleDocumentに属するTextRevisionであることを検証し、Import/Refresh成功Transaction内で更新する。Work全体解析はこのPointerを使う。

### style_documents

```text
id
kind TEXT NOT NULL
reference_episode_id INTEGER REFERENCES style_reference_episodes(id) ON DELETE CASCADE
project_work_id INTEGER
project_episode_id INTEGER
created_at
```

Kind: `reference_episode | project_episode_draft`。

CHECK:

```text
reference_episode:
  reference_episode_id NOT NULL
  project_work_id/project_episode_id NULL

project_episode_draft:
  reference_episode_id NULL
  project_work_id/project_episode_id NOT NULL
```

`FOREIGN KEY (project_work_id,project_episode_id) REFERENCES episodes(work_id,id) ON DELETE CASCADE`。

ReferenceEpisode Documentは1件、Project Documentは `(project_work_id,project_episode_id)` で1件。

### style_text_revisions

```text
id
document_id INTEGER NOT NULL REFERENCES style_documents(id) ON DELETE CASCADE
revision_no INTEGER NOT NULL CHECK(revision_no >= 1)
source_snapshot_id INTEGER REFERENCES style_source_snapshots(id) ON DELETE SET NULL
project_draft_id INTEGER REFERENCES drafts(id) ON DELETE SET NULL
raw_text TEXT NOT NULL
canonical_text TEXT NOT NULL
raw_sha256 TEXT NOT NULL CHECK(length(raw_sha256)=64)
canonical_sha256 TEXT NOT NULL CHECK(length(canonical_sha256)=64)
normalizer_id TEXT NOT NULL
normalizer_version INTEGER NOT NULL
metadata_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metadata_json))
created_at
```

- UNIQUE `(document_id,revision_no)`
- INDEX `(document_id,canonical_sha256)`
- UPDATE禁止

### style_text_mappings

```text
id
text_revision_id INTEGER NOT NULL REFERENCES style_text_revisions(id) ON DELETE CASCADE
order_index INTEGER NOT NULL CHECK(order_index >= 1)
raw_start INTEGER NOT NULL CHECK(raw_start >= 0)
raw_end INTEGER NOT NULL CHECK(raw_end >= raw_start)
canonical_start INTEGER NOT NULL CHECK(canonical_start >= 0)
canonical_end INTEGER NOT NULL CHECK(canonical_end >= canonical_start)
operation TEXT NOT NULL
```

- UNIQUE `(text_revision_id,order_index)`
- Operation: `identity | replace | delete | collapse`
- Raw/Canonical両方0長は禁止

### style_structure_revisions

```text
id
text_revision_id INTEGER NOT NULL REFERENCES style_text_revisions(id) ON DELETE CASCADE
revision_no INTEGER NOT NULL CHECK(revision_no >= 1)
segmenter_id TEXT NOT NULL
segmenter_version INTEGER NOT NULL
source_kind TEXT NOT NULL
parent_structure_revision_id INTEGER REFERENCES style_structure_revisions(id) ON DELETE SET NULL
fingerprint TEXT NOT NULL CHECK(length(fingerprint)=64)
created_at
```

Source Kind: `automatic | semantic | manual`。

- UNIQUE `(text_revision_id,revision_no)`
- UNIQUE `(text_revision_id,fingerprint)`

### style_scenes

```text
id
structure_revision_id INTEGER NOT NULL REFERENCES style_structure_revisions(id) ON DELETE CASCADE
order_index INTEGER NOT NULL CHECK(order_index >= 1)
start_cp INTEGER NOT NULL CHECK(start_cp >= 0)
end_cp INTEGER NOT NULL CHECK(end_cp > start_cp)
created_at
```

UNIQUE `(structure_revision_id,order_index)`。

### style_blocks

```text
id
structure_revision_id INTEGER NOT NULL REFERENCES style_structure_revisions(id) ON DELETE CASCADE
scene_id INTEGER REFERENCES style_scenes(id) ON DELETE CASCADE
order_index INTEGER NOT NULL CHECK(order_index >= 1)
paragraph_index INTEGER NOT NULL CHECK(paragraph_index >= 1)
block_type TEXT NOT NULL
start_cp INTEGER NOT NULL CHECK(start_cp >= 0)
end_cp INTEGER NOT NULL CHECK(end_cp > start_cp)
warning_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(warning_json))
```

- Block Type: `dialogue,narration,monologue,heading,separator,unknown`
- `order_index` はStructureRevision全体でGlobal 1..N
- UNIQUE `(structure_revision_id,order_index)`
- Scene外Separatorは `scene_id=NULL`
- INDEX `(structure_revision_id,start_cp)`

### style_sentences

```text
id
block_id INTEGER NOT NULL REFERENCES style_blocks(id) ON DELETE CASCADE
order_index INTEGER NOT NULL CHECK(order_index >= 1)
start_cp INTEGER NOT NULL CHECK(start_cp >= 0)
end_cp INTEGER NOT NULL CHECK(end_cp > start_cp)
```

UNIQUE `(block_id,order_index)`。

### style_jobs

Project-local persisted queue。

```text
id
job_type TEXT NOT NULL
payload_json TEXT NOT NULL CHECK(json_valid(payload_json))
status TEXT NOT NULL
cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK(cancel_requested IN (0,1))
progress_current INTEGER CHECK(progress_current IS NULL OR progress_current >= 0)
progress_total INTEGER CHECK(progress_total IS NULL OR progress_total >= 0)
result_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(result_json))
warning_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(warning_json))
created_at
started_at
finished_at
error_code
error_message
version INTEGER NOT NULL DEFAULT 1
```

Job Type:

```text
source_import
source_refresh
analyze_document
analyze_reference_work
recompute_aggregate
build_profile
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

INDEX `(status,created_at,id)`。

`progress_total` 未確定時はNULL可。`partial` はWork一括解析など複数対象Jobで一部成功した状態。通常のDocument Jobで任意Failure率からpartialを捏造しない。

### style_analysis_runs

Document Analyzerだけを格納する。

```text
id
document_id INTEGER NOT NULL REFERENCES style_documents(id) ON DELETE CASCADE
analyzer_id TEXT NOT NULL
analyzer_version INTEGER NOT NULL
text_revision_id INTEGER NOT NULL REFERENCES style_text_revisions(id) ON DELETE CASCADE
structure_revision_id INTEGER NOT NULL REFERENCES style_structure_revisions(id) ON DELETE CASCADE
status TEXT NOT NULL
fingerprint TEXT NOT NULL CHECK(length(fingerprint)=64)
config_json TEXT NOT NULL CHECK(json_valid(config_json))
policy_version INTEGER NOT NULL
state_fingerprint TEXT
registry_input_fingerprint TEXT
model_provider TEXT
model_id TEXT
prompt_id TEXT
prompt_version INTEGER
started_at
finished_at
error_code
error_message
warning_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(warning_json))
created_at
```

- `state_fingerprint` / `registry_input_fingerprint` はNULLまたはSHA-256 64文字
- INDEX `(document_id,analyzer_id,created_at,id)`
- ServiceでDocument/TextRevision/StructureRevision所属整合を検証

Status: `queued | running | succeeded | partial | failed | cancelled`。

### style_analysis_run_dependencies

```text
run_id INTEGER NOT NULL REFERENCES style_analysis_runs(id) ON DELETE CASCADE
dependency_run_id INTEGER NOT NULL REFERENCES style_analysis_runs(id) ON DELETE CASCADE
PRIMARY KEY (run_id,dependency_run_id)
CHECK (run_id != dependency_run_id)
```

Dependency LinkはHistorical Provenance。Registry DAGとServiceでDependency Analyzer ID・同Lineageを検証する。

### style_structure_analysis_sources

```text
structure_revision_id INTEGER PRIMARY KEY REFERENCES style_structure_revisions(id) ON DELETE CASCADE
analysis_run_id INTEGER NOT NULL UNIQUE REFERENCES style_analysis_runs(id) ON DELETE CASCADE
```

Service Constraint:

- Structure `source_kind=semantic`
- Run `analyzer_id=scene-boundary-detector`
- Run Structure = Semantic RevisionのParent Automatic Structure

## 6. 007 Semantics

### style_entities

Stable Identity。

```text
id
reference_work_id INTEGER REFERENCES style_reference_works(id) ON DELETE CASCADE
document_id INTEGER REFERENCES style_documents(id) ON DELETE CASCADE
entity_type TEXT NOT NULL
canonical_name TEXT NOT NULL
origin TEXT NOT NULL
created_by_run_id INTEGER REFERENCES style_analysis_runs(id) ON DELETE SET NULL
created_at
```

- Exactly One Scope: Reference Work / Document
- Origin: `inferred | manual`
- INDEX `(reference_work_id,entity_type,canonical_name)` / `(document_id,entity_type,canonical_name)`
- Effective `enabled/name/type` は10 ManualOverride

### style_mentions

Mention Extractor Output。Entity Mappingを直接持たない。

```text
id
structure_revision_id INTEGER NOT NULL REFERENCES style_structure_revisions(id) ON DELETE CASCADE
scene_id INTEGER NOT NULL REFERENCES style_scenes(id) ON DELETE CASCADE
block_id INTEGER NOT NULL REFERENCES style_blocks(id) ON DELETE CASCADE
start_cp INTEGER NOT NULL CHECK(start_cp >= 0)
end_cp INTEGER NOT NULL CHECK(end_cp > start_cp)
surface TEXT NOT NULL
mention_type TEXT NOT NULL
confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1)
analysis_run_id INTEGER NOT NULL REFERENCES style_analysis_runs(id) ON DELETE CASCADE
```

INDEX `(structure_revision_id,start_cp)`。Entity Resolverは `mention.entity_resolution` Annotationを作る。

### style_entity_aliases

```text
id
entity_id INTEGER NOT NULL REFERENCES style_entities(id) ON DELETE CASCADE
alias TEXT NOT NULL
alias_kind TEXT NOT NULL
origin TEXT NOT NULL
analysis_run_id INTEGER REFERENCES style_analysis_runs(id) ON DELETE SET NULL
source_mention_id INTEGER REFERENCES style_mentions(id) ON DELETE SET NULL
created_at
```

自動AliasはAnalysisRun必須、ManualはNULL可。重複防止はRepository。

### style_entity_links

```text
id
style_entity_id INTEGER NOT NULL REFERENCES style_entities(id) ON DELETE CASCADE
project_character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE
origin TEXT NOT NULL
confidence REAL
analysis_run_id INTEGER REFERENCES style_analysis_runs(id) ON DELETE SET NULL
created_at
```

v1はManual Linkだけでもよい。

### style_relations

```text
id
source_entity_id INTEGER NOT NULL REFERENCES style_entities(id) ON DELETE CASCADE
target_entity_id INTEGER NOT NULL REFERENCES style_entities(id) ON DELETE CASCADE
relation_type TEXT NOT NULL
scene_id INTEGER REFERENCES style_scenes(id) ON DELETE CASCADE
confidence REAL
origin TEXT NOT NULL
analysis_run_id INTEGER NOT NULL REFERENCES style_analysis_runs(id) ON DELETE CASCADE
created_at
```

### style_terms

Stable Identity。

```text
id
reference_work_id INTEGER REFERENCES style_reference_works(id) ON DELETE CASCADE
document_id INTEGER REFERENCES style_documents(id) ON DELETE CASCADE
canonical_label TEXT NOT NULL
term_type TEXT NOT NULL
origin TEXT NOT NULL
created_by_run_id INTEGER REFERENCES style_analysis_runs(id) ON DELETE SET NULL
created_at
```

- Exactly One Scope
- Origin: `inferred | manual`
- Effective `enabled/label/type` は10 ManualOverride
- Novelty/Exact MatchはColumnに持たない

### style_term_aliases

```text
id
term_id INTEGER NOT NULL REFERENCES style_terms(id) ON DELETE CASCADE
alias TEXT NOT NULL
origin TEXT NOT NULL
analysis_run_id INTEGER REFERENCES style_analysis_runs(id) ON DELETE SET NULL
created_at
```

### style_term_mentions

Term Resolver Output。

```text
id
term_id INTEGER NOT NULL REFERENCES style_terms(id) ON DELETE CASCADE
structure_revision_id INTEGER NOT NULL REFERENCES style_structure_revisions(id) ON DELETE CASCADE
scene_id INTEGER NOT NULL REFERENCES style_scenes(id) ON DELETE CASCADE
block_id INTEGER NOT NULL REFERENCES style_blocks(id) ON DELETE CASCADE
start_cp INTEGER NOT NULL CHECK(start_cp >= 0)
end_cp INTEGER NOT NULL CHECK(end_cp > start_cp)
surface TEXT NOT NULL
analysis_run_id INTEGER NOT NULL REFERENCES style_analysis_runs(id) ON DELETE CASCADE
```

Occurrence Indexなし。

### style_term_entity_links

```text
id
term_id INTEGER NOT NULL REFERENCES style_terms(id) ON DELETE CASCADE
entity_id INTEGER NOT NULL REFERENCES style_entities(id) ON DELETE CASCADE
origin TEXT NOT NULL
confidence REAL
analysis_run_id INTEGER REFERENCES style_analysis_runs(id) ON DELETE SET NULL
created_at
```

### style_annotations

Run付き推論値。

```text
id
annotation_type TEXT NOT NULL
subject_type TEXT NOT NULL
subject_id INTEGER NOT NULL
value_json TEXT NOT NULL CHECK(json_valid(value_json))
confidence REAL CHECK(confidence IS NULL OR confidence BETWEEN 0 AND 1)
analysis_run_id INTEGER NOT NULL REFERENCES style_analysis_runs(id) ON DELETE CASCADE
start_cp INTEGER
end_cp INTEGER
created_at
```

INDEX `(subject_type,subject_id,annotation_type,analysis_run_id)`。

用途:

```text
term_candidate
mention.entity_resolution
speaker
scene.function/tone/pace/information_load/interaction
pov
block.semantic_primary
scene_boundary_candidate
term.novelty
term.exact_match_safe
term_explanation
```

Generic Subject FKはOverride/Annotation RegistryでValidationする。

### style_review_items

```text
id
item_type TEXT NOT NULL
subject_type TEXT NOT NULL
subject_id INTEGER NOT NULL
analysis_run_id INTEGER REFERENCES style_analysis_runs(id) ON DELETE SET NULL
priority TEXT NOT NULL
status TEXT NOT NULL
reason_code TEXT NOT NULL
evidence_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(evidence_json))
version INTEGER NOT NULL DEFAULT 1
created_at
resolved_at
```

Priority: `low | normal | high`。Status: `open | resolved | ignored | superseded`。

### style_inference_reviews

```text
id
subject_type TEXT NOT NULL
subject_id INTEGER NOT NULL
field_path TEXT NOT NULL
analysis_run_id INTEGER NOT NULL REFERENCES style_analysis_runs(id) ON DELETE CASCADE
review_status TEXT NOT NULL
note TEXT
created_at
```

Status: `confirmed | rejected`。同一Inference/Fieldは最新 `created_at,id` をEffective Reviewとする。

### style_manual_overrides

```text
id
subject_type TEXT NOT NULL
subject_id INTEGER NOT NULL
field_path TEXT NOT NULL
operation TEXT NOT NULL
value_json TEXT
base_analysis_run_id INTEGER REFERENCES style_analysis_runs(id) ON DELETE SET NULL
structure_revision_id INTEGER REFERENCES style_structure_revisions(id) ON DELETE SET NULL
note TEXT
created_at
superseded_by_id INTEGER REFERENCES style_manual_overrides(id) ON DELETE SET NULL
```

Operation: `set | clear | revert`。

CHECK:

- `set`: value_json NOT NULL + valid JSON
- `clear/revert`: value_json NULL

INDEX `(subject_type,subject_id,field_path,superseded_by_id)`。Direct OverrideはReviewItem FK不要。

## 7. 008 Analytics

### style_measurements

```text
id
analysis_run_id INTEGER NOT NULL REFERENCES style_analysis_runs(id) ON DELETE CASCADE
structure_revision_id INTEGER NOT NULL REFERENCES style_structure_revisions(id) ON DELETE CASCADE
target_type TEXT NOT NULL
target_id INTEGER NOT NULL
metric_name TEXT NOT NULL
metric_version INTEGER NOT NULL
value_real REAL
value_int INTEGER
sample_count INTEGER NOT NULL CHECK(sample_count >= 0)
created_at
```

Value Real/Int同時設定禁止CHECK。INDEX `(target_type,target_id,metric_name,metric_version)` と `(analysis_run_id,metric_name)`。

### style_corpora

```text
id
name TEXT NOT NULL
description TEXT NOT NULL DEFAULT ''
created_at
updated_at
```

### style_corpus_work_memberships

```text
corpus_id INTEGER NOT NULL REFERENCES style_corpora(id) ON DELETE CASCADE
reference_work_id INTEGER NOT NULL REFERENCES style_reference_works(id) ON DELETE CASCADE
include_all_episodes INTEGER NOT NULL CHECK(include_all_episodes IN (0,1))
created_at
PRIMARY KEY (corpus_id,reference_work_id)
```

### style_corpus_episode_memberships

```text
corpus_id INTEGER NOT NULL REFERENCES style_corpora(id) ON DELETE CASCADE
reference_episode_id INTEGER NOT NULL REFERENCES style_reference_episodes(id) ON DELETE CASCADE
membership_mode TEXT NOT NULL
PRIMARY KEY (corpus_id,reference_episode_id)
```

Mode: `include | exclude`。

### style_aggregates

```text
id
scope_type TEXT NOT NULL
scope_id INTEGER NOT NULL
filter_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(filter_json))
metric_name TEXT NOT NULL
metric_version INTEGER NOT NULL
statistic TEXT NOT NULL
value_real REAL NOT NULL
sample_count INTEGER NOT NULL
source_measurement_count INTEGER NOT NULL
work_count INTEGER NOT NULL
fingerprint TEXT NOT NULL CHECK(length(fingerprint)=64)
created_at
```

INDEX `(scope_type,scope_id,metric_name,metric_version)` と `(fingerprint)`。

### style_profiles

```text
id
name TEXT NOT NULL
description TEXT NOT NULL DEFAULT ''
source_corpus_id INTEGER REFERENCES style_corpora(id) ON DELETE SET NULL
status TEXT NOT NULL
active_version_id INTEGER
created_at
updated_at
```

Status: `draft | active | archived`。`active_version_id` はLogical FKでProfileServiceが同Profile所属をValidation。

### style_profile_versions

```text
id
profile_id INTEGER NOT NULL REFERENCES style_profiles(id) ON DELETE CASCADE
version_no INTEGER NOT NULL CHECK(version_no >= 1)
parent_version_id INTEGER REFERENCES style_profile_versions(id) ON DELETE SET NULL
created_at
```

UNIQUE `(profile_id,version_no)`。UPDATE禁止。

### style_rules

```text
id
profile_version_id INTEGER NOT NULL REFERENCES style_profile_versions(id) ON DELETE CASCADE
scope_selector_json TEXT NOT NULL CHECK(json_valid(scope_selector_json))
metric_name TEXT NOT NULL
metric_version INTEGER NOT NULL
preferred_value REAL
min_value REAL
max_value REAL
weight REAL NOT NULL CHECK(weight BETWEEN 0 AND 5)
enabled INTEGER NOT NULL CHECK(enabled IN (0,1))
severity_policy TEXT NOT NULL
source_kind TEXT NOT NULL
created_at
```

ProfileVersion/RuleはImmutable。

### style_lint_runs

```text
id
document_id INTEGER NOT NULL REFERENCES style_documents(id) ON DELETE CASCADE
text_revision_id INTEGER NOT NULL REFERENCES style_text_revisions(id) ON DELETE CASCADE
structure_revision_id INTEGER NOT NULL REFERENCES style_structure_revisions(id) ON DELETE CASCADE
profile_id INTEGER NOT NULL REFERENCES style_profiles(id) ON DELETE CASCADE
profile_version_id INTEGER NOT NULL REFERENCES style_profile_versions(id) ON DELETE CASCADE
basic_metric_run_id INTEGER REFERENCES style_analysis_runs(id) ON DELETE SET NULL
semantic_metric_run_id INTEGER REFERENCES style_analysis_runs(id) ON DELETE SET NULL
status TEXT NOT NULL
warning_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(warning_json))
enabled_rule_count INTEGER NOT NULL DEFAULT 0
applicable_rule_count INTEGER NOT NULL DEFAULT 0
missing_rule_count INTEGER NOT NULL DEFAULT 0
created_at
finished_at
```

### style_findings

```text
id
lint_run_id INTEGER NOT NULL REFERENCES style_lint_runs(id) ON DELETE CASCADE
rule_id INTEGER NOT NULL REFERENCES style_rules(id) ON DELETE CASCADE
target_type TEXT NOT NULL
target_id INTEGER NOT NULL
metric_name TEXT NOT NULL
observed_value REAL NOT NULL
expected_min REAL
expected_max REAL
preferred_value REAL
deviation REAL NOT NULL
severity TEXT NOT NULL
sort_score REAL NOT NULL
explanation_code TEXT NOT NULL
evidence_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(evidence_json))
created_at
```

INDEX `(lint_run_id,severity,sort_score)`。

### style_finding_reviews

```text
id
finding_id INTEGER NOT NULL REFERENCES style_findings(id) ON DELETE CASCADE
status TEXT NOT NULL
note TEXT
created_at
```

Status: `acknowledged | ignored`。

## 8. Reference Work Purge

Reference Work PurgeはService Transaction。

1. Workから `source_id` 取得
2. ReferenceWork DELETE
3. Episode/Document/Entity/Term/Corpus Membership Cascade
4. 同Sourceを参照する別ReferenceWorkが0ならSource DELETE
5. SourceSnapshot Cascade
6. Commit

Refreshで消えたEpisodeの古いSnapshotはWork全体Purgeまでは残す。過去Aggregate/Profile/Ruleは本文を含まない履歴値として保持可。

## 9. DB容量

v1はRaw Payload BLOBとRaw/Canonical TextをSQLiteへ保存する。実測で容量問題が出てからStorage抽象化を追加する。

## 10. Repository分割

```text
SourceRepository
TextRepository
StructureRepository
AnalysisRepository
EntityRepository
TermRepository
ReviewRepository
MetricRepository
CorpusRepository
ProfileRepository
LintRepository
```

既存同様 `sqlite3.Connection` 注入。ORM追加なし。

## 11. Migration / Integration Test

- Fresh 001〜008
- 005 DB -> 006〜008
- Migration Checksum
- Foreign Key / Integrity Check
- JSON/Enum/CHECK
- Mapping片側Zero/両側Zero
- Block Global Order
- ReferenceEpisode Current Text Pointer Validation
- Job Type/Status/Progress/Partial
- Entity/Term Exactly-one Scope
- Mention RowにEntity IDなし
- Term IdentityにNovelty/ExactMatchSafeなし
- AnalysisRun State/Registry Fingerprint
- AnalysisRun Dependency Link
- Dependency Link Purge Cascade
- Semantic Structure Source Run Link
- ManualOverride Set/Clear/Revert CHECK
- Profile Version Uniqueness / Active Version所属Validation
- Reference Work Purge Transaction
- Refresh削除EpisodeではSnapshot保持
- Project Episode Cascade
- Immutable Snapshot/TextRevision/ProfileVersion UPDATE拒否

DB IntegrityはMigration/Integration Suiteで確認し、各Caseへ重複追加しない。

## 12. Codex禁止事項

- 001〜005変更
- ORM追加
- Style TableへProject ID追加
- EPUB Raw PayloadをTEXTへ変換
- ReferenceEpisode Current Text Pointerを暗黙Latest Queryだけで代替
- Job Progress/PartialをAPI memoryだけに保持
- Entity/TermをEpisode単位へ分断
- Mention RowへEntity IDを戻す
- Entity/Term Identity Rowを再解析で推論上書き
- Term IdentityへNovelty/ExactMatchSafe追加
- Occurrence Index追加
- AnalysisRun Dependency/State Provenance省略
- Profile Identity/Versionを同Rowへ戻す
- Active Versionを暗黙Latestで更新
- ReferenceWork DELETEだけでSource/Snapshotも消えると仮定
- Purge不能DELETE Trigger追加
