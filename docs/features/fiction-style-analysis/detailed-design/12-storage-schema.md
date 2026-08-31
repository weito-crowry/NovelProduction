# 12 Storage Schema 詳細設計

## 1. 目的

Style AnalysisのSQLite永続化schema、migration分割、主要制約・indexを確定する。既存NovelProductionのauthoring schemaを変更せず、`style_` prefixのbounded contextとして追加する。

上位仕様は `../basic-design.md`。

## 2. Migration方針

既存 `001_initial.sql`〜`005_structured_drafts.sql` は絶対に変更しない。

新規migrationを以下3本に固定する。

```text
006_style_analysis_foundation.sql
007_style_analysis_semantics.sql
008_style_analysis_analytics.sql
```

実装途中でも005以前を編集してまとめ直さない。各migrationは一度mainへmergeした後はbyte変更禁止。

## 3. Project scope

NovelProductionはprojectごとの `story.db` を既存Project Registryが解決する。Style Analysisも同じDBへ保存する。

したがって各 `style_*` tableへ `project_id` columnを追加しない。APIの `{project_id}` は既存service container/database connection選択にだけ使用する。

Reference corpusはv1ではproject-local。別project間共有DBは作らない。

## 4. 共通ルール

- PK: `INTEGER PRIMARY KEY`
- timestamp: `TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`
- boolean: `INTEGER NOT NULL CHECK (... IN (0,1))`
- enum: TEXT + CHECK
- JSON: TEXT + `CHECK (json_valid(column))`
- hash: lowercase SHA-256 hex 64文字
- code point span: `start_cp INTEGER NOT NULL CHECK(start_cp >= 0)`, `end_cp INTEGER NOT NULL CHECK(end_cp > start_cp)`
- order index: 1-based integer
- delete: reference workの明示purge時に関係データをCASCADE可能にする
- UPDATE禁止が必要なimmutable rowだけupdate triggerを付ける。DELETEは権利/プライバシー上のpurgeを可能にするため禁止しない

## 5. 006 Foundation tables

### style_imports

```text
id
source_type TEXT NOT NULL
locator TEXT NOT NULL
rights_basis TEXT NOT NULL
status TEXT NOT NULL
job_id INTEGER
error_code TEXT
error_message TEXT
created_at
finished_at
```

status CHECK: `queued,running,succeeded,failed,cancelled`。

### style_sources

```text
id
source_type TEXT NOT NULL
external_work_id TEXT
canonical_url TEXT
rights_basis TEXT NOT NULL
adapter_id TEXT NOT NULL
adapter_version INTEGER NOT NULL
created_at
```

UNIQUE `(source_type, external_work_id)` where external IDが非NULL。SQLite partial unique indexを使う。

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
raw_payload TEXT NOT NULL
adapter_id TEXT NOT NULL
adapter_version INTEGER NOT NULL
rights_basis TEXT NOT NULL
metadata_json TEXT NOT NULL DEFAULT '{}'
```

INDEX `(source_id, external_key, fetched_at)`。
UNIQUE `(source_id, external_key, payload_sha256)`。
UPDATE禁止triggerを付ける。

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
```

