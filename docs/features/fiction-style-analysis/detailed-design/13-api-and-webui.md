# 13 API and WebUI 詳細設計

## 1. 目的

Style AnalysisのCORE機能を既存FastAPI/React WebUIへ統合するAPI契約、画面構成、query invalidation、非同期job表示を確定する。既存NovelProductionのauthoring導線を壊さず、独立featureとして追加する。

上位仕様は `../basic-design.md`。

## 2. 重要な境界

v1では **MCPへStyle Analysis toolを追加しない**。

理由:

- 既存MCP tool count/契約を変更しない
- 外部作品本文をConnector経由で意図せず露出しない
- まずWebUI/APIでlocal workflowを確立する

したがって `MCP/` は本開発scope外。既存59 tool contractを維持する。将来MCP公開する場合は別設計・別Phaseとする。

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

`routes/__init__.py` で各routerを既存appへ登録する。

`service_container.py` にStyle Analysis用CORE repositories/servicesとAPI ingestion/runtimeを追加する。既存serviceのconstructor signatureを不要に変更しない。

## 4. URL prefix

全endpointを以下でproject scopeにする。

```text
/projects/{project_id}/style-analysis
```

`project_id` 解決・404/error contractは既存APIのproject scoped routeと同じ実装を再利用する。

## 5. Source/Reference API

```text
POST   /imports
GET    /imports/{import_id}
GET    /reference-works
GET    /reference-works/{work_id}
POST   /reference-works/{work_id}/refresh
DELETE /reference-works/{work_id}
GET    /reference-works/{work_id}/episodes
GET    /reference-episodes/{episode_id}
```

### POST /imports

network source JSON:

```json
{
  "source_type": "narou",
  "locator": "https://ncode.syosetu.com/.../",
  "rights_basis": "private_personal_use"
}
```

file uploadはmultipart endpointを同URLでoverloadせず、明示的に分ける。

```text
POST /imports/file
```

fields: `source_type=text|html_file|epub`, `rights_basis`, `file`。

response `202`:

```json
{"import_id": 12, "job_id": 44, "status": "queued"}
```

### DELETE reference work

body不要。purgeは明示操作。成功 `204`。存在しない場合既存404 contract。

## 6. Document/Structure API

```text
POST /project-episodes/{episode_id}/capture
GET  /documents
GET  /documents/{document_id}
GET  /documents/{document_id}/text
GET  /documents/{document_id}/structure
POST /documents/{document_id}/scenes/{scene_id}/split
POST /documents/{document_id}/scenes/merge
```

### capture

request:

```json
{"draft_id": 123}
```

`draft_id` omitted時にlatestへ暗黙解決しない。UIが現在のlatest draftを先に取得し、そのIDを明示送信する。

responseにtext_revision_id、canonical_sha256を返す。

### split

```json
{
  "after_block_id": 55,
  "expected_structure_revision_id": 9,
  "reason": "時間が切り替わっているため"
}
```

### merge

```json
{
  "left_scene_id": 4,
  "right_scene_id": 5,
  "expected_structure_revision_id": 9,
  "reason": "同一シーンとして扱うため"
}
```

## 7. Analysis/Job API

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

analyze:

```json
{
  "text_revision_id": 10,
  "structure_revision_id": 9,
  "preset": "full"
}
```

`preset=full` でprovider未設定なら `409 ANALYZER_PROVIDER_UNAVAILABLE` をjob作成前に返す。`deterministic` はprovider不要。

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

compare query:

```text
?corpus_id=1&corpus_id=2&metric=dialogue.char_ratio&metric=sentence.len.p50
```

corpus最大5件、metric最大20件。超過は422。

## 9. Profile API

```text
GET    /profiles
POST   /profiles/from-corpus
GET    /profiles/{profile_id}
POST   /profiles/{profile_id}/versions
POST   /profiles/{profile_id}/activate
POST   /profiles/{profile_id}/archive
GET    /profiles/{profile_id}/export
POST   /profiles/import
```

active/archiveはimmutable profile contentを変更せずstatus管理recordだけを更新する。Rule編集はnew version作成endpointで全rules snapshotを送る。

## 10. Review API

```text
GET  /review-items
GET  /review-items/{item_id}
POST /review-items/{item_id}/confirm
POST /review-items/{item_id}/reject
POST /review-items/{item_id}/override
POST /review-items/{item_id}/ignore
```

全writeに `expected_version` とreason/noteを必要に応じて要求する。

ReviewItem detail responseにexcerptを含めるがraw source payloadは返さない。

## 11. Lint API

```text
POST /documents/{document_id}/lint
GET  /lint-runs
GET  /lint-runs/{lint_run_id}
GET  /lint-runs/{lint_run_id}/findings
POST /findings/{finding_id}/review
```

lint request:

```json
{
  "text_revision_id": 10,
  "structure_revision_id": 9,
  "profile_id": 3,
  "profile_version": 2
}
```

response `202` + job_id。

