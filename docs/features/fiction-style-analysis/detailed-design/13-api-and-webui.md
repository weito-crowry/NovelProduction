# 13 API and WebUI 詳細設計

## 1. 目的

Style AnalysisのCORE機能を既存FastAPI/React WebUIへ統合するAPI契約、画面構成、job表示、query invalidationを確定する。Authoring導線を壊さず独立featureとして追加する。

上位仕様は `../basic-design.md`。

## 2. 境界

v1ではMCPへStyle Analysis toolを追加しない。`MCP/` はscope外、既存tool count 59を維持する。

Style Analysis推論から既存Character/World/Canonを自動更新しない。

## 3. API実装先

```text
API/src/novel_api/
  style_analysis/
    __init__.py
    ingestion_service.py
    source_fetcher.py
    runtime.py
    model_client.py
    adapters/...

  routes/
    style_sources.py
    style_analysis.py
    style_corpora.py
    style_profiles.py
    style_review.py
    style_lint.py

  schemas/
    style_analysis.py
```

既存 `service_container.py` へStyle Analysis servicesを追加する。既存service constructorを不要に変更しない。

## 4. URL prefix

```text
/projects/{project_id}/style-analysis
```

Project解決/error contractは既存project-scoped routeを再利用する。

## 5. Revision指定方針

本文・Structure・解析結果を返すendpointでは、どのRevision/Runを表示しているかをresponseへ必ず含める。

### 明示必須

- Text本文取得: `text_revision_id`
- Structure取得/編集: `structure_revision_id`
- Lint: `text_revision_id + structure_revision_id + profile_version_no`
- Profile export: `version_no`

### Effective Run選択を許可するもの

Semantics/Metricの通常UI表示は、`structure_revision_id` を明示した上で09のEffective AnalysisRun選択規則をserver側で使ってよい。Responseには採用した `analysis_run_id` を必ず返す。

過去Runを厳密に表示したい場合はRun endpointを使う。

この方針により「latest draft/latest structure」の暗黙参照は避けつつ、AnalyzerごとのRun IDを通常画面で毎回入力させない。

## 6. Source / Reference API

```text
POST   /imports
POST   /imports/file
GET    /imports/{import_id}
GET    /reference-works
GET    /reference-works/{work_id}
POST   /reference-works/{work_id}/refresh
DELETE /reference-works/{work_id}
GET    /reference-works/{work_id}/episodes
GET    /reference-episodes/{episode_id}
```

Network import:

```json
{
  "source_type": "narou",
  "locator": "https://ncode.syosetu.com/.../"
}
```

`rights_basis` や同意flagはAPI contractへ入れない。

File importはmultipart:

```text
source_type = text | html_file | epub
file
```

Response `202`:

```json
{"import_id": 12, "job_id": 44, "status": "queued"}
```

### DELETE Reference Work

明示Purge。成功204。

実装は12のPurge transactionを呼ぶ。ReferenceWorkだけでなく、そのWork専用SourceであればSource/Snapshotまで削除する。

UI confirmは通常の削除確認1回だけ。権利確認や追加二重確認はしない。

## 7. Document / Text / Structure API

```text
POST /project-episodes/{episode_id}/capture
GET  /documents
GET  /documents/{document_id}
GET  /documents/{document_id}/revisions
GET  /documents/{document_id}/text
GET  /documents/{document_id}/structures
GET  /documents/{document_id}/structure
GET  /documents/{document_id}/structure/boundary-proposals
POST /documents/{document_id}/scenes/{scene_id}/split
POST /documents/{document_id}/scenes/merge
```

### capture

```json
{"draft_id": 123}
```

latestへ暗黙解決しない。

Response:

```json
{
  "document_id": 5,
  "text_revision_id": 10,
  "canonical_sha256": "..."
}
```

Structureはcapture時に必須生成しない。

### GET text

```text
GET /documents/{document_id}/text?text_revision_id=10
```

Responseに `text_revision_id`, `raw_sha256`, `canonical_sha256`, `canonical_text`。