import_state: `complete,failed,deleted_source`。通常成功時のみcomplete rowを作るためfailedは診断移行用。

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
```

UNIQUE `(reference_work_id, external_episode_id)`
UNIQUE `(reference_work_id, order_index)`

### style_documents

```text
id
kind TEXT NOT NULL
reference_episode_id INTEGER FK style_reference_episodes ON DELETE CASCADE
project_work_id INTEGER
project_episode_id INTEGER
created_at
```

kind: `reference_episode,project_episode_draft`。

CHECK:

- reference_episode: reference_episode_id NOT NULL, project IDs NULL
- project_episode_draft: reference_episode_id NULL, project_work_id/project_episode_id NOT NULL

project pairへ `FOREIGN KEY (project_work_id, project_episode_id) REFERENCES episodes(work_id,id) ON DELETE CASCADE`。

UNIQUE reference episode document。project documentは `(project_work_id,project_episode_id)` で1 document。

### style_text_revisions

```text
id
document_id INTEGER NOT NULL FK style_documents ON DELETE CASCADE
revision_no INTEGER NOT NULL CHECK >=1
source_snapshot_id INTEGER FK style_source_snapshots ON DELETE SET NULL
project_draft_id INTEGER
raw_text TEXT NOT NULL
canonical_text TEXT NOT NULL
raw_sha256 TEXT NOT NULL CHECK length=64
canonical_sha256 TEXT NOT NULL CHECK length=64
normalizer_id TEXT NOT NULL
normalizer_version INTEGER NOT NULL
metadata_json TEXT NOT NULL DEFAULT '{}'
created_at
```

UNIQUE `(document_id,revision_no)`。
INDEX `(document_id,canonical_sha256)`。
UPDATE禁止trigger。

project_draft_idは既存draftへの参照。project document以外はNULL。FKは `(project_work_id,project_episode_id,draft_id)` を直接張れないためserviceでdocumentとの整合を検証し、`drafts.id` 単独FKは既存schemaのglobal uniquenessを利用できる場合のみ張る。実装時に既存draft PKがglobal integer PKであることを確認済みなので `REFERENCES drafts(id) ON DELETE SET NULL` とする。

### style_text_mappings

```text
id
text_revision_id INTEGER NOT NULL FK ON DELETE CASCADE
order_index INTEGER NOT NULL
raw_start INTEGER NOT NULL
raw_end INTEGER NOT NULL
canonical_start INTEGER NOT NULL
canonical_end INTEGER NOT NULL
operation TEXT NOT NULL
```

UNIQUE `(text_revision_id,order_index)`。
operation: `identity,replace,delete,collapse`。

### style_structure_revisions

```text
id
text_revision_id INTEGER NOT NULL FK ON DELETE CASCADE
revision_no INTEGER NOT NULL
segmenter_id TEXT NOT NULL
segmenter_version INTEGER NOT NULL
source_kind TEXT NOT NULL
parent_structure_revision_id INTEGER FK self ON DELETE SET NULL
fingerprint TEXT NOT NULL
created_at
```

source_kind: `automatic,manual`。
UNIQUE `(text_revision_id,revision_no)`。
UNIQUE `(text_revision_id,fingerprint)`。

### style_scenes

```text
id
structure_revision_id INTEGER NOT NULL FK ON DELETE CASCADE
order_index INTEGER NOT NULL
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
order_index INTEGER NOT NULL
paragraph_index INTEGER NOT NULL
block_type TEXT NOT NULL
start_cp INTEGER NOT NULL
end_cp INTEGER NOT NULL
warning_json TEXT NOT NULL DEFAULT '[]'
```

block_type CHECK: `dialogue,narration,monologue,heading,separator,unknown`。
Scene外separatorを許可するためscene_id NULL可。
INDEX `(structure_revision_id,start_cp)`。

### style_sentences

```text
id
block_id INTEGER NOT NULL FK ON DELETE CASCADE
order_index INTEGER NOT NULL
start_cp INTEGER NOT NULL
end_cp INTEGER NOT NULL
```

UNIQUE `(block_id,order_index)`。

### style_jobs

```text
id
job_type TEXT NOT NULL
payload_json TEXT NOT NULL
status TEXT NOT NULL
cancel_requested INTEGER NOT NULL DEFAULT 0
created_at
started_at
finished_at
error_code
error_message
version INTEGER NOT NULL DEFAULT 1
```

INDEX `(status,created_at,id)`。

### style_analysis_runs

006で作る。後続semantic/analyticsの共通親になるため。

```text
id
document_id INTEGER NOT NULL FK ON DELETE CASCADE
analyzer_id TEXT NOT NULL
analyzer_version INTEGER NOT NULL
text_revision_id INTEGER NOT NULL FK ON DELETE CASCADE
structure_revision_id INTEGER FK ON DELETE CASCADE
status TEXT NOT NULL
fingerprint TEXT NOT NULL
config_json TEXT NOT NULL
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
UNIQUE `(analyzer_id,fingerprint,status)` はfailed/queuedを含むと不適切なので作らない。repositoryがsucceeded fingerprintをqueryする。

## 6. 007 Semantics tables

### style_entities

```text
id
document_id INTEGER NOT NULL FK ON DELETE CASCADE
entity_type TEXT NOT NULL
canonical_name TEXT NOT NULL
description TEXT
status TEXT NOT NULL
created_by_run_id INTEGER FK style_analysis_runs ON DELETE SET NULL
created_at
```

INDEX `(document_id,entity_type,canonical_name)`。

### style_entity_aliases

```text
id
entity_id INTEGER NOT NULL FK ON DELETE CASCADE
alias TEXT NOT NULL
alias_kind TEXT NOT NULL
status TEXT NOT NULL
source_mention_id INTEGER
created_at
```

