# 13 API and WebUI 詳細設計

## 1. 目的

Style AnalysisのCORE機能を既存FastAPI/React WebUIへ統合するAPI契約、画面構成、Job表示、Revision選択、Query Invalidationを確定する。Authoring導線を壊さず独立Featureとして追加する。

上位仕様は `../basic-design.md`。

## 2. 境界

- v1ではMCPへStyle Analysis Toolを追加しない。既存Tool Count 59を維持。
- Style Analysis推論から既存Character/World/Canonを自動更新しない。
- WebSocket/SSEは追加せずJob状態はPollingする。
- Source Import/Full Analysisにrights checkboxや毎回の確認Dialogを追加しない。

## 3. API実装先

```text
API/src/novel_api/
  style_analysis/
    __init__.py
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
  schemas/
    style_analysis.py
```

既存 `service_container.py` へService/Repositoryを追加する。独自API Clientや別Query Cacheは作らない。

## 4. URL Prefix

```text
/projects/{project_id}/style-analysis
```

Project解決・Error Envelopeは既存Project-scoped Routeを再利用する。

## 5. Revision / Run指定方針

### 明示必須

- Text取得: `text_revision_id`
- Structure取得/編集: `structure_revision_id`
- Lint: `text_revision_id + structure_revision_id + profile_version_no`
- Profile Export: `version_no`

### Effective Run選択を許可

Semantics/Metricの通常UIは `structure_revision_id` を明示し、Serverが09 Current AnalysisRun Resolverで採用Runを選んでよい。Responseには採用 `analysis_run_id` を返す。

過去Runの厳密表示はRun ID endpointを使う。Latest Draft/Latest Structureへ暗黙読み替えしない。

## 6. Source / Reference API

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

### Import

Network:

```json
{"source_type":"narou","locator":"https://ncode.syosetu.com/.../"}
```

File: multipart `source_type=text|html_file|epub`, `file`。

Response:

```json
{"import_id":12,"job_id":44,"status":"queued"}
```

### Refresh

`source_refresh` Jobを作り `202 + job_id`。Import Rowは作らない。

### Reference Work Analyze

```json
{"preset":"full"}
```

`preset=deterministic|full` を許可する。Response `202 + job_id`。

Work Detail/Episode Listは各Episodeの `current_text_revision_id` を返す。Work Analyzeは09に従いJob開始時のCurrent Episode/Revision Snapshotを対象にする。

### Purge

12のPurge Transactionを同期実行し204。通常の削除確認1回でよい。

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

Capture:

```json
{"draft_id":123}
```

latest Draftへ暗黙解決しない。

Text:

```text
GET /documents/{document_id}/text?text_revision_id=10
```

Structure:

```text
GET /documents/{document_id}/structure?structure_revision_id=9
```

Structure Response:

```text
text_revision_id
structure_revision_id
source_kind
parent_structure_revision_id
semantic_source_run_id nullable
scenes/blocks/sentences
```

Boundary Proposal:

```text
GET /documents/{document_id}/structure/boundary-proposals?base_structure_revision_id=7
```

採用Boundary Run IDを返す。

Split/Mergeは `expected_structure_revision_id` を必須とし、noteは任意。

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

Document Analyze:

```json
{
  "text_revision_id":10,
  "structure_revision_id":null,
  "preset":"full"
}
```

- `text_revision_id` required
- `structure_revision_id` optional
- explicit StructureならScene Boundary Detectorを再実行しない
- `full` でProvider未設定ならJob作成前に `409 ANALYZER_PROVIDER_UNAVAILABLE`

### Job Response

```json
{
  "job_id":44,
  "job_type":"analyze_reference_work",
  "status":"partial",
  "progress_current":8,
  "progress_total":10,
  "result":{},
  "warnings":[],
  "error_code":null,
  "error_message":null
}
```

Status:

```text
queued | running | succeeded | partial | failed | cancelled
```

`progress_total` はNULL可。`partial` は終了状態なのでPollingを停止する。

Retryは元Job Rowをqueuedへ戻さず、同payloadの新Jobを作る。成功後 `worker.notify(project_id)`。

### Semantics / Metrics

```text
GET /documents/{document_id}/semantics?structure_revision_id=9
GET /documents/{document_id}/metrics?structure_revision_id=9&group=basic
GET /documents/{document_id}/metrics?structure_revision_id=9&group=semantic
```

ResponseにはAnalyzerごとのSelected Run IDを含める。Historical閲覧はRun endpoint。

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

Compare: Corpus 2〜5件、Metric最大20件。

## 10. Profile API

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

- PATCHはname/descriptionだけ
- Version作成はRules Snapshot全送信
- Activate Request: `{"version_no":3}`
- 新Version作成だけではactive Versionを切替えない
- List/Detailは `status`, `active_version_no`, `latest_version_no` を返す

## 11. Review / Direct Override API

Review Queue:

```text
GET  /review-items
GET  /review-items/{item_id}
POST /review-items/{item_id}/confirm
POST /review-items/{item_id}/reject
POST /review-items/{item_id}/ignore
```

ReviewItem Writeは `expected_version`。

Direct Override:

```text
POST /overrides
```

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

