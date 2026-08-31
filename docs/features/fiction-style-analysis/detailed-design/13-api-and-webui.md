# 13 API and WebUI 詳細設計

## 1. 目的

Style Analysisを既存FastAPI/React WebUIへ統合するAPI契約、Revision選択、Current Structure、Job表示、Manual Entity/Term操作、Query Invalidationを確定する。

上位仕様は `../basic-design.md`。

## 2. 境界

- v1でMCP Tool追加なし、既存Tool Count 59維持。
- Style推論から既存Character/World/Canonを自動更新しない。
- WebSocket/SSE追加なし。JobはPolling。
- rights_basis/毎回の確認Dialogなし。

## 3. API実装先

```text
API/src/novel_api/
  style_analysis/
    ingestion_service.py
    source_fetcher.py
    runtime.py
    job_worker.py
    model_client.py
    adapters/...
  routes/
    style_sources.py
    style_analysis.py
    style_corpora.py
    style_profiles.py
    style_review.py
    style_lint.py
  schemas/style_analysis.py
```

既存API Client/Query Cacheを再利用する。

## 4. URL Prefix / Revision方針

```text
/projects/{project_id}/style-analysis
```

明示必須:

- Text: text_revision_id
- Structure閲覧/編集: structure_revision_id
- Lint: text_revision_id + structure_revision_id + profile_version_no
- Profile Export: version_no

Semantics/MetricはStructure IDを明示しServerが09 Current Run Resolverを使える。ResponseはSelected Run IDを返す。

## 5. Source / Reference Work API

```text
POST   /imports
POST   /imports/file
GET    /imports/{import_id}
GET    /reference-works
GET    /reference-works/{work_id}
GET    /reference-works/{work_id}/episodes
GET    /reference-episodes/{episode_id}
POST   /reference-works/{work_id}/refresh
POST   /reference-works/{work_id}/analyze
DELETE /reference-works/{work_id}
```

Import Response `202 + import_id + job_id`。Refresh/Analyze Response `202 + job_id`。

Work/Episode Responseには `current_text_revision_id` とDocumentの `current_structure_revision_id` を含める。

Work Analyze:

```json
{"preset":"deterministic"}
```

または `full`。

Purgeは12 Service Transaction、204。

## 6. Document / Structure API

```text
POST /project-episodes/{episode_id}/capture
GET  /documents
GET  /documents/{document_id}
GET  /documents/{document_id}/revisions
GET  /documents/{document_id}/text
GET  /documents/{document_id}/structures
GET  /documents/{document_id}/structure
POST /documents/{document_id}/structures/{structure_revision_id}/select-current
GET  /documents/{document_id}/structure/boundary-proposals
POST /documents/{document_id}/scenes/{scene_id}/split
POST /documents/{document_id}/scenes/merge
```

### Document Detail

返却:

```text
document_id
kind
current_text_revision_id nullable
current_structure_revision_id nullable
```

Reference DocumentのCurrent TextはReferenceEpisode Pointer。Project Documentは最新CaptureされたTextRevisionをDocument Serviceが明示管理する。Capture成功時に新TextRevisionをCurrent Textとし、Current StructureをNULLへClearする。

### Text

```text
GET /documents/{id}/text?text_revision_id=10
```

省略422。

### Structures List

各Revision:

```text
structure_revision_id
text_revision_id
source_kind
parent_structure_revision_id
is_current
created_at
```

### Structure Detail

```text
GET /documents/{id}/structure?structure_revision_id=9
```

返却:

```text
text_revision_id
structure_revision_id
is_current
source_kind
parent_structure_revision_id
semantic_source_run_id nullable
scenes/blocks/sentences
```

### Select Current

```text
POST /documents/{id}/structures/{structure_revision_id}/select-current
```

Body不要。

Validation:

- StructureがDocument所属。
- Document Current TextRevision所属。
- 成功204またはCurrent Document Summary 200。実装では既存API慣例に合わせ、v1は200で更新後Document Summaryを返す。

この操作はStructureを変更せずPointerだけ更新する。Corpus/Aggregate/Lint Current入力が変わるため関連QueryをInvalidateする。

