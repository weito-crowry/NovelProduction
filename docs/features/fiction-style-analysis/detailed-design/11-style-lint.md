# 11 Style Lint 詳細設計

## 1. 目的

自作品のMeasurementを選択したStyleProfileと比較し、差分を `Finding` として提示する。Lintは文章の優劣を断定せず、「参照基準からどの程度外れているか」と根拠spanを示す。

上位仕様は `../basic-design.md`。

## 2. 実装先

```text
CORE/src/novel_core/style_analysis/
  lint_models.py
  lint_repository.py
  lint_service.py
  evidence_service.py
```

文章自動修正機能は実装しない。

## 3. Lint入力

必須:

```text
project document_id
text_revision_id
structure_revision_id
profile_id/profile_version
metric analysis run
```

project draftが解析後に更新されていても、Lintは指定TextRevisionに対して実行する。最新draftへ自動読み替えしない。

## 4. StyleRule適用

Ruleは08のscope selectorで対象scopeを選ぶ。

適用順:

1. global rule
2. Scene label rule
3. character rule

同一metricへ複数ruleが適用される場合、よりspecificなruleを優先する。

specificity:

```text
character > multi-axis scene selector > single-axis scene selector > global
```

同specificityで競合するRuleはprofile validation errorとし、Lintを開始しない。

## 5. Range判定

Ruleにmin/maxがある場合:

- `min <= observed <= max`: Findingなし
- 下回る: lower deviation
- 上回る: upper deviation

preferredは表示用であり、preferredから外れただけではFindingを作らない。

片側rangeも許可する。

## 6. Deviation score

severity計算用のnormalized deviationを以下で定義する。

通常range幅 > 0:

```text
upper: (observed - max) / (max - min)
lower: (min - observed) / (max - min)
```

zero-width range `min == max`:

metric unitごとのabsolute toleranceを使う。

```text
ratio: 0.02
chars: 5.0
count: 1.0
per_1000_chars: 0.2
other float: max(abs(preferred)*0.05, 0.01)
```

```text
deviation = excess / tolerance
```

## 7. Severity

rule `severity_policy` default=`standard`。

standard:

| deviation | severity |
|---:|---|
| <= 0 | none |
| >0〜0.25 | info |
| >0.25〜0.75 | warning |
| >0.75 | strong_warning |

weightはseverity thresholdへ掛けない。Findingのsort scoreに使用する。

```text
sort_score = deviation * rule.weight
```

UIで `strong_warning` を「重大な文章欠陥」等と表示しない。「参照範囲から大きく外れています」とする。

## 8. Finding

```text
id
lint_run_id
rule_id
target_type
target_id
metric_name
observed_value
expected_min nullable
expected_max nullable
preferred_value nullable
deviation
severity
sort_score
explanation_code
evidence_json
created_at
```

explanation_code例:

```text
above_reference_range
below_reference_range
insufficient_dialogue
long_narration_run
high_exposition_ratio
high_new_term_density
long_term_explanation_delay
```

explanation textはUI側でcodeから定型生成し、LLMへ再説明させない。

## 9. Evidence span

Findingごとに最大5span。

### 長いnarration run

該当runのstart/end span。

### exposition ratio

長いexposition blockをchar数降順で最大5件。

### new term density

該当Scene内のeligible初出Term mention span最大5件。

### explanation delay

Term初出spanとfirst sufficient explanation span。

### dialogue ratio

作品/Scene全体の率だけでは局所evidenceが一意でないため、spanなしでもよい。その場合 `evidence_kind=scope_metric`。

## 10. Lint scope

実行単位:

```text
document whole
specific scene
```

複数episode一括Lintはv1でUIから順次job作成する。1runに複数documentを入れない。

## 11. Missing metric

Rule対象Metricが存在しない場合:

- Findingを作らない
- lint run warningへ `METRIC_UNAVAILABLE:{metric}` を追加
- Lint全体はpartialではなくsucceeded with warnings

profile rule全体の50%以上がmissingの場合は `LINT_INSUFFICIENT_ANALYSIS` でfailed。

## 12. Staleness

Lint結果にはinputのTextRevision/Draft IDを表示する。

現在のlatest draft IDが異なる場合APIは `stale=true` を返すが、旧Findingを削除しない。

UIはstale Lintを明示し、「最新本文を解析して再Lint」操作を提供する。

## 13. 推奨文言

初期Lintは数値的な指摘だけにする。生成的な書き換え提案はしない。

許可例:

```text
このSceneの説明文比率は42%で、参照範囲18〜31%を上回っています。
最長の説明Blockは286文字です。
```

禁止例:

```text
この段落を以下のように書き換えてください: ...
```

将来Writing Guidanceを追加する場合は別詳細設計を作る。

## 14. Finding抑制

ユーザーはFindingを `acknowledged` または `ignored` にできる。元Findingは不変。

`style_finding_reviews`:

```text
finding_id
status = acknowledged | ignored
note
created_at
```

同一TextRevision/Profileで再Lintした際、同じrule+target+evidence fingerprintならignored状態を表示継承してよい。別revisionへ自動継承しない。

## 15. Sort

default:

```text
strong_warning
warning
info
```

同severity内は `sort_score DESC, target order ASC, id ASC`。

## 16. API返却

Finding listには全文を含めない。

```text
finding metadata
metric values
up to 5 excerpt objects
```

excerptはEvidenceServiceが最大400 code points/件で切り出す。

## 17. テスト

- range内Findingなし
- min/max上下
- zero-width tolerance
- boundaryちょうどはFindingなし
- specificity優先
- 同specificity競合error
- weightはseverityを変えない
- evidence最大5
- missing metric warning
- missing 50%以上failed
- stale detection
- ignored継承は同revisionのみ

## 18. Codex実装時の禁止事項

- 総合「文章品質スコア」を追加しない。
- Lint結果を自動修正へ接続しない。
- preferredとの差だけでwarningにしない。
- profile外の独自heuristic警告を勝手に追加しない。
- stale結果をlatestとして表示しない。
- 作品本文の長い引用をFinding recordへ複製しない。