`text_revision_id` 省略は422。

### GET structure

```text
GET /documents/{document_id}/structure?structure_revision_id=9
```

Responseに:

```text
text_revision_id
structure_revision_id
source_kind
parent_structure_revision_id
semantic_source_run_id nullable
scenes/blocks/sentences
```

`structure_revision_id` 省略は422。

### Boundary proposals

```text
GET /documents/{document_id}/structure/boundary-proposals?base_structure_revision_id=7
```

09のEffective AnalysisRun選択で対象 `scene-boundary-detector` Runを選び、responseに `boundary_analysis_run_id` を返す。

厳密な過去Runを見たい場合はRun output endpointを使う。

### split

```json
{
  "after_block_id": 55,
  "expected_structure_revision_id": 9,
  "note": "時間の切替"
}
```

`note` optional。

### merge

```json
{
  "left_scene_id": 4,
  "right_scene_id": 5,
  "expected_structure_revision_id": 9,
  "note": "同一Scene"
}
```

## 8. Analysis / Job API

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

Analyze request:

```json
{
  "text_revision_id": 10,
  "structure_revision_id": null,
  "preset": "full"
}
```

- `text_revision_id` required
- `structure_revision_id` optional
- omitted: automatic Structure build/reuse、fullならSemantic Boundaryをmaterialize
- provided: exact Structureを使用。Scene Boundary Detectorを再実行しない

`preset=full` でprovider未設定ならjob作成前に `409 ANALYZER_PROVIDER_UNAVAILABLE`。

### GET semantics

```text
GET /documents/{document_id}/semantics?structure_revision_id=9
```

09 Effective AnalysisRun選択に従ってEntity/Speaker/Term/Scene Semanticsのeffective/raw概要を返す。ResponseはAnalyzerごとの採用Run ID一覧を含む。

```json
{
  "structure_revision_id": 9,
  "selected_runs": {
    "speaker-attribution": 31,
    "scene-semantic-classifier": 33
  },
  "...": "..."
}
```

### GET metrics

```text
GET /documents/{document_id}/metrics?structure_revision_id=9&group=basic
GET /documents/{document_id}/metrics?structure_revision_id=9&group=semantic
```

Responseに採用 `analysis_run_id` を含める。

Scene metricsも同じgroup/Structure指定。

過去Runを完全固定したい場合は `/analysis-runs/{run_id}/measurements` を使う。

## 9. Corpus API

```text
GET    /corpora
POST   /corpora
GET    /corpora/{corpus_id}
PATCH  /corpora/{corpus_id}
DELETE /corpora/{corpus_id}
POST   /corpora/{corpus_id}/works
DELETE /corpora/{corpus_id}/works/{work_id}
PUT    /corpora/{corpus_id}/episodes/{episode_id}
DELETE /corpora/{corpus_id}/episodes/{episode_id}
POST   /corpora/{corpus_id}/recompute
GET    /corpora/{corpus_id}/metrics
GET    /corpora/compare
```

Compareは2〜5 Corpus、Metric最大20。

## 10. Profile API

Profile identityとVersionを分離する。

```text
GET    /profiles
POST   /profiles/from-corpus
GET    /profiles/{profile_id}
PATCH  /profiles/{profile_id}
GET    /profiles/{profile_id}/versions
GET    /profiles/{profile_id}/versions/{version_no}
POST   /profiles/{profile_id}/versions
POST   /profiles/{profile_id}/activate
POST   /profiles/{profile_id}/archive
GET    /profiles/{profile_id}/versions/{version_no}/export
POST   /profiles/import
```

- PATCH: name/descriptionだけ
- Version作成: Rules snapshot全送信
- ProfileVersion/Ruleはupdateしない

### Activate

Request:

```json
{"version_no": 3}
```

08に従い、同Profile所属Versionを検証して:

```text
status = active
active_version_id = selected version
```

を1 transactionで更新する。

新Version作成だけではactive versionを切替えない。

Profile detail/list response:

