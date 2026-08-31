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

Metric計算は決定論的処理。LLM由来annotationは入力として参照してよい。

## 3. Metric実行グループ

Analysis Runtimeではmetricを2 Analyzerへ分ける。

```text
style-metrics-basic
style-metrics-semantic
```

### basic

StructureRevisionだけで計算可能。

- length
- dialogue ratio/utterance
- narration run

### semantic

Entity/Speaker/Term/Block semantics等のeffective resultが必要。

- semantic composition
- term load
- speaker/character

これによりsemantic analyzer未完了でも基本文体統計を利用できる。

## 4. 文字数定義

`metric_char_count(text)`:

```text
Unicode code pointのうち str.isspace() == false の文字数
```

句読点・括弧・記号は含める。

`analyzable_chars` は `dialogue/narration/monologue` Blockの合計。heading/separator/unknownは除外。

## 5. MetricDefinition

コードregistryを正本とする。

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

`zero_width_tolerance` は11 Lintで `min == max` の場合だけ使用する。Lint側でunit名から推測しない。

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

03 `Block.paragraph_index` を使用する。同じparagraph_indexのBlock char数を合計してparagraph length観測値とする。adapter hintがなければ02の空行定義から生成されたparagraph indexを使う。

## 8. dialogue.char_ratio

```text
sum(dialogue Block chars) / analyzable_chars
```

分母0はNULL。DBは0.0〜1.0。

## 9. utterance length / percentile

外側の `「` `」` が1組ある場合だけ除外してchar countする。内側句読点/nested quoteは含める。

percentileはlinear interpolation:

```text
sorted values
index = (n - 1) * q
lower = floor(index)
upper = ceil(index)
value = lower_value + fraction * (upper_value - lower_value)
```

結果はfloat。

## 10. Dialogue turn

連続dialogue Blockのまとまりをconversation runとする。

40 chars以下のnarrationが1件だけ間に入り、speaker attributionで `adjacent_action` evidenceとして使われている場合は同runを継続。それ以外のnarration、separator、Scene境界で終了。

`turn_count` はrun内dialogue Block数。speaker unknownもturn数へ含める。

## 11. Narration run

連続 `narration + monologue` Blockのchar数合計。dialogue、heading、separator、Scene境界で区切る。

## 12. Semantic ratio

06 effective primary semanticが有効なBlockだけカテゴリ分子へ入れる。

```text
category chars / analyzable_chars
```

`other/unclear` は分子に入らない。5ratio合計は1未満でもよい。

## 13. Speaker metric

speaker effective viewが確定したdialogueだけ人物別metricに使う。

question ratio:

```text
閉じ括弧除外後の発言末尾が ? または ？ の発言数 / speaker確定発言数
```

文法解析はしない。

## 14. Term metric

`new_per_1000_chars`:

```text
eligible first term mentions / analyzable_chars * 1000
```

eligibleは05 `work_specific` / `specialized_real_world`。

`explained_same_scene_ratio`:

```text
同Sceneにsufficient explanationがあるeligible初出Term数 / eligible初出Term数
```

分母0はNULL。delay NULLはpercentileから除外。

## 15. Scope

Measurement target:

```text
document
episode
scene
character
```

work/corpusは08 Aggregate。

## 16. Measurement

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

value columnは型に応じ片方だけ。

`sample_count` は「そのMeasurementを構成した離散観測数」とする。

- percentile: sentence/Block/utterance/run等の件数
- char ratio:対象カテゴリを含む/含まないを問わずanalyzable Block数
- term ratio: eligible Term数
- scalar char_count: 1

Aggregateでのsample countは別途「入力Measurement数」を保持するため、ここで文字分母を重複格納しない。

## 17. Partial semantic入力

`style-metrics-semantic` は必要Analyzerのeffective output coverageを確認する。

- document全体ratioの必須入力に欠落Sceneがある場合、そのdocument-level metricは作らない。
- 成功SceneについてのScene metricは作成可能。
- unknown speaker発言はcharacter metricから除外する。

missingを0/NULL Measurementで代用しない。

## 18. Profile利用

Aggregate対象は:

- succeeded basic metric run
- semantic metricは、対象scopeの必要入力がcompleteなMeasurement
- current effective StructureRevision
- ManualOverride反映後に再計算されたMeasurement

旧Measurementは削除しない。

## 19. 初期zero-width tolerance

MetricDefinitionへ明示する。例:

```text
dialogue.char_ratio: 0.02
semantic.*.char_ratio: 0.02
sentence/block/paragraph/utterance/run length: 5.0 chars
count系: 1.0
term.new_per_1000_chars: 0.2
term.explanation_delay: 10.0 chars
```

この値を変更する場合はMetricDefinition versionまたはLint policy versionを上げる。Codexがunitから新しい値を推測しない。

## 20. テスト

- whitespace除外char count
- paragraph index grouping
- dialogue ratio 0/1/混在
- analyzable chars 0
- percentile n=1/2/奇数/偶数
- nested quote utterance
- adjacent action conversation
- narration run
- semantic other/unclear
- term分母0
- speaker unknown
- semantic partial時document metric未生成/Scene metric生成
- override後recompute

## 21. Codex実装時の禁止事項

- 平均だけ保存して分布を捨てない。
- Metric式をUI側へ再実装しない。
- 率を0〜100でDB保存しない。
- semantic tagを二重カウントしない。
- missing analyzer結果を0として扱わない。
- basic metricをsemantic provider未設定で実行不能にしない。
- zero-width toleranceをLint側でunit名から推測しない。