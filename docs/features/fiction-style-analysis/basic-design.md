# 小説文体分析・執筆支援パイプライン 基本設計書

**収集・正規化・構造解析・意味抽出・文体プロファイル・自作品評価**
**v0.1 Draft / 2026-09-01**

> 本書は本機能の基本設計である。分析指標・分類体系・LLMプロンプトは将来変更される前提とし、データ基盤と再解析可能性を優先する。詳細設計は `detailed-design/` 配下で本書を上位仕様として具体化する。

## 0. エグゼクティブサマリー

本システムの目的は、既存小説から「読み心地」を構成する観測可能な特徴を抽出し、作品・シーン・人物ごとの文体プロファイルとして再利用可能にすることである。最終的には、自作品の各話・各シーンを参照プロファイルと比較し、執筆時に具体的な差分と根拠を提示する。

中心原則は「原文を不変で保持する」「派生データをレイヤー分離する」「解析結果から必ず原文位置へ逆引きできる」「LLM推論と決定論的計測を区別する」「人手修正をAI再解析で破壊しない」「分析器を追加可能なDAGとして扱う」の6点である。

```text
Source Adapter
  ↓
Immutable Source Snapshot
  ↓
Normalization / Canonical Text
  ↓
Structure Detection (Scene / Block / Sentence)
  ↓
Semantic Extraction (Entity / Mention / Speaker / Term / Scene Tags)
  ↓
Measurement
  ↓
Aggregate / Corpus Statistics
  ↓
StyleProfile / StyleRule
  ↓
Compare / Draft Lint / Writing Guidance
```

## 1. 目的・スコープ

### 1.1 目的
- 小説本文を収集し、再現可能な形でローカル保存する。
- 本文をシーン・ブロック・文へ分解し、分析可能な構造データへ変換する。
- 人物、発話者、用語、場所、組織、視点、シーン種別などの意味情報を抽出する。
- 会話率、発言長、地の文連続長、説明密度、新規用語密度などを定量化する。
- 作品・シーン種別・人物・コーパス単位で統計を集約し、文体プロファイルを作成する。
- 自作品を参照プロファイルと比較し、差分・根拠・改善候補を提示する。

### 1.2 非目標
- 「良い文章」を単一スコアで断定すること。
- 特定作品の文章を生成モデルへそのまま模倣させること。
- 初期段階で全ての文学的特徴を網羅すること。
- 分析結果を根拠なく自動修正へ直結させること。
- 取得元の利用条件を無視した大量取得・再配布を前提にすること。

## 2. 設計原則

| 原則 | 設計上の意味 |
|---|---|
| 原文不変 | SourceSnapshotはimmutable。再取得時は新snapshotを作る。 |
| 派生データ分離 | Raw / Canonical / Structure / Semantic / Metrics / Profileを分離。 |
| Provenance優先 | revision、位置、analyzer version、設定へ追跡可能。 |
| 拡張可能性 | AnalyzerとMetric registryを追加可能にする。 |
| 人手優先 | AI推定とHuman Overrideを分離。 |
| 再解析可能 | fingerprintで必要箇所のみ再解析。 |
| 定量と推論を分離 | 決定論的計測とモデル推論を区別。 |
| 局所性を保持 | 作品平均だけでなく話・Scene・Block・人物単位を保持。 |

## 3. 論理アーキテクチャ

```text
[Collection] SourceAdapter -> SourceSnapshot
[Text Foundation] SourceSnapshot -> TextRevision -> CanonicalText -> TextMapping
[Structure] Episode -> Scene -> Block -> Sentence
[Semantics] Entity <-> Mention / Annotation / Relation / Speaker Attribution / Scene Tags
[Analytics] AnalysisRun -> Measurement -> Aggregate
[Style] Corpus -> StyleProfile -> StyleRule
[Review] ReviewQueue -> ManualOverride -> Effective View
[Consumer] Compare / Visualization / Draft Lint / NovelProduction Integration
```

文体分析機能は独立したbounded contextとして扱う。制作側の人物・設定・本文管理と直接テーブル結合せず、work/episode/revision識別子とAPI契約で疎結合にする。

## 4. 処理パイプライン

| Phase | 工程 | 主処理 | 主要出力 |
|---|---|---|---|
| P1 | 収集 | なろう / カクヨム / TXT / EPUB / HTML等から取得 | SourceSnapshot |
| P2 | 正規化 | 解析用Canonical Text生成 | TextRevision / TextMapping |
| P3 | 構造解析 | 章・話・Scene・Block・Sentence切り出し | Scene / Block / Sentence |
| P4 | 要素抽出 | 人物・用語・場所・組織等 | Entity / Mention |
| P5 | 意味解析 | 話者、POV、地の文種別、Scene tags等 | Annotation / Relation |
| P6 | 定量計測 | 会話率、文長、連続長、密度等 | Measurement |
| P7 | 集約 | 各scopeで統計化 | Aggregate |
| P8 | プロファイル化 | 執筆用目標・許容範囲へ変換 | StyleProfile / StyleRule |
| P9 | 比較・lint | 逸脱と根拠箇所を提示 | Finding / Evidence |
| P10 | 執筆支援 | 必要な制約だけ生成支援へ供給 | Writing Constraints |

