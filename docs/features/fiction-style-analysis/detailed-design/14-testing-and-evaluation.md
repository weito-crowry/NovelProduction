# 14 Testing and Evaluation 詳細設計

## 1. 目的

Style Analysisの決定論的処理、DB整合性、Runtime/Job、API/WebUI、Semantic Model、Source Adapterを再現可能に検証する。CIはLive Site/Modelへ依存させない。

上位仕様は `../basic-design.md`。

## 2. テスト層

```text
unit
integration
API/WebUI contract
manual dogfood/evaluation
```

同一Invariantを全層へ重複配置しない。

## 3. 実装先

```text
CORE/tests/style_analysis/
API/tests/style_analysis/
WEBUI/frontend/src/features/styleAnalysis/*.test.tsx
WEBUI/frontend/e2e/style-analysis.spec.ts
```

短い自作日本語Fixtureを使う。外部作品本文を長くRepositoryへ保存しない。

## 4. Normalization / Structure Unit

Normalization:

- Input/Output/Hash/Mapping
- Unicode Code Point Span

Structure:

- Scene/Block/Sentence Order/Span
- Block Global Order
- Separator scene_id NULL
- Automatic/Semantic/Manual Revision
- Boundary Candidate/Source Run
- `current_structure_revision_id` Pointer規則

Current Pointer Cases:

- New Current Text -> Structure Pointer NULL
- Omitted Deterministic Analyze -> Automatic Current
- Omitted Full Analyze -> Final Automatic/Semantic Current
- Explicit Structure Analyze -> Pointer不変
- Manual Split/Merge -> New Manual Current
- Select Current -> Pointerのみ更新
- Current Textと異なるStructure Select拒否

## 5. Metrics Unit

- Metric Name/Version/Value/Sample Count
- Percentile
- Basic/Semantic Group分離
- Basic MetricはSemantic/Speaker/Term Annotation非依存
- Dialogue Bridge Rule 40/41 chars
- Speaker Streak
- Disabled Term除外

## 6. Source Adapter / Import Integration

Mock Network。

- Narou/Kakuyomu Success/Parse Failure/Restricted
- Redirect Host/429/Size
- EPUB Binary Hash
- Sync Adapter API
- Initial Import: Job + Import受付Row
- Import RowはStatus/Errorを重複保持しない
- Fetch FailureでCatalog未更新
- New Textで `document.current_text_revision_id` 更新 + Structure Clear
- Same Text ReuseでPointer不変
- Refresh Reorder
- Removed Episode Cascade + Snapshot保持
- Purge専用Source/Snapshot削除

## 7. Storage / Migration Gate

- Fresh001→008
- Existing005→008
- Migration Checksum
- Foreign Key/Integrity Check
- Job Table before Import FK
- Current Text/Structure Logical FK Service Validation
- Mention Candidate Fields保存
- MentionにEntity ID Columnなし
- Entity/Term Exactly-one Scope
- Term IdentityにNovelty/ExactMatch Columnなし
- Term Attribute Partial Unique
- AnalysisRun State/Registry/Dependency Link
- ManualOverride Set/Clear/Revert
- Corpus Membership Validation
- Aggregate Count Columns
- Profile Active Version
- Immutable Row Update拒否

## 8. Entity Regression

- Mention Extractor Registry非依存
- Mention candidate `entity_type_candidate/canonical_name_candidate` Persist
- ResolverがCandidate Fieldsを読む
- Resolver Cache不可 + Registry Fingerprint
- Work Episode跨ぎResolution
- 同名候補複数で強制選択なし
- Manual Entity作成、Same-name許容
- Manual Alias Idempotent
- Manual Entity/Aliasでentity_registry State変更
- Disabled Entity除外
- Inferred AliasだけではMergeなし
- Confirmed/Manual Alias Resolution
- Speaker Explicit/Ambiguous Unknown

## 9. Term Regression

- Candidate Extractor Term/Entity Registry非依存
- Candidate Annotationのみ、Identityを作らない
- Resolver Cache不可 + Registry Fingerprint
- Work Episode跨ぎResolution
- Manual Term作成、Same-label許容
- Manual Alias Idempotent
- Disabled Term除外
- Novelty Reduction: Agreement/Conflict/All Uncertain
- Exact Match Reduction: All True/One False
- Same Run/Term Attribute重複Insert拒否
- First AppearanceはDocument Current Text/Structure/Current Resolver Runのみ
- Explanation/Delay

## 10. Scene / Semantic Regression

- Taxonomy Other/Unclear
- Scene/Block ClassifierはEntity/Term/Speaker Registry非依存
- POVはEntity Resolver依存
- Boundary Membership/Threshold
- Scene OverrideでRaw ClassifierはCurrentのまま、Semantic Metricだけ再計算

