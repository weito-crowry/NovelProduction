# 13 API and WebUI 詳細設計

## 1. 目的

Style Analysisを既存FastAPI/React WebUIへ統合するAPI契約、Revision選択、Current Pointer、Local File Import、Analysis Job、Manual Correction、Aggregate/Profile/Lint UIを確定する。

上位仕様は `../basic-design.md`。Local Parserは01、Semantic Model Client/Prompt Contractは15を正本とする。

## 2. 境界

- v1でMCP Tool追加なし。既存Tool Count 59維持。
- Style推論から既存Character/World/Canonを自動更新しない。
- WebSocket/SSE追加なし。JobはPolling。
- Source Site固有Network Downloader/Refreshなし。
- Local TXT/HTML/EPUB Importのみ。
- rights_basis/毎回の確認Dialogなし。
- 既存API Client/Query Cache/Project Scope Error Contractを再利用する。
- Profile Import/Exportはv1 scope外。
- API Runtime Dependency追加は01 `beautifulsoup4`、Local File Multipart Importの
  `python-multipart`、15 `httpx`。

URL Prefix:

```text
/projects/{project_id}/style-analysis
```

## 3. Revision明示方針

- Text取得:`text_revision_id`。
- Structure取得/編集:`structure_revision_id`。
- Analyze:`text_revision_id`必須、Structure optional。
- Lint:Text + Structure + Profile Version。

Semantics/MetricはStructure IDを明示しServerが09 Current Runを選ぶ。Responseは採用Run IDを返す。

latest Revision/Structureへ暗黙読み替えしない。

## 4. Analysis Status

10 `AnalysisStatusService`を正本とする。

```json
{
  "analysis_status": {
    "basic":{"state":"not_analyzed | current | stale","reasons":[]},
    "semantic":{"state":"not_analyzed | current | stale | partial","reasons":[]}
  }
}
```

Deterministicのみ完了ならBasic current / Semantic not_analyzed。

`analysis_stale`等の永続boolをAPI Contractへ追加しない。

## 5. Local File Import API

```text
POST /imports/file
```

Multipart:

```text
source_type = text | html_file | epub
file
```

同期処理。Job Rowを作らない。

- New:`201` + `reused_existing=false/reference_work_id/source_id`。
- Duplicate:`200` + `reused_existing=true/reference_work_id/source_id`。
- Upload超過:`413`。

Unsupported Type/Parse/Encoding/Normalization Errorは既存Error EnvelopeでCodeを返す。

URL Import/Refresh Endpointはv1で作らない。

## 6. Reference Work API

```text
GET    /reference-works
GET    /reference-works/{work_id}
GET    /reference-works/{work_id}/episodes
GET    /reference-episodes/{episode_id}
POST   /reference-works/{work_id}/analyze
DELETE /reference-works/{work_id}
```

### Work Detail

```text
reference_work_id
source_id
source_type
title
author_name
episode_count
created_at
```

Workは複数Episode/StyleDocumentを持つため単一`style_document_id`/Current Pointerを返さない。

### Episode Detail

```text
reference_episode_id
reference_work_id
title
order_index
style_document_id
current_text_revision_id nullable
current_structure_revision_id nullable
current_structure_kind nullable
analysis_status
```

### Work Analyze

Request:

```json
{
  "preset":"full",
  "rebuild_structure":false
}
```

Preset:`deterministic|full`。

Full Provider未設定はJob作成前409 `ANALYZER_PROVIDER_UNAVAILABLE`。Provider設定判定は15 `ApiSettings`を使う。

Job開始時に各Episode Current TextをSnapshotし09どおりEpisode Order順にinline処理する。

Response:`202 + job_id`。

Deleteは01 Source Row Purge、204、通常確認1回。

## 7. Project Capture / Document API

```text
POST /project-episodes/{episode_id}/capture
GET  /documents
GET  /documents/{document_id}
GET  /documents/{document_id}/revisions
GET  /documents/{document_id}/text?text_revision_id={id}
GET  /documents/{document_id}/structures
GET  /documents/{document_id}/structure?structure_revision_id={id}
POST /documents/{document_id}/structures/{structure_revision_id}/select-current
GET  /documents/{document_id}/structure/boundary-proposals
POST /documents/{document_id}/scenes/{scene_id}/split
POST /documents/{document_id}/scenes/merge
```

