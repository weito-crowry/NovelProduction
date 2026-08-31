# 12 Storage Schema 詳細設計

## 1. 目的

Style AnalysisのSQLite永続化schema、migration分割、主要制約・indexを確定する。既存NovelProduction authoring schemaを変更せず、`style_` prefixのbounded contextとして追加する。

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

Style Analysisは既存Project Registryが解決したproject-local `story.db` へ保存する。各 `style_*` tableに `project_id` は重複保持しない。

Reference Corpusもv1ではproject-local。

## 4. 共通ルール

- PK: `INTEGER PRIMARY KEY`
- timestamp: `TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`
- boolean: `INTEGER NOT NULL CHECK (... IN (0,1))`
- enum: TEXT + CHECK
- JSON: TEXT + `CHECK (json_valid(column))`
- SHA-256: lowercase hex 64文字
- 通常text span: `[start_cp,end_cp)`, `end_cp > start_cp`
- mapping segmentは片側長0を許可、両側長0は禁止
- order indexは1-based
- immutable rowだけUPDATE禁止trigger
- Reference Work purgeのためDELETEは禁止しない

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

File importのlocatorは元filename。`rights_basis` 等の同意管理fieldは持たない。

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

external ID非NULLなら partial unique index `(source_type,external_work_id)`。

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

HTML/TXT/EPUBの元bytesを同じschemaで保持する。

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

`import_state = complete | deleted_source`。

ReferenceWorkはcurrent catalog projectionなのでtitle等のmetadata updateを許可する。本文履歴はSnapshot/TextRevision側。

### style_reference_episodes

```text
id
reference_work_id INTEGER NOT NULL REFERENCES style_reference_works(id) ON DELETE CASCADE
external_episode_id TEXT NOT NULL
title TEXT NOT NULL
order_index INTEGER NOT NULL CHECK(order_index >= 1)
source_url TEXT
latest_snapshot_id INTEGER REFERENCES style_source_snapshots(id) ON DELETE SET NULL
created_at
updated_at
```

- UNIQUE `(reference_work_id,external_episode_id)`
- UNIQUE `(reference_work_id,order_index)`

refresh時はtitle/order/latest pointerを更新可能。

### style_documents

```text
id
kind TEXT NOT NULL
reference_episode_id INTEGER REFERENCES style_reference_episodes(id) ON DELETE CASCADE
project_work_id INTEGER
project_episode_id INTEGER
created_at
```

kind: `reference_episode | project_episode_draft`。

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

- ReferenceEpisode documentは1件
- Project documentは `(project_work_id,project_episode_id)` で1件

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

Serviceでdocument kindとsource_snapshot/project_draftの整合を検証する。

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
- operation: `identity,replace,delete,collapse`
- raw/canonical両方0長は禁止

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

source kind: `automatic | semantic | manual`。

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

- block type: `dialogue,narration,monologue,heading,separator,unknown`
- `order_index` はStructureRevision全体でglobal 1..N
- UNIQUE `(structure_revision_id,order_index)`
- Scene外separatorは `scene_id=NULL`
- INDEX `(structure_revision_id,start_cp)`

