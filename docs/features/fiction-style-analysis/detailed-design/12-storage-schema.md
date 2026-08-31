# 12 Storage Schema 詳細設計

## 1. 目的

Style AnalysisのSQLite Schema、Migration分割、主要Constraint/Indexを確定する。既存Authoring Schemaを変更せず `style_` prefixで追加する。

上位仕様は `../basic-design.md`。

## 2. Migration

既存001〜005は変更しない。

```text
006_style_analysis_foundation.sql
007_style_analysis_semantics.sql
008_style_analysis_analytics.sql
```

Merge済みMigrationはByte変更しない。

## 3. 共通

- Project-local `story.db`。style tableへproject_idを追加しない。
- PK: `INTEGER PRIMARY KEY`
- Timestamp: `TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`
- Boolean/Enum/JSONはCHECKを付ける。
- SHA-256は64文字Lowercase Hex。
- Text Spanは `[start_cp,end_cp)`。
- Immutable RowだけUPDATE禁止Trigger。
- Purgeを阻害するDELETE禁止Triggerは作らない。

## 4. 006 Foundation作成順

```text
style_jobs
style_imports
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

後続Tableを指すCurrent PointerはLogical FKとしてService Validationする。

## 5. style_jobs / style_imports

### style_jobs

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

Type:

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

### style_imports

Import受付記録だけを持つ。

```text
id
source_type TEXT NOT NULL
locator TEXT NOT NULL
job_id INTEGER NOT NULL UNIQUE REFERENCES style_jobs(id) ON DELETE CASCADE
created_at
```

Status/Error/Progressを重複保持しない。GET ImportはJobをJoinする。

## 6. Source / Reference Catalog

### style_sources

```text
id
source_type
external_work_id nullable
canonical_url nullable
adapter_id
adapter_version
created_at
```

External ID非NULLならPartial Unique `(source_type,external_work_id)`。

### style_source_snapshots

```text
id
source_id INTEGER NOT NULL REFERENCES style_sources(id) ON DELETE CASCADE
resource_kind
external_key
canonical_url nullable
fetched_at
status_code nullable
etag nullable
last_modified nullable
media_type
payload_sha256
raw_payload BLOB
adapter_id
adapter_version
metadata_json
```

UNIQUE `(source_id,external_key,payload_sha256)`。UPDATE禁止。

### style_reference_works

```text
id
source_id nullable REFERENCES style_sources(id) ON DELETE SET NULL
external_work_id nullable
source_url nullable
title
author_name nullable
metadata_json
import_state
created_at
updated_at
```

### style_reference_episodes

```text
id
reference_work_id INTEGER NOT NULL REFERENCES style_reference_works(id) ON DELETE CASCADE
external_episode_id
title
order_index INTEGER NOT NULL CHECK(order_index >= 1)
source_url nullable
latest_snapshot_id nullable REFERENCES style_source_snapshots(id) ON DELETE SET NULL
created_at
updated_at
```

UNIQUE `(reference_work_id,external_episode_id)`、`(reference_work_id,order_index)`。

**Current Text PointerはReferenceEpisodeへ持たない。StyleDocumentに統一する。**

## 7. style_documents

```text
id
kind TEXT NOT NULL
reference_episode_id INTEGER REFERENCES style_reference_episodes(id) ON DELETE CASCADE
project_work_id INTEGER
project_episode_id INTEGER
current_text_revision_id INTEGER
current_structure_revision_id INTEGER
created_at
```

Kind:

```text
reference_episode
project_episode_draft
```

Scope CHECK:

- Reference: reference_episode_idのみ。
- Project: project_work_id/project_episode_idのみ。

Project Pairは既存episodesへFK。

Current PointerはLogical FK。Serviceで:

### current_text_revision_id

- NULLまたは同DocumentのTextRevision。

### current_structure_revision_id

- NULLまたは同DocumentのStructureRevision。
- さらにそのStructureのTextRevision = `current_text_revision_id`。

新Current Textへ切替時はCurrent StructureをNULLへClearする。

## 8. Text / Structure

### style_text_revisions

```text
id
document_id INTEGER NOT NULL REFERENCES style_documents(id) ON DELETE CASCADE
revision_no
source_snapshot_id nullable
project_draft_id nullable
raw_text
canonical_text
raw_sha256
canonical_sha256
normalizer_id
normalizer_version
metadata_json
created_at
```

UNIQUE `(document_id,revision_no)`。UPDATE禁止。

### style_text_mappings

TextRevision、Order、Raw/Canonical Start/End、Operation。片側0長可、両側0長不可。

### style_structure_revisions

```text
id
text_revision_id INTEGER NOT NULL REFERENCES style_text_revisions(id) ON DELETE CASCADE
revision_no
segmenter_id
segmenter_version
source_kind
parent_structure_revision_id nullable
fingerprint
created_at
```

Source Kind `automatic|semantic|manual`。UNIQUE Revision No/Fingerprint。

### style_scenes / style_blocks / style_sentences

- Scene OrderはRevision内。
- Block OrderはRevision全体Global。
- Sentence OrderはBlock内。
- SpanはCanonical Text内。
- Separator Blockはscene_id NULL可。

## 9. AnalysisRun

```text
id
document_id
analyzer_id/analyzer_version
text_revision_id
structure_revision_id
status
fingerprint
config_json
policy_version
state_fingerprint nullable
registry_input_fingerprint nullable
model_provider/model_id nullable
prompt_id/prompt_version nullable
started_at/finished_at
error_code/error_message
warning_json
created_at
```

State/Registry FingerprintはNULLまたは64文字。

### style_analysis_run_dependencies

```text
run_id
dependency_run_id
PRIMARY KEY(run_id,dependency_run_id)
CHECK(run_id != dependency_run_id)
```

双方ON DELETE CASCADE。

### style_structure_analysis_sources

Semantic Structure Revision IDをPK、Boundary AnalysisRun IDをUNIQUE FK。ServiceでParent/Analyzer整合を検証。

## 10. 007 Semantics

### style_entities

```text
id
reference_work_id nullable
document_id nullable
entity_type
canonical_name
origin = inferred | manual
created_by_run_id nullable
created_at
```

Exactly One Scope。

### style_mentions

```text
id
structure_revision_id
scene_id
block_id
start_cp/end_cp
surface
mention_type
entity_type_candidate
canonical_name_candidate
confidence
analysis_run_id
```

Mention RowにEntity IDを持たない。Candidate Typeは04 enum、Candidate Name 1〜200をService Validation。

### Entity Alias/Link/Relation

04契約どおり。Manual AliasはRun NULL可。RelationはRun必須。

### style_terms

Stable Identity。Scope Exactly One。Novelty/ExactMatch Columnなし。

### Term Alias/Mention/Entity Link

05契約どおり。Occurrence Indexなし。

### style_annotations

Generic Run Output。JSON + optional Confidence/Span + AnalysisRun FK。

Term Resolver Attributeについて:

```text
UNIQUE logical rule:
analysis_run_id + subject_type=term + subject_id + annotation_type
for annotation_type in term.novelty, term.exact_match_safe
```

SQLite Partial Unique Indexを使えるなら次を作る。

```sql
CREATE UNIQUE INDEX ...
ON style_annotations(analysis_run_id, subject_type, subject_id, annotation_type)
WHERE subject_type='term'
  AND annotation_type IN ('term.novelty','term.exact_match_safe');