UNIQUE `(entity_id,alias,alias_kind)`。

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
confidence REAL NOT NULL CHECK 0<=confidence<=1
analysis_run_id INTEGER NOT NULL FK ON DELETE CASCADE
```

INDEX `(structure_revision_id,start_cp)`。

### style_entity_links

```text
id
style_entity_id INTEGER NOT NULL FK ON DELETE CASCADE
project_character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE
status TEXT NOT NULL
confidence REAL
created_at
```

UNIQUE style_entity_id。

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

### style_terms

```text
id
document_id INTEGER NOT NULL FK ON DELETE CASCADE
canonical_label TEXT NOT NULL
term_type TEXT NOT NULL
novelty TEXT NOT NULL
exact_match_safe INTEGER NOT NULL
status TEXT NOT NULL
created_by_run_id INTEGER FK ON DELETE SET NULL
created_at
```

INDEX `(document_id,canonical_label)`。

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
occurrence_index INTEGER NOT NULL
analysis_run_id INTEGER NOT NULL FK ON DELETE CASCADE
```

### style_term_entity_links

term/entity pair、confidence、status。

### style_annotations

汎用推論値。

```text
id
annotation_type TEXT NOT NULL
subject_type TEXT NOT NULL
subject_id INTEGER NOT NULL
value_json TEXT NOT NULL
confidence REAL
analysis_run_id INTEGER NOT NULL FK ON DELETE CASCADE
start_cp INTEGER
end_cp INTEGER
created_at
```

INDEX `(subject_type,subject_id,annotation_type)`。
subjectのFKはgenericなため張らず、repositoryでtype registry validationする。

### style_review_items

10定義のfields + version。

### style_inference_reviews

10定義。UNIQUE `(subject_type,subject_id,field_path,analysis_run_id)`。

### style_manual_overrides

10定義。`superseded_by_id` self FK。active lookup index `(subject_type,subject_id,field_path,superseded_by_id)`。

## 7. 008 Analytics tables

### style_measurements

07定義。INDEX `(target_type,target_id,metric_name,metric_version)`。

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

08定義。fingerprint index。

### style_profiles

08定義。UNIQUE `(name,version)` はname変更履歴を妨げるため作らず、parent chainでversion管理。`version>=1`。

### style_rules

08定義。scope_selector_json JSON check、weight 0〜5。

### style_lint_runs

```text
id
document_id
text_revision_id
structure_revision_id
profile_id
profile_version
analysis_run_id
status
warning_json
created_at
finished_at
```

### style_findings

11定義。INDEX `(lint_run_id,severity,sort_score)`。

### style_finding_reviews

11定義。

## 8. Deletion/Purge

Reference Work削除APIはsoft-deleteではなく明示purgeを提供する。著作物本文をローカル保存し続けない要求へ対応するためである。

Purge順はFK cascadeに任せる。`style_source_snapshots` もsource削除で消える。

ただしCorpus membershipがあるReference Workをpurgeする場合、membershipもCASCADEし、既存Aggregate/Profileは履歴snapshotとして残してよいが、raw source IDを参照するFKは `ON DELETE SET NULL` にする。

Profile JSON/Ruleは本文を含まないため保持可能。

Project documentはauthoring episode削除にCASCADEする。

## 9. DB容量

raw payloadとraw/canonical textをSQLite TEXTとしてv1保存する。content-addressed filesystem storageは実装しない。

理由:

- ローカル単一user
- transaction/backupの単純性
- 初期Corpus規模では十分

DBサイズ問題が実測で出るまで別storageへ抽象化しない。

## 10. Repository分割

1巨大Repositoryを作らない。

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

全Repositoryは既存同様 `sqlite3.Connection` を注入して使用する。独自ORMを追加しない。

## 11. Migration test

必須:

- empty DBへ001〜008適用
- 005適用済DBへ006〜008適用
- migration checksum invariant
- foreign_keys ON
- reference work purge cascade
- project episode delete cascade
- immutable snapshot/text revision UPDATE拒否
- JSON CHECK
- enum CHECK
- duplicate order/index拒否
- span CHECK

## 12. Codex実装時の禁止事項

- 001〜005を変更しない。
- SQLAlchemy等ORMを追加しない。
- style tableへproject_idを重複追加しない。
- raw payloadをGit repository配下の通常fileとして保存しない。
- foreign keyを無効化しない。
- cascade purgeできないappend-only DELETE triggerを追加しない。
- migrationを1本の巨大006へ勝手に統合しない。