Operation: `set | clear | revert`。

- `revert` はManual指定を解除しInferenceへ戻す
- `clear` はField定義に従うExplicit None/Unknown
- note optional
- Structure SubjectだけStructureRevision必須
- Generic二重CASは要求しない

Inference Review:

```text
POST /inference-reviews
```

ReviewItemなしでConfirm/Reject可能。

## 12. Lint API

```text
POST /documents/{document_id}/lint
GET  /lint-runs
GET  /lint-runs/{lint_run_id}
GET  /lint-runs/{lint_run_id}/findings
POST /findings/{finding_id}/review
```

```json
{
  "text_revision_id":10,
  "structure_revision_id":9,
  "profile_id":3,
  "profile_version_no":2
}
```

Profile Version省略不可。LintRun DetailはCoverage Counts/RatioとStaleを返す。

## 13. Pagination / Error

List: `limit default 50 max 200`, `offset default 0`。

Error Envelopeは既存契約。

```text
400 invalid operation/source
404 not found
409 version conflict/provider unavailable/stale structure
413 source/upload too large
422 schema/revision validation
500 internal/invariant
502 upstream source/model
```

Job内部FailureはJob Errorへ保存する。

## 14. WebUI実装先

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

既存 `src/api/client.ts` / TanStack Queryを使う。

## 15. Routes

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

Project Sidebarに `文体分析` 1件追加。

## 16. Sources / Reference Work UI

Sources:

- Narou/Kakuyomu URL
- File Upload
- Import Job Progress
- Reference Work List
- Refresh/Purge

Reference Work Page:

- Metadata / Episode List
- Current TextRevision ID
- `作品全体を分析` Button
- Preset `deterministic | full`
- Work Job Progress `current / total`
- Partial時にSucceeded/Failed Episode一覧
- EpisodeからDocument Analysisへ遷移

Purge確認は1回。

## 17. Document Analysis UI

Header:

```text
Work / Episode
TextRevision selector
StructureRevision selector
Analysis status
```

Tabs: Text / Structure / Semantics / Metrics。

Structure:

- Revision Kind/Parent
- Boundary Source Run
- Boundary Proposal Overlay
- Manual Split/Merge

Semantics:

- Entity/Term/Speaker/Scene/POV
- unresolved/unclear filter
- raw/effective切替
- Selected Run IDs
- Direct Set/Clear/Revert Override
- Entity/Term Enable/Disable/Name/Type修正
- Alias Confirm/Reject

Metrics:

- Basic/Semantic Group
- Selected Metric Run ID
- Table + Metric単位Chart

## 18. Corpus / Profile / Review / Lint UI

Corpus CompareはTableを正本とし異Unitを同Axisへ混ぜない。

Profile Editor:

```text
保存
保存して有効化
```

を分離可能。SaveだけではActive Version変更なし。

Review Queueは任意Review Workflowだけを扱い、Low Confidence修正を必ず経由させない。

Lintは対象Revision/Profile Version/Coverage/Stale/Findingを表示する。Coverage 0はError画面にせず「比較可能なMetricなし」。

## 19. Job Polling

TanStack Queryで `queued|running` の間だけ2秒Polling。

停止Status:

```text
succeeded
partial
failed
cancelled
```

画面離脱後もServer Jobは継続。再訪時GET Jobで復元する。

## 20. Query Invalidation

- Import/Refresh/Purge -> imports/referenceWorks/referenceEpisodes
- Work Analysis -> work/episodes/jobs/documents/runs/semantics/metrics
- Document Analysis -> structures/runs/semantics/metrics
- Override/Inference Review -> semantics/metrics/jobs
- Aggregate -> Corpus metrics
- Profile Version -> profile versions
- Activate -> profile identity/list
- Lint -> lint runs/findings

全Project Queryを無差別Invalidateしない。

## 21. Testing

API:

- Project isolation
- Initial Import / Refresh / Work Analyze 202
- Work Analyze deterministic/full
- Job progress + partial + result
- Retry creates new Job
- explicit Text/Structure retrieval
- Semantics/Metric Selected Run ID
- Historical Run retrieval
- Explicit StructureでBoundary Skip
- Profile Identity/Version/Activation
- Direct Set/Clear/Revert Override
- ReviewItem CAS
- Purge Source/Snapshot
- Provider unavailable

WEBUI:

- Import Form
- Job Polling stops on partial/succeeded/failed/cancelled
- Work Analysis progress/partial display
- Project A/B isolation
- Revision Selector
- Boundary Proposal
- Entity/Term Direct Correction
- Profile Save vs Save+Activate
- Review conflict
- Lint coverage/stale
- Purge confirm 1回

## 22. Codex禁止事項

- MCP Tool/Count変更
- WebSocket/SSE追加
- 独自API Client/Query Cache追加
- Authoring DBへ推論自動Write
- rights_basis/同意Checkbox再追加
- Full Analysis毎回確認Dialog追加
- Text/Structure/LintをLatestへ暗黙解決
- Work一括解析をUI側でEpisode LoopしてServer Jobを分散生成
- Partial JobをRunning扱いし続ける
- Profile Version作成だけでActive切替
- Low-confidence修正をReviewQueue必須にする
