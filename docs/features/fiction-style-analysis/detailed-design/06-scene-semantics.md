# 06 Scene Semantics 詳細設計

## 1. 目的

Scene/Blockへ意味ラベルを付与し、局面別に文体統計を比較できるようにする。Scene分類はmulti-axisを正本とし、判断不能を無理に既知labelへ押し込まない。Scene Boundary Analyzerは03が安全にmaterializeできるBlock境界候補だけを返す。

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

`unclear` は他labelと同時指定しない。`other` はtaxonomy外だが判定可能、`unclear` は判定不能。

## 4. Annotation形式

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

`style_annotations` にaxisごとに保存する。

## 5. Scene classifier入力

- Scene全文
- Block ID/type/text
- effective speaker名があればそれ
- Term名称一覧

前後Scene全文、あらすじ、ジャンルは渡さない。

## 6. function定義

| label | 判定基準 |
|---|---|
| daily | 日常行動・雑談・通常生活が中心 |
| setup | 後続展開の前提・準備 |
| dialogue | 会話自体がScene推進の中心 |
| exposition | 設定・背景・知識伝達が中心 |
| meeting | 会議・協議・正式打合せ |
| investigation | 情報収集・推理・検証 |
| travel | 移動そのものが主要活動 |
| introspection | 内面思考・自己評価が中心 |
| conflict | 対立・交渉・口論 |
| action | 身体行動・戦闘・追跡等 |
| transition | 時間/場所/章の橋渡し |
| reveal | 重要情報の明示 |
| payoff | 前段準備/伏線の成果が中心 |
| other | 上記以外の明確な機能 |
| unclear | 十分な材料がなく判定不能 |

## 7. pace / information_load

pace:

- slow: 内省・詳細描写・長い説明が多く状態変化が少ない
- medium: 中間
- fast: 短いやり取り/行動/状態変化が連続
- unclear: 単一判定が不安定

information_load:

- low: 既知前提の会話/行動中心
- medium: 数個の新情報
- high: 固有概念・設定・因果説明が集中
- unclear: 判定不能

Term情報は補助signalであり必須依存にしない。

## 8. POV

```text
pov_mode = first_person | third_limited | omniscient | objective | unclear
pov_entity_id nullable
confidence
```

Entity未解決でもmode保存可。POV shift疑いはraw annotationで保持するだけでSceneを直接変更しない。

## 9. Block semantics

primary:

```text
action
description
exposition
psychology
transition
other
unclear
```

secondary:

```text
sensory
worldbuilding
backstory
emotion
reasoning
summary
foreshadowing
```

構成比はprimaryだけ。`other/unclear` はカテゴリ分子に入れない。

Dialogue function:

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

multi-label可、v1必須Metric外。

## 10. Scene Boundary Analyzer

Analyzer ID: `scene-boundary-detector`。

入力は03 automatic base StructureRevisionの**1 base Sceneずつ**。候補位置はそのScene内Block境界だけ。

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

validator:

- `after_block_id` が入力base Scene所属Blockであること。
- Scene末尾Blockは候補にしない。既にScene終端だからである。
- separator/heading由来既存境界へ重複candidateを作らない。
- confidence 0〜1。
- reasonはknown enum、最低1件。

invalid candidateだけを捨て、他候補は保持する。

## 11. Boundary Annotation

有効candidateは03と同じ契約で保存する。

```text
annotation_type = scene_boundary_candidate
subject_type = block
subject_id = after_block_id
analysis_run_id = boundary run
confidence = candidate confidence
value_json = {
  "base_structure_revision_id": 7,
  "reasons": ["time_shift"]
}
```

Runの `structure_revision_id` も同じbase revisionを指す。二重情報はmaterialize時の整合validationに使う。

## 12. Boundary適用

09 AnalysisPolicy:

```text
scene_boundary_auto_apply = 0.85
scene_boundary_candidate_min = 0.60
```

- >= auto_apply: 03 Semantic Structureへ自動materialize候補。
- candidate_min以上/auto_apply未満: proposalとして保存。
- candidate_min未満: DBへcandidate Annotationを保存しなくてよい。AnalysisRun output countにも含めない。

ReviewQueueへ自動追加しない。

## 13. Confidence policy

09 AnalysisPolicyが正本。

```text
scene_label_effective = 0.80
block_semantic_effective = 0.75
scene_boundary_auto_apply = 0.85
scene_boundary_candidate_min = 0.60
```

threshold未満Scene/Block分類はraw inferenceとして保存し、effective viewでは `unclear`。

## 14. Chunking / Reduce

Scene >30,000 code points:

- Block境界で最大15,000 code points chunk
- 各chunk分類
- function/toneはlabelごとに最高confidenceを採用しthreshold前のraw候補集合を作る
- `unclear` が1 chunkに出ただけで他labelを消さない
- 統合後、具体labelが1件以上残れば`unclear`を除く。具体labelが0なら`unclear`
- pace/information_load/interactionはchunk summaryからreduce callしsingle value
- POV矛盾は`unclear`

Boundary Analyzerは隣接chunk境界周辺Blockを重複contextとして含めてよいが、出力Block IDは一意dedupeする。

## 15. Version

```text
scene-semantic-classifier v1
block-semantic-classifier v1
pov-classifier v1
scene-boundary-detector v1
scene-taxonomy-v1
```

## 16. Test

- daily/exposition/meeting/introspection/action/travel/reveal/conflict
- unclear + otherの区別
- chunk reduceでconcrete labelとunclear混在
- POV shift
- boundary candidate Block membership
- Scene末尾candidate拒否
- invalid candidateのみdrop
- high candidate auto apply対象
- middle candidate proposal
- low candidate非保存
- Annotation contract/base structure一致

Model精度は14 evaluationで追跡しCIはschema/invariant gate。

## 17. Codex禁止事項

- Sceneを単一scene_typeへ縮約
- functionを数値heuristicだけで決定
- LLMがStructure rowを直接編集
- secondary tag二重カウント
- 判断不能を`other`へ強制
- boundary proposal全件ReviewItem化
- arbitrary character offset boundary
- `unclear` と具体labelの同時effective化