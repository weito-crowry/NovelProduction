# 小説文体分析・執筆支援パイプライン 基本設計書

**収集・正規化・構造解析・意味抽出・文体プロファイル・自作品評価**
**v0.2 Draft / 2026-09-01**

> 本書は本機能の基本設計である。データ責務・version/revision・再解析可能性を上位仕様として固定し、具体的な取得方式、分類体系、Metric、LLM prompt、閾値、API/UI契約は `detailed-design/` で定義する。

## 0. エグゼクティブサマリー

本システムの目的は、既存小説から「読み心地」を構成する観測可能な特徴を抽出し、作品・Scene・人物ごとの文体プロファイルとして再利用可能にすることである。最終的には、自作品の各話・各Sceneを参照Profileと比較し、数値差と根拠箇所を提示する。

中心原則:

1. Sourceの元データを不変Snapshotとして保持する。
2. Raw / Canonical / Structure / Semantic / Measurement / Aggregate / Profileを分離する。
3. 解析結果からTextRevisionと原文spanへ逆引きできる。
4. 決定論的処理とLLM推論を分離する。
5. 人手修正を推論rowの上書きではなくoverlayとして保持する。
6. Analyzerをversion/fingerprint付きDAGとして再解析可能にする。
7. 安全確認・レビュー工程は必要箇所だけに置き、low-confidence結果を全件ReviewQueueへ送る等の過剰な停止条件を作らない。

```text
Source Adapter
  -> Immutable SourceSnapshot
  -> TextRevision / Canonical Text
  -> Automatic StructureRevision
  -> Semantic StructureRevision (必要な場合)
  -> Semantic Extraction
  -> Measurement
  -> Aggregate / Corpus Statistics
  -> StyleProfile / StyleProfileVersion / StyleRule
  -> Compare / Draft Lint
```

## 1. 目的・スコープ

### 1.1 目的

- なろう・カクヨム・TXT・HTML・EPUB等をReference Workとして取り込む。
- 本文をScene / Block / Sentenceへ分解する。
- 人物、話者、用語、POV、Scene種別等を抽出する。
- 会話率、発言長、地の文連続長、説明密度、新規用語密度等を定量化する。
- Corpus単位で統計を集約する。
- StyleProfileを作成し、自作品との差分をLintとして提示する。

### 1.2 非目標

- 「良い文章」を単一スコアで断定すること。
- 特定作品の表現をそのまま生成用模倣データへ変換すること。
- 初期段階で文学的特徴を網羅すること。
- Lint結果から本文を自動書き換えすること。
- 汎用Web crawler、ログイン回避、有料壁回避を作ること。
- Style Analysis推論から既存Character/World/Canon DBを自動更新すること。
- v1でMCP toolを追加すること。

## 2. 設計原則

| 原則 | 意味 |
|---|---|
| Source不変 | 元resource bytesはSourceSnapshotとしてimmutable保持。 |
| 派生データ分離 | Text/Structure/Semantic/Metric/Profileを別layerにする。 |
| Provenance | TextRevision、StructureRevision、AnalysisRun、spanへ追跡可能。 |
| 再解析 | Analyzer/Policy/Metric/Prompt versionをfingerprintへ含める。 |
| Stable identity | Entity/Term/Profileのidentityと推論/version snapshotを分離。 |
| Human override | 推論rowを直接編集せずManualOverrideをoverlay。 |
| Partial許容 | 一部Scene失敗を全episode失敗へ拡大しない。 |
| 過剰Review回避 | unknown/low-confidenceを正常状態として保持可能にする。 |
| Explicit text state | 本文/Structure/Lint入力はRevision/Versionを明示する。 |
| Existing architecture尊重 | project-local SQLite、CORE/API/WEBUI責務を維持。 |

## 3. 論理アーキテクチャ