```text
status
active_version_no nullable
latest_version_no
```

Lint/Exportはactive/latestへ暗黙読み替えしない。

### Archive

Profile identity statusを `archived` にする。active_version_idは履歴として保持可。

## 11. Review / Direct Override API

ReviewQueue:

```text
GET  /review-items
GET  /review-items/{item_id}
POST /review-items/{item_id}/confirm
POST /review-items/{item_id}/reject
POST /review-items/{item_id}/ignore
```

ReviewItem writeは `expected_version`。

Direct OverrideはReviewItemを経由しないendpointを用意する。

```text
POST /overrides
```

Request例:

```json
{
  "subject_type": "block",
  "subject_id": 55,
  "field_path": "block.speaker_entity_id",
  "operation": "set",
  "value": 3,
  "structure_revision_id": 9,
  "base_analysis_run_id": 31,
  "note": null
}
```

- `note` optional
- Structure依存subjectだけ `structure_revision_id` required
- 汎用二重CAS tokenは要求しない

Inference confirm/rejectをReviewItemなしで行う必要がある場合:

```text
POST /inference-reviews
```

に `subject/field_path/analysis_run_id/status/note` を送る。

低confidence結果はReviewItem化せずDocument Semanticsから直接確認・Overrideできる。

## 12. Lint API

```text
POST /documents/{document_id}/lint
GET  /lint-runs
GET  /lint-runs/{lint_run_id}
GET  /lint-runs/{lint_run_id}/findings
POST /findings/{finding_id}/review
```

Request:

```json
{
  "text_revision_id": 10,
  "structure_revision_id": 9,
  "profile_id": 3,
  "profile_version_no": 2
}
```

Response `202` + job ID。

Profileがactiveでも `profile_version_no` 省略はしない。

LintRun detail:

```text
enabled_rule_count
applicable_rule_count
missing_rule_count
coverage_ratio
stale
```

## 13. Pagination

List endpointは既存pattern:

```text
limit default 50, max 200
offset default 0
```

Cursor paginationはv1で導入しない。

## 14. Error contract

既存API envelopeを再利用。

```text
400 invalid source/operation
404 not found
409 version conflict/provider unavailable/stale structure
413 upload/source too large
422 schema/revision validation
500 invariant/internal
502 external source/model upstream failure
```

Network import/model job中の失敗はJob errorとして返す。

## 15. WebUI実装先

```text
WEBUI/frontend/src/features/styleAnalysis/
  api.ts
  types.ts
  hooks.ts
  utils.ts
  StyleAnalysisHome.tsx
  SourcesPage.tsx
  ReferenceWorkPage.tsx
  DocumentAnalysisPage.tsx
  CorpusPage.tsx
  CorpusComparePage.tsx
  ProfilesPage.tsx
  ProfileEditorPage.tsx
  ReviewPage.tsx
  LintPage.tsx
  components/
```

既存 `src/api/client.ts` とquery cacheを使う。

## 16. Route

```text
/projects/:projectId/style-analysis
/projects/:projectId/style-analysis/sources
/projects/:projectId/style-analysis/reference-works/:workId
/projects/:projectId/style-analysis/documents/:documentId
/projects/:projectId/style-analysis/corpora
/projects/:projectId/style-analysis/corpora/compare
/projects/:projectId/style-analysis/profiles
/projects/:projectId/style-analysis/profiles/:profileId
/projects/:projectId/style-analysis/review
/projects/:projectId/style-analysis/lint
```

Project sidebarに `文体分析` 1件追加。

## 17. Home

```text
Reference Works count
Open Review count
Queued/Running Jobs
Active Profiles count
Latest Lint summary
```

`Latest Lint` はDashboard表示用の一覧順であり、解析入力としてlatestを暗黙利用する意味ではない。

## 18. Sources

- Narou/Kakuyomu URL入力
- file upload
- import開始
- job progress
- Reference Work list
- refresh
- purge

画面上部に短い利用注意文を表示してよいが、blocking checkbox/rights selectは置かない。