Capture Request:`{"draft_id":123}`。Draft ID必須。

Document Summary:

```text
document_id
kind
current_text_revision_id nullable
current_structure_revision_id nullable
current_structure_kind nullable
analysis_status
```

## 8. Structure Select / Manual Edit

Structure Selectorは閲覧対象変更だけ。Selector変更でCurrent Pointerを更新しない。

Select Currentは同Document + Current TextRevision所属をValidationし200 updated Document Summary。

Split/Merge:

- Current Structureのみ。
- `expected_structure_revision_id`必須。
- 成功新Manual RevisionをCurrent化。

Boundary Proposal:

- Default:`confidence >= scene_boundary_candidate_min`。
- `include_below_threshold=true`:Raw全Valid Candidate。

Candidate Minは表示Filterだけ。

## 9. Document Analysis / Job API

```text
POST /documents/{document_id}/analyze
GET  /jobs/{job_id}
POST /jobs/{job_id}/cancel
POST /jobs/{job_id}/retry
GET  /analysis-runs
GET  /analysis-runs/{run_id}
GET  /analysis-runs/{run_id}/outputs
GET  /analysis-runs/{run_id}/measurements
GET  /documents/{document_id}/semantics?structure_revision_id={id}
GET  /documents/{document_id}/metrics?structure_revision_id={id}
GET  /documents/{document_id}/scenes/{scene_id}/metrics?structure_revision_id={id}
```

Analyze Request:

```json
{
  "text_revision_id":10,
  "structure_revision_id":null,
  "preset":"full",
  "rebuild_structure":false
}
```

Validation:

- Explicit Structureは指定Text所属。
- Explicit Structure + rebuild=true ->422。
- Current Manual/Semantic + default Full ->保持。
- Current Automatic + Full ->Boundary実行/Semantic昇格可能。
- rebuild=true ->Automaticから再生成。

Public preset:`deterministic|full`のみ。09 `metrics`は内部Correction Job専用。

Full Provider未設定はJob作成前409 `ANALYZER_PROVIDER_UNAVAILABLE`。

Job Response:`job_id/job_type/status/progress/result/warnings/error`。

Pollingは`queued|running`中だけ。

Job Type別`partial`可否は09を正本とし、Aggregate/Lintでは`partial`を返さない。

## 10. Entity / Character Link / Term API

```text
POST   /entities
POST   /entities/{entity_id}/aliases
PUT    /documents/{document_id}/character-links/{project_character_id}
DELETE /documents/{document_id}/character-links/{project_character_id}
POST   /terms
POST   /terms/{term_id}/aliases
```

Manual Entity/TermはReference WorkまたはDocument Scope exactly one。04/05のService SignatureをRequest Schemaへそのまま写す。Same Name/Label別Identity可。

Alias再送Idempotent。

Character Link PUT:

```json
{"style_entity_id":77}
```

Style Entityは指定Project DocumentのEnabled Person。Authoring Character/World/Canonを作成/更新しない。

## 11. Semantics / Direct Correction API

```text
GET  /documents/{document_id}/semantics?structure_revision_id={id}
POST /overrides
POST /inference-reviews
```

Semantics Response:

- Entity/Mention/Speaker。
- Term/TermMention Explanation。
- Scene Axis/POV。
- Block Primary Semantic。
- Raw + Effective。
- Selected AnalysisRun IDs。
- Analysis Status。

Override Request:

```json
{
  "subject_type":"block",
  "subject_id":55,
  "field_path":"block.speaker_entity_id",
  "operation":"set",
  "value":5,
  "base_analysis_run_id":101,
  "structure_revision_id":9,
  "note":null
}
```

`subject_type/field_path/operation/value`は10 Override Registryを正本とする。`value`はAPI層でField型Validation後、Repositoryでは`value_json`へ保存する。Clear/Revertでは`value`省略またはNULL。

Note optional。Generic二重CASなし。

Inference Review Request:

```json
{
  "analysis_run_id":101,
  "subject_type":"block",
  "subject_id":55,
  "field_path":"block.speaker",
  "review_status":"confirmed",
  "note":null
}
```

`review_status=confirmed|rejected`。