```

### Review / Override

ReviewItem、InferenceReview、ManualOverrideは10契約。Override Operation `set|clear|revert`。

## 11. 008 Analytics

### style_measurements

Run/Structure/Target/Metric/Value/Sample Count。Value Real/Intは片方だけ。

### Corpus Membership

Work Membership:

```text
corpus_id
reference_work_id
include_all_episodes
created_at
PRIMARY KEY(corpus_id,reference_work_id)
```

Episode Override:

```text
corpus_id
reference_episode_id
membership_mode = include | exclude
PRIMARY KEY(corpus_id,reference_episode_id)
```

Episode Overrideは同Corpus Work Membership存在をService Validation。Work Membership削除時、配下Overrideを同Transaction削除。

### style_aggregates

```text
id
scope_type/scope_id
filter_json
metric_name/metric_version
statistic
value_real
source_measurement_count
sample_count
work_count
skipped_target_count
fingerprint
created_at
```

Count意味は08正本。

### Profile / Lint

ProfileはIdentity + Immutable Version/Rule。`active_version_id` はLogical FK。同Profile所属をService Validation。

LintRun/Finding/FindingReviewは11契約。

## 12. Purge

Reference Work Purge:

1. WorkのSource ID取得
2. Work DELETE
3. Episode/Document/Entity/Term/Membership Cascade
4. 同Source参照Workが0ならSource DELETE
5. Snapshot Cascade

過去Aggregate/Profile/Ruleは本文を含まない履歴値として保持可。

## 13. Migration / Integration Test

- Fresh001〜008 / Existing005→008
- Job Table→Import Table作成順 + Import FK
- Import Status重複Columnなし
- Current Text Pointer同Document Validation
- Current Structure Pointer同Current Text Validation
- Current Text切替でStructure Clear
- Block Global Order
- Mention Candidate Fields + Entity IDなし
- Term Attribute Partial Unique
- Entity/Term Exactly-one Scope
- AnalysisRun State/Registry/Dependency
- Override Set/Clear/Revert
- Corpus Membership Validation
- Aggregate Count Columns
- Profile Active Version Validation
- Purge/Cascade
- Immutable Row Update拒否

## 14. Codex禁止事項

- Current TextをReferenceEpisodeとDocumentで二重管理
- Import Status/ErrorをJobと二重管理
- Current PointerをLatest Queryで代替
- Mention Candidate Fields省略
- Mention RowへEntity ID追加
- Term Attribute重複保存
- Aggregate Count統合
- Profile Identity/Version統合
- 001〜005変更
- ORM追加