Purge確認は1回。

## 19. Document Analysis

```text
Header:
  work / episode
  TextRevision selector
  StructureRevision selector
  analysis status
Tabs:
  Text
  Structure
  Semantics
  Metrics
```

Text/Structure selector変更時はURL queryまたはcomponent stateで明示IDを保持する。

### Structure

- automatic/semantic/manual revision種別
- parent revision
- Semantic Structure生成元Boundary Run
- Scene list
- boundary proposal overlay
- manual split/merge

### Semantics

- Entity/Term/Speaker/Scene tags
- unresolved/unclear filter
- raw/effective切替
- 採用AnalysisRun ID表示
- Direct Override

低confidence結果を修正したい場合だけ操作する。ReviewQueueへの移動は任意。

### Metrics

- Basic/Semantic group切替
- 採用Metric Run ID
- table + metric単位chart

## 20. Corpus / Compare

Corpus membership編集。

Compareはtableを正本。ChartはMetricごとに1 chart、異unit混在なし。

```text
median
p25-p75
sample count
work count
```

## 21. Profile Editor

Identity:

```text
name
description
status
active version
latest version
```

Version Rule table:

```text
enabled
scope
metric
preferred
min
max
weight
severity policy
source
```

Saveはnew ProfileVersion。active profileを編集してもSaveだけではactive versionを切替えない。

UIは:

```text
保存
保存して有効化
```

を分けてよい。「保存して有効化」はVersion作成後Activate APIを呼ぶ。

Dirty guardは既存component再利用。

## 22. Review

左ReviewItem、右evidence/actions。

Queueにないlow-confidence結果はDocument Semanticsから直接Overrideする。

Scene Boundary ProposalはStructure画面を主導線とする。

## 23. Lint

表示:

```text
対象draft/TextRevision
StructureRevision
Profile/version
coverage
stale indicator
Finding list
```

Finding:

```text
metric
observed
reference range
short explanation
evidence
acknowledge/ignore
```

coverage 0でもerror画面にせず「比較可能なMetricなし」。

## 24. Job polling

WebSocket/SSEは追加しない。

TanStack Queryで `queued|running` の間2秒poll。終了statusで停止。

## 25. Query invalidation

- import/refresh/purge -> imports/referenceWorks/referenceEpisodes
- analysis -> document structures/runs/metrics/semantics
- Direct Override -> semantics/metrics/jobs
- Aggregate -> Corpus metrics
- Profile Version -> profiles/versions
- Activate -> profile identity/list
- Lint -> lint runs/findings

全Project queryを無差別invalidateしない。

## 26. 操作性

- input label
- progress text
- status/severityを色だけで示さない
- table keyboard操作
- confirm dialogは既存pattern

新規の独自安全確認modalは作らない。

## 27. Testing

API:

- Project isolation
- 202 job
- explicit Text/Structure retrieval
- Effective Run response includes selected run ID
- exact historical Run output/Measurement retrieval
- optional Structure in Analyze
- explicit StructureでBoundary skip
- Profile identity/Version/active Version API
- Direct Override without ReviewItem
- ReviewItem CAS
- Purgeで専用Source/Snapshot削除
- Provider unavailable

WEBUI:

- import form
- job polling stop
- Project A/B isolation
- Revision selector
- Structure Boundary Proposal
- Profile Save vs Save+Activate
- Direct Override
- Review conflict
- Lint coverage/stale
- Purge confirm 1回

## 28. Codex実装時の禁止事項

- MCP tool/countを変更しない。
- WebSocket/SSEを追加しない。
- 独自API client/query cacheを作らない。
- Authoring DBを推論で自動更新しない。
- Source importにrights_basis/同意checkboxを再追加しない。
- Full Analysisに毎回確認dialogを追加しない。
- Text/Structure/Lint入力をlatestへ暗黙解決しない。
- Profile Version作成だけでactive Versionを勝手に切替えない。
- Low-confidence修正を必ずReviewQueue経由にしない。
