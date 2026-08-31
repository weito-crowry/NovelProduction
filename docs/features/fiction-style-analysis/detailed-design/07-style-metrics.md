# 07 Style Metrics 詳細設計

## 1. 目的

文体特徴を再現可能な数値として計測し、作品・episode・scene・character・corpus単位の比較に利用する。Metricは定義とversionを固定し、同名metricの意味を後から変えない。

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

metric計算はCORE内の決定論的処理とし、LLMを直接呼ばない。LLM由来annotationは入力として参照してよい。

## 3. 文字数共通定義

`metric_char_count(text)` を1箇所に実装する。

```text
Unicode code pointのうち `str.isspace()` がfalseの文字数
```

改行、ASCII space、全角空白等のwhitespaceは文字数から除外する。句読点・括弧・記号は含める。

本文scopeの `analyzable_chars` は `dialogue/narration/monologue` blockのmetric_char_count合計。heading/separator/unknownは分母から除外する。

## 4. MetricDefinition

コード上のregistryを正本とする。DBへ定義masterを重複保存しない。

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
```

Measurementには `metric_name` と `metric_version` を保存する。

metric式変更時はversionを上げる。旧Measurementを上書きしない。

## 5. 初期必須Metric

### length

```text
text.char_count
sentence.len.p50
sentence.len.p90
block.len.p50
block.len.p90
paragraph.len.p50
paragraph.len.p90
```

paragraphは03の原paragraph境界hintから生成したblock groupを使う。hintがなければblock単位をparagraphとして扱う。

### dialogue

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

### term load

```text
term.new_per_1000_chars
term.explained_same_scene_ratio
term.explanation_delay.p50
term.explanation_delay.p90
```

### character/speaker

```text
speaker.utterance_count
speaker.utterance_len.p50
speaker.utterance_len.p90
speaker.question_ratio
speaker.consecutive_turns.p50
```

character metricはspeaker effective viewが確定した発言だけを使う。

## 6. dialogue.char_ratio

式:

```text
sum(dialogue block chars) / analyzable_chars
```

analyzable_chars=0ならNULL。百分率へ変換せず0.0〜1.0 ratioで保存する。

## 7. utterance length

対象blockの外側 `「` `」` が存在する場合だけ、その1組を除いてmetric_char_countする。内側の句読点やnested quoteは含める。

空発言は0として観測値に含める。

p50/p90はnearest-rankではなくPython標準ライブラリだけで再現可能なlinear interpolationを独自実装する。定義:

```text
sorted values, index=(n-1)*q
lower=floor(index), upper=ceil(index)
value=lower_value + fraction*(upper_value-lower_value)
```

整数観測でもpercentile結果はfloat。

## 8. Dialogue turn

連続dialogue blockのまとまりをconversation runとする。

- narration blockが間に1件入っても、そのnarrationが40 chars以下かつspeaker attributionのadjacent_action evidenceとして使われている場合はconversationを継続する。
- それ以外のnarration、separator、scene境界でrun終了。

`turn_count` はrun内のspeaker確定済みdialogue block数。speaker unknownも発言としてturn数には数えるが、speaker transition分析には使わない。

## 9. Narration run length

連続する `narration + monologue` blockのchar数合計を1runとする。dialogue、heading、separator、scene境界で区切る。

semantic primaryが異なってもrunは分割しない。

## 10. semantic ratio

06 Block primary semanticのeffective値がconfidence thresholdを満たすblockだけ分類する。

式:

```text
category chars / analyzable_chars
```

unknown/other blockはどのcategoryにも入らないため5ratioの合計は1未満になり得る。無理に正規化しない。

## 11. question ratio

speaker別:

```text
発言末尾（閉じ括弧除外後）が `?` `？` の発言数 / speaker確定発言数
```

疑問文を文法解析しない。

## 12. term metric

`new_per_1000_chars`:

```text
eligible first term mentions / analyzable_chars * 1000
```

05で定義した `work_specific` と `specialized_real_world` のみeligible。

`explained_same_scene_ratio`:

```text
同Scene内にsufficient explanationがあるeligible初出Term数 / eligible初出Term数
```

分母0はNULL。

Explanation delayは05定義のcode point差。NULL値はpercentileから除外する。

## 13. Scope

Measurement target:

```text
document
episode
scene
character
```

work/corpus統計は08 Aggregateで計算する。Metric計算時にcorpusを直接参照しない。

project draftのdocument metricとreference episode metricは同じ式を使用する。

## 14. Measurement永続化

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

valueは型に応じて片方だけ使用。CHECKで同時設定を禁止する。

`sample_count` はpercentile/ratioの元観測数。char_ratioの場合は対象block数ではなく、metric定義に従い `sample_count=analyzable_chars` とするのではなく、block/utterance等の離散sample数を保存する。単純char_countは1。

## 15. 不完全semantic入力

semantic/speaker/term依存metricは、必要Analyzerが未完了ならMeasurement自体を作らない。0やNULLで「解析済みだがゼロ」と混同しない。

APIはmissing metricとnull metricを区別する。

## 16. Profile利用条件

08 profile生成対象となるMeasurementは以下を満たすものだけ。

- AnalysisRun succeeded
- effective structureを参照
- semantic依存metricはconfidence policy通過
- manual override反映後のeffective viewから再計算済み

override後に旧Measurementをそのまま使わない。

## 17. Test

metricごとに式を直接検証するfixtureを作る。

必須:

- whitespace除外char count
- dialogue ratio 0/1/混在
- analyzable chars 0
- percentile n=1/2/奇数/偶数
- nested quote utterance
- short adjacent actionを挟むconversation
- long narrationでconversation終了
- semantic otherを分母に残す
- term分母0
- speaker unknown混在
- override後recompute

外部LLMをmetric testから呼ばない。

## 18. Codex実装時の禁止事項

- 平均値だけ保存して分布を捨てない。
- metric定義をUI側で再実装しない。
- 率を0〜100でDB保存しない。
- semantic複数タグを二重カウントしない。
- missing analyzer結果を0として扱わない。
- metric式変更時にversion据え置きにしない。