## 12. Pagination

list endpointは既存API patternに合わせ、初期default 50、max 200。

query:

```text
limit
offset
```

新規cursor paginationは導入しない。

metrics/finding等大量listも同じ方式。

## 13. Error contract

既存NovelProduction API error envelopeを再利用する。Style Analysis用codeは各詳細設計に定義したものを追加する。

HTTP mapping:

```text
400 invalid source/operation
404 project/document/entity not found
409 version conflict/provider unavailable/stale structure
413 upload/source too large
422 schema validation
429 source site rate-limitを直接転送せず、job failureとしてSOURCE_RATE_LIMITED
500 invariant/internal
502 external model/source upstream failure
```

job内外部失敗はHTTP request自体を後から500にできないためJob status/errorとして返す。

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

共通API clientは既存 `src/api/client.ts` を使用。独自fetch wrapperを作らない。

query keyは既存 `src/api/queryKeys.ts` に `styleAnalysis` familyを追加する。

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

既存Project shell/sidebar配下に `文体分析` navigationを1件追加する。

## 16. Home画面

Dashboard card:

```text
Reference Works count
Open Review count
Queued/Running Jobs
Active Profiles count
Latest Lint summary
```

ここからSources/Corpus/Profile/Review/Lintへ移動する。

## 17. Sources画面

機能:

- Narou/Kakuyomu URL入力
- source type
- rights_basis select
- import開始
- text/html/epub upload
- job progress
- reference work list
- refresh
- purge

初回network import前に次の確認checkboxを表示する。

```text
この取得は、自分が利用権限を持つ、または私的利用として扱う作品をローカル分析する目的で行います。
```

checkboxはUI convenienceであり、APIでもrights_basis validationする。

## 18. Document Analysis画面

レイアウト:

```text
Header: work / episode / revision / analysis status
Tabs:
  Text
  Structure
  Semantics
  Metrics
```

Text: canonical text read-only。
Structure: Scene list + Block type + manual split/merge。
Semantics: Entity/Term/Speaker/Scene tags overview。
Metrics: table + metric単位ごとのchart。

1画面で全raw inference編集を可能にせず、修正はReviewへ遷移する。

## 19. Corpus/Compare画面

Corpus editはwork membershipをcheckbox/listで操作。

Compareはmetric tableを正本。chartはmetricごとに1 chartとし、異なるunitを同一axisに重ねない。

表示:

```text
median
p25-p75
sample count
work count
```

## 20. Profile Editor

Rule table columns:

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

saveはnew profile versionを作る。dirty navigation guardは既存componentを再利用する。

## 21. Review画面

左: ReviewQueue list。
右: evidence excerpt + raw inference + effective value +操作。

speaker overrideではScene participant Entityからselect。自由文字入力で新Entityをその場作成しない。Entity作成/統合は別review action。

Scene boundary候補acceptはsplit操作を実行する旨を明示し、structure revisionが変わることを表示する。

## 22. Lint画面

上部:

```text
対象episode/draft
TextRevision
Profile/version
stale indicator
```

Findingをseverity→sort score順。

各Finding:

```text
metric
observed
reference range
short explanation
evidence excerpts
acknowledge/ignore
```

「AIで修正」buttonはv1で置かない。

## 23. Job polling

WebSocket/SSEを追加しない。

TanStack Queryで `queued|running` の間だけ2秒polling。completed/failed/cancelledで停止。

画面を離れてもjobはserver側で継続。再訪時はGET jobで状態復元する。

## 24. Query invalidation

成功時に最低限以下をinvalidate。

- import complete → imports, referenceWorks
- analysis complete → document, structure, analysisRuns, metrics, reviewItems
- override → reviewItems, effective semantics, metrics/jobs
- aggregate → corpus metrics
- profile version → profiles
- lint → lintRuns/findings

全project queryを無差別invalidateしない。

## 25. Accessibility/操作

- form inputはlabel必須
- progressはtextでも状態表示
- colorだけでseverity/statusを示さない
- table操作はkeyboard可能
- confirm dialogは既存UI patternを使う

## 26. Testing

API:

- project isolation
- endpoint schema
- 202 job
- version conflict
- purge
- provider unavailable
- no raw payload leakage

WEBUI:

- import form validation
- rights checkbox
- polling stop
- project A/B query isolation
- profile dirty guard
- review CAS conflict
- lint stale表示
- source purge confirm

既存WebUI flakeをStyle Analysisテストへコピーしない。user-event操作対象はdisabled/focusable状態を明示waitしてから操作する。

## 27. Codex実装時の禁止事項

- MCP toolを追加・変更しない。
- tool count 59を変更しない。
- 新WebSocket/SSE infrastructureを追加しない。
- 独自API client/query cacheを作らない。
- authoring character/world/canonをStyle Analysis推論で自動更新しない。
- reference本文全文をMCP/connectorへ返さない。
- Style Analysis都合で既存route URLを変更しない。