Historical Structure Selector変更だけではこのAPIを呼ばない。

### Split/Merge

`expected_structure_revision_id` 必須。対象はCurrent Structureに限定する。成功時に新Manual RevisionがCurrentになる。

## 7. Analysis / Job API

```text
POST /documents/{document_id}/analyze
GET  /jobs/{job_id}
POST /jobs/{job_id}/cancel
POST /jobs/{job_id}/retry
GET  /analysis-runs
GET  /analysis-runs/{run_id}
GET  /analysis-runs/{run_id}/outputs
GET  /analysis-runs/{run_id}/measurements
GET  /documents/{document_id}/semantics
GET  /documents/{document_id}/metrics
GET  /documents/{document_id}/scenes/{scene_id}/metrics
```

Analyze:

```json
{
  "text_revision_id":10,
  "structure_revision_id":null,
  "preset":"full"
}
```

- Structure omitted: 09のFinal StructureをCurrentへ設定可能。
- Structure explicit: Current Pointer変更なし。
- Full Provider未設定: 409 before Job creation。

Job Response:

```text
job_id/job_type/status
progress_current/progress_total
result
warnings
error_code/error_message
```

終了Status `succeeded|partial|failed|cancelled`。Retryは新Job Row。

## 8. Entity API

Manual Entity/Manual AliasをStyle Analysis内で作成する。

```text
POST /entities
POST /entities/{entity_id}/aliases
```

### POST /entities

```json
{
  "reference_work_id":12,
  "document_id":null,
  "entity_type":"person",
  "canonical_name":"田中"
}
```

Scope exactly one。Response 201 Entity Effective Summary。

Project Document用は `document_id` を指定する。

これはStyle Entity作成であり、Authoring `characters` を作らない。

### Alias

```json
{"alias":"田中さん","alias_kind":"title"}
```

Response 201。完全同一Manual Alias再送はIdempotentに200/既存Resource返却でもよいが、API契約を単純化するためv1は200でEntity Alias Summaryを返す。

Manual Entity/Alias作成後、関連Documentに `analysis_stale=true` を表示できる。自動Work全再解析はしない。

## 9. Term API

```text
POST /terms
POST /terms/{term_id}/aliases
```

### POST /terms

```json
{
  "reference_work_id":12,
  "document_id":null,
  "canonical_label":"統合国家知性機構",
  "term_type":"institution"
}
```

Scope exactly one。Response 201 Style Term Summary。

### Alias

```json
{"alias":"知性機構"}
```

同一Manual Alias再送はIdempotent。

Authoring World/Canonへ自動登録しない。

## 10. Semantics / Direct Correction

```text
GET  /documents/{document_id}/semantics?structure_revision_id=9
POST /overrides
POST /inference-reviews
```

Semantics Response:

- Entity/Term/Speaker/Scene/POV Effective/Raw
- Selected Run IDs
- `analysis_stale` / stale reasons where applicable

Override:

```json
{
  "subject_type":"block",
  "subject_id":55,
  "field_path":"block.speaker_entity_id",
  "operation":"set",
  "value":3,
  "structure_revision_id":9,
  "base_analysis_run_id":31,
  "note":null
}
```

Operation `set|clear|revert`。Note optional。Generic二重CASなし。

## 11. Corpus API

```text
GET/POST /corpora
GET/PATCH/DELETE /corpora/{corpus_id}
POST   /corpora/{corpus_id}/works
DELETE /corpora/{corpus_id}/works/{work_id}
PUT    /corpora/{corpus_id}/episodes/{episode_id}
DELETE /corpora/{corpus_id}/episodes/{episode_id}
POST   /corpora/{corpus_id}/recompute
GET    /corpora/{corpus_id}/metrics
GET    /corpora/compare
```

Work Membership追加Request:

```json
{"reference_work_id":12,"include_all_episodes":true}
```

Episode PUT:

```json
{"membership_mode":"exclude"}
```

08 Membership ResolverをCOREで共用する。

Corpus Metrics/Compare Responseは:

```text
source_measurement_count
sample_count
work_count
skipped_target_count
```

を区別して返す。

