# 14 Testing and Evaluation 詳細設計

## 1. 目的

Style Analysisの決定論的処理、DB整合性、API/WebUI、Runtime/Job、LLM推論、Source Adapterを再現可能に検証する。CIはLive Site/Modelへ依存させず、Model品質はCI外Evaluation/Dogfoodとして扱う。

上位仕様は `../basic-design.md`。

## 2. テスト層

```text
unit
integration
API/WebUI contract
manual dogfood/evaluation
```

同一Invariantを全層へ重複配置しない。

- DB Integrity: Migration/Integration
- Analyzer: Schema/Output/Fingerprint/Dependency
- API: Contract/Revision/Job State
- WebUI: User Flow
- Model品質: CI外

## 3. 実装先

```text
CORE/tests/style_analysis/
  fixtures/
  gold/
  test_normalization.py
  test_segmentation.py
  test_entities.py
  test_terms.py
  test_semantics.py
  test_metrics.py
  test_runtime.py
  test_review.py
  test_profiles.py
  test_lint.py
  test_storage.py

API/tests/style_analysis/
  fixtures/
  test_source_adapters.py
  test_style_routes.py
  test_style_jobs.py
  test_model_client.py

WEBUI/frontend/src/features/styleAnalysis/
  *.test.tsx

WEBUI/frontend/e2e/
  style-analysis.spec.ts
```

既存Naming Conventionが異なる場合は既存へ合わせる。

## 4. Deterministic Unit Gate

### Normalization

- Input/Output
- Hash
- Mapping
- Unicode Code Point Span

### Structure

- Scene/Block/Sentence Order/Span
- Block Global Order
- Separator `scene_id=NULL`
- Automatic Fingerprint
- Boundary Candidate Contract
- Semantic Structure Materialization
- Semantic Structure Source AnalysisRun Link

### Metrics

- Metric Name/Version
- Scalar/Percentile/Sample Count
- Basic/Semantic Group分離
- Basic MetricがSpeaker/Term/Semantic Annotation非依存
- 40 chars Bridge Rule
- Speaker Streak
- Term Effective State

Floatは `pytest.approx(..., abs=1e-9)`。

## 5. Fixture方針

巨大Snapshot Frameworkは導入しない。短い自作日本語Fixtureを使い必要FieldだけAssertする。

Source Adapter HTML FixtureはDOM構造だけ残し、本文は自作文へ置換する。外部作品本文を長くRepositoryへ保存しない。

## 6. Source Adapter Test

`httpx.MockTransport` 等でNetworkをMockする。

必須:

```text
Narou index/episode success
Narou parse failure
Kakuyomu success/restricted
redirect allowed/disallowed host
429 retry success/failure
response size limit
multi-episode fetch途中失敗 -> catalog未更新
EPUB binary snapshot hash
Adapter sync API
Refresh reorder
Refresh削除Episode -> Document削除 + Snapshot保持
Reference Work purge -> 専用Source/Snapshot削除
```

Selector変更はAdapter Version変更対象。

## 7. DB / Migration Gate

CORE CIで:

- Fresh 001→008
- Existing 005→006→008
- Migration Checksum
- `PRAGMA foreign_key_check` empty
- `PRAGMA integrity_check` = ok
- JSON/Enum/CHECK
- Mapping片側Zero/両側Zero
- Block Global Order
- ReferenceEpisode Current Text Pointer Service Validation
- Job Type/Status/Progress/Partial Persistence
- Entity/Term Exactly-one Scope
- Mention RowにEntity IDなし
- Term IdentityにNovelty/ExactMatchSafeなし
- AnalysisRun State/Registry Fingerprint
- AnalysisRun Dependency Link
- Semantic Structure Source Run Link
- ManualOverride Set/Clear/Revert
- Profile Identity/Version/Active Version
- Immutable Snapshot/TextRevision/ProfileVersion UPDATE拒否
- Reference Work Purge Transaction
- Project Episode Cascade

各Integration Scenario末尾へ同じIntegrity Checkを重複追加しない。

## 8. Analyzer Mocked Test

Fake `SemanticModelClient` で固定JSONを返す。

検証:

- Required Context
- Response Schema/Version
- Invalid JSON/Schema/Offset
- Timeout/429/Repair
- Partial Subject
- AnalysisPolicy
- Dependency Link
- State Fingerprint
- Registry Input Fingerprint
- Current Run Resolver