Serviceでscene_idが同じStructureRevision所属であることを検証する。

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
document_id INTEGER NOT NULL REFERENCES style_documents(id) ON DELETE CASCADE
analyzer_id TEXT NOT NULL
analyzer_version INTEGER NOT NULL
text_revision_id INTEGER NOT NULL REFERENCES style_text_revisions(id) ON DELETE CASCADE
structure_revision_id INTEGER NOT NULL REFERENCES style_structure_revisions(id) ON DELETE CASCADE
status TEXT NOT NULL
fingerprint TEXT NOT NULL CHECK(length(fingerprint)=64)
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
warning_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(warning_json))
created_at
```

INDEX `(document_id,analyzer_id,created_at,id)`。

ServiceでTextRevision/StructureRevision/Documentの所属整合を検証する。

### style_structure_analysis_sources

Semantic Structureの生成元Boundary AnalysisRunを記録する。

```text
structure_revision_id INTEGER PRIMARY KEY REFERENCES style_structure_revisions(id) ON DELETE CASCADE
analysis_run_id INTEGER NOT NULL UNIQUE REFERENCES style_analysis_runs(id) ON DELETE RESTRICT
```

制約:

- 対象StructureRevisionは `source_kind=semantic`
- Runは `analyzer_id=scene-boundary-detector`
- Runの `structure_revision_id` はsemantic revisionのparent automatic StructureRevision

DB CHECKだけでは表跨ぎ条件を表現できないためStructureServiceで検証する。

## 6. 007 Semantics

### style_entities

Stable identity。

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

- exactly one scope: reference_work_id / document_id
- origin: `inferred | manual`
- INDEX `(reference_work_id,entity_type,canonical_name)`
- INDEX `(document_id,entity_type,canonical_name)`

推論による確認/却下/名称変更はidentity rowをupdateせず10のoverlayを使う。

### style_mentions

```text
id
entity_id INTEGER REFERENCES style_entities(id) ON DELETE SET NULL
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

INDEX `(structure_revision_id,start_cp)`。

ServiceでScene/Block/Structureの所属一致を検証する。

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

- origin: `inferred | manual`
- UNIQUE `(entity_id,alias,alias_kind,origin,analysis_run_id)` をそのまま使うとNULL重複の意味が不安定になるため、重複防止はRepositoryで行う
- 自動aliasはanalysis_run_id必須、manualはNULL可

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

v1はmanual linkだけでもよい。Serviceでdocument-scoped Entityだけ許可する。

### style_relations

```text
id
source_entity_id INTEGER NOT NULL REFERENCES style_entities(id) ON DELETE CASCADE
target_entity_id INTEGER NOT NULL REFERENCES style_entities(id) ON DELETE CASCADE
relation_type TEXT NOT NULL
scene_id INTEGER REFERENCES style_scenes(id) ON DELETE CASCADE
confidence REAL
origin TEXT NOT NULL
analysis_run_id INTEGER REFERENCES style_analysis_runs(id) ON DELETE CASCADE
created_at
```

Serviceでsource/target scope一致を検証する。

### style_terms

Stable identity。`novelty` と `exact_match_safe` は持たない。

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

- exactly one scope
- origin: `inferred | manual`
- INDEX `(reference_work_id,canonical_label)`
- INDEX `(document_id,canonical_label)`

### style_term_aliases

```text
id
term_id INTEGER NOT NULL REFERENCES style_terms(id) ON DELETE CASCADE
alias TEXT NOT NULL
origin TEXT NOT NULL
analysis_run_id INTEGER REFERENCES style_analysis_runs(id) ON DELETE SET NULL
created_at
```

自動aliasはanalysis_run_id必須。ManualはNULL可。

### style_term_mentions

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

`occurrence_index` は持たない。current effective revision/runをsortして初出を算出する。

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

Serviceでscope一致。v1 manual link可。

### style_annotations

汎用Run付き推論値。

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

用途例:

```text
speaker
scene.function / scene.tone / scene.pace / ...
block.semantic_primary
scene_boundary_candidate
term.novelty
term.exact_match_safe
term_explanation
```

Generic subject FKは張らずRegistry validationする。

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

priority: `low,normal,high`。
status: `open,resolved,ignored,superseded`。

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

review status: `confirmed | rejected`。

1 Run/subject/fieldにactiveな判定を1件とし、変更時は新rowを追加してRepositoryが最新を採用する。過剰なhistory pointer tableは追加しない。

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

operation: `set | clear`。

- value_jsonはset時必須、clear時NULL
- active lookup INDEX `(subject_type,subject_id,field_path,superseded_by_id)`
- Direct OverrideはReviewItem FKを要求しない

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