```text
[Collection]
SourceAdapter -> Source -> SourceSnapshot

[Text]
ReferenceEpisode / ProjectEpisodeDraft
  -> StyleDocument
  -> TextRevision
  -> TextMapping

[Structure]
TextRevision
  -> Automatic StructureRevision
  -> Semantic StructureRevision optional
  -> Manual StructureRevision optional
  -> Scene / Block / Sentence

[Semantics]
Entity / Mention / Alias / Relation
Term / TermMention
Annotation
Speaker / Scene tags / POV / Term attributes

[Runtime]
AnalysisPolicy
AnalysisRun
Analyzer DAG
Persisted Job

[Analytics]
Measurement
Aggregate
Corpus

[Style]
StyleProfile
StyleProfileVersion
StyleRule

[Review]
InferenceReview
ManualOverride
ReviewItem optional
Effective View

[Consumer]
Compare
Draft Lint
Finding / Evidence
```

Style Analysisは既存NovelProduction authoring機能とはbounded contextを分ける。ただしProject draft captureでは既存Work/Episode/Draft IDを明示参照する。

## 4. 処理パイプライン

| 工程 | 主処理 | 主要出力 |
|---|---|---|
| P1 Collection | Source取得/Import | SourceSnapshot, ReferenceWork/Episode |
| P2 Normalize | Canonical Text生成 | TextRevision, TextMapping |
| P3 Structure | 決定論的構造化 | Automatic StructureRevision |
| P4 Boundary | Scene境界推定 | Boundary Annotation, Semantic StructureRevision |
| P5 Semantic | Entity/Term/Speaker/Scene/POV | Mention, Annotation, Relation |
| P6 Metric | 決定論的計測 | Basic/Semantic Measurement |
| P7 Aggregate | Corpus/Work/Scene等の統計化 | Aggregate |
| P8 Profile | 参照範囲作成 | StyleProfileVersion, StyleRule |
| P9 Lint | Project draftとProfile比較 | LintRun, Finding, Evidence |

## 5. Collection

- Site固有処理はSourceAdapterへ隔離する。
- Network処理はAPI層。COREはDB/domainのみ。
- SourceSnapshotはHTML/TXT/EPUBを含め元resource bytesをBLOBで保持する。
- ReferenceWork/ReferenceEpisodeはcurrent catalog projectionとしてmetadata/order/latest snapshot pointerを更新可能。
- Network fetch中に長時間DB transactionを開かない。
- Import成功時にcatalog/Snapshot/TextRevisionをtransactionで反映する。
- Source refreshで消えたEpisodeはcatalogから削除可能。SourceSnapshotはWork全体Purgeまで取得履歴として残す。
- ReferenceWork Purgeは専用SourceであればSource/Snapshotまで削除するService transactionとする。
- `rights_basis` の必須入力、毎回の同意checkbox等は機能contractに入れない。

## 6. TextRevision / Normalization

- Adapterが抽出した可読本文をraw_textとして保持する。
- Canonical Textは解析用派生本文。
- OffsetはUnicode code point単位の半開区間 `[start_cp,end_cp)`。
- UnicodeはNFC。NFKC等、文体表現を変える正規化は行わない。
- Raw→Canonical変換はTextMappingで追跡する。
- TextRevisionはimmutable。
- 同一Raw hash + Normalizer versionなら再利用可能。

## 7. StructureRevision

Structure階層:

```text
TextRevision
  -> StructureRevision
      -> Scene
          -> Block
              -> Sentence
```

StructureRevision kind:

```text
automatic
semantic
manual
```

### Automatic

Quote/Heading/Separator等、決定論的ルールでbase構造を作る。明示境界がなければEpisode全体1 Sceneでもよい。

### Semantic

Scene Boundary Analyzerは任意文字offsetではなく `after_block_id` 候補だけを返す。AnalysisPolicyのauto-apply threshold以上をStructureServiceが決定論的にmaterializeする。

Semantic Structureはparent Structureと生成元Boundary AnalysisRunを追跡する。

### Manual

ユーザーsplit/mergeはparentを持つ新StructureRevisionとして保存する。既存revisionをupdateしない。

Block type:

```text
dialogue
narration
monologue
heading
separator
unknown
```

Action/Description/Exposition/Psychology等はSemantic Annotationとする。

## 8. Entity / Mention

Entityはstable identity。