## 12. Profile API

```text
GET/POST/PATCH Profile系
GET/POST Version系
POST /profiles/{id}/activate
POST /profiles/{id}/archive
GET /profiles/{id}/versions/{version_no}/export
POST /profiles/import
```

ActivateはVersion No明示。New VersionだけでActive Version変更なし。

## 13. Review / Lint API

Review Item:

```text
GET /review-items
POST confirm/reject/ignore
```

ReviewItem Writeだけ `expected_version`。

Lint:

```text
POST /documents/{id}/lint
GET /lint-runs
GET /lint-runs/{id}/findings
POST /findings/{id}/review
```

Lint RequestはText/Structure/Profile Version明示。

## 14. WebUI Routes

```text
/projects/:projectId/style-analysis
.../sources
.../reference-works/:workId
.../documents/:documentId
.../corpora
.../corpora/compare
.../profiles
.../profiles/:profileId
.../review
.../lint
```

Project Sidebarに `文体分析`。

## 15. Reference Work UI

- Metadata/Episode List
- Current Text/Current Structure表示
- Work全体Analyze Button/Preset
- Job Progress
- Partial時Succeeded/Partial/Failed Episode表示
- Refresh/Purge

## 16. Document Analysis UI

Header:

```text
TextRevision selector
StructureRevision selector
Current Structure badge
Analysis status
```

Structure Selectorは閲覧対象を変えるだけ。

CurrentでないRevisionを表示時:

```text
「このStructureをCurrentに設定」
```

Buttonを表示する。押した時だけSelect Current API。

Tabs:

- Text
- Structure
- Semantics
- Metrics

Semantics:

- Manual Entity/Term作成
- Manual Alias追加
- Entity/Term Enable/Disable/Name/Type修正
- Mention/Speaker修正
- Alias Confirm/Reject
- Selected Run ID

## 17. Corpus / Profile / Lint UI

Corpus Membership UIは08のDefault/Override規則をそのまま表示する。Include All=false時は明示Include Episodeを選ぶ。

Corpus MetricsはMeasurement Count/Sample Count/Work Count/Skippedを表示する。

Profile Editorは `保存` と `保存して有効化` を分離。

LintはRevision/Profile Version/Coverage/Stale/Findingを表示。Coverage 0は通常結果。

## 18. Job Polling / Query Invalidation

`queued|running` の間2秒Polling。`partial` は終了状態。

Invalidate:

- Import/Refresh/Purge -> Reference系
- Work/Document Analyze -> Document/Structure/Run/Semantics/Metric
- Select Current -> Document/Structures/Corpus Metrics/Lint Staleness
- Manual Entity/Term/Alias -> Semantics/Analysis Stale State
- Override/Review -> Semantics/Metric/Jobs
- Corpus Membership -> Corpus Detail/Metrics
- Profile Version/Activate -> Profile系
- Lint -> Lint系

## 19. Testing

API:

- Explicit Revision
- Select Current: valid/current-text mismatch
- Historical SelectorでPointer不変
- Omitted AnalyzeでPointer更新 / Explicit Analyzeで不変
- Manual Entity/Term Create Scope Validation
- Same-name Manual Identity許容
- Manual Alias Idempotent
- Authoring Table非更新
- Job Progress/Partial/Retry
- Corpus Membership Mode Validation
- Corpus Count Fields
- Profile Activation
- Direct Override/Revert

WebUI:

- Current Structure Badge/Select Button
- SelectorだけではCurrent変更なし
- Manual Entity/Term/Alias操作
- Work Analysis Progress/Partial
- Corpus Include/Exclude
- Count表示
- Profile Save vs Activate
- Lint Coverage

## 20. Codex禁止事項

- MCP変更
- WebSocket/SSE追加
- Authoring Character/World/CanonへStyle Identity自動Write
- Structure Selector変更だけでCurrent Pointer変更
- Explicit Structure AnalyzeでCurrent Pointer変更
- Manual Entity/Term作成をReviewQueue必須にする
- Corpus Membership規則をUI独自実装
- Count Fieldsを1つにまとめる
- Low-confidence修正をReviewQueue必須化
