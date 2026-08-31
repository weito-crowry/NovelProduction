# 小説文体分析・執筆支援パイプライン 基本設計書

**収集・正規化・構造解析・意味抽出・文体プロファイル・自作品評価**
**v0.2 Draft / 2026-09-01**

> 本書は本機能の基本設計である。具体的なデータ契約・閾値・API・SQLite schemaは `detailed-design/` を正本とする。

## 0. エグゼクティブサマリー

本機能は、既存小説から「読み心地」を構成する観測可能な特徴を抽出し、作品・Scene・人物ごとの文体プロファイルとして再利用可能にする。自作品を参照Profileと比較し、差分と根拠spanを提示する。

中心原則:

1. 原文Snapshotを不変で保持する。
2. Raw / Canonical / Structure / Semantic / Measurement / Aggregate / Profileを分離する。
3. 推論・計測結果からCanonical Textへ逆引きできる。
4. 決定論的処理とLLM推論を分離する。
5. AI推論とManualOverrideを分離し、再解析で人手修正を消さない。
6. Analyzer/Metric/Policyをversion/fingerprintで管理する。
7. 不明値を許容し、低confidence結果を無理に確定しない一方、確認UIを過剰に挟まない。

```text
Source Adapter
  -> Immutable Source Snapshot
  -> TextRevision / Canonical Text
  -> Automatic Structure
  -> Semantic Scene Boundary (Full analysis)
  -> Semantic StructureRevision
  -> Entity / Mention / Speaker / Term / Scene Semantics
  -> Basic / Semantic Measurement
  -> Aggregate / Corpus
  -> StyleProfile + immutable StyleProfileVersion / StyleRule
  -> Draft Lint / Finding / Evidence
```

## 1. 目的・非目標

### 目的

- なろう・カクヨム・TXT・HTML・EPUB等から分析対象を取り込む。
- Scene / Block / Sentenceへ構造化する。
- 人物、話者、用語、場所、組織、POV、Scene意味分類を抽出する。
- 会話率、発言長、地の文連続長、説明比率、新規用語密度等を計測する。
- Corpus単位で統計を集約しStyleProfileを作る。
- 自作品をProfileと比較し、根拠付きFindingを提示する。

### 非目標

- 「良い文章」を単一品質scoreで断定する。
- 特定作品の文章そのものを模倣生成する。
- v1で全文学的特徴を網羅する。
- Lint結果から本文を自動書き換えする。
- 汎用Web crawler、ログイン回避、有料壁回避を実装する。

## 2. 論理アーキテクチャ

```text
[Collection]
Source -> SourceSnapshot -> ReferenceWork/ReferenceEpisode

[Text Foundation]
Document -> TextRevision -> TextMapping

[Structure]
Automatic StructureRevision
-> Semantic StructureRevision
-> Manual StructureRevision
-> Scene -> Block -> Sentence

[Semantics]
Entity <-> Mention
Term <-> TermMention
Annotation / Relation / Speaker / POV / Scene Tags

[Runtime]
AnalysisPolicy
AnalysisRun(Document Analyzer only)
Persisted Job

[Analytics]
Measurement -> Aggregate -> Corpus

[Style]
StyleProfile -> StyleProfileVersion -> StyleRule

[Review]
Raw Inference -> ManualOverride -> Effective View
Optional ReviewItem

[Consumer]
Compare / Visualization / Draft Lint
```

文体分析機能は既存authoring機能と同じproject DBを使用するが、`style_` prefixのbounded contextとして分離する。既存character/world/canonを推論結果で自動更新しない。

## 3. 処理パイプライン

| Phase | 工程 | 出力 |
|---|---|---|
| P1 | Source import | SourceSnapshot / Reference catalog |
| P2 | Normalization | TextRevision / TextMapping |
| P3 | Deterministic structure | Automatic StructureRevision |
| P4 | Semantic boundary | Semantic StructureRevision |
| P5 | Entity/Term/Semantic extraction | Entity / Mention / Annotation |
| P6 | Metric | Measurement |
| P7 | Corpus aggregation | Aggregate |
| P8 | Profile | StyleProfileVersion / StyleRule |
| P9 | Draft comparison | LintRun / Finding / Evidence |