`subject_type + field_path + analysis_run_id`は10 Inference Review Registryへ完全一致する必要がある。Registry外は422 `INFERENCE_REVIEW_TARGET_INVALID`。

ReviewItemを経由しない。

Correction後のJob/Stateは10を正本とする。

## 12. ReviewItem API

ReviewItemは10どおり「後で確認したい項目」の管理であり、Inference Reviewと別責務にする。

```text
GET  /review-items
GET  /review-items/{id}
POST /review-items
POST /review-items/{id}/resolve
POST /review-items/{id}/ignore
```

### Create

User作成は`manual_review`だけ。

Request:

```json
{
  "subject_type":"scene",
  "subject_id":42,
  "analysis_run_id":null,
  "priority":"normal"
}
```

- `subject_type`は10 ReviewItem Subject Registryだけ。
- `priority`省略時`normal`。
- `normal|high`のみ。
- Serverが`item_type=manual_review`, `reason_code=user_marked`, `status=open`, `version=1`を設定。
- Response:`201 ReviewItem`。
- 同SubjectのOpen Manual Review重複は許容する。
- Note入力はCreate時に持たない。

### Resolve / Ignore

Request:

```json
{
  "expected_version":3,
  "note":null
}
```

- `expected_version`必須。
- note optional。
- Success:`200 ReviewItem`。
- Version conflict:`409 VERSION_CONFLICT`。
- Closed Item再更新:`409 REVIEW_ITEM_CLOSED`。

ReviewItem Resolve/Ignore自体はInference Confirm/Reject、Override、Structure Split等のDomain変更を暗黙実行しない。必要なDomain操作を先に専用APIで行い、その後Itemを閉じる。

Generic `/review-items/{id}/confirm` / `reject` Endpointは作らない。

## 13. Corpus API

```text
GET/POST /corpora
GET/PATCH/DELETE /corpora/{corpus_id}
POST   /corpora/{corpus_id}/works
DELETE /corpora/{corpus_id}/works/{work_id}
PUT    /corpora/{corpus_id}/episodes/{episode_id}
DELETE /corpora/{corpus_id}/episodes/{episode_id}
GET    /corpora/compare
```

Membership解決は08 CORE Resolverを共用する。

## 14. Aggregate API

Corpus:

```text
POST /corpora/{corpus_id}/aggregates/recompute
GET  /corpora/{corpus_id}/aggregates
```

Reference Work:

```text
POST /reference-works/{work_id}/aggregates/recompute
GET  /reference-works/{work_id}/aggregates
```

Recompute Request:

```json
{
  "measurement_target_type":"scene",
  "filter":{"scene":{"function":["daily"]}},
  "metric_names":["dialogue.char_ratio","sentence.len.p50"]
}
```

Document Targetでは`filter={}`のみ許可。Metric Namesは07 Registry存在必須。Metric VersionはRegistry Current Version。

Response:`202 + recompute_aggregate job_id`。

Job ResultはSpec/MetricごとにStatistic→Aggregate IDを返す。

GETはHistorical Aggregateに`stale/warnings/aggregate_policy_version/count4種`を返す。

## 15. Profile APIは同期

```text
GET    /profiles
POST   /profiles/from-corpus
POST   /profiles/manual
GET    /profiles/{profile_id}
PATCH  /profiles/{profile_id}
GET    /profiles/{profile_id}/versions
GET    /profiles/{profile_id}/versions/{version_no}
POST   /profiles/{profile_id}/versions
POST   /profiles/{profile_id}/activate
POST   /profiles/{profile_id}/archive
```

Profile/Version作成は同期Transaction。Jobを作らない。

### from-corpus

Rule Source Request:

```json
{
  "corpus_id":3,
  "name":"参考文体",
  "description":"",
  "rules":[
    {
      "preferred_aggregate_id":101,
      "min_aggregate_id":102,
      "max_aggregate_id":103
    }
  ]
}
```

08 Validation後201。Sample Policy不足SourceはRule Skipし、Response Warningへ理由を返す。

Stale Aggregate明示利用時もWarningのみで拒否しない。

### manual / new version

Manual Profile Requestは`name/description/rules` Full Snapshot。

New Version Request:

```json
{
  "parent_version_no":2,
  "rules":[...full rule snapshot...]
}
```

Rule必須Field:

