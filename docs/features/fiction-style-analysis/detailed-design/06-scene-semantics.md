# 06 Scene Semantics 詳細設計

## 1. 目的

Scene/Blockへ意味ラベルを付与し、局面別に文体統計を比較できるようにする。Scene分類はMulti-axisを正本とし、判断不能を無理に既知Labelへ押し込まない。Scene Boundary Analyzerは03がMaterializeできるBlock境界候補だけを返す。

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

## 3. Scene Taxonomy

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

`unclear` は他Labelと同時指定しない。`other` は分類可能だがTaxonomy外、`unclear` は判断不能。

## 4. Annotation形式

Multi-select:

```json
[
  {"label": "daily", "confidence": 0.91},
  {"label": "dialogue", "confidence": 0.96}
]
```

Single-select:

```json
{"label": "medium", "confidence": 0.84}
```

Axisごとに `style_annotations` へ保存する。

## 5. Scene ClassifierはEntity/Term非依存

`scene-semantic-classifier` はScene本文の読み味を分類するため、次だけを入力にする。

- Scene全文
- Block ID/type/text

Speaker名、Entity一覧、Term一覧、作品あらすじ、Genre、前後Scene全文を入力しない。

これによりEntity/Term Resolverの状態変更でScene Classifierを無駄にStale化しない。

## 6. Function定義

| Label | 判定基準 |
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
| unclear | 材料不足・混在で判断不能 |

## 7. Pace / Information Load

Pace:

- slow: 内省・詳細描写・長い説明が多く状態変化が少ない
- medium: 中間
- fast: 短いやり取り/行動/状態変化が連続
- unclear: 単一判定が不安定

Information Load:

- low: 既知前提の会話/行動中心
- medium: 数個の新情報
- high: 固有概念・設定・因果説明が集中
- unclear: 判断不能

Term Analyzer結果を補助Signalに使わない。Scene本文だけで判定する。

## 8. POV Classifier

POV:

```text
pov_mode = first_person | third_limited | omniscient | objective | unclear
pov_entity_id nullable
confidence
```

`pov-classifier` は `entity-resolver` に依存する。

入力:

- Scene Text/Blocks
- 同SceneのEffective Mention Entity
- Enabled Person EntityのEffective Name

Mode自体はEntity未解決でも判定可能。Entityが一意に解決できない場合は `pov_entity_id=NULL`。

POV Shift疑いはRaw Annotationで保持し、Structureを直接変更しない。

## 9. Block Semantics

`block-semantic-classifier` はBlock Text/Typeだけを入力とし、Entity/Term/Speakerに依存しない。

Primary:

```text
action
description
exposition
psychology
transition
other
unclear
```

Secondary:

```text
sensory
worldbuilding
backstory
emotion
reasoning
summary
foreshadowing
```

構成比はPrimaryだけ。`other/unclear` はカテゴリ分子に入れない。

Dialogue Function:

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

Multi-label可。v1必須Metric外。

## 10. Scene Boundary Analyzer

Analyzer ID: `scene-boundary-detector`。

入力は03 Automatic Base StructureRevisionの1 Base Sceneずつ。Candidate位置はそのScene内Block境界だけ。

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

Reason:

```text
time_shift
location_shift
pov_shift
participant_reset
context_reset
```

Boundary AnalyzerはEntity Resolver/Speaker/Termを入力にしない。本文の文脈だけで判定する。

Validation:

- `after_block_id` がInput Base Scene所属
- Scene末尾Blockは候補不可
- 既存Separator/Heading境界重複不可
- Confidence 0〜1
- Reason Known Enum >=1

Invalid CandidateだけDrop。

## 11. Boundary Annotation

```text
annotation_type = scene_boundary_candidate
subject_type = block
subject_id = after_block_id
analysis_run_id = boundary run
confidence
value_json = {
  "base_structure_revision_id": 7,
  "reasons": ["time_shift"]
}
```

Run `structure_revision_id` も同Base Revision。

## 12. Boundary適用

09 AnalysisPolicy:

```text
scene_boundary_auto_apply = 0.85
scene_boundary_candidate_min = 0.60
```

- >= Auto Apply: Semantic Structure Materialize対象
- Candidate Min以上/Auto Apply未満: Proposalとして保存
- Candidate Min未満: DB保存不要

ReviewQueueへ自動追加しない。

## 13. Confidence Policy

09 AnalysisPolicy正本:

```text
scene_label_effective = 0.80
block_semantic_effective = 0.75
scene_boundary_auto_apply = 0.85
scene_boundary_candidate_min = 0.60
```

Threshold未満Scene/Block分類はRaw Inferenceとして保存しEffective Viewでは `unclear`。

## 14. Chunking / Reduce

Scene >30,000 Code Points:

- Block境界で最大15,000 Code Points Chunk
- 各Chunk分類
- Function/Tone: Labelごと最高ConfidenceでRaw集合
- Concrete Labelが残れば`unclear`除外。Concrete 0なら`unclear`
- Pace/InformationLoad/Interaction: Chunk SummaryからReduce Call
- POV: Entity Resolver結果を参照しつつ矛盾時`unclear`

BoundaryはAdjacent Chunk ContextをOverlap可。Output Block IDはDedupe。

## 15. Human Overrideとの関係

Scene/Block Classifier Run自体はManual OverrideでStaleにしない。Raw Inferenceとして有効なまま保持する。

10 Scene Semantic OverrideはEffective Viewだけを変え、07 `style-metrics-semantic` のState Fingerprintを変化させてMetric再計算を促す。

POV Entity解決に影響するEntity Human State変更は09 `pov-classifier` Current判定へ反映する。

## 16. Version

```text
scene-semantic-classifier v1
block-semantic-classifier v1
pov-classifier v1
scene-boundary-detector v1
scene-taxonomy-v1
```

## 17. Test

- Daily/Exposition/Meeting/Introspection/Action/Travel/Reveal/Conflict
- Unclear vs Other
- Scene ClassifierがSpeaker/Entity/Term非依存
- Block ClassifierがSemantic Registry非依存
- Chunk Reduce
- POV Entity Resolver Dependency
- Disabled EntityはPOV Entity候補外
- Boundary Block Membership
- Scene末尾Candidate拒否
- Invalid CandidateだけDrop
- High Candidate Auto Apply
- Middle Candidate Proposal
- Low Candidate非保存
- Annotation Contract/Base Structure一致
- Scene OverrideでClassifier Run自体はStaleにならずMetricだけ再計算

## 18. Codex禁止事項

- Sceneを単一Scene Typeへ縮約
- Functionを数値Heuristicだけで決定
- Scene ClassifierへSpeaker/Entity/Termを暗黙入力
- Block ClassifierへEntity/Termを暗黙入力
- LLMがStructure Rowを直接編集
- Secondary Tag二重カウント
- 判断不能をOtherへ強制
- Boundary Proposal全件ReviewItem化
- Arbitrary Character Offset Boundary
- UnclearとConcrete Labelの同時Effective化
