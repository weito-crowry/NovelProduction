# 小説文体分析・執筆支援パイプライン 基本設計書

**v0.4 Draft / 2026-09-01**

> 本書は上位の基本設計である。具体的なDB列、API、分類、Metric、Runtime、テスト条件は `detailed-design/` を正本とする。

## 1. 目的

既存小説をReference Corpusとして収集・解析し、文章の構造・意味・文体指標を作品、Scene、人物単位で比較可能にする。自作品はStyleProfileと比較し、数値差・Coverage・根拠箇所をFindingとして提示する。

## 2. 設計原則

1. 元ResourceはImmutable SourceSnapshotとして保持する。
2. Raw / Canonical / Structure / Semantic / Measurement / Aggregate / Profileを分離する。
3. TextRevision / StructureRevision / AnalysisRun / Spanへ追跡可能にする。
4. 決定論的処理とModel推論を分離する。
5. Entity/TermのStable IdentityとRunごとの推論を分離する。
6. 人手修正はInference Rowを書き換えずOverlayとして保持する。
7. AnalyzerはVersion/Dependency/Human State込みでCurrent/Staleを判定する。
8. Unknown/Low-confidenceを正常状態として扱い、不要なReview/停止条件を増やさない。
9. Reference WorkはEpisode順に解析しWork単位Registryを漸進的に構築する。
10. JobはProject-local DBへPersistし、API Process全体の単一Workerで処理する。
11. Current Text/Current StructureはStyleDocumentの明示Pointerで管理し、Latest Queryで推測しない。

## 3. 全体フロー

```text
Source Adapter
 -> SourceSnapshot
 -> StyleDocument / Current TextRevision
 -> Automatic StructureRevision
 -> Semantic StructureRevision optional
 -> Current StructureRevision
 -> Entity / Term / Speaker / Scene / POV Analysis
 -> Basic / Semantic Measurement
 -> Aggregate / Corpus
 -> StyleProfile / StyleProfileVersion / StyleRule
 -> Project Draft Lint
```

## 4. Collection / Document Revision

- NetworkはAPI層、Domain/DBはCORE。
- SourceSnapshotは元Resource BytesをBLOB保持する。
- ReferenceWork/ReferenceEpisodeはCurrent Catalog Projection。
- Current解析本文は `style_documents.current_text_revision_id` に統一する。
- ReferenceEpisodeへ別Current Text Pointerを持たない。
- Current Textが変わると `current_structure_revision_id` をNULLへClearする。
- TextRevisionはImmutable、OffsetはUnicode Code Point `[start_cp,end_cp)`。
- Initial ImportとRefreshは別Job。Import状態はJobを正本とする。

## 5. Structure

Structure Kind:

```text
automatic | semantic | manual
```

Automaticは決定論的Base。Semantic Boundaryは任意文字位置ではなくBlock境界候補を返し、新RevisionへMaterializeする。Manual Split/Mergeも新Revision。

`style_documents.current_structure_revision_id` が通常のCorpus/Current解析で採用するStructureを示す。

- Structure未指定Analyze成功/Partial: Final StructureをCurrentに設定。
- Explicit Structure Analyze: Current Pointerを変えない。
- Manual Split/Merge: 新ManualをCurrentに設定。
- Historical閲覧用Selector変更だけではCurrentを変えない。

## 6. Entity

EntityはReference WorkまたはProject Document ScopeのStable Identity。

Mention ExtractorはEntity Registry非依存。Mention RowはEntity IDを持たず、`entity_type_candidate` / `canonical_name_candidate` を保持する。

Entity ResolverだけがRegistryを読み、Resolution Annotationを作る。ResolverはCache不可。

Model見落とし時はManual Entity/Manual AliasをStyle Analysis内に直接作成可能。

Correction:

```text
entity.enabled
entity.canonical_name
entity.entity_type
mention.entity_id
block.speaker_entity_id
```

Authoring Characterへ自動Writeしない。

## 7. Term

Term Candidate ExtractorはTerm/Entity Registry非依存でCandidate Annotationだけを作る。Term ResolverはCache不可でIdentity/TermMentionを作る。

Manual Term/Manual Aliasを直接作成可能。

Run付き推論:

```text
term.novelty
term.exact_match_safe
term_explanation
```

同Resolver Runの同TermについてNovelty/Exact Matchは各最大1件にReductionする。

Occurrence Indexは保存せず、Current Document Text/Structure/Resolver RunのMentionをEpisode Order + OffsetでSortして初出を求める。