## 5. P1 収集設計

- サイト固有処理はSourceAdapterへ隔離する。
- adapter例: NarouAdapter / KakuyomuAdapter / TxtAdapter / EpubAdapter / HtmlAdapter。
- 作品メタデータ、エピソード一覧、取得URL、取得日時、HTTP情報、raw payload hashを保持する。
- 再取得時は差分検知し、本文変更時のみ新SourceSnapshotを作る。
- retry、rate limit、並列数はadapter policyとする。
- 取得元の利用条件・robots・公開範囲・再配布可否を運用設定として扱い、外部公開をデフォルト禁止とする。

## 6. P2 正規化・テキストRevision

- SourceSnapshotのraw本文は不変。
- Canonical Textは解析用派生revision。
- 正規化規則にversionを付ける。
- ルビ、傍点、HTML、前後書き、広告、見出し、区切り線等の扱いを規則化する。
- CanonicalとRawの対応をTextMappingとして保持する。
- canonical offsetはUnicode code point単位の半開区間 `[start,end)` とする。

## 7. P3 構造解析

```text
Work
 └─ Episode
     └─ TextRevision
         ├─ Scene
         │   └─ Block
         │       └─ Sentence
         └─ TextMapping
```

Block type初期値: `dialogue / narration / monologue / heading / separator / unknown`。action / description / exposition / psychology / transition は固定typeではなくsemantic annotationとする。

Scene境界はseparatorに加え、時間・場所・POV・登場人物集合・文脈断絶を利用し、confidenceを持つ。手動split/mergeを可能にする。

## 8. P4/P5 要素抽出・意味解析

### EntityとMention
Entityは同一実体、Mentionは本文中の出現。別名・代名詞・呼称はMentionとして同一Entityへ解決する。

初期Entity type: `person / organization / location / technology / concept / product / event / other`。

### 人物抽出
1. 人物候補Mention抽出
2. coreference解析
3. entity resolution
4. speaker attribution
5. scene participants判定
6. relation抽出
7. 人物別文体統計

### 用語抽出
- 固有語だけでなく作品内固有意味を持つ一般語も候補化。
- first appearance、頻度、scene、説明ブロックとの近接を保持。
- 新規用語密度と説明遅延を計測可能にする。

### Scene taxonomy
排他的enumではなくmulti-labelを正本とする。例: function / tone / pace / information_load / interaction。

## 9. Analyzerプラグイン設計

AnalyzerDefinitionはid、version、input scope、dependencies、config schema、output contract、deterministic/model_basedを宣言する。AnalysisRunはinput revision、model、prompt version、config、dependency fingerprint、statusを保存する。AnalyzerはDAGとして依存関係を宣言し、fingerprint一致時は結果を再利用する。

## 10. P6 文体Measurement

初期metric例:

```text
dialogue.char_ratio
dialogue.utterance_len.p50
dialogue.utterance_len.p90
dialogue.turn_count.p50
narration.run_len.p50
narration.run_len.p90
sentence.len.p50
paragraph.len.p50
exposition.char_ratio
psychology.char_ratio
scene.new_term_per_1000_chars
scene.term_explanation_delay.p50
```

MetricDefinitionで単位、value type、算出定義、versionを管理する。

## 11. P7 集約・Corpus

Measurementは局所観測値、Aggregateは複数観測値から算出した統計値。scopeはwork / episode / scene_type / character / corpus。meanだけでなくmedian、p10、p25、p75、p90、標準偏差、sample countを保持する。Corpusは目的別の作品集合で、作品は複数Corpusへ所属可能。

## 12. P8 StyleProfile / StyleRule

Measurementは実測、StyleProfileは執筆時の基準。Profileは作品全体、scene tag、character等のscope別ruleを持てる。ruleはpreferred/range/percentile band、weight、severity policy、evidence policyを持つ。

## 13. P9 自作品比較・Style Lint

Findingはtarget、rule、observed value、expected range、severity、evidence spans、explanationを持つ。判定は「悪い」ではなく参照プロファイルとの差分として提示し、必ず原文spanへ逆引きできるようにする。

## 14. 論理データモデル