## 4. Source / Raw data

- サイト固有処理はAPI側SourceAdapterへ隔離する。
- Snapshotは元resource bytesを不変保存する。
- HTML/TXT/EPUBを共通してBLOB Snapshotとして扱う。
- ReferenceWork/ReferenceEpisodeはcurrent catalog projectionで、refresh時にmetadata/order/latest pointerを更新可能。
- ユーザーが明示した作品だけを取得し、汎用crawlerは作らない。
- 利用条件の自動法的判定、`rights_basis`必須入力、毎回の同意checkboxは設けない。

## 5. TextRevision / Normalization

- adapterが抽出した可読 `raw_text` と解析用 `canonical_text` を分離する。
- SourceSnapshot payloadを上書きしない。
- Normalizerにversionを付ける。
- Canonical offsetはUnicode code point単位 `[start,end)`。
- Raw/Canonical対応をTextMappingへ保持する。
- 自作品は既存Document engineからplain text projectionを取得し、Style Analysis独自parserを複製しない。

## 6. Structure

Block type:

```text
dialogue / narration / monologue / heading / separator / unknown
```

Block `order_index` はStructureRevision全体でglobal 1..N。

### Automatic Structure

quote/separator/heading等の決定論的規則でbase構造を作る。

### Semantic Structure

Full analysisではLLM Scene Boundary AnalyzerがBlock境界候補を出す。高confidence候補は新しい `semantic` StructureRevisionへ自動materializeする。本文文字列は変更しない。

### Manual Structure

ユーザーsplit/mergeは新しい `manual` StructureRevision。既存revisionは更新しない。

## 7. Entity / Term scope

reference作品のEntity/Termは `reference_work_id` scopeとし、episodeを跨いで同一人物・同一用語を追跡する。

project draftは `document_id` scope。既存NovelProduction characterとの対応が必要な場合だけ明示linkを使う。

EntityとMention、TermとTermMentionを分離する。初出順のようなrefreshでstaleになる派生indexは保存せず、current effective revisionから計算する。

## 8. Scene Semantics

Scene分類はmulti-axis:

```text
function
tone
pace
information_load
interaction
POV
```

判断不能は `unclear`。`other` と区別する。

Block semantic primary:

```text
action / description / exposition / psychology / transition / other / unclear
```

構成比はprimaryだけで計測する。

## 9. Analysis Runtime

AnalysisRunは「既存TextRevision/StructureRevisionからDocument派生データを作るAnalyzer」だけを管理する。

Normalization、StructureRevision作成、Aggregate、Profile生成、LintはAnalysisRunへ含めない。

confidence threshold、Scene boundary auto-apply、Profile minimum sample等はversioned `AnalysisPolicy` を唯一の正本とする。

v1 job workerはAPI process内1本。Redis/Celery/parallel workerは導入しない。

Semantic LLM providerはAPI側 `openai_compatible` adapter。Full analysisをユーザーが明示実行する操作を送信開始操作とし、追加の確認dialogは必須にしない。

## 10. Measurement

Metricを2群へ分ける。

```text
basic: structureだけで計測
semantic: speaker/term/semantic outputを使用
```

semantic入力が一部欠落した場合、completeなScene metricは保持できるが、不完全なdocument全体semantic ratioは作らない。

MetricDefinitionはversion、unit、算出定義、zero-width Lint toleranceを持つ。

## 11. Aggregate / Corpus

AggregateはMeasurement rowを観測単位として等重み集約する。長い作品のraw sentenceを再poolして自動weightしない。

保持統計:

```text
mean / median / p10 / p25 / p75 / p90 / pstdev / min / max
```

Corpusはユーザーが目的別に作るreference work集合。

## 12. StyleProfile

Profile identityとVersionを分離する。