## 11. Runtime Integration

Fake Model + Temp SQLite。

- DAG/Cycle
- Analyzer Cacheable Flag
- Dependency Link
- Current Run Analyzer/Policy/State/Dependency mismatch
- Resolver Cache不可
- Registry成長だけで過去Resolverを全Stale化しない
- Omitted Analyze Current Structure更新
- Explicit Structure Pointer不変
- Analyze中にCurrent Text変更 -> Pointer不変 + Warning
- Work Job開始時Document Current Text Snapshot
- Work途中Refreshを同Jobへ追加しない
- Work Episode Order
- Work Result succeeded/partial/failed lists

## 12. StyleJobWorker Integration

- Worker Thread 1本
- Request DB Connection非再利用
- Notify
- Project内FIFO
- Project公平Requeue
- Startup Active Scan
- Running -> WORKER_INTERRUPTED Failed
- Queued Recovery
- 1 Project Failureでも継続
- Archived Skip
- Source Refresh
- Work Analyze
- Progress Persist/Reload
- Partial終了
- Retryは新Job
- Cancel Queued/Running

## 13. Corpus / Aggregate

Membership:

- include_all=true + exclude
- include_all=false + include
- Work MembershipなしEpisode Override拒否
- Work Membership削除でOverride削除
- Refresh Episode削除でOverride Cascade

Aggregate:

- Measurement Row等重み
- Work等重みではない
- `source_measurement_count = input Measurement数`
- `sample_count = input sample_count合計`
- `work_count = distinct Work`
- `skipped_target_count`
- Document Current Text/Structure/Runのみ使用
- Missing Current StructureはSkip
- Stale RunへFallbackなし
- Fingerprint Membership/Input Measurement IDs

## 14. Profile / Lint

- Sample不足Auto Ruleなし、Manual Rule可
- Profile Identity/Version
- Active Version同Profile所属
- New VersionでActive不変
- Rule Range/Tolerance
- Missing MetricはCoverage、Lint Failにしない
- Coverage 0 Succeeded
- Stale Lint

## 15. API Contract

- Project A/B Isolation
- Import/Refresh/Work Analyze/Document Analyze 202
- Job Status/Progress/Partial/Result
- Retry New Job
- Document Detail Current Text/Structure
- Text/Structure explicit IDs
- Select Current API
- Historical SelectorだけではPointer変更なし
- Semantics/Metric Selected Run ID
- Manual Entity/Term Create Scope Validation
- Manual Alias Idempotent
- Authoring Tables非更新
- Direct Override Set/Clear/Revert
- Corpus Membership Request/Count Response
- Profile Activation
- Lint explicit Version
- Purge

## 16. WebUI

- Import/Refresh/Purge
- Work Analyze Progress/Partial
- Text/Structure Selector
- Current Structure Badge + Select Current
- Selector変更だけではPointer変更なし
- Manual Entity/Term/Alias
- Direct Correction
- Corpus Include/Exclude
- Count表示
- Profile Save vs Save+Activate
- Review Conflict
- Lint Coverage/Stale

Pollingは `succeeded|partial|failed|cancelled` で停止する。

## 17. Gold / Model Evaluation

自作短文の小さなGold Set。固定件数ノルマや根拠の薄い固定Precision/F1 Release Gateは置かない。

CI外EvaluationはProvider/Model/Prompt/Policy/Dataset Hash、Precision/Recall/F1 where meaningful、Unknown Rate、Schema Failure、Latencyを記録する。

## 18. E2E / Dogfood

E2EはExternal Site/ModelをMock/Fakeにする。代表Flowだけを通し、Unit/Integrationの細部を重複しない。

Live DogfoodはCI外。ユーザー指定作品を少数Episodeから確認し、問題なければWork Analyzeへ拡張する。毎回の権利確認UIは不要。Access Restriction回避はしない。

## 19. CI / Completion

既存Ruff/Format/Mypy/Pytest/Coverage、WEBUI lint/typecheck/test/build/e2e、Pre-commitを正本とする。MCPは変更しないがRegressionとして既存CIを通す。

既存Coverage Gateを下げない。ただしCoverageだけの低価値Testを大量追加しない。

各SA Phaseは対応ScopeのTest/Static Checkだけを必須とし、無関係Dogfoodを毎回要求しない。

## 20. Codex禁止事項

- Live Site/有料ModelをCIからCall
- Flaky Test Skipで完了扱い
- Coverage Threshold低下
- 全Layerへ同じIntegrity Assertion重複
- Current Pointer Contract Test省略
- Mention Candidate Field Test省略
- Manual Identity Test省略
- Corpus Count/Membership Test省略
- Resolver Cache不可Test省略
- Unrelated Test Refactor拡大
