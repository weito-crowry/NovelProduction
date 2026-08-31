# 12 Storage Schema 詳細設計

## 1. 目的

Style AnalysisのSQLite永続化schema、migration分割、主要制約・indexを確定する。既存NovelProductionのauthoring schemaを変更せず、`style_` prefixのbounded contextとして追加する。

上位仕様は `../basic-design.md`。

## 2. Migration方針

既存 `001_initial.sql`〜`005_structured_drafts.sql` は変更しない。

新規migrationは次の3本に固定する。

```text
006_style_analysis_foundation.sql
007_style_analysis_semantics.sql
008_style_analysis_analytics.sql
```

mainへmerge済みmigrationはbyte変更しない。

## 3. Project scope

Style Analysisは既存Project Registryが解決したproject-local `story.db` へ保存する。各 `style_*` tableに `project_id` を重複保持しない。

Reference corpusもv1ではproject-local。

## 4. 共通ルール

- PK: `INTEGER PRIMARY KEY`
- timestamp: `TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`
- boolean: `INTEGER NOT NULL CHECK (... IN (0,1))`
- enum: TEXT + CHECK
- JSON: TEXT + `CHECK (json_valid(column))`
- SHA-256: lowercase hex 64文字
- 通常text span: `[start_cp,end_cp)`, `end_cp > start_cp`
- mapping segmentはdelete/collapseを表せるためraw/canonical片側長0を許可する
- order indexは1-based
- immutable rowのみUPDATE禁止trigger
- DELETEはReference Work purgeを可能にする

## 5. 006 Foundation

### style_imports

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

status: `queued,running,succeeded,failed,cancelled`。

file importのlocatorは元filename。利用権利判定用fieldは保存しない。

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

external IDが非NULLなら partial unique index `(source_type,external_work_id)`。

### style_source_snapshots

```text
id
source_id INTEGER NOT NULL FK style_sources ON DELETE CASCADE
resource_kind TEXT NOT NULL
external_key TEXT NOT NULL
canonical_url TEXT
fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
status_code INTEGER
etag TEXT
last_modified TEXT
media_type TEXT NOT NULL
payload_sha256 TEXT NOT NULL
raw_payload BLOB NOT NULL
adapter_id TEXT NOT NULL
adapter_version INTEGER NOT NULL
metadata_json TEXT NOT NULL DEFAULT '{}'
```

- INDEX `(source_id,external_key,fetched_at)`
- UNIQUE `(source_id,external_key,payload_sha256)`
- UPDATE禁止

BLOBを正本とし、HTML/TXT/EPUBの元bytesを同じschemaで保持する。

### style_reference_works

```text
id
source_id INTEGER FK style_sources ON DELETE SET NULL
external_work_id TEXT
source_url TEXT
title TEXT NOT NULL
author_name TEXT
metadata_json TEXT NOT NULL DEFAULT '{}'
import_state TEXT NOT NULL
created_at
updated_at
```

`import_state = complete | deleted_source`。

ReferenceWorkはcurrent catalog projectionなのでtitle等のmetadata updateを許可する。本文履歴はSnapshot/TextRevision側で保持する。

### style_reference_episodes

```text
id
reference_work_id INTEGER NOT NULL FK ON DELETE CASCADE
external_episode_id TEXT NOT NULL
title TEXT NOT NULL
order_index INTEGER NOT NULL CHECK(order_index >= 1)
source_url TEXT
latest_snapshot_id INTEGER FK style_source_snapshots ON DELETE SET NULL
created_at
updated_at
```

- UNIQUE `(reference_work_id,external_episode_id)`
- UNIQUE `(reference_work_id,order_index)`

refresh時はtitle/order/latest pointerをcurrent catalogとして更新可能。

### style_documents

```text
id
kind TEXT NOT NULL
reference_episode_id INTEGER FK style_reference_episodes ON DELETE CASCADE
project_work_id INTEGER
project_episode_id INTEGER
created_at
```

kind: `reference_episode | project_episode_draft`。

CHECK:

- reference_episode: reference_episode_id NOT NULL、project IDs NULL
- project_episode_draft: reference_episode_id NULL、project_work_id/project_episode_id NOT NULL

`FOREIGN KEY (project_work_id,project_episode_id) REFERENCES episodes(work_id,id) ON DELETE CASCADE`。

- reference episode documentは1件
- project documentは `(project_work_id,project_episode_id)` で1件

### style_text_revisions

