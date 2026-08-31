# 06 Scene Semantics 詳細設計

## 1. 目的

Scene/Blockへ意味ラベルを付与し、局面別に文体統計を比較できるようにする。Scene分類はmulti-axisを正本とし、判断不能を無理に既知labelへ押し込まない。

上位仕様は `../basic-design.md`。

## 2. 実装先

```text
CORE/src/novel_core/style_analysis/
  semantic_models.py
  semantic_service.py
  analyzers/
    scene_classifier.py
    block_semantics.py
    pov_classifier.py
    scene_boundary.py
```

## 3. Scene taxonomy

`scene-taxonomy-v1`。

### function: multi-select

```text
daily
setup
dialogue
exposition
meeting
investigation
travel
introspection
conflict
action
transition
reveal
payoff
other
unclear
```

### tone: multi-select

```text
neutral
calm
humorous
warm
tense
emotional
ominous
sad
excited
other
unclear
```

### pace: single-select

```text
slow
medium
fast
unclear
```

### information_load: single-select

```text
low
medium
high
unclear
```

### interaction: single-select

```text
solo
dialogue
group_dialogue
crowd
mixed
unclear
```

`unclear` は他labelと同時指定しない。`other` は「判定できるがtaxonomy外」、`unclear` は「判定不能」。

## 4. Annotation形式

axisごとに `style_annotations` へ保存する。

multi-select:

```json
[
  {"label": "daily", "confidence": 0.91},
  {"label": "dialogue", "confidence": 0.96}
]
```

single-select:

```json
{"label": "medium", "confidence": 0.84}
```

巨大なScene JSONへまとめない。

## 5. Scene classifier入力

- Scene全文
- Block ID/type/text
- effective speakerがあればspeaker名
- Term名称一覧

前後Scene全文、作品あらすじ、ジャンルは渡さない。対象Scene自体の読み味を分類する。

## 6. function定義

| label | 判定基準 |
|---|---|
| daily | 日常行動・雑談・通常生活が中心 |
| setup | 後続展開の前提・準備 |
| dialogue | 会話そのものがScene推進の中心 |
| exposition | 設定・背景・知識伝達が中心 |
| meeting | 会議・協議・正式打合せ |
| investigation | 情報収集・推理・検証 |
| travel | 移動そのものが主要活動 |
| introspection | 内面思考・自己評価が中心 |
| conflict | 対立・交渉・口論 |
| action | 身体的行動・戦闘・追跡等 |
| transition | 時間/場所/章の橋渡し |
| reveal | 重要情報の明示 |
| payoff | 前段準備/伏線の成果が中心 |
| other | 上記以外の明確な機能 |
| unclear | 十分な判定材料がない |

会話率等の数値だけでfunctionを決めない。

## 7. pace / information_load

pace:

- slow: 内省・詳細描写・長い説明が多く状態変化が少ない
- medium: 中間
- fast: 短いやり取り/行動/状態変化が連続
- unclear: 混在し単一判定が不安定

information_load:

- low: 既知前提の会話/行動中心
- medium: 数個の新情報
- high: 複数の固有概念・因果説明が集中
- unclear: 判定不能

Term情報は補助signal。Term analyzerを必須依存にしない。

## 8. POV

```text
pov_mode = first_person | third_limited | omniscient | objective | unclear
pov_entity_id nullable
confidence
```

Entity未解決でもmodeは保存可能。Scene内POV shiftはannotationとして残す。

## 9. Block semantics

narration/monologueのprimary category:

```text
action
description
exposition
psychology
transition
other
unclear
```

secondary tags:

```text
sensory
worldbuilding
backstory
emotion
reasoning
summary
foreshadowing
```

構成比はprimaryだけを使う。`unclear` はsemantic ratioのカテゴリ分子へ入れない。

dialogueは別 `dialogue_function` annotation:

```text
casual
information
question
exposition
conflict
command
emotional
other
unclear
```

multi-label可。v1必須metricにはしない。

## 10. Scene Boundary Analyzer

03 automatic base structure内のBlock境界を評価する。Analyzer IDは `scene-boundary-detector`。

出力:

```json
{
  "boundaries": [
    {
      "after_block_id": 55,
      "reasons": ["time_shift", "location_shift"],
      "confidence": 0.88
    }
  ]
}
```

reason:

```text
time_shift
location_shift
pov_shift
participant_reset
context_reset
```

09 `AnalysisPolicy.scene_boundary_auto_apply` 以上は03がsemantic StructureRevisionへ自動materializeする。初期default 0.85。

`scene_boundary_candidate_min` 以上/auto_apply未満はproposalとして保存する。初期default 0.60。proposalをReviewItemへ自動投入する必要はなく、Structure画面で「候補表示」を選択した場合に表示する。

## 11. Confidence policy

正本は09 AnalysisPolicy。

初期default:

```text
scene_label_effective = 0.80
block_semantic_effective = 0.75
scene_boundary_auto_apply = 0.85
scene_boundary_candidate_min = 0.60
```

threshold未満の判定はraw inferenceとして保持する。threshold未満を強制的に`other`へ置換しない。effective viewでは`unclear`を返す。

## 12. Chunking

Sceneが30,000 code pointsを超える場合:

- Block境界で最大15,000 code pointsのchunk
- 各chunk分類
- function/toneはconfidence付き候補を統合
- pace/information_load/interactionはchunk summaryからreduce call
- POV矛盾は`unclear`

provider tokenizerへ依存せずcode pointで分割する。

Scene Boundary Analyzerはbase Sceneごとに処理し、30,000超では隣接chunk境界周辺Blockも重複contextとして含める。

## 13. Version

```text
scene-semantic-classifier v1
block-semantic-classifier v1
pov-classifier v1
scene-boundary-detector v1
scene-taxonomy-v1
```

taxonomy変更はtaxonomy versionを上げる。

## 14. テスト

- 日常会話
- 設定説明
- 会議
- 内省
- action
- travel
- reveal
- dialogueだがexposition主体
- conflictだが会話率低
- unclear分類
- POV shift
- boundary high-confidence自動適用
- boundary middle-confidence proposal
- boundary low-confidence破棄

Model精度は14のevaluationで追跡し、CIではschema/invariantをgateする。

## 15. Codex実装時の禁止事項

- Sceneを単一scene_typeへ縮約しない。
- functionを数値heuristicだけで決めない。
- LLMがStructureRevision rowを直接編集しない。
- block secondary tagを構成比で二重カウントしない。
- 判断不能結果を無理に`other`へ確定しない。
- boundary proposalごとにReviewItemを自動生成しない。