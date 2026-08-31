# 07 Style Metrics 詳細設計

## 1. 目的

文体特徴を再現可能な数値として計測し、作品・Episode・Scene・Character・Corpus比較に利用する。Metric定義はversioned registryを正本とし、UIへ式を複製しない。

上位仕様は `../basic-design.md`。

## 2. 実装先

```text
CORE/src/novel_core/style_analysis/
  metric_models.py
  metric_registry.py
  metric_service.py
  metrics/
    __init__.py
    length_metrics.py
    dialogue_metrics.py
    semantic_metrics.py
    term_metrics.py
```

Metric計算は決定論的処理。LLM由来AnnotationはSemantic MetricだけがEffective Inputとして参照する。

## 3. Metric実行Group

```text
style-metrics-basic
style-metrics-semantic
```

### Basic

StructureRevisionだけで計算する。**Speaker/Entity/Term/Semantic Annotationを一切読まない。**

対象:

- Length
- Dialogue Ratio / Utterance
- Narration Run
- Conversation Run / Dialogue Turn Count

### Semantic

Effective Semantic Dataを入力にする。

- Semantic Composition
- Term Load
- Speaker / Character

Semantic Provider未設定でもBasic Metricは利用可能。

## 4. 文字数

`metric_char_count(text)`:

```text
Unicode code pointのうち str.isspace() == false
```

句読点・括弧・記号は含める。

`analyzable_chars` は `dialogue/narration/monologue` Block合計。Heading/Separator/Unknown除外。

## 5. MetricDefinition

```python
@dataclass(frozen=True)
class MetricDefinition:
    name: str
    version: int
    unit: str
    value_type: Literal["int", "float", "nullable_float"]
    scope_types: tuple[str, ...]
    required_inputs: tuple[str, ...]
    description: str
    zero_width_tolerance: float | None
```

Measurementは `metric_name + metric_version` を保存する。

## 6. 初期Metric

### Basic Length

```text
text.char_count
sentence.len.p50
sentence.len.p90
block.len.p50
block.len.p90
paragraph.len.p50
paragraph.len.p90
```

### Basic Dialogue / Rhythm

```text
dialogue.char_ratio
dialogue.utterance_count
dialogue.utterance_len.p50
dialogue.utterance_len.p90
dialogue.turn_count.p50
dialogue.turn_count.p90
narration.run_len.p50
narration.run_len.p90
```

### Semantic Composition

```text
semantic.action.char_ratio
semantic.description.char_ratio
semantic.exposition.char_ratio
semantic.psychology.char_ratio
semantic.transition.char_ratio
```

### Term

```text
term.new_per_1000_chars
term.explained_same_scene_ratio
term.explanation_delay.p50
term.explanation_delay.p90
```

### Speaker

```text
speaker.utterance_count
speaker.utterance_len.p50
speaker.utterance_len.p90
speaker.question_ratio
speaker.consecutive_turns.p50
```

## 7. Paragraph

03 `Block.paragraph_index` でgroupし、同ParagraphのBlock char数を合計する。

## 8. dialogue.char_ratio

```text
sum(dialogue Block chars) / analyzable_chars
```

分母0はNULL。DBは0〜1 ratio。

## 9. Utterance Length / Percentile

外側 `「` `」` が1組あればその1組だけ除外。内側句読点/Nested Quoteは含める。

Percentile:

```text
sorted values
index = (n - 1) * q
lower = floor(index)
upper = ceil(index)
value = lower_value + fraction * (upper_value - lower_value)
```

整数観測でもpercentile結果はfloat。

## 10. Basic Conversation Run / dialogue.turn_count

Conversation Runは**Structureだけ**から決める。

基本規則:

1. 同一Scene内の連続Dialogue Blockを1 Runとする。
2. Dialogue Block間にNarration Blockが1件だけ挟まる場合、そのNarrationが `metric_char_count <= 40` ならRunを継続する。
3. 2件以上連続Narration、40 chars超Narration、Monologue、Heading、Separator、Scene境界、UnknownでRun終了。
4. Narrationの意味・Speaker Attribution Evidenceは参照しない。

例:

```text
dialogue
narration 18 chars
dialogue
```

は1 Conversation Run。

```text
dialogue
narration 58 chars
dialogue
```

は2 Run。

`dialogue.turn_count` の1観測値はRun内Dialogue Block数。Speakerの同一/異同は見ない。

この40 chars bridge ruleを変更する場合は `dialogue.turn_count` Metric versionを上げる。

## 11. speaker.consecutive_turns.p50

Semantic Character Metric。

