# 13 API and WebUI 詳細設計

## 1. 目的

Style AnalysisのCORE機能を既存FastAPI/React WebUIへ統合するAPI契約、画面構成、job表示、query invalidationを確定する。authoring導線を壊さず独立featureとして追加する。

上位仕様は `../basic-design.md`。

## 2. 境界

v1ではMCPへStyle Analysis toolを追加しない。`MCP/` はscope外、既存tool count 59を維持する。

Style Analysis推論から既存character/world/canonを自動更新しない。

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

project解決/error contractは既存project scoped routeを再利用する。

## 5. Source / Reference API

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

response `202`:

```json
{"import_id": 12, "job_id": 44, "status": "queued"}
```

DELETE reference workは明示Purge、成功204。

## 6. Document / Structure API

```text
POST /project-episodes/{episode_id}/capture
GET  /documents
GET  /documents/{document_id}
GET  /documents/{document_id}/text
GET  /documents/{document_id}/structure
GET  /documents/{document_id}/structure/boundary-proposals
POST /documents/{document_id}/scenes/{scene_id}/split
POST /documents/{document_id}/scenes/merge
```

### capture

```json
{"draft_id": 123}
```

latestへ暗黙解決しない。response:

```json
{
  "document_id": 5,
  "text_revision_id": 10,
  "canonical_sha256": "..."
}
```

Structureはcapture時に必須生成しない。`analyze` deterministic/fullが指定TextRevisionからbuild/reuseする。

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

## 7. Analysis / Job API

```text
POST /documents/{document_id}/analyze
GET  /jobs/{job_id}
POST /jobs/{job_id}/cancel
POST /jobs/{job_id}/retry
GET  /analysis-runs
GET  /analysis-runs/{run_id}
GET  /documents/{document_id}/metrics
GET  /documents/{document_id}/scenes/{scene_id}/metrics
```

request:

```json
{
  "text_revision_id": 10,
  "structure_revision_id": null,
  "preset": "full"
}
```

- `text_revision_id` required。
- `structure_revision_id` optional。
- omitted: automatic Structure build/reuse、fullならsemantic boundaryをmaterialize。
- provided: exact Structureを使用。manual Structureではboundary auto applyを再実行しない。

`preset=full` でprovider未設定ならjob作成前に `409 ANALYZER_PROVIDER_UNAVAILABLE`。

## 8. Corpus API

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

Compareは2〜5 Corpus、metric最大20。

## 9. Profile API

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

- PATCHはname/descriptionだけ。
- version作成endpointでrules snapshotを全送信。
- active/archiveはProfile identity statusだけ変更。
- ProfileVersion/Ruleはupdateしない。

## 10. Review API

```text
GET  /review-items
GET  /review-items/{item_id}
POST /review-items/{item_id}/confirm
POST /review-items/{item_id}/reject
POST /review-items/{item_id}/override
POST /review-items/{item_id}/ignore
```

ReviewItem writeは `expected_version`。

Override body:

```json
{
  "value": 3,
  "structure_revision_id": 9,
  "note": null
}
```

`note` optional。別の汎用effective tokenは要求しない。

低confidence推論一覧はReviewItem化せず、Document Semantics API/filterから参照可能にする。

## 11. Lint API

```text
POST /documents/{document_id}/lint
GET  /lint-runs
GET  /lint-runs/{lint_run_id}
GET  /lint-runs/{lint_run_id}/findings
POST /findings/{finding_id}/review
```

request:

```json
{
  "text_revision_id": 10,
  "structure_revision_id": 9,
  "profile_id": 3,
  "profile_version_no": 2
}
```

response `202` + job ID。

LintRun detailは:

```text
enabled_rule_count
applicable_rule_count
missing_rule_count
coverage_ratio
stale
```

を返す。

## 12. Pagination

list endpointは既存pattern:

```text
limit default 50, max 200
offset default 0
```

cursor paginationはv1で導入しない。

## 13. Error contract

既存API envelopeを再利用。

```text
400 invalid source/operation
404 not found
409 version conflict/provider unavailable/stale structure
413 upload/source too large
422 schema validation
500 invariant/internal
502 external source/model upstream failure
```

network import/model job中の失敗はJob errorとして返す。

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

既存 `src/api/client.ts` とquery cacheを使う。

## 15. Route

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

## 16. Home

```text
Reference Works count
Open Review count
Queued/Running Jobs
Active Profiles count
Latest Lint summary
```

## 17. Sources

- Narou/Kakuyomu URL入力
- file upload
- import開始
- job progress
- Reference Work list
- refresh
- purge

画面上部に短い利用注意文を表示してよいが、blocking checkboxやrights selectは置かない。

## 18. Document Analysis

```text
Header: work / episode / text revision / structure revision / analysis status
Tabs:
  Text
  Structure
  Semantics
  Metrics
```

### Structure

- automatic/semantic/manual revision種別表示
- Scene list
- boundary proposal overlay on/off
- manual split/merge

semantic boundaryのauto apply済み箇所も元base structureとの差として表示可能にする。

### Semantics

- Entity/Term/Speaker/Scene tags
- unresolved/unclear filter
- raw/effective切替

低confidence結果を修正したい場合だけOverride/Reviewへ進む。

## 19. Corpus / Compare

Corpus membership編集。

Compareはtableを正本。chartはmetricごとに1 chart、異unit混在なし。

```text
median
p25-p75
sample count
work count
```

## 20. Profile Editor

Profile identity fields:

```text
name
description
status
```

Version rule table:

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

Saveはnew ProfileVersion。dirty guardは既存component再利用。

## 21. Review

左ReviewItem、右evidence/raw/effective/actions。

Queueにないlow-confidence結果はDocument Semanticsから直接Override可能にしてよい。

Scene boundary proposalはStructure画面を主導線とし、Review画面はユーザーがQueueへ追加した候補だけ扱う。

## 22. Lint

表示:

```text
対象draft/TextRevision
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

## 23. Job polling

WebSocket/SSEは追加しない。

TanStack Queryで `queued|running` の間2秒poll。終了statusで停止。

## 24. Query invalidation

- import -> imports/referenceWorks
- analysis -> document/structure/runs/metrics/semantics
- override -> semantics/metrics/jobs
- aggregate -> corpus metrics
- profile version -> profiles/profile versions
- lint -> lint runs/findings

全project queryを無差別invalidateしない。

## 25. 操作性

- input label
- progress text
- status/severityを色だけで示さない
- table keyboard操作
- confirm dialogは既存pattern

新規の独自安全確認modalは作らない。

## 26. Testing

API:

- project isolation
- 202 job
- optional structure revision
- manual structureではboundary auto apply skip
- Profile identity/version API
- ReviewItem CAS
- optional override note
- purge
- provider unavailable

WEBUI:

- import form
- job polling stop
- project A/B isolation
- Structure boundary proposal表示
- Profile version dirty guard
- Review conflict
- Lint coverage/stale
- purge confirm

## 27. Codex実装時の禁止事項

- MCP tool/countを変更しない。
- WebSocket/SSEを追加しない。
- 独自API client/query cacheを作らない。
- authoring DBを推論で自動更新しない。
- source importにrights_basis/同意checkboxを再追加しない。
- full analysisに毎回確認dialogを追加しない。
- Profile identityとVersion endpointを混同しない。