```text
id
document_id INTEGER NOT NULL FK style_documents ON DELETE CASCADE
revision_no INTEGER NOT NULL CHECK(revision_no >= 1)
source_snapshot_id INTEGER FK style_source_snapshots ON DELETE SET NULL
project_draft_id INTEGER REFERENCES drafts(id) ON DELETE SET NULL
raw_text TEXT NOT NULL
canonical_text TEXT NOT NULL
raw_sha256 TEXT NOT NULL CHECK(length(raw_sha256)=64)
canonical_sha256 TEXT NOT NULL CHECK(length(canonical_sha256)=64)
normalizer_id TEXT NOT NULL
normalizer_version INTEGER NOT NULL
metadata_json TEXT NOT NULL DEFAULT '{}'
created_at
```

- UNIQUE `(document_id,revision_no)`
- INDEX `(document_id,canonical_sha256)`
- UPDATE禁止

serviceでkindとsource_snapshot/project_draftの整合を検証する。

### style_text_mappings

```text
id
text_revision_id INTEGER NOT NULL FK ON DELETE CASCADE
order_index INTEGER NOT NULL CHECK(order_index >= 1)
raw_start INTEGER NOT NULL CHECK(raw_start >= 0)
raw_end INTEGER NOT NULL CHECK(raw_end >= raw_start)
canonical_start INTEGER NOT NULL CHECK(canonical_start >= 0)
canonical_end INTEGER NOT NULL CHECK(canonical_end >= canonical_start)
operation TEXT NOT NULL
```

- UNIQUE `(text_revision_id,order_index)`
- operation: `identity,replace,delete,collapse`
- raw長とcanonical長の両方が0のsegmentは禁止

### style_structure_revisions

```text
id
text_revision_id INTEGER NOT NULL FK ON DELETE CASCADE
revision_no INTEGER NOT NULL CHECK(revision_no >= 1)
segmenter_id TEXT NOT NULL
segmenter_version INTEGER NOT NULL
source_kind TEXT NOT NULL
parent_structure_revision_id INTEGER FK self ON DELETE SET NULL
fingerprint TEXT NOT NULL
created_at
```

source kind: `automatic | semantic | manual`。

- UNIQUE `(text_revision_id,revision_no)`
- UNIQUE `(text_revision_id,fingerprint)`

### style_scenes

```text
id
structure_revision_id INTEGER NOT NULL FK ON DELETE CASCADE
order_index INTEGER NOT NULL CHECK(order_index >= 1)
start_cp INTEGER NOT NULL
end_cp INTEGER NOT NULL
created_at
```

UNIQUE `(structure_revision_id,order_index)`。

### style_blocks

```text
id
structure_revision_id INTEGER NOT NULL FK ON DELETE CASCADE
scene_id INTEGER FK style_scenes ON DELETE CASCADE
order_index INTEGER NOT NULL CHECK(order_index >= 1)
paragraph_index INTEGER NOT NULL CHECK(paragraph_index >= 1)
block_type TEXT NOT NULL
start_cp INTEGER NOT NULL
end_cp INTEGER NOT NULL
warning_json TEXT NOT NULL DEFAULT '[]'
```

- block type: `dialogue,narration,monologue,heading,separator,unknown`
- `order_index` はStructureRevision全体でglobal 1..N
- UNIQUE `(structure_revision_id,order_index)`
- Scene外separatorは `scene_id=NULL`
- INDEX `(structure_revision_id,start_cp)`

### style_sentences

```text
id
block_id INTEGER NOT NULL FK ON DELETE CASCADE
order_index INTEGER NOT NULL CHECK(order_index >= 1)
start_cp INTEGER NOT NULL
end_cp INTEGER NOT NULL
```

UNIQUE `(block_id,order_index)`。

### style_jobs

```text
id
job_type TEXT NOT NULL
payload_json TEXT NOT NULL CHECK(json_valid(payload_json))
status TEXT NOT NULL
cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK(cancel_requested IN (0,1))
created_at
started_at
finished_at
error_code
error_message
version INTEGER NOT NULL DEFAULT 1
```

INDEX `(status,created_at,id)`。

### style_analysis_runs

Document Analyzerだけを格納する。

```text
id
document_id INTEGER NOT NULL FK ON DELETE CASCADE
analyzer_id TEXT NOT NULL
analyzer_version INTEGER NOT NULL
text_revision_id INTEGER NOT NULL FK ON DELETE CASCADE
structure_revision_id INTEGER NOT NULL FK ON DELETE CASCADE
status TEXT NOT NULL
fingerprint TEXT NOT NULL
config_json TEXT NOT NULL CHECK(json_valid(config_json))
policy_version INTEGER NOT NULL
model_provider TEXT
model_id TEXT
prompt_id TEXT
prompt_version INTEGER
started_at
finished_at
error_code
error_message
warning_json TEXT NOT NULL DEFAULT '[]'
created_at
```