Conversation Runの切り方はSection 10の決定論的Runを再利用し、その中でEffective Speakerだけを参照する。

同一Effective Speakerが連続するDialogue Block数をStreakとする。

例:

```text
A, A, B, A, A, A, unknown, A
```

A:

```text
2, 3, 1
```

B:

```text
1
```

UnknownはStreakを切り、どのCharacter観測にも含めない。Bridge NarrationはRunを維持するだけでStreak数に加算しない。

Streak 0件ならMeasurementを作らない。

## 12. Narration Run

連続 `narration + monologue` Blockのchar数合計。Dialogue、Heading、Separator、Scene境界で区切る。

## 13. Semantic Ratio

06 Effective Primary SemanticだけCategory分子へ入れる。

```text
category chars / analyzable_chars
```

`other/unclear` は分子に入れない。合計1未満可。

## 14. Speaker Metric

Effective Speaker確定Dialogueだけ人物別Metricへ使用する。

Question Ratio:

```text
閉じ括弧除外後末尾が ?/？ の発言数 / Speaker確定発言数
```

## 15. Term Metric

Effective Termが `term.enabled=false` なら全Term Metric対象から除外する。

Eligible Novelty:

```text
work_specific
specialized_real_world
```

`new_per_1000_chars`:

```text
eligible first TermMention / analyzable_chars * 1000
```

`explained_same_scene_ratio`:

```text
同SceneにEffective Sufficient ExplanationがあるEligible初出Term数
/ Eligible初出Term数
```

分母0はNULL。Delay NULLはPercentile除外。

Term canonical label/typeのManualOverrideは表示・分類へ反映するが、Metric eligibilityは `enabled + novelty + explanation` を正本とする。

## 16. Scope

Measurement target:

```text
document
episode
scene
character
```

Work/Corpusは08 Aggregate。

## 17. Measurement

```text
id
analysis_run_id
structure_revision_id
target_type
target_id
metric_name
metric_version
value_real nullable
value_int nullable
sample_count
created_at
```

Valueは型に応じ片方だけ。

`sample_count`:

- Percentile: Sentence/Block/Utterance/Run/Streak件数
- Char Ratio: Analyzable Block件数
- Term Ratio: Eligible Term件数
- Scalar Char Count: 1

## 18. Partial Semantic Input

`style-metrics-semantic`:

- 必要Semantic Inputが欠けるSceneではその依存Scene Metricを作らない。
- Document-wide ratioに必要なSceneが欠けるならDocument Metricを作らない。
- Unknown SpeakerはCharacter Metricから除外。
- Disabled Entity/Termは対象から除外。

Missingを0/NULL rowで代用しない。

## 19. Profile利用

Aggregate対象は09 Effective AnalysisRun選択を通過したCurrent Measurementだけ。

- Basic: Current `style-metrics-basic` Run
- Semantic: Current `style-metrics-semantic` Runまたは利用可能なComplete Scene Measurement
- Current Effective StructureRevision
- ManualOverride反映後のRecompute済み結果

旧Measurementは削除しない。

## 20. Zero-width Tolerance

MetricDefinitionへ明示する。

```text
dialogue.char_ratio: 0.02
semantic.*.char_ratio: 0.02
sentence/block/paragraph/utterance/run length: 5.0 chars
count系: 1.0
term.new_per_1000_chars: 0.2
term.explanation_delay: 10.0 chars
```

変更時はMetricDefinitionまたはLint Policy Versionを上げる。

## 21. Test

- Whitespace Char Count
- Paragraph Grouping
- Dialogue Ratio
- Analyzable Chars 0
- Percentile n=1/2/odd/even
- Nested Quote
- Conversation Run: Dialogue連続
- Conversation Run: 40 chars以下NarrationでBridge
- Conversation Run: 41 chars以上Narrationで分断
- **Basic MetricがSpeaker/Semantic Annotationを読まない**
- A,A,B,A,A,A,unknown,A Streak
- Bridge NarrationでRun維持/Streak非加算
- Narration Run
- Semantic other/unclear
- Term enabled=false除外
- Term Effective Novelty/Explanation
- Speaker Unknown
- Semantic Partial Scope
- Override Recompute

## 22. Codex禁止事項

- 平均だけ保存
- Metric式をUIへ複製
- Ratioを0〜100保存
- Semantic二重カウント
- Missingを0扱い
- Basic MetricをSpeaker/Term/Semantic Annotation依存にする
- `dialogue.turn_count` Bridge判定へSpeaker Evidenceを持ち込む
- Zero-width ToleranceをLint側で推測
- `speaker.consecutive_turns.p50` をConversation全体Turn Countと混同