Prompt全文完全一致Testは作らない。

## 9. Entity / Term Regression

### Entity

- Mention ExtractorがEntity Registry非依存
- Mention RowはEntity IDなし
- Entity Resolver AnnotationでMapping
- Resolver Cache不可
- Work Episode跨ぎResolution
- 同名候補複数で強制選択なし
- Disabled Entity除外
- Inferred AliasだけではAuto Mergeなし
- Confirmed/Manual Alias Resolution
- Speaker Explicit Tag / Ambiguous Unknown

### Term

- Candidate ExtractorがTerm/Entity Registry非依存
- Candidate ExtractorはIdentity/TermMentionを作らない
- Resolver Cache不可
- Work Episode跨ぎTerm統合
- Disabled Term除外
- Novelty/Exact Match Run Annotation
- Occurrence Index非依存
- Explanation/Delay

## 10. Scene / Semantic Regression

- Daily/Exposition/Meeting/Introspection/Action/Conflict
- `other` / `unclear` 区別
- Scene ClassifierがEntity/Term/Speaker非依存
- Block ClassifierがEntity/Term非依存
- POVはEntity Resolver依存
- Boundary Block Membership
- Auto Apply / Proposal / Low Candidate Drop
- Scene OverrideでClassifier Raw RunはStaleにならずSemantic Metricだけ更新

## 11. Gold Dataset / Model Evaluation

`CORE/tests/style_analysis/gold/` に自作短文を置く。固定件数ノルマや小規模Datasetに対する固定Precision/F1 Release Gateは設けない。

最低カテゴリ:

```text
speaker: explicit / adjacent action / 2-person / 3-person ambiguous / unknown
scene: daily / exposition / meeting / introspection / action / conflict / unclear
term: work-specific / common / alias / explanation before-after / no explanation
```

CI外Script:

```text
API/scripts/evaluate_style_analysis.py
```

記録:

```text
provider/model
prompt/analyzer/policy version
dataset hash
precision/recall/F1 where applicable
unknown rate
schema failure rate
latency summary
```

結果はGitignored領域。

## 12. Runtime Integration

Temp SQLite + Fake Modelで:

```text
Reference Import
-> Current TextRevision Pointer
-> Automatic Structure
-> Boundary Run
-> Semantic Structure
-> Entity Mention/Resolver/Speaker/POV
-> Term Candidate/Resolver/Explanation
-> Scene/Block Semantic
-> Basic/Semantic Metric
-> Corpus Aggregate
-> Profile Version + Activate
-> Project Draft Capture
-> Lint explicit Version
```

追加:

- Cacheable Analyzer Cache Hit
- Entity/Term Resolverは再実行
- Policy Version変更
- Dependency Run変更 -> Dependent Stale
- State Fingerprint変更 -> 対応Analyzer Stale
- Registry成長だけでは過去Resolver Current判定を全Stale化しない
- Manual Structure -> Boundary Skip
- Override -> 必要Metric/Reanalysis
- Partial Analyzer

## 13. Reference Work Analysis Job

必須:

- Episode `order_index` 順
- Job開始時Current Episode/TextRevision Snapshot固定
- Resolverは各Episodeで再実行
- Succeeded/Failed Episodeを `result_json` へ保存
- 全成功 `succeeded`
- 一部成功 `partial`
- 成功0 `failed`
- Cancel `cancelled`
- `progress_current/progress_total`
- Work再解析でResolver再実行
- 後続Episode Registry成長で前Episodeを自動再解析しない

## 14. StyleJobWorker Integration

- API Process全体でWorker Thread 1本
- ProjectごとにThreadを増やさない
- Request-bound SQLite ConnectionをWorkerで再利用しない
- `notify(project_id)` でQueued Job回収
- 同Project FIFO
- Job完了後同Projectを末尾再Queue
- 複数Projectを順番に処理
- StartupでActive ProjectをRegistry列挙
- Running Job/Run -> `WORKER_INTERRUPTED` Failed
- Queued Job回収
- 1 Project DB FailureでもWorker継続
- Archived Project Startup Skip
- Source Refresh Job
- Retryは新Job Row
- Job Progress Persist
- Polling再取得でProgress復元
- Cancel Queued/Running

Global FIFOや中央Queue DBはTest要件にしない。

