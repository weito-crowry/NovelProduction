# 07 Style Metrics 詳細設計

## 1. 目的

文体特徴を再現可能なMetricとして計測する。Metric計算はCOREの決定論的処理とし、式・対象Scope・Version・`sample_count`の意味を明示する。

上位仕様は `../basic-design.md`。

## 2. Metric Group

```text
style-metrics-basic
style-metrics-semantic
```

BasicはStructureRevisionだけで計算し、Speaker/Entity/Term/Semantic Annotationを読まない。

SemanticはCurrent Dependency Run + 10 Effective Viewから得られるSpeaker、Term Novelty/Explanation、Block Primary Semanticを使う。

Scene Function/Tone/Pace/InformationLoad/Interaction/POVはMetric入力にしない。08/11 selector/filter用途。

## 3. MetricDefinition

```python
@dataclass(frozen=True)
class MetricDefinition:
    name: str
    version: int
    unit: str
    value_type: Literal["int", "float"]
    scope_types: tuple[Literal["document", "scene", "character"], ...]
    group: Literal["basic", "semantic"]
    description: str
    zero_width_tolerance: float | None
```

MetricDefinitionはv1ではCode Registryを正本としDB Tableを作らない。

MissingはNULL値MeasurementではなくMeasurement Row不存在で表現する。

式、対象集合、分母、Bridge Rule、許可Scope等を変更したらMetric Versionを上げる。

## 4. Metric Scope Matrix

LunaはMetric名からScopeを推測せず、次をMetricDefinitionへそのまま登録する。

| Metric | document | scene | character |
|---|:---:|:---:|:---:|
| `text.char_count` | yes | yes | no |
| `sentence.len.p50/p90` | yes | yes | no |
| `block.len.p50/p90` | yes | yes | no |
| `paragraph.len.p50/p90` | yes | yes | no |
| `dialogue.char_ratio` | yes | yes | no |
| `dialogue.utterance_count` | yes | yes | no |
| `dialogue.utterance_len.p50/p90` | yes | yes | no |
| `dialogue.turn_count.p50/p90` | yes | yes | no |
| `narration.run_len.p50/p90` | yes | yes | no |
| `semantic.*.char_ratio` | yes | yes | no |
| `speaker.utterance_count` | no | no | yes |
| `speaker.utterance_len.p50/p90` | no | no | yes |
| `speaker.question_ratio` | no | no | yes |
| `speaker.consecutive_turns.p50` | no | no | yes |
| `term.new_per_1000_chars` | yes | yes | no |
| `term.explained_same_scene_ratio` | yes | yes | no |
| `term.explanation_delay.p50/p90` | yes | yes | no |

Scene ScopeのTerm Metricは「Work/Document First Appearance MentionがそのScene内に存在するTerm」だけをそのSceneの分子/観測へ含める。

Character Metricはv1でDocument全体人物単位だけ。Scene×Character Measurementは作らない。

## 5. 共通文字数 / Percentile

`metric_char_count(text)` = `str.isspace()==False`のUnicode Code Point数。句読点、括弧、記号は含める。

Percentile:

```text
valuesを昇順Sort
index = (n - 1) * q
floor/ceil間をlinear interpolation
```

観測0件ならPercentile Measurementを作らない。

## 6. Character Target Enumeration

Target IDはStyle Entity ID。

対象Entity:

```text
Enabled Person Entity
AND
Current Structure内で
  Effective Mentionが1件以上
  OR Effective Speakerが1件以上
```

Reference Work Scope Entityでも、そのEpisodeにCurrent Mention/SpeakerがなければそのDocumentにCharacter Measurementを作らない。

登場Mentionはあるが発言0件の場合:

```text
speaker.utterance_count = 0
sample_count = 1
```

は有効。Utterance Length/Question Ratio/Consecutive Turnsは観測なしなので作らない。

## 7. Basic Length Metric

```text
text.char_count
sentence.len.p50
sentence.len.p90
block.len.p50
block.len.p90
paragraph.len.p50
paragraph.len.p90
```

