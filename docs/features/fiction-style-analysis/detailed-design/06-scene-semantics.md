# 06 Scene Semantics 詳細設計

## 1. 目的

Scene/Blockへ意味ラベルを付与し、局面別統計・StyleRule Selector・Lintを可能にする。Scene分類はMulti-axisを正本とし、**解析結果としての`unclear`** と **Current推論が存在しない`unknown`** を区別する。

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

## 3. Scene Taxonomy v1

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

### pace

```text
slow
medium
fast
unclear
```

### information_load

```text
low
medium
high
unclear
```

### interaction

```text
solo
dialogue
group_dialogue
crowd
mixed
unclear
```

Multi-selectで`unclear`はConcrete Labelと同時Effectiveにしない。

`other` = 分類可能だがTaxonomy外。

`unclear` = Current推論は存在するが判断不能。

`unknown` = Current推論/Manual値が存在しないEffective View状態でありTaxonomy Labelではない。

## 4. Raw Annotation

Axisごとに1 Annotation。

Multi-select:

```json
{"labels":[{"label":"daily","confidence":0.91},{"label":"dialogue","confidence":0.96}]}
```

Single-select:

```json
{"label":"medium","confidence":0.84}
```

`scene-semantic-classifier`入力:

- Scene Text。
- Block ID/type/text。

Entity/Term/Speaker/Genre/別Scene全文は入力しない。

## 5. Effective View共通順位

10を正本とし、Scene/Block/POVも次を使う。

```text
ManualOverride
> Confirmed Current Inference
> Current Eligible Inference
> Unknown/Default
```

Rejected Current InferenceはEffectiveにしない。

ConfirmedはConfidence Thresholdに関係なくRaw値を採用するが、Taxonomy/Schema Validationは必須。

Current Rawが存在しない、またはCurrent RawがRejectedされManual/Confirmed代替もない場合:

```text
source = unknown
value = null
```

## 6. Effective Function / Tone

Manual Set List:

- Known Labelのみ。
- 1件以上。
- 重複なし。
- `unclear` + Concrete同時禁止。

Confirmed Current Annotation:

- Raw Label集合をValidation。
- Concrete Labelが1件以上なら`unclear`除外。
- Concrete 0件なら`[unclear]`。

Unreviewed Current Raw:

1. `confidence >= AnalysisPolicy.scene_label_effective` のConcrete Labelだけ採用。
2. Concreteが1件以上なら`unclear`除外。
3. Concreteが0件だがRaw Annotationあり -> `[unclear]`, source=inferred。
4. Rawなし -> source=unknown/value=null。

## 7. Effective Single Axis

Pace/InformationLoad/Interaction:

- ManualOverride最優先。
- Confirmed Current -> Raw Labelを採用。
- Unreviewed Current Raw confidence >= `scene_label_effective` -> Raw Label。
- Unreviewed Current Rawはあるがthreshold未満 -> `unclear`, source=inferred。
- Rawなし/Rejectedのみ -> value=null, source=unknown。

## 8. POV

Raw:

```text
pov_mode = first_person | third_limited | omniscient | objective | unclear
pov_entity_id nullable
confidence
```

`pov-classifier` はEntity Resolverに`subject_partial_allowed`で依存し、04 `mention_resolution` Stateも入力に含める。

入力:

- Scene Text/Blocks。
- 同Scene Current Effective Mention Entity。
- Enabled Person Entity Name。

Effective:

- Manual Override。
- Confirmed Current。
- Unreviewed Current confidence >= `pov_effective`。
- Unreviewed Current confidence未満 -> mode=unclear/source=inferred。
- Rawなし/Rejectedのみ -> source=unknown、mode/entity null。
- Raw EntityがDisabled/Current Resolution外 -> Entity IDだけNULL。Modeは保持可。

POVはv1 Aggregate/Lint Selector対象外。

## 9. Block Primary Semantic

`block-semantic-classifier` は`block_type=narration`だけ。

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

Entity/Term/Speaker非依存。Dialogueは分類しない。

Effective:

- Manual `block.semantic_primary`。
- Confirmed Current。
- Unreviewed Current Raw + confidence >= `block_semantic_effective`。
- Unreviewed Current Rawありthreshold未満 -> unclear/inferred。
- Rawなし/Rejectedのみ -> value=null/source=unknown。

Secondary Tag/Dialogue Functionはv1で実装しない。

## 10. Scene Boundary Analyzer

Input: 03 Automatic Base Scene。OutputはBlock境界`after_block_id`だけ。

```json
{
  "after_block_id":55,
  "reasons":["time_shift","location_shift"],
  "confidence":0.88
}
```

Reason:

```text
time_shift
location_shift
pov_shift
context_reset
```

Entity/Speaker/Term非依存。

Validation:

- Input Base Scene所属。
- Scene末尾不可。
- Existing明示境界重複不可。
- Confidence 0..1。
- Known Reason 1件以上。

全Valid CandidateをRaw Annotation保存する。`scene_boundary_candidate_min`未満も保存する。

## 11. Boundary Policy

- `scene_boundary_auto_apply`: 03 Semantic Materializationにだけ使用。
- `scene_boundary_candidate_min`: API/UI Proposal表示下限にだけ使用。

Candidate Min変更でAnalysisRun/StructureをStaleにしない。

Raw Boundary AnalyzerはPolicy Threshold非依存。

## 12. Chunking

Scene >30,000 Code Points:

- Block境界で最大15,000 Code Points Chunk。
- Function/Tone: Labelごとmax confidence Reduce。
- Pace/InformationLoad/Interaction: Chunk SummaryからReduce Call。
- POV: Reduce Call。
- Block Primary: Block単位。

Chunkingで永続Structureを変更しない。

## 13. Aggregate / Lint State

Scene Axisは07 Semantic Metric入力ではない。

Function/Tone/Pace/InformationLoad/Interaction Correction/Review:

- Raw Scene Classifier Run非Stale。
- Semantic Metric非Stale。
- 08 Scene Filter State変更。
- 11参照Selector Axis Input変更。

POV Correctionはv1 Display-only。

Block Primary Correction/Reviewだけ07 Semantic Metricへ影響する。

## 14. Selector Matching

08/11共通:

- `source=unknown` -> Selector判定不能。
- Effective `unclear` -> 通常Taxonomy値としてMatch/Non-match。
- Multi-select Axis: Selector scalarはContains、Selector listはIntersection>=1。
- Single-select Axis: Equality、Selector listならIN。
- 複数AxisはAND。

## 15. Test

- Multi-select / unclear exclusivity。
- No Current Run -> source unknown/value null。
- Low Confidence Current -> unclear/inferred。
- Rejected Currentだけ -> unknown。
- Confirmed InferenceはThreshold未満でもValidation後採用。
- Manual unclearとunknown区別。
- Scene Classifier Registry非依存。
- POV mention_resolution State依存/threshold/Disabled Entity。
- Block Primary Narration only。
- Block Primary unknown vs unclear。
- Boundary all-valid save。
- Candidate Minはdisplay only。
- Scene Axis OverrideでMetric非Stale。
- Block Primary OverrideでMetric Stale。
- Selector unknown/unclear区別。

## 16. Codex禁止事項

- Current分類なしをTaxonomy `unclear`として保存/集計。
- Sceneを単一Typeへ縮約。
- Scene ClassifierへEntity/Term/Speaker入力。
- DialogueをBlock Primary分類。
- Secondary/Dialog Function追加。
- LLMから任意Character Offset Split。
- Candidate Minを保存Thresholdにする。
- Scene Axis修正だけでSemantic Metric再解析。
