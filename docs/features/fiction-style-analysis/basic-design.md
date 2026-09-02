# 小説文体分析・執筆支援パイプライン 基本設計書

**v1.0 Implementation Ready / 2026-09-01**

本書は上位の基本設計である。具体的なDB列、API、分類、Metric、Runtime、テスト条件は `detailed-design/` を正本とする。

## 1. 目的

ユーザーが手元に用意した小説本文をReference Corpusとして取り込み、文章の構造・意味・文体指標を作品、Scene、人物単位で比較可能にする。

自作品はVersion付きStyleProfileと比較し、数値差・Coverage・根拠箇所をFindingとして提示する。

目的は「良い文章」を単一Scoreで決めることではなく、Reference作品の構造的特徴を再現可能なMetric/Profileへ変換し、自作品との差を観測可能にすることである。

## 2. v1 Scope

### 対象

- Local TXT Import。
- Local HTML File Import。
- Local EPUB Import。
- Raw/Canonical Text Revision。
- Automatic/Semantic/Manual Structure Revision。
- Entity/Mention/Speaker。
- Term/TermMention/初出/同Scene説明。
- Scene Multi-axis Semantic / POV / Block Primary Semantic。
- Basic/Semantic Style Metric。
- Reference Work一括解析。
- Corpus/Aggregate。
- Version付きStyleProfile/StyleRule。
- ManualOverride/Inference Review。
- Project Draft Capture。
- Style Lint。
- WebUI。

### v1対象外

- Narou/Kakuyomu等のサイト固有Network Downloader。
- Generic Crawler/Remote URL Import。
- Source Refresh。
- Profile Import/Export。
- Entity Relation専用解析。
- Term↔Entity Link。
- Scene×Character Metric。
- 総合品質Score。
- 生成的な自動本文修正。
- MCP Tool追加。

Site Adapterは取得方式を別途検討し、将来Phaseで追加する。

## v1.1 SA-I extension

External Agent MCP / ChatGPT Analysis は v1.0 の Internal Model Execution を
保持したまま追加する。ChatGPT が MCP 経由で Persistent Task を取得し、構造化
JSON を submit する。NovelProduction から ChatGPT/OpenAI API への request、
callback、webhook は存在しない。Session/Task、resumable engine、transaction、
runtime contract、API 5 endpoint、MCP 6 tools の正本は
`detailed-design/16-external-agent-mcp.md` である。

## 3. 設計原則

1. 元ResourceはImmutable SourceSnapshotとして保持する。
2. Raw / Canonical / Structure / Semantic / Measurement / Aggregate / Profileを分離する。
3. TextRevision / StructureRevision / AnalysisRun / Spanへ追跡可能にする。
4. 決定論的処理とModel推論を分離する。
5. Entity/TermのStable IdentityとRunごとの推論を分離する。
6. 人手修正はInference Rowを書き換えずAppend-only Overlayとして保持する。
7. AnalyzerはVersion/Dependency/Relevant Policy/Human State込みでCurrent/Staleを判定する。
8. Unknown/Low-confidenceを正常状態として扱い、不要なReview/停止条件を増やさない。
9. Reference WorkはEpisode順に解析しWork単位Registryを漸進的に構築する。
10. JobはProject-local DBへPersistし、API Process全体の単一Workerで処理する。
11. Current Text/Current StructureはStyleDocumentの明示Pointerで管理し、Latest Queryで推測しない。
12. Site固有取得条件を分析Domainへ混ぜない。
13. 実装判断をCodexへ残さず、詳細設計を承認済み仕様として扱う。

## 4. 全体フロー

```text
Local TXT / HTML / EPUB
 -> SourceSnapshot
 -> Reference Work / Episode
 -> StyleDocument
 -> Current TextRevision
 -> Automatic StructureRevision
 -> optional Semantic StructureRevision
 -> Current StructureRevision
 -> Entity / Term / Speaker / Scene / POV / Block Analysis
 -> Basic / Semantic Measurement
 -> Corpus / Aggregate
 -> StyleProfile / StyleProfileVersion / StyleRule

Project Draft
 -> explicit Draft Capture
 -> StyleDocument / TextRevision
 -> Analysis
 -> StyleProfile Lint
 -> Finding / Evidence / Coverage
```

## 5. Source / Text Revision

- v1 Source ImportはLocal File同期処理。
- Source Identityは`source_type + upload bytes SHA-256`。
- 1 Source = 1 Reference Work。
- SourceSnapshotは元Upload BytesをBLOB保持する。
- ReferenceWork/ReferenceEpisodeはCurrent Catalog Projection。
- Current解析本文は`style_documents.current_text_revision_id`に統一する。
- ReferenceEpisodeへ別Current Text Pointerを持たない。
- TextRevisionはImmutable。
- OffsetはUnicode Code Point `[start_cp,end_cp)`。
- TextRevision ReuseはRaw HashだけでなくNormalizer Version + Structure Hintを含む`normalization_input_fingerprint`を使う。
- Current Textが変わるとCurrent StructureをNULLへClearする。