INDEX `(document_id,analyzer_id,created_at)`。

succeeded fingerprint reuseはrepository queryで解決する。failed/partialを含むUNIQUEは作らない。

## 6. 007 Semantics

### style_entities

```text
id
reference_work_id INTEGER FK style_reference_works ON DELETE CASCADE
document_id INTEGER FK style_documents ON DELETE CASCADE
entity_type TEXT NOT NULL
canonical_name TEXT NOT NULL
description TEXT
status TEXT NOT NULL
created_by_run_id INTEGER FK style_analysis_runs ON DELETE SET NULL
created_at
```

CHECK exactly one scope:

```text
(reference_work_id IS NOT NULL) != (document_id IS NOT NULL)
```

INDEX `(reference_work_id,entity_type,canonical_name)` と `(document_id,entity_type,canonical_name)`。

### style_mentions

```text
id
entity_id INTEGER FK style_entities ON DELETE SET NULL
structure_revision_id INTEGER NOT NULL FK ON DELETE CASCADE
scene_id INTEGER NOT NULL FK ON DELETE CASCADE
block_id INTEGER NOT NULL FK ON DELETE CASCADE
start_cp INTEGER NOT NULL
end_cp INTEGER NOT NULL
surface TEXT NOT NULL
mention_type TEXT NOT NULL
confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1)
analysis_run_id INTEGER NOT NULL FK ON DELETE CASCADE
```

INDEX `(structure_revision_id,start_cp)`。

### style_entity_aliases

```text
id
entity_id INTEGER NOT NULL FK ON DELETE CASCADE
alias TEXT NOT NULL
alias_kind TEXT NOT NULL
status TEXT NOT NULL
source_mention_id INTEGER FK style_mentions ON DELETE SET NULL
created_at
```

UNIQUE `(entity_id,alias,alias_kind)`。

Migration内では `style_mentions` の後に作成する。

### style_entity_links

```text
id
style_entity_id INTEGER NOT NULL FK ON DELETE CASCADE
project_character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE
status TEXT NOT NULL
confidence REAL
created_at
```

UNIQUE `style_entity_id`。serviceでdocument-scoped Entityだけ許可する。

### style_relations

```text
id
source_entity_id INTEGER NOT NULL FK ON DELETE CASCADE
target_entity_id INTEGER NOT NULL FK ON DELETE CASCADE
relation_type TEXT NOT NULL
scene_id INTEGER FK ON DELETE CASCADE
confidence REAL
status TEXT NOT NULL
analysis_run_id INTEGER FK ON DELETE CASCADE
```

serviceでsource/target scope一致を検証する。

### style_terms

```text
id
reference_work_id INTEGER FK style_reference_works ON DELETE CASCADE
document_id INTEGER FK style_documents ON DELETE CASCADE
canonical_label TEXT NOT NULL
term_type TEXT NOT NULL
novelty TEXT NOT NULL
exact_match_safe INTEGER NOT NULL CHECK(exact_match_safe IN (0,1))
status TEXT NOT NULL
created_by_run_id INTEGER FK style_analysis_runs ON DELETE SET NULL
created_at
```

Entity同様、reference_work/document exactly one scope。

### style_term_aliases

```text
id
term_id INTEGER NOT NULL FK ON DELETE CASCADE
alias TEXT NOT NULL
created_at
```

UNIQUE `(term_id,alias)`。

### style_term_mentions

```text
id
term_id INTEGER NOT NULL FK ON DELETE CASCADE
scene_id INTEGER NOT NULL FK ON DELETE CASCADE
block_id INTEGER NOT NULL FK ON DELETE CASCADE
start_cp INTEGER NOT NULL
end_cp INTEGER NOT NULL
surface TEXT NOT NULL
analysis_run_id INTEGER NOT NULL FK ON DELETE CASCADE
```

`occurrence_index` は持たない。

### style_term_entity_links

```text
id
term_id INTEGER NOT NULL FK ON DELETE CASCADE
entity_id INTEGER NOT NULL FK ON DELETE CASCADE
confidence REAL
status TEXT NOT NULL
created_at
```

UNIQUE `(term_id,entity_id)`。serviceでscope一致を検証。

### style_annotations

```text
id
annotation_type TEXT NOT NULL
subject_type TEXT NOT NULL
subject_id INTEGER NOT NULL
value_json TEXT NOT NULL CHECK(json_valid(value_json))
confidence REAL
analysis_run_id INTEGER NOT NULL FK ON DELETE CASCADE
start_cp INTEGER
end_cp INTEGER
created_at
```