主要Entity: `Corpus / Source / SourceSnapshot / Work / Episode / TextRevision / TextMapping / Scene / Block / Sentence / Entity / Mention / Relation / Annotation / AnalyzerDefinition / AnalysisRun / MetricDefinition / Measurement / Aggregate / StyleProfile / StyleRule / Finding / ManualOverride`。

## 15. Provenance・Confidence・人手修正

- confidenceはモデル推論の確からしさ。
- statusは`inferred / confirmed / rejected / manual`。
- evidenceはrevision + span。
- ManualOverrideはAI出力を削除せずoverlayとして保持。
- Effective Viewは`manual > confirmed > inferred`を基本優先順位とする。
- review queueへ低confidence、高影響、矛盾、未解決speaker等を送る。

## 16. 再解析・キャッシュ・変更伝播

```text
analysis_fingerprint = hash(
  input_text_hash,
  analyzer_id,
  analyzer_version,
  analyzer_config,
  dependency_fingerprints,
  model_id,
  prompt_version
)
```

正規化変更なら構造解析以降をinvalidateし、個別Analyzer更新なら依存部分だけ再解析する。ManualOverrideは再解析で消さない。

## 17. 永続化・API境界

- DB実装から論理モデルを分離。
- raw payloadはDBまたはcontent-addressed file storage。
- APIではrevisionを明示し、latestを暗黙参照しない。
- effective viewとraw inference viewを分ける。
- StyleProfileはversion付きJSONでexport/import可能にする。

## 18. Web UI

- Collection
- Work Explorer
- Analysis Runs
- Semantic Review
- Metrics
- Corpus Compare
- Profile Builder
- Draft Lint

## 19. 品質保証

- deterministic parser/metricはfixture unit test。
- Scene/speaker/entity resolutionはgold datasetで回帰評価。
- Analyzer version変更時の精度回帰を実施。
- fingerprint cache、override保持、revision追跡をintegration test。
- Downloaderはrecorded response/fixtureでサイト変更を検知。

## 20. 推奨実装フェーズ

| Phase | 名称 | 主要scope |
|---|---|---|
| A | Foundation | Source/Work/Episode/TextRevision/AnalysisRun、hash、version、基本API |
| B | Collection | TXT/HTML + なろう/カクヨムadapter、snapshot、再取得 |
| C | Deterministic Structure | 正規化、Scene候補、Block、Sentence、基本metric |
| D | Semantic Extraction | Entity/Mention、人物統合、speaker、用語、Scene tags |
| E | Analytics | Measurement registry、Aggregate、分布 |
| F | Style Profile | Corpus、Profile Builder、StyleRule、比較 |
| G | Draft Lint | Finding、Evidence、UI、執筆支援連携 |
| H | Hardening | gold set、再解析最適化、差分解析、運用監視 |

## 21. 現時点で確定する事項 / 保留する事項

### 確定してよい事項
- SourceSnapshot immutable。
- RawとCanonicalを分離。
- Scene / Block / Sentenceを構造レイヤー化。
- EntityとMentionを分離。
- Annotation / Measurement / Aggregate / StyleProfileを分離。
- revision/span/provenance必須。
- Analyzerはversioned plugin + DAG。
- ManualOverride分離。
- Style Lintはprofileとの差分。

### 次段階で詰める事項
- 正規化規則。
- Scene境界検出。
- semantic taxonomy。
- coreference / speaker attribution。
- 用語の新規性・説明定義。
- 初期Metric set。
- 集約統計とminimum sample size。
- Profile生成・severity policy。
- 各Source Adapterの具体取得方式。

## 22. v0.1 アーキテクチャ完了条件

- 1話をSourceSnapshot→Canonical→Structure→Measurementまで処理可能。
- Measurement/Annotationから原文spanへ逆引き可能。
- Analyzer新旧runを共存・比較可能。
- fingerprintで不要再解析を省略可能。
- ManualOverrideが再解析で失われない。
- Corpusで主要指標分布を比較可能。
- StyleProfileから根拠span付きFindingを生成可能。

## 23. 将来拡張候補

- Scene類似検索。
- 文章リズム時系列可視化。
- Character voice fingerprint。
- POV逸脱検知。
- 初出用語説明タイミング支援。
- 読者負荷モデル。
- ジャンル別Corpusプリセット。
- リアルタイムlint。

## 付録A. 最小データフロー

```text
Episode取得
-> SourceSnapshot
-> TextRevision
-> Scene/Block/Sentence
-> Entity/Mention
-> speaker Annotation
-> Measurement
-> Aggregate
-> StyleProfile比較
-> Finding
-> evidence span
-> Canonical
-> Raw
```

## 付録B. 初期Analyzer候補

`normalizer / block_parser / scene_segmenter / entity_mention_extractor / entity_resolver / speaker_attributor / semantic_block_classifier / scene_classifier / term_analyzer / style_metrics / profile_linter`