## 6. Structure

Structure Kind:

```text
automatic
semantic
manual
```

Automaticは決定論的Base。

Semantic Boundaryは任意文字位置ではなくBlock境界候補だけを返し、新StructureRevisionへMaterializeする。

Manual Split/Mergeも新Revision。

`style_documents.current_structure_revision_id` が通常の表示、Current解析、Corpus集約で採用するStructure。

通常Analyze:

- Explicit Structure -> そのStructureを使用、Pointer不変。
- Current Manual -> deterministic/fullとも保持。
- Current Semantic -> deterministic/fullとも保持。
- Current Automatic + deterministic ->保持。
- Current Automatic + full ->Boundary解析しSemanticへ昇格可能。
- Currentなし -> AutomaticをBuild/Reuse。
- `rebuild_structure=true` ->明示的にAutomaticから再生成。

同fingerprint StructureRevisionはReuseする。

## 7. Entity / Speaker

EntityはReference WorkまたはProject Document ScopeのStable Identity。

Mention ExtractorはEntity Registry非依存。Mention RowはEntity IDを持たずCandidate Type/Canonical Nameを保持する。

Entity ResolverだけがRegistryを読みResolution Annotationを作る。ResolverはCache不可。

Reference Work Registryの自然成長だけで過去Episodeを自動全Stale化しない。実行時RegistryはProvenanceとして記録し、Manual Registry CorrectionだけState Fingerprintで明示Stale化する。

Speaker AnalyzerはCurrent Effective Mention集合と本文Contextを入力とし、過去Speaker/Manual Speakerを入力へ戻さない。

turn-taking単独推論は自動Effectiveにしない。

Model見落とし時はManual Entity/Manual AliasをStyle Analysis内に直接作成可能。

Authoring Characterへ自動Writeしない。Project Characterとの対応はManual Linkだけ。

## 8. Term

Term Candidate ExtractorはRegistry非依存でCandidate Annotationだけを作る。

Term ResolverはCache不可でStable Term/TermMentionを作る。

NoveltyはRun付きInferenceとして保持する。

Reference Work初出は対象EpisodeまでのCurrent Term Resolverが連続してSucceededしている場合だけ確定する。

Project Document初出もTarget Resolver Succeededを必須とする。

Term ExplanationはTerm Identity単位ではなくTermMention単位。

探索は同Scene内に限定する。

説明遅延はFirst MentionからSufficient Explanation SpanまでのCode Point差。説明先行は負値可。

## 9. Scene / Block Semantic

Sceneは単一TypeではなくMulti-axis:

```text
function
tone
pace
information_load
interaction
```

Current推論がない`unknown`と、Current推論はあるが判断不能のTaxonomy値`unclear`を分離する。

Scene AxisはStyle Metric入力にせず、Aggregate/Lint Selectorとして使う。

Block Primary SemanticはNarrationだけ:

```text
action
description
exposition
psychology
transition
other
unclear
```

POVはEntity Resolutionへ依存するが、v1 Aggregate/Lint Selectorには使わない。

## 10. Analysis Runtime

AnalyzerはDependency DAGで実行する。

AnalysisRunは:

- Analyzer/Version。
- Text/Structure Revision。
- Config。
- Prompt/Taxonomy/Metric Version。
- Dependency Run Link。
- Relevant Policy Input Fingerprint。
- Human State Fingerprint。
- Resolver実行時Registry Input Fingerprint。
- Model/Prompt Provenance。

を保持する。

Current Runを単純Latest Succeededで選ばない。

Policy Version全体ではなくAnalyzerが実際に読むPolicy KeyだけをCurrent条件にする。

Persisted Job Type:

```text
analyze_document
analyze_reference_work
recompute_aggregate
run_lint
```

Local Import/Profile生成は同期処理。

WorkerはAPI Process全体で1 Thread。Work Jobは子Document Jobを作らずDocument OrchestratorをEpisode順にinline実行する。

## 11. Analysis Status

DBへ`analysis_stale` boolを保存しない。

Group別派生状態:

```text
basic:
  not_analyzed | current | stale

semantic:
  not_analyzed | current | stale | partial
```

Current Runが揃っていれば古いHistorical Runが存在してもCurrent。

Revision/State/Dependency変更で旧成功Runしかない場合はStale。

Current Lineage上の実行不完全だけPartial。

Deterministicのみ完了ならBasic current / Semantic not_analyzed。

## 12. Manual Override / Review

ManualOverride:

```text
set
clear
revert
```

Append-only Event。

- clear: Field定義上のExplicit Unknown/None。
- revert: Manual指定解除、Inferenceへ戻る。

Effective順位:

```text
Manual
> Confirmed Current Inference
> Current Eligible Inference
> Unknown/Default
```

Low-confidenceだけでReviewQueueを自動大量生成しない。

Direct OverrideにReviewItemは不要。