Reference作品では `reference_work_id` scopeでEpisodeを跨いで共有する。Project draftでは `document_id` scope。

Entity identityに保持するもの:

```text
entity_type
canonical_name
origin
```

Mention、Alias、Relationは生成元AnalysisRunを追跡する。推論による確認/却下/名称修正はInferenceReview/ManualOverrideでoverlayする。

既存NovelProduction Character rowへ名前一致で自動mergeしない。

## 9. Term

Termもstable identityでReference Work全体またはProject Documentへ所属する。

Identity:

```text
canonical_label
term_type
origin
```

次はRun付きAnnotationとして保持する。

```text
term.novelty
term.exact_match_safe
term_explanation
```

これによりAnalyzer再実行時にTerm identityを上書きしない。

初出は永続 `occurrence_index` ではなく、current effective revision/runのMentionをEpisode order + offsetでsortして算出する。

## 10. Scene Semantics

Scene分類はmulti-axis。

```text
function
tone
pace
information_load
interaction
POV
```

判断不能は `unclear`。`other` と区別する。

Narration/Monologue Blockにはprimary semantic:

```text
action
description
exposition
psychology
transition
other
unclear
```

を付ける。

Taxonomy/Prompt/Analyzerはversionを持つ。

## 11. AnalysisRuntime

AnalysisRunはDocument内派生Analyzerに限定する。

対象例:

```text
scene-boundary-detector
entity-mention-extractor
entity-resolver
speaker-attribution
term-candidate-extractor
term-resolver
term-explanation-detector
scene-semantic-classifier
block-semantic-classifier
pov-classifier
style-metrics-basic
style-metrics-semantic
```

Normalization、Structure materialization、Aggregate、Profile、LintはAnalysisRunへ入れない。

### AnalysisPolicy

Confidence thresholdやProfile最小sample等はversioned `AnalysisPolicy` に一元化する。各Analyzerへ重複hard-codeしない。

### Effective Run

同一Document/TextRevision/StructureRevision/Analyzerに複数Runが存在する場合、09の一貫した選択規則でeffective Runを決める。Responseは採用Run IDを返す。

### Partial

Scene/Block単位Analyzerは一部subjectだけ失敗した場合 `partial` とし、成功subjectを保持する。任意の失敗率thresholdで全Runをfailさせない。

## 12. Measurement

Metric計算はCOREの決定論的処理。

Group:

```text
style-metrics-basic
style-metrics-semantic
```

BasicはStructureだけで計算可能。SemanticはSpeaker/Term/Semantic Annotationへ依存する。

初期Metric例:

```text
text.char_count
sentence.len.p50/p90
paragraph.len.p50/p90
dialogue.char_ratio
dialogue.utterance_len.p50/p90
dialogue.turn_count.p50/p90
narration.run_len.p50/p90
semantic.exposition.char_ratio
semantic.psychology.char_ratio
term.new_per_1000_chars
term.explanation_delay.p50/p90
speaker.utterance_len.p50/p90
speaker.consecutive_turns.p50
```

MetricDefinitionは式、unit、version、zero-width toleranceを持つ。

Missing inputを0値へ変換しない。

## 13. Corpus / Aggregate

CorpusはReference Work/Episode集合。

AggregateはMeasurement rowを観測単位として集約し、mean/median/p10/p25/p75/p90/pstdev等を保持する。

Corpus membershipやInput Measurementが変わればfingerprintが変わり新Aggregateを作る。過去Aggregateは履歴として保持可能。

## 14. StyleProfile

Stable identityとimmutable Versionを分離する。

```text
StyleProfile
  id/name/description/status/active_version_id

StyleProfileVersion
  profile_id/version_no/parent_version_id

StyleRule
  profile_version_id/metric/scope/preferred/min/max/weight/...
```

Corpus生成default:

```text
preferred = median
min = p25
max = p75
```

Sample不足時はCorpus由来Ruleを自動生成しないが、Manual Rule作成を妨げない。

Profileがactiveの場合は `active_version_id` を明示する。新Version作成だけではactive Versionを暗黙切替しない。

