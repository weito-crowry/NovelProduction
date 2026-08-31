# 07 Style Metrics 詳細設計

## 1. 目的

文体特徴を再現可能な数値として計測し、作品・episode・Scene・character・Corpus比較に利用する。Metric定義はversioned registryを正本とし、UIへ式を複製しない。

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

Metric計算は決定論的処理。LLM由来annotationはeffective inputとして参照してよい。

## 3. Metric実行グループ

```text
style-metrics-basic
style-metrics-semantic
```

### basic

StructureRevisionだけで計算可能。

- length
- dialogue ratio/utterance
- narration run
- dialogue run/turn count（speaker identityを使わない範囲）

### semantic

- semantic composition
- term load
- speaker/character

Semantic provider未設定でもbasic Metricは利用可能。

## 4. 文字数

`metric_char_count(text)`:

```text
Unicode code pointのうち str.isspace() == false
```

句読点・括弧・記号は含める。

`analyzable_chars` は `dialogue/narration/monologue` Block合計。heading/separator/unknown除外。

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

Measurementは `metric_name + metric_version` を保存。

## 6. 初期Metric

### basic length

```text
text.char_count
sentence.len.p50
sentence.len.p90
block.len.p50
block.len.p90
paragraph.len.p50
paragraph.len.p90
```

### basic dialogue/rhythm

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

### semantic composition

```text
semantic.action.char_ratio
semantic.description.char_ratio
semantic.exposition.char_ratio
semantic.psychology.char_ratio
semantic.transition.char_ratio
```

### term

```text
term.new_per_1000_chars
term.explained_same_scene_ratio
term.explanation_delay.p50
term.explanation_delay.p90
```

### speaker

```text
speaker.utterance_count
speaker.utterance_len.p50
speaker.utterance_len.p90
speaker.question_ratio
speaker.consecutive_turns.p50
```

## 7. Paragraph

03 `Block.paragraph_index` でgroupし、同paragraphのBlock char数を合計する。

## 8. dialogue.char_ratio

```text
sum(dialogue Block chars) / analyzable_chars
```

分母0はNULL。ratio 0〜1。

## 9. utterance length / percentile

外側 `「` `」` が1組あればその1組だけ除外。内側句読点/nested quoteは含める。

percentile:

```text
sorted values
index = (n - 1) * q
lower = floor(index)
upper = ceil(index)
value = lower_value + fraction * (upper_value - lower_value)
```

## 10. Conversation run / dialogue.turn_count

連続dialogue Block群をconversation runとする。

40 chars以下のnarrationが1件だけ間に入り、そのBlockがspeaker attributionで `adjacent_action` evidenceとして使われている場合はrun継続。それ以外のnarration、separator、Scene境界で終了。

`dialogue.turn_count` の1観測値はrun内のdialogue Block数。speaker unknownも1 turnとして数える。

p50/p90は全runのturn count分布。

## 11. speaker.consecutive_turns.p50

人物別Metric。conversation run内の**連続する同一effective speakerのdialogue Block数**をstreakとして数える。

例:

```text
A, A, B, A, A, A, unknown, A
```

Aのstreak観測値:

```text
2, 3, 1
```

B:

```text
1
```

`unknown` はstreakを必ず切り、どの人物の観測値にも含めない。短いadjacent-action narrationはconversation runを維持するがspeaker streak自体には加算しない。

`speaker.consecutive_turns.p50` は対象speakerのstreak長のp50。streak 0件ならMeasurementを作らない。

## 12. Narration run

連続 `narration + monologue` Blockのchar数合計。dialogue、heading、separator、Scene境界で区切る。

## 13. Semantic ratio

06 effective primary semanticだけカテゴリ分子へ入れる。

```text
category chars / analyzable_chars
```

`other/unclear` は分子に入らない。合計1未満可。

## 14. Speaker metric

effective speaker確定dialogueだけ人物別Metricへ使用。

question ratio:

```text
閉じ括弧除外後末尾が ?/？ の発言数 / speaker確定発言数
```

## 15. Term metric

eligible noveltyは05 Effective Viewの:

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
同Sceneにeffective sufficient explanationがあるeligible初出Term数 / eligible初出Term数
```

分母0はNULL。delay NULLはpercentile除外。

## 16. Scope

Measurement target:

```text
document
episode
scene
character
```

work/corpusは08 Aggregate。

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

valueは型に応じ片方だけ。

`sample_count` は元の離散観測数:

- percentile: sentence/Block/utterance/run/streak件数
- char ratio: analyzable Block件数
- term ratio: eligible Term件数
- scalar char_count: 1

## 18. Partial semantic input

`style-metrics-semantic`:

- 必要semantic inputが欠けるSceneではその依存Scene Metricを作らない。
- document-wide ratioに必要なSceneが欠けるならdocument Metricを作らない。
- unknown speakerはcharacter Metricから除外。

missingを0/NULL rowで代用しない。

## 19. Profile利用

Aggregate対象:

- succeeded basic Metric run
- semantic Metricは対象scopeの入力complete
- current effective StructureRevision
- Override反映後に再計算済み

旧Measurementは削除しない。

## 20. zero-width tolerance

MetricDefinitionへ明示する。

```text
dialogue.char_ratio: 0.02
semantic.*.char_ratio: 0.02
sentence/block/paragraph/utterance/run length: 5.0 chars
count系: 1.0
term.new_per_1000_chars: 0.2
term.explanation_delay: 10.0 chars
```

変更時はMetricDefinitionまたはLint policy versionを上げる。

## 21. Test

- whitespace char count
- paragraph grouping
- dialogue ratio
- analyzable chars 0
- percentile n=1/2/odd/even
- nested quote
- conversation run
- A,A,B,A,A,A,unknown,A consecutive streak
- adjacent actionでrun維持/streak非加算
- narration run
- semantic other/unclear
- term effective novelty/explanation
- speaker unknown
- semantic partial scope
- override recompute

## 22. Codex禁止事項

- 平均だけ保存
- Metric式をUIへ複製
- ratioを0〜100保存
- semantic二重カウント
- missingを0扱い
- basic Metricをprovider依存にする
- zero-width toleranceをLint側で推測
- `speaker.consecutive_turns.p50` をconversation全体turn countと混同