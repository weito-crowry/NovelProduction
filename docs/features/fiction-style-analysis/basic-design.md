# 小説文体分析・執筆支援パイプライン 基本設計書

**v0.3 Draft / 2026-09-01**

> 本書は上位の基本設計である。具体的なDB列、API、閾値、分類、Metric、テスト条件は `detailed-design/` を正本とする。

## 1. 目的

既存小説をReference Corpusとして収集・解析し、文章の構造・意味・文体指標を作品、Scene、人物単位で比較可能にする。自作品はStyleProfileと比較し、数値差・Coverage・根拠箇所をFindingとして提示する。

## 2. 設計原則

1. 元Resourceは不変SourceSnapshotとして保持する。
2. Raw / Canonical / Structure / Semantic / Measurement / Aggregate / Profileを分離する。
3. TextRevision / StructureRevision / AnalysisRun / Spanまで追跡可能にする。
4. 決定論的処理とModel推論を分離する。
5. Entity/Term等のStable IdentityとRunごとの推論を分離する。
6. 人手修正はInference Rowを書き換えずOverlayとして保持する。
7. AnalyzerはVersion、Dependency、Human Stateを含めてCurrent/Staleを判定する。
8. Unknown/Low-confidenceを正常状態として扱い、不要なReviewや停止条件を増やさない。
9. Reference Work全体はEpisode順に解析し、Work単位Registryを漸進的に構築する。
10. JobはProject-local DBへ永続化し、API Process全体の単一Workerで順番に処理する。

## 3. 全体フロー

```text
Source Adapter
 -> SourceSnapshot
 -> TextRevision / TextMapping
 -> Automatic StructureRevision
 -> Semantic StructureRevision optional
 -> Entity / Term / Speaker / Scene / POV Analysis
 -> Basic / Semantic Measurement
 -> Aggregate / Corpus
 -> StyleProfile / StyleProfileVersion / StyleRule
 -> Project Draft Lint
```

## 4. Collection / Text

- Network処理はAPI層、Domain/DBはCORE。
- SourceSnapshotは元Resource Bytesを保持する。
- ReferenceWork/ReferenceEpisodeはCurrent Catalog Projectionとして更新可能。
- ReferenceEpisodeはCurrent TextRevisionを明示的に指す。
- RawとCanonical Textを分離する。
- Canonical OffsetはUnicode Code Pointの半開区間 `[start_cp,end_cp)`。
- TextRevisionはImmutable。

## 5. Structure

StructureRevisionは:

```text
automatic | semantic | manual
```

Automaticは決定論的Base。Semantic Scene Boundaryは任意文字位置ではなくBlock境界候補を返し、StructureServiceが新RevisionへMaterializeする。Manual Split/Mergeも新Revisionとして保存し、既存Revisionを更新しない。

Block OrderはStructureRevision全体でGlobal 1..N。Block TypeとSemantic分類は分離する。

## 6. Entity / Term

EntityとTermはStable Identity。

Reference作品ではWork Scope、Project DraftではDocument Scopeとする。

### Entity

Mention Extractorは既存Entity Registryに依存しない。Mention RowはEntity IDを直接持たず、Entity ResolverがResolution Annotationを作る。ResolverはCurrent Registryを読むためCacheしない。

誤抽出の訂正は:

```text
entity.enabled
entity.canonical_name
entity.entity_type
```

をEffective Overrideとして扱う。

### Term

Term Candidate Extractorは既存Term/Entity Registryに依存しない。CandidateはAnnotation、Identity/TermMentionはResolverが作る。Term ResolverもCacheしない。

Run付き推論値:

```text
term.novelty
term.exact_match_safe
term_explanation
```

訂正:

```text
term.enabled
term.canonical_label
term.term_type
```

初出順序を永続番号として保存せず、Current MentionをEpisode OrderとOffsetでSortして求める。

## 7. Semantic Analysis

Scene分類はMulti-axisで、判断不能 `unclear` と分類可能だがその他の `other` を分離する。

Scene/Block分類は本文構造を中心入力とし、Entity/Term Registryの変化で不要に再実行しない。POVは人物Resolutionへ依存する。

## 8. Analysis Runtime

AnalysisRunはDocument内の派生Analyzerだけを管理する。Normalization、Structure Materialization、Aggregate、Profile、Lintは別責務。

Analyzerは以下を宣言する。

```text
id / version
dependencies
cacheable
state_inputs
registry_input
model / prompt
```

AnalysisRunはDependency Link、Policy、State Fingerprint、Registry Input FingerprintをProvenanceとして保持する。