```text
target_scope
scope_selector
metric_name
metric_version
weight
enabled
severity_policy
```

Enabledなら`min_value/max_value`必須、preferred optional。

Rule `preferred_value/min_value/max_value/weight`はJSON Numberを受ける。bool、NaN、Infinityは拒否。MetricDefinitionが`value_type=int`でもRule Rangeの整数性は要求しない。Serverはfinite floatへ正規化する。

New VersionだけでActive変更なし。

### profile identity update / activate / archive

`PATCH /profiles/{id}`は`name`/`description`だけ変更可能。status/active_versionは変更しない。

Activate Request:

```json
{"version_no":3}
```

指定Versionを`active_version_id`へ設定しProfile status=`active`。

ArchiveはBodyなしでstatus=`archived`。Version/Rule保持。Archived VersionをHistorical Lint Requestで明示利用することは許可するが、WebUI新規LintのDefault Selectorからは除外する。

Import/Export Endpointはv1で作らない。

## 16. Lint API

```text
POST /documents/{id}/lint
GET  /lint-runs
GET  /lint-runs/{id}
GET  /lint-runs/{id}/findings
POST /findings/{id}/review
```

Lint Request:

```json
{
  "text_revision_id":10,
  "structure_revision_id":9,
  "profile_id":3,
  "profile_version_no":2,
  "scene_id":null
}
```

POST lintは`202 + run_lint job_id`。ClientはMetric Run IDを指定しない。

Job Resultへ`lint_run_id`。Selector unavailable/Metric missingはCoverage WarningでありJob Failureではない。

## 17. WebUI Routes

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

Project Sidebarに`文体分析`。

## 18. Sources / Reference UI

Sources:

- TXT/HTML/EPUB File Picker。
- Import Type選択。
- 同期Import Result。
- Duplicate Existing Work Link。
- Reference Work一覧。

Network URL Input/Refresh Buttonは表示しない。

Reference Work:

- Work metadata。
- Episode一覧。
- Episode Current Text/Structure/Analysis Status。
- deterministic/full Work Analyze。
- Work Job Progress/Partial Episode表示。
- Purge確認1回。

Blocking rights checkboxなし。

## 19. Document Analysis UI

Header:`TextRevision selector / StructureRevision selector / Current Structure badge / Basic state / Semantic state`。

Selector変更だけでCurrent Pointer変更なし。

Analyze UI:

- Manual/Semantic Current ->通常Fullで保持。
- Automatic Current ->FullでSemantic昇格可能。
- Advanced `構造を再生成して解析` ->rebuild=true。

Tabs:`Text|Structure|Semantics|Metrics`。

SemanticsではManual Entity/Term/Alias、Character Link、Mention Resolution/Speaker、Term Novelty/Explanation、Scene Axis/POV、Block Primary、Raw/Effective/Selected Run IDsを表示・編集する。

Inference Review UIは10 RegistryにあるRaw InferenceだけConfirm/Rejectを表示する。

`not_analyzed`, `stale`, `partial`を同じエラー表示にしない。

Review画面:

- Open/Resolved/Ignored Item一覧。
- 10 Registry内Subjectから`後で確認`でManual ReviewItem作成。
- priority normal/highはCreate時だけ。v1で既存Item priority編集APIは作らない。
- Resolve/Ignore。
- Confirm/Rejectは対象InferenceのSemantics UIから`/inference-reviews`を呼ぶ。

## 20. Corpus / Aggregate / Profile UI

Corpus Membershipは08規則をそのまま表示する。

Aggregate BuilderはTarget/Filter/Metricを選択しRecompute Job、Statistic/Count/Stale/Warning/Provenanceを表示する。

Profile from CorpusではAggregate Groupを選択しUIがmedian/p25/p75 Exact IDsを送る。

Rule Editor:

```text
document -> selectorなし
scene -> Scene Axis
character -> Project Character
```

Count MetricでもRange入力は小数可。表示上のstepを整数へ固定しない。

Enabled Ruleはmin/max両方必須。

`保存`と`保存して有効化`を分離する。

Archived Profileは通常選択肢から除外し、Historical Lint Detailからは参照可能。

## 21. Lint UI