INDEX `(subject_type,subject_id,annotation_type)`。
Generic subject FKは張らずregistry validation。

### style_review_items

10のfields。priority `low,normal,high`、status `open,resolved,ignored,superseded`、version integer。

### style_inference_reviews

10定義。UNIQUE `(subject_type,subject_id,field_path,analysis_run_id)`。

### style_manual_overrides

10定義。`note` nullable、`superseded_by_id` self FK。active lookup index `(subject_type,subject_id,field_path,superseded_by_id)`。

## 7. 008 Analytics

### style_measurements

07定義。

INDEX `(target_type,target_id,metric_name,metric_version)`。

### style_corpora

08定義。

### style_corpus_work_memberships

`corpus_id`, `reference_work_id`, `include_all_episodes`, unique pair。

### style_corpus_episode_memberships

```text
corpus_id
reference_episode_id
membership_mode = include | exclude
```

UNIQUE pair。

### style_aggregates

08定義。`work_count` を含む。fingerprint index。

### style_profiles

stable identity:

```text
id
name TEXT NOT NULL
description TEXT NOT NULL DEFAULT ''
source_corpus_id INTEGER FK style_corpora ON DELETE SET NULL
status TEXT NOT NULL
created_at
updated_at
```

status: `draft,active,archived`。

### style_profile_versions

```text
id
profile_id INTEGER NOT NULL FK style_profiles ON DELETE CASCADE
version_no INTEGER NOT NULL CHECK(version_no >= 1)
parent_version_id INTEGER FK self ON DELETE SET NULL
created_at
```

UNIQUE `(profile_id,version_no)`。version rowはUPDATE禁止。

### style_rules

```text
id
profile_version_id INTEGER NOT NULL FK style_profile_versions ON DELETE CASCADE
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

ProfileVersionとRuleはimmutable。

### style_lint_runs

```text
id
document_id INTEGER NOT NULL FK style_documents ON DELETE CASCADE
text_revision_id INTEGER NOT NULL FK style_text_revisions ON DELETE CASCADE
structure_revision_id INTEGER NOT NULL FK style_structure_revisions ON DELETE CASCADE
profile_id INTEGER NOT NULL FK style_profiles ON DELETE CASCADE
profile_version_id INTEGER NOT NULL FK style_profile_versions ON DELETE CASCADE
basic_metric_run_id INTEGER FK style_analysis_runs ON DELETE SET NULL
semantic_metric_run_id INTEGER FK style_analysis_runs ON DELETE SET NULL
status TEXT NOT NULL
warning_json TEXT NOT NULL DEFAULT '[]'
enabled_rule_count INTEGER NOT NULL DEFAULT 0
applicable_rule_count INTEGER NOT NULL DEFAULT 0
missing_rule_count INTEGER NOT NULL DEFAULT 0
created_at
finished_at
```

serviceでprofile_version_idがprofile_id所属であることを検証する。

### style_findings

11定義。INDEX `(lint_run_id,severity,sort_score)`。

### style_finding_reviews

11定義。`note` nullable。

## 8. Deletion/Purge

Reference Work purgeはsoft-deleteではなく明示DELETE。関連Source/Snapshot/Document/Semantic dataはFK cascadeで削除する。

Corpus membershipもcascade。既存Aggregateはsource FKを持たないsnapshot値なので残してよい。Profile/Ruleも本文を含まないため保持可能。

Project documentはauthoring Episode削除にcascadeする。

## 9. DB容量

v1はraw payload BLOBとraw/canonical textをSQLiteへ保存する。content-addressed filesystemは導入しない。

DBサイズ問題が実測で発生してからstorage抽象化を追加する。

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

## 11. Migration test

- fresh 001〜008
- 005 DBへ006〜008
- migration checksum
- foreign key check
- reference purge cascade
- project episode cascade
- immutable Snapshot/TextRevision/ProfileVersion UPDATE拒否
- JSON/enum/check
- Block global order unique
- Entity/Term exactly-one scope
- profile version uniqueness
- mapping zero-length片側許容、両側zero拒否

DB integrityはmigration/integration suiteで確認し、各個別テストcaseの末尾へ重複追加しない。

## 12. Codex実装時の禁止事項

- 001〜005を変更しない。
- ORMを追加しない。
- style tableへproject_idを追加しない。
- EPUB raw payloadをTEXTへ無理に変換しない。
- Entity/Termをreference episode document単位へ分断しない。
- Block orderをScene内indexとして実装しない。
- occurrence_indexをTermMentionへ追加しない。
- Profile identityとVersionを同じrowへ戻さない。
- purge不能なDELETE禁止triggerを追加しない。