Current Runは単純なLatest成功Runではなく、Current Analyzer/Policy/State/Dependency等と整合するRunだけを採用する。

Entity Resolver / Term ResolverはIncremental Registryを更新するためCache不可。Registry Input Hashは履歴の再現性に使うが、Registryが後続Episodeで成長しただけで過去Episodeを自動再解析しない。

## 9. Human State / Review

ManualOverride Operation:

```text
set | clear | revert
```

`clear` はField定義上の明示Unknown/None、`revert` はManual指定を解除して下位Inferenceへ戻る操作として区別する。

Low-confidence結果をReviewQueueへ全件投入しない。Direct OverrideはReviewItemなしで利用可能にする。

## 10. Measurement

```text
style-metrics-basic
style-metrics-semantic
```

Basic MetricはStructureだけを入力にし、Speaker/Entity/Term/Semantic Annotationを参照しない。Semantic MetricはEffective Semantic Stateを入力にする。

MetricDefinitionは式、Unit、Version、Toleranceを持つ。Missing Inputを0として保存しない。

## 11. Reference Work一括解析

作品全体解析Jobは、Job開始時にCurrent Episode一覧とCurrent TextRevisionを固定し、Episode Order順にDocument解析する。

Status:

```text
succeeded | partial | failed | cancelled
```

成功済みEpisodeは一部失敗時も保持し、ProgressとSucceeded/Failed Episode一覧をJobへ保存する。再解析時はCache不可Resolverを各Episodeで再実行する。

## 12. Job Worker

Style Jobは各Project `story.db` に保存する。

- API Process全体でWorker Thread 1本。
- Workerは自身でProject DB ConnectionをOpen/Closeする。
- Project内FIFO。
- Job終了後、同ProjectをReady Queue末尾へ戻して他Projectも処理可能にする。
- JobはProgress / Result / Warning / Partial Statusを永続化する。
- 外部Queue基盤はv1では追加しない。

## 13. Corpus / Profile / Lint

AggregateはMeasurement Rowを観測単位に集約する。

ProfileはStable IdentityとImmutable Versionを分離する。

```text
StyleProfile
StyleProfileVersion
StyleRule
```

Active ProfileはActive Versionを明示する。新Version作成だけでActive Versionを切替えない。

LintはTextRevision、StructureRevision、Profile Versionを明示し、Missing MetricはCoverageとして返す。総合文章品質Scoreや自動本文修正はv1対象外。

## 14. Storage / API / UI

Migration:

```text
006_style_analysis_foundation.sql
007_style_analysis_semantics.sql
008_style_analysis_analytics.sql
```

既存001〜005は変更しない。

API Prefix:

```text
/projects/{project_id}/style-analysis
```

Text/Structure/Lint/Profile Versionは明示IDを使う。Semantics/MetricのResponseは採用AnalysisRun IDを返す。

WebUIはSources、Reference Work、Document Analysis、Corpus、Profile、Review/Override、Lintを提供する。Reference Work画面では作品全体解析Progress、Document画面ではRevision SelectorとDirect Correctionを扱う。

## 15. 品質保証

- Deterministic処理はFixture Unit Test。
- DB/Migration/WorkerはIntegration Test。
- Semantic AnalyzerはFake Model Contract Testと小規模Gold Dataset。
- Model品質はCI外で相対評価する。
- 同一の整合性検査を全Layerへ重複配置しない。

## 16. 実装分割

`detailed-design/README.md` のSA-A〜SA-Hを正本とする。

```text
SA-A Foundation / DB / Job / Runtime State
SA-B Source Import / Refresh / Purge
SA-C Normalization / Structure / Basic Metrics
SA-D Semantic Analysis / Work Analysis
SA-E Corpus / Aggregate / Profile
SA-F Review / Override / Recompute
SA-G Project Capture / Lint
SA-H WebUI / E2E / Dogfood
```

## 17. 完了条件

- Reference WorkをImport/Refresh/Purgeできる。
- Work全体をEpisode順に解析できる。
- Automatic/Semantic/Manual Structureを履歴付きで扱える。
- Entity/Term Stable RegistryとRun付きResolutionを扱える。
- AnalysisRun Dependency/State/Registry Provenanceを追跡できる。
- Basic/Semantic Metricを再現可能に計測できる。
- CorpusからVersion付きProfileを生成できる。
- Project DraftからCoverage付きFindingを生成できる。
- ManualOverrideがSet/Clear/Revert可能で再解析後も保持される。
- Job Progress/PartialがDBから復元できる。