- `text.char_count`: Scope内Dialogue+Narration Block文字数合計。Heading/Separator/Unknown除外。対象Block 0件でも0を保存可。
- `sentence.len`: Scope内Dialogue/Narration Sentenceを1観測。
- `block.len`: Scope内Dialogue/Narration Blockを1観測。
- `paragraph.len`: `paragraph_index`でGroupし、同ParagraphのDialogue/Narration文字数合計を1観測。Heading/SeparatorだけのParagraphは観測外。

## 8. Dialogue Metric

```text
dialogue.char_ratio
dialogue.utterance_count
dialogue.utterance_len.p50
dialogue.utterance_len.p90
dialogue.turn_count.p50
dialogue.turn_count.p90
```

`dialogue.char_ratio`:

```text
sum(dialogue chars) / sum(dialogue+narration chars)
```

分母0ならMeasurementなし。Dialogue 0件かつ分母>0なら有効0。

`utterance_count`はDialogue Block件数。0件も有効Count。

`utterance_len`はDialogue Blockを1発言とし、外側`「」`1組だけ除いて長さを測る。

### Conversation Run / turn_count

同一Scene内:

1. 連続Dialogueは同Run。
2. Dialogue間にNarration 1 Blockだけで40 chars以下ならBridge。
3. Narration 41 chars以上、Narration連続2件、Heading/Separator/Unknown、Scene境界で終了。

`dialogue.turn_count`はRun内Dialogue Block数。Speaker交替数ではない。

40 chars Rule変更時はMetric Version Up。

## 9. Narration Run

```text
narration.run_len.p50
narration.run_len.p90
```

同一Scene内の連続Narration Block文字数合計を1観測。Dialogue/Heading/Separator/Unknown/Scene境界で終了。

## 10. Semantic Composition

```text
semantic.action.char_ratio
semantic.description.char_ratio
semantic.exposition.char_ratio
semantic.psychology.char_ratio
semantic.transition.char_ratio
```

06 Effective `block.semantic_primary`を使う。

分子: 該当PrimaryのNarration Block chars。

分母: ScopeのDialogue+Narration Block chars。

`other/unclear`は分子外。Dialogueは分母に入るため比率合計は1未満になり得る。

Current Block Primaryが`source=unknown`のNarration Blockが1件でもある場合、そのDocument/SceneのComposition Ratioは作らない。

Narration Blockが0件で分母>0の場合、各Composition Ratioは有効0。

## 11. Speaker Metric

```text
speaker.utterance_count
speaker.utterance_len.p50
speaker.utterance_len.p90
speaker.question_ratio
speaker.consecutive_turns.p50
```

Section 6 Eligible Characterごとに算出する。

Current Effective SpeakerがそのEnabled Person Entityへ確定したDialogueだけ発言観測に使う。

`question_ratio` = 外側閉じ括弧除外後末尾が`?`/`？`の発言数 / Speaker確定発言数。分母0ならRowなし。

`consecutive_turns` = Section 8 Conversation Run内の同一Speaker連続Dialogue Block数。Unknown SpeakerはStreakを切る。Bridge NarrationはStreakへ加算しない。

## 12. Term Metric

```text
term.new_per_1000_chars
term.explained_same_scene_ratio
term.explanation_delay.p50
term.explanation_delay.p90
```

05 `first_appearance_complete=true` のTargetだけ生成する。

- Reference: Work Prefix Complete。
- Project: Target Text/Structure Term Resolver Succeeded。

Eligible Novelty:

```text
work_specific
specialized_real_world
```

`new_per_1000_chars` = Eligible First Term数 / Dialogue+Narration chars ×1000。分母0ならなし。Eligible Term 0件は有効0、`sample_count=0`。

Scene Scopeでは、そのSceneにFirst Appearance Mentionを持つEligible Termだけを分子へ含め、分母はそのSceneのDialogue+Narration chars。

`explained_same_scene_ratio` = Effective Sufficient ExplanationありEligible First Term数 / Eligible First Term数。分母0ならなし。