Lint/ExportはProfile Versionを明示指定する。

## 15. Review / ManualOverride

Effective View基本優先順位:

```text
ManualOverride
> Confirmed inference
> latest eligible inferred value
> unknown
```

Low-confidence/unknownは正常状態。ReviewQueueへ全件自動投入しない。

ReviewItemはScene Boundary ProposalをユーザーがReviewへ追加した場合、stale Override等、Review workflowに価値がある項目だけに使う。

ManualOverrideはReviewItemなしで直接作成可能。

Structure依存subjectはStructureRevision IDを持ち、stale subjectを検出できるようにする。

## 16. Style Lint

Lint入力:

```text
Project Document
TextRevision
StructureRevision
Profile ID
Profile Version
Metric Run
```

FindingはRule rangeからの逸脱を示す。文章品質の総合スコアは作らない。

Rule対象MetricがmissingでもLintRunを割合thresholdでfailさせず、coverageとして表示する。

Evidenceはspan/Block ID等を保持し、本文excerptをFinding rowへ複製しない。

## 17. 永続化

v1は既存project-local `story.db` に `style_` prefix tableを追加する。

Migration:

```text
006_style_analysis_foundation.sql
007_style_analysis_semantics.sql
008_style_analysis_analytics.sql
```

既存001〜005は変更しない。

Raw resource bytes、Raw/Canonical textもSQLiteに保存する。実測で容量問題が出るまで別Storageを導入しない。

## 18. API境界

URL prefix:

```text
/projects/{project_id}/style-analysis
```

原則:

- Text取得は `text_revision_id` 明示
- Structure取得/編集は `structure_revision_id` 明示
- LintはProfile Version明示
- Semantics/MetricはStructureRevisionを明示し、serverが09 Effective Runを選択可能
- Effective Runを選んだResponseは採用AnalysisRun IDを返す
- 過去Runの厳密表示用endpointを別途持つ
- Latest Draft/Structureへ暗黙読み替えしない

## 19. WebUI

主要画面:

```text
Style Analysis Home
Sources / Reference Works
Document Analysis
Corpus / Compare
Profiles / Profile Editor
Review
Lint
```

Document AnalysisはTextRevision/StructureRevision selectorを持つ。

Profile Editorは `保存` と `保存して有効化` を分離できる。

Source importやFull Analysisにrights checkbox・毎回の確認dialog等の追加blocking UIは設けない。

## 20. Quality Assurance

- Deterministic parser/Metricはfixture unit test。
- DB migration/invariantはintegration test。
- Semantic AnalyzerはFake Model contract test + 小さなGold dataset。
- CIは実サイト/実LLMへ接続しない。
- Gold datasetに根拠の薄い固定精度gateを置かない。
- Live dogfoodはCI外で実施する。
- 同じintegrity/safety assertionを全test layerへ重複配置しない。

## 21. 実装分割

詳細な実装順は `detailed-design/README.md` のSA-A〜SA-Hを正本とする。

```text
SA-A Foundation / DB / Job
SA-B Source Import
SA-C Normalization / Structure / Basic Metrics
SA-D Semantic Analysis
SA-E Corpus / Aggregate / Profile
SA-F Review / Override
SA-G Project Capture / Lint
SA-H WebUI / E2E / Dogfood
```

## 22. 完了条件

- Reference WorkをimportしTextRevisionへ変換できる。
- Automatic/Semantic/Manual Structureを履歴付きで扱える。
- Entity/TermをReference Work横断で追跡できる。
- Annotation/MeasurementからAnalysisRun/Structure/Text spanへ追跡できる。
- Basic/Semantic Metricを再現可能に計測できる。
- Corpus AggregateからVersion付きStyleProfileを生成できる。
- Project DraftをProfile Versionと比較しcoverage付きFindingを生成できる。
- ManualOverrideが再解析で失われない。

## 23. 将来拡張候補

- Scene類似検索
- 文体リズム時系列
- Character voice fingerprint
- POV逸脱検知
- 読者負荷モデル
- Genre Corpus preset
- Realtime Lint
- Writing Guidance
- MCP公開（別設計）