CHECKでvalue_real/value_intの同時設定を禁止する。

INDEX `(target_type,target_id,metric_name,metric_version)`。
INDEX `(analysis_run_id,metric_name)`。

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

membership mode: `include | exclude`。

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

INDEX `(scope_type,scope_id,metric_name,metric_version)`。
INDEX `(fingerprint)`。

Aggregateは履歴snapshot値でReferenceWorkへのFKを持たない。

### style_profiles

Stable identity。

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

status: `draft | active | archived`。

`active_version_id` のFKは、参照先tableを後続で作るためmigration内でtable再構築を避け、SQLiteでは通常のFKを後付けできない。したがってv1では **active_version_idを論理FKとしてServiceで検証**し、INDEXだけ作る。`active` status時に非NULLかつ同Profile所属VersionであることをProfileServiceがtransaction内で保証する。

### style_profile_versions

```text
id
profile_id INTEGER NOT NULL REFERENCES style_profiles(id) ON DELETE CASCADE
version_no INTEGER NOT NULL CHECK(version_no >= 1)
parent_version_id INTEGER REFERENCES style_profile_versions(id) ON DELETE SET NULL
created_at
```

- UNIQUE `(profile_id,version_no)`
- UPDATE禁止
- parent_version_idは同Profile所属をServiceで検証

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

ProfileVersionとRuleはimmutable。

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

ServiceでProfileVersion所属、Text/Structure/Metric Run所属を検証する。

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

status: `acknowledged | ignored`。

## 8. Reference Work Purge

`DELETE style_reference_works` だけでは `style_sources` / `style_source_snapshots` は消えない。Reference Work purgeはRepository/Serviceの明示transactionとして実装する。

手順:

1. `reference_work_id` から `source_id` を取得
2. ReferenceWorkをDELETE
3. Work配下Episode/Document/Entity/Term/Corpus membershipはFK cascade
4. 同 `source_id` を参照する別ReferenceWorkが0件なら `style_sources` をDELETE
5. Source DELETEによりSourceSnapshotをcascade
6. commit

これによりrefreshで消えたEpisodeの古いSourceSnapshotはWork全体Purgeまでは履歴として残り、Work Pruge時にまとめて削除される。

Sourceを複数ReferenceWorkが共有する将来実装でも、別Workが参照中なら消さない。

過去Aggregate/Profile/Ruleは本文そのものを含まないため残してよい。ただしCorpus membership消失後の新しいAggregateではPurge済Workを含めない。

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
- `PRAGMA foreign_key_check` empty
- `PRAGMA integrity_check = ok`
- JSON/enum/CHECK
- Reference Work purge transactionでSource/Snapshotまで削除
- refresh削除EpisodeではSnapshot保持
- Project Episode cascade
- immutable Snapshot/TextRevision/ProfileVersion UPDATE拒否
- Block global order unique
- Entity/Term exactly-one scope
- Term identityにnovelty/exact_match_safeがないこと
- Semantic Structure source Run link
- Profile Version uniqueness
- active Profileのactive_version所属検証
- mapping片側zero許容/両側zero拒否

DB integrityはmigration/integration suiteで確認し、各個別case末尾へ重複追加しない。

## 12. Codex実装時の禁止事項

- 001〜005を変更しない。
- ORMを追加しない。
- style tableへproject_idを追加しない。
- EPUB raw payloadをTEXTへ無理に変換しない。
- Entity/TermをReference Episode単位へ分断しない。
- Entity/Term identity rowを再解析で推論上書きしない。
- Term identityへnovelty/exact_match_safeを追加しない。
- Block orderをScene内indexとして実装しない。
- occurrence_indexをTermMentionへ追加しない。
- Profile identityとVersionを同じrowへ戻さない。
- active Versionを暗黙latestで更新しない。
- `DELETE reference_work` だけでSource/Snapshotも消えると仮定しない。
- purge不能なDELETE禁止triggerを追加しない。