- Text/Structure/Profile Version。
- Document/Specific Scene Scope。
- 202 Job Polling。
- Coverage/Stale。
- Finding + Rule Scope + Evidence。
- Selector unavailable Warning。
- Coverage0も通常結果。

## 22. Query Invalidation

- Local Import/Purge ->Reference系。
- Capture ->Document/Revisions。
- Analyze/Rebuild ->Document/Structure/Run/Semantics/Metric。
- Select Current ->Document/Structures/Aggregate/Lint Staleness。
- Manual Entity/Term/Alias ->Semantics/Analysis Status。
- Character Link ->Semantics/Lint。
- Metric-only Override ->Semantics/Metric/Job/Aggregate/Lint。
- Semantic Reanalysis Required Correction ->Semantics/Analysis Status。
- Scene Axis Override ->Semantics/Aggregate/Lint。
- ReviewItem Create/Resolve/Ignore ->ReviewItemのみ。
- Inference Review ->10分類に従う。
- Corpus Membership ->Corpus/Aggregate Staleness。
- Aggregate Recompute ->Aggregate。
- Profile Sync Write ->Profile。
- Lint Job ->Lint。

全Project Queryを無差別Invalidateしない。

## 23. Test

API:

- Local New201/Duplicate200/Jobなし。
- Network Import/Refresh Endpoint不存在。
- Work Detailに単一Document Pointerを返さない。
- Episode DetailにDocument/Current Pointer/Statusを返す。
- Work Full Analyze Provider disabled ->409。
- Basic/Semantic Status。
- Explicit Revision。
- Select CurrentとHistorical Selector分離。
- Current Manual/Semantic Full保持、Automatic Full昇格。
- rebuild/Explicit validation。
- Job Type別Partial可否。
- Override Request Field Registry/Value型。
- Inference Review Registry exact field paths。
- Manual Identity/Link。
- ReviewItem Create Subject Registry/priority/default。
- ReviewItem resolve/ignore expected_version/note/closed conflict。
- ReviewItem resolveでDomain Correctionを暗黙実行しない。
- Generic ReviewItem confirm/reject不存在。
- Aggregate Recompute Request/202/Stale/Policy Version。
- Profile from-corpus Exact3 ID Request。
- Profile manual/new-version同期、Jobなし。
- PATCH profile name/description only。
- Activate version_no/Archive/Historical archived lint。
- Count Metric Ruleへ小数Range可、bool/NaN/Infinity拒否。
- Profile min/max/preferred Validation。
- Profile Import/Export不存在。
- Lint POST202/run_lint result。

WebUI:

- Local Sync Import/No Network Controls。
- Work/Episode表示責務分離。
- Status/Current Structure/Automatic昇格/Rebuild。
- Semantic Correction/Inference ReviewとReviewItem管理の分離。
- Manual ReviewItem作成/Resolve/Ignore。
- Aggregate Builder。
- Profile Exact Aggregate Group/Stale Warning/Range必須/Count小数Range。
- Save vs Activate/Archived Default除外。
- Lint Job Polling/Coverage/Stale。

## 24. Codex禁止事項

- `analysis_stale`等永続bool追加。
- Basic/Semantic状態を単一化。
- MCP変更。
- WebSocket/SSE追加。
- Network Source Import/Refresh UI/API追加。
- Work Detailへ単一EpisodeのCurrent Pointerを混入。
- Local File ImportをJob化。
- 01/15以外のParser/Model Client方式を独自追加。
- Inference Review Registry外Field Path追加。
- Generic ReviewItem confirm/reject Endpoint追加。
- ReviewItem CreateをInference Review Createとして実装。
- ReviewItem resolveにInference/Override/Structure変更を暗黙連動。
- Count Metric Ruleを整数入力だけに制限。
- `build_profile` Job追加。
- Profile作成をWorkerへ回す。
- Authoring Character/World/Canonへ自動Write。
- Structure Selector変更だけでCurrent Pointer変更。
- Current Manual/Semanticを通常Fullで置換。
- Current Automatic FullでBoundary常時Skip。
- metrics presetをPublic UIへ露出。
- Manual CorrectionをReviewQueue必須化。
- Profile生成でAggregateを暗黙Latest選択。
- Stale Aggregateを安全上の理由だけで選択禁止。
- Enabled片側Rangeを追加。
- Profile Import/Export追加。