Human Correction後は変更種類に応じて:

- Metric-only Recompute。
- Semantic Reanalysis Required。
- Aggregate/Lint Stateのみ。
- Display-only。

へ分類する。

## 13. Measurement

```text
style-metrics-basic
style-metrics-semantic
```

BasicはStructureだけを入力にしSemantic/Speaker/Term Annotationを読まない。

SemanticはCurrent Effective Speaker/Term/Block Stateを読む。

MetricDefinitionはCode Registryで式/Unit/Version/Toleranceを持つ。

Missing Inputを0として保存しない。

Character MeasurementはDocument全体人物単位だけ。対象DocumentにCurrent Mention/Speakerが存在するEnabled Personだけ生成する。

## 14. Corpus / Aggregate

Corpus MembershipはWork Membership + Episode Override。

- include_all=true: Default Included、exclude Override。
- include_all=false: Default Excluded、include Override。

AggregateはMeasurement Rowを等重みでPoolする。Work等重みではない。

Count:

```text
source_measurement_count = 入力Measurement Row数
sample_count = 入力Measurement.sample_count合計
work_count = Distinct Work数
skipped_target_count = 列挙できたTargetの入力不足件数
```

Current Document Text/Structure/Runだけを使い、Latest/古いRunへFallbackしない。

Scene FilterでRequired AxisがunknownならSkipped + Warning。

AggregateはImmutable Historical Snapshot。AggregatePolicy Version + Input FingerprintでStale判定する。

## 15. Profile

Profile IdentityとImmutable Versionを分離しActive Versionを明示する。

Corpus由来Rule:

```text
preferred = median Aggregate
min = p25 Aggregate
max = p75 Aggregate
```

Exact Aggregate IDsを指定し、Rule→Aggregate Provenanceを保存する。

Stale Aggregateも明示選択なら利用可能で、Warningだけ表示する。

StyleRule:

```text
target_scope = document | scene | character
```

Enabled Ruleはmin/max両方必須。preferred指定時は範囲内。

Character RuleはManualのみ。Reference人物名からProject Characterへ自動対応しない。

New VersionだけではActive Versionを変更しない。

## 16. Lint

LintはTextRevision/StructureRevision/Profile Versionを明示する。

Document Lint:

- Document Rule。
- 全Scene Rule。
- Character Rule。

Scene-only Lint:

- 指定SceneのScene Ruleだけ。

Missing Metric/SelectorはCoverageとして扱い、割合だけでFailさせない。

Specific Scene分類がunknownでもGlobal Scene Ruleの評価を妨げない。

FindingはRule/Target/Observed/Expected/Deviation/Severity/Evidenceを保存する。

総合品質Score/自動本文修正はv1対象外。

## 17. Storage / API / UI

Migration:

```text
006_style_analysis_foundation.sql
007_style_analysis_semantics.sql
008_style_analysis_corpus_profile.sql
009_style_analysis_external_agent.sql
```

既存001〜008変更なし。009はv1.1 SA-I External Session/Task用の追加migrationである。

API Prefix:

```text
/projects/{project_id}/style-analysis
```

WebUIは:

- Local Sources/Reference Work。
- Document Analysis。
- Corpus/Aggregate/Profile。
- Review/Override。
- Lint。

を提供する。

Historical Structure選択と`Currentに設定`は別操作。

## 18. 実装分割

```text
SA-A Foundation / DB / Job / Runtime State
SA-B Local Source Import / Reference Catalog
SA-C Normalization / Automatic Structure / Basic Metrics
SA-D Boundary / Entity / Term / Speaker / POV / Semantics / Work Analysis
SA-E Corpus / Aggregate / Profile
SA-F Manual Identity / Override / Review / Recompute
SA-G Project Capture / Style Lint
SA-H WebUI / E2E / Dogfood
```

SA系列は既存NovelProduction Phase系列とは別系列。

## 19. Quality Assurance

- Deterministic処理: Unit Test。
- DB/Migration/Worker: Integration。
- Semantic: Fake Model Contract + 小規模Gold。
- API/WebUI: Contract/E2E。
- CIからLive Site/Modelへ接続しない。
- 同じ整合性検査を全Layerへ重複しない。
- Coverage Gateを下げないが、Coverageだけの低価値Testを大量追加しない。

## 20. 完了条件

- Local TXT/HTML/EPUB Import/Purge。
- Document Current Text/Structure明示管理。
- Automatic→optional Semantic Structure。
- Work全体Episode順解析。
- Entity/Term Stable Registry + Manual Identity + Run Resolution。
- AnalysisRun Dependency/State/Policy/Registry Provenance。
- Basic/Semantic Analysis Status。
- Basic/Semantic Metric。
- Corpus Membership/Aggregate/Stale判定。
- Version付きProfile/Exact Aggregate Provenance。
- Coverage付きLint。
- ManualOverride Set/Clear/Revert。
- Job Progress/Partial/Recovery。
- Existing CI Regression PASS。