```text
StyleProfile          # name/status等のstable identity
StyleProfileVersion   # immutable Rule snapshot
StyleRule
```

Corpusからのdefault Rule:

```text
preferred = median
min = p25
max = p75
```

sample不足時は自動Ruleを作らないが、manual Rule作成は許可する。

## 13. Review / ManualOverride

Effective View:

```text
manual > confirmed > inferred above policy threshold > unknown
```

低confidence結果を全件ReviewQueueへ積まない。unknownは正常値として保持し、Semantics画面のfilterから確認できる。

ReviewItemはspeaker/entity conflict、ユーザーがQueueへ追加したScene boundary proposal、stale override等の「操作価値がある項目」だけに使う。

Override noteは任意。ローカル単一user前提で不要な二重CAS tokenを追加しない。

## 14. Style Lint

FindingはProfileとの差だけを示す。

- preferredとの差だけではFindingを作らない。
- zero-width rangeのtoleranceはMetricDefinitionを使う。
- missing Metricはwarning + coverageとして返し、missing割合だけでLintRunをfailさせない。
- 総合文章品質scoreは作らない。

## 15. 永続化

- project-local `story.db`
- `style_` prefix
- migration 006/007/008
- 001〜005変更禁止
- raw payload: SQLite BLOB
- raw/canonical text: SQLite TEXT
- ORM追加なし
- ProfileVersion等のimmutable rowのみUPDATE禁止
- Reference Work PurgeはFK cascadeで本文を削除可能

## 16. API / WebUI / MCP

APIはすべて `/projects/{project_id}/style-analysis`。

- `text_revision_id` は解析時必須。
- `structure_revision_id` はoptional。省略時は指定TextRevisionからbuild/reuse。
- latest revisionへ暗黙読み替えしない。
- Profile APIはidentity/versionを分離する。
- Lint UIはcoverageとstaleを表示する。
- v1ではMCP変更なし、tool count 59維持。

## 17. 品質保証

- Deterministic処理はexact fixture test。
- Source Adapterはmock HTTP fixture。
- LLM Analyzerはfake client + small curated gold set。
- 小規模datasetへ統計的根拠の薄い固定precision/F1 release gateを置かない。
- DB integrityはmigration/integration suiteで確認し、各test layerへ重複させない。
- CIからlive site/LLMへ接続しない。

## 18. 推奨実装フェーズ

| Phase | 名称 | 主要scope |
|---|---|---|
| SA-A | Foundation | DB、models/repositories、job、AnalysisPolicy |
| SA-B | Collection | Source Adapter、Snapshot、Reference catalog |
| SA-C | Deterministic Analysis | Normalization、Automatic Structure、Basic Metric |
| SA-D | Semantic Analysis | Scene Boundary、Entity/Speaker/Term/Semantics、Semantic Metric |
| SA-E | Analytics/Profile | Corpus、Aggregate、Profile/Version/Rule |
| SA-F | Review | Effective View、Override、限定ReviewItem |
| SA-G | Draft Lint | project capture、Lint/Finding/Evidence |
| SA-H | WebUI/E2E | UI integration、dogfood |

## 19. v0.2 設計完了条件

- SourceSnapshotからTextRevisionまでprovenanceが追跡可能。
- Automatic/Semantic/Manual StructureRevisionの責務が明確。
- reference Entity/Termがepisodeを跨いで扱える。
- basic/semantic Metricを分離できる。
- Analyzer責務とAggregate/Profile/Lint責務が循環しない。
- Profile identity/versionが一意に扱える。
- ManualOverrideが再解析で失われない。
- Lintがmissing Metricをcoverageとして扱える。
- API/DB/UIで同じrevision/profile versionを参照できる。

## 20. 将来拡張候補

- Scene類似検索
- リズム時系列可視化
- Character voice fingerprint
- POV逸脱検知
- 用語説明タイミング支援
- 読者負荷モデル
- Corpus preset
- realtime lint
- Writing Guidance