Scene Scopeでは、そのSceneにFirst Appearance Mentionを持つEligible Termだけを分母へ含める。

`explanation_delay`はExplanationありEligible First Termだけ観測。Scene ScopeではFirst Appearance Mentionが対象Scene内のTermだけ。説明なしTermをDelay=0にしない。

## 13. Semantic Metric Partial Policy

`style-metrics-semantic`はDependencyを`subject_partial_allowed`で利用できるがMetricごとにCompleteness判定する。

- Speaker Metric: Section 6 Eligible Character + Current Effective Speakerで算出。
- Semantic Composition: Scope内Narration Block Primaryが全件`source != unknown`必須。
- Term First Appearance Metric: 05 Completeness必須。

Run Status:

- 実行対象Metricがすべて正常算出または仕様上Not Applicable -> `succeeded`。
- 1件以上Measurement生成 + 必要Input不足で生成できないMetricあり -> `partial`。
- Measurement 0件かつ必要Input Branchがすべて利用不能 -> `failed`。

## 14. Measurement Schema / sample_count

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

MetricDefinitionに従いValueはReal/Intの片方だけ非NULL。Missing Rowは作らない。

`sample_count`:

- Scalar Count/Char Count: 1。
- Percentile: 元観測数。
- Dialogue/Semantic char ratio: 分母に寄与したAnalyzable Block数。
- Speaker question ratio: Speaker確定発言数。
- Term ratio: Eligible First Appearance Term数。

## 15. State / Policy Dependency

09 `style-metrics-semantic` State Input:

```text
metric_effective_state
term_first_appearance
```

`metric_effective_state`:

- Speaker Correction/Review。
- Term Novelty Correction/Review。
- First Appearance TermMention Explanation Correction/Review。
- Block Primary Correction/Review。

Entity/Term EnabledはRegistry→Resolver Dependency経路だけ。Scene Axis/POVも含めない。

Semantic Metric Policy Input:

```text
speaker_effective
term_explanation_effective
block_semantic_effective
```

## 16. Zero-width Tolerance

初期値:

```text
ratio: 0.02
length: 5 chars
count: 1
term.new_per_1000_chars: 0.2
term.explanation_delay: 10 chars
```

MetricDefinitionへ保持する。

## 17. Test

- MetricDefinition Scope Matrix完全一致。
- Profile ValidationがMetric Scope Matrixを利用。
- Basic Metric Semantic State非依存。
- MetricDefinition value_typeはint/floatのみ、Missing Row不存在。
- Sentence/Block/Paragraph対象集合。
- Dialogue0件 Count/Ratio。
- Dialogue Bridge40-41/Narration Run。
- Character対象はCurrent Mention/SpeakerのあるEntityだけ。
- 非登場Reference EntityへCharacter Rowなし。
- Mentionのみ人物 -> utterance_count=0、他Speaker Metricなし。
- Semantic Composition source=unknownでなし / Narration0で0。
- Speaker Streak/Question Ratio。
- Prefix Complete/Incomplete Term Metric。
- Project Resolver PartialでTerm Metricなし。
- Scene Scope Term MetricはFirst Appearance Sceneだけに計上。
- Eligible Term0件new_per_1000=0。
- 説明なしTermはRatio分母/Delay sample外。
- sample_count。
- Scene Axis変更でMetric State不変。

## 18. Codex禁止事項

- Metric Scopeを名前から推測。
- Basic MetricへSemantic依存追加。
- Nullable Value MeasurementでMissingを表現。
- 全Work Entityへ全Episode Character Measurement生成。
- Scene×Character Measurement追加。
- Dialogue turn_countをSpeaker交替数として実装。
- source=unknown Blockを`unclear`扱いしてComposition算出。
- Partial Term Resolverから初出Metric作成。
- Scene Term Metricへ別Scene初出Termを混入。
- 説明なしTermをDelay=0扱い。
- Missingを0へ変換。
- Ratioを0〜100保存。