## 8. Semantic / Runtime

Scene/Block分類は本文構造を中心入力とし、Entity/Term Registry変更で無関係にStale化しない。POVはEntity Resolverへ依存する。

AnalysisRunはDocument派生Analyzerのみ。Dependency Link、AnalysisPolicy、Human State Fingerprint、Registry Input Fingerprint、Model/PromptをProvenanceとして保持する。

Current Runは単純Latest成功ではなくCurrent定義/State/Dependencyと一致するものだけ。Entity/Term ResolverはCache不可だがRegistry成長だけで過去Episodeを自動全再解析しない。

## 9. Human State / Review

ManualOverride:

```text
set | clear | revert
```

- clear: Field定義上のExplicit Unknown/None
- revert: Manual指定解除、Inferenceへ戻る

Direct OverrideにReviewItemは不要。Low-confidenceだけでReviewQueueを自動大量生成しない。

## 10. Measurement

```text
style-metrics-basic
style-metrics-semantic
```

BasicはStructureだけを入力にしSemantic/Speaker/Term Annotationを読まない。SemanticはEffective Semantic Stateを読む。

MetricDefinitionは式/Unit/Version/Toleranceを持つ。Missing Inputを0として保存しない。

## 11. Reference Work一括解析 / Job

`analyze_reference_work` はJob開始時にEpisode Catalog + 各StyleDocument Current TextをSnapshotしEpisode Order順に処理する。

成功済みEpisodeは一部失敗時も保持。Job Status `succeeded|partial|failed|cancelled`、Progress/ResultをDB保存する。

途中RefreshでCurrent Textが変わったEpisodeを古い結果でCurrent更新しない。

WorkerはAPI Process全体で同期Thread 1本。Project内FIFO、Project間はReady Queueで順番に処理する。Request-bound SQLite ConnectionをWorkerへ渡さない。

## 12. Corpus / Aggregate

Corpus MembershipはWork Membership + Episode Override。

- include_all=true: Default Included、exclude Override。
- include_all=false: Default Excluded、include Override。

AggregateはMeasurement Rowを等重みでPoolする。Work等重みではない。

Countを分離:

```text
source_measurement_count = 入力Measurement Row数
sample_count = 入力Measurement.sample_count合計
work_count = Distinct Work数
skipped_target_count = Current入力不足でSkipしたTarget数
```

Current Document Text/Structure/Runだけを使い、Latest/古いRunへFallbackしない。

## 13. Profile / Lint

Profile IdentityとImmutable Versionを分離し、Active Versionを明示する。New Version作成だけでActive切替しない。

LintはTextRevision/StructureRevision/Profile Version明示。Missing MetricはCoverageとして扱い、割合だけでFailさせない。総合品質Score/自動本文修正はv1対象外。

## 14. Storage / API / UI

Migration:

```text
006_style_analysis_foundation.sql
007_style_analysis_semantics.sql
008_style_analysis_analytics.sql
```

既存001〜005変更なし。

API Prefix:

```text
/projects/{project_id}/style-analysis
```

WebUIはSources/Reference Work、Document Analysis、Corpus/Profile、Review/Override、Lintを提供する。

Document UIではHistorical Structure選択と `Currentに設定` を別操作にする。Manual Entity/Term/Alias作成をSemantics画面から行える。

## 15. Quality Assurance / 実装分割

- Deterministic処理: Unit Test
- DB/Migration/Worker: Integration
- Semantic: Fake Model Contract + 小規模Gold
- CIからLive Site/Modelへ接続しない
- 同じ整合性検査を全Layerへ重複しない

実装順:

```text
SA-A Foundation / DB / Job / Runtime State
SA-B Source Import / Refresh / Purge
SA-C Normalization / Structure / Basic Metrics
SA-D Semantic / Work Analysis
SA-E Corpus / Aggregate / Profile
SA-F Review / Override / Recompute
SA-G Project Capture / Lint
SA-H WebUI / E2E / Dogfood
```

## 16. 完了条件

- Import/Refresh/Purge。
- Document Current Text/Structureを明示管理。
- Work全体Episode順解析。
- Entity/Term Stable Registry + Manual Identity + Run Resolution。
- AnalysisRun Dependency/State/Registry Provenance。
- Basic/Semantic Metric。
- Corpus Membership/Aggregate Count。
- Version付きProfile。
- Coverage付きLint。
- ManualOverride Set/Clear/Revert。
- Job Progress/Partialの再起動後復元。