## 15. Review / Override

- Manual > Confirmed > Inferred
- Rejected非Effective
- Direct Override without ReviewItem
- Set/Clear/Revert差
- Speaker Clear = Explicit Unknown
- Revert = InferenceへFallback
- Non-null Field Clear拒否
- Entity/Term Enabled/Name/Type Correction
- Alias Confirm/Reject
- Stale Structure Override
- Explanation Annotation Lineage
- Low ConfidenceだけではReviewItem生成なし
- Note Optional

## 16. Profile / Lint

- Corpus Equal-weight Measurement Aggregate
- Sample不足時Auto Ruleなし / Manual Rule可
- Profile Identity/Version分離
- Active Version同Profile所属
- New Version作成でActive Version不変
- ExportはVersion明示/本文なし
- Rule Range/Zero-width Tolerance
- Missing MetricはCoverageへ反映しLint Failにしない
- Coverage 0でもSucceeded
- Stale Lint

## 17. API Contract

- Project A/B Isolation
- Import/Refresh/Work Analyze/Document Analyze 202
- Job `queued/running/succeeded/partial/failed/cancelled`
- Job Progress/Result/Warning
- Retry Creates New Job
- Text取得 explicit TextRevision
- Structure取得 explicit StructureRevision
- Semantics/Metric Response Selected Run ID
- Historical Run Output/Measurement
- Analyze TextRevision required / Structure optional
- Work Analyze deterministic/full
- Profile Version/Activation
- Direct Override Set/Clear/Revert
- ReviewItem CAS
- Lint explicit Profile Version
- Purge

API Key非露出はModel Config Test 1箇所で確認し各Routeへ重複しない。

## 18. WebUI

Testing Library既存Pattern。

必須Flow:

```text
Source Import
Refresh/Purge
Job progress/retry
Reference Work Analyze progress/partial
TextRevision selector
StructureRevision selector
Document deterministic/full analysis
Boundary/manual split
Entity/Term direct correction
Corpus membership
Profile Save vs Save+Activate
Review conflict
Lint coverage/stale
Finding ignore
```

Pollingは `partial` を含む終了Statusで停止する。

## 19. E2E

External Site/ModelはMock/Fake Server。

代表Flow:

```text
Project open
-> Local Text import
-> Deterministic Analysis
-> Corpus create
-> Profile build/activate
-> Project Draft capture
-> Lint
-> Finding display
```

Semantic FlowはFake Providerで別1本。全細部をE2Eへ重複させない。

## 20. Live Dogfood

CI外・明示実行。

Source:

- Narou/Kakuyomuのユーザー指定作品を少数Episodeから確認
- Title/Order/本文抽出を目視
- 問題なければWork全体解析へ拡張

Model:

- Configured Provider/Model確認
- Representative Episode/WorkでFull Analysis
- Boundary/Speaker/Term/Semanticsを目視
- 明確な誤りはRegression Fixtureへ追加

毎回のrights checkbox等は不要。Login/有料壁回避はしない。

## 21. CI Commands

既存CIを正本とする。

CORE/API:

```text
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -W error
uv run pytest -W error --cov=src/... --cov-report=term-missing
```

WEBUI:

```text
npm run lint
npm run typecheck
npm test -- --run
npm run build
npm run test:e2e
```

MCPは変更しないが既存RegressionとしてPASS。Pre-commitもPASS。

## 22. Coverage / Completion

既存80% Gate維持。Coverageのためだけの低価値Testを大量追加しない。

各SA Phase:

1. 対応詳細設計の必須要件
2. 必要なUnit/Integration
3. Static Checks
4. Migration変更PhaseはMigration Gate
5. Existing CI
6. 未実施検証は理由を報告
7. Commit/Push
8. ChatGPT Review

無関係なDogfood/全品質評価を毎Phase要求しない。

## 23. Codex禁止事項

- CIから実Site/有料LLMへ接続
- 外部作品本文をFixture/Goldへ長くコピー
- Flaky Test Skipで完了扱い
- Coverage Threshold低下
- 小規模Goldへ根拠のない精度Gate
- 全Integration Caseへ同じIntegrity/Safety Assertion重複
- Resolver Cache不可/State Dependency Test省略
- Job Partial/Progress Test省略
- Revision/Version Contract Test省略
- Unrelated Test Refactor拡大
