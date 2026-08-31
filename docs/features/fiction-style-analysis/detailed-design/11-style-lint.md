# 11 Style Lint 詳細設計

## 1. 目的

自作品Measurementを選択したStyleProfileと比較し、差分を `Finding` として提示する。Lintは文章の優劣を断定せず、参照範囲との差・根拠・解析coverageを示す。

上位仕様は `../basic-design.md`。

## 2. 実装先

```text
CORE/src/novel_core/style_analysis/
  lint_models.py
  lint_repository.py
  lint_service.py
  evidence_service.py
```

自動書き換えはv1 scope外。

## 3. Lint入力

```text
project document_id
text_revision_id
structure_revision_id
profile_id
profile_version_no
basic/semantic metric run IDs
```

指定revisionを正本としlatest draftへ暗黙読み替えしない。

## 4. Rule適用

specificity:

```text
character
> multi-axis scene selector
> single-axis scene selector
> global
```

同metric/同specificityで複数enabled Ruleが競合する場合はProfile version作成時のvalidation errorとする。Lint開始時に初めて発見しない。

## 5. Range判定

- `min <= observed <= max`: Findingなし
- 下回る: lower deviation
- 上回る: upper deviation
- preferredだけから外れてもFindingなし
- min/max片側のみ可

## 6. Deviation

通常range幅 > 0:

```text
upper = (observed - max) / (max - min)
lower = (min - observed) / (max - min)
```

`min == max` は07 `MetricDefinition.zero_width_tolerance` を使う。

```text
deviation = abs(observed - boundary) / tolerance
```

MetricDefinitionにtoleranceがないzero-width RuleはProfile validation errorとする。Lint側でunitから値を推測しない。

## 7. Severity

`severity_policy=standard`:

| deviation | severity |
|---:|---|
| <= 0 | none |
| >0〜0.25 | info |
| >0.25〜0.75 | warning |
| >0.75 | strong_warning |

weightはsortだけに使う。

```text
sort_score = deviation * weight
```

UI文言は「参照範囲との差」として表示する。

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

初期explanation code:

```text
above_reference_range
below_reference_range
insufficient_dialogue
long_narration_run
high_exposition_ratio
high_new_term_density
long_term_explanation_delay
```

定型説明はCORE/APIでcode + metric dataから生成し、LLM callは不要。

## 9. Evidence

最大5span。

- narration run: run span
- exposition ratio: 長いexposition Block上位5
- new term density: eligible初出Term Mention上位5
- explanation delay: 初出 + sufficient explanation
- scope ratio: 一意spanがなければ `evidence_kind=scope_metric`

Finding rowへ本文excerptを複製しない。

## 10. Scope

```text
document whole
specific scene
```

複数episodeは1documentずつjob作成。

## 11. Missing metric / coverage

Rule対象Metricがない場合はFindingを作らずwarningへ追加する。

```text
METRIC_UNAVAILABLE:{metric}
```

「50%以上missingならfail」のような割合thresholdは設けない。LintRunは最後まで処理し、次を返す。

```text
enabled_rule_count
applicable_rule_count
missing_rule_count
coverage_ratio
```

`applicable_rule_count=0` でもrun自体は `succeeded`。UIは「比較可能なMetricがありません」と表示する。分析不足とシステム障害を混同しない。

## 12. Staleness

LintRunはinput TextRevision/Draft IDを保持する。latest draftが異なればAPI `stale=true`。

旧Findingは削除しない。UIから最新本文capture/analyze/lintへ進める。

## 13. Finding review

`style_finding_reviews`:

```text
finding_id
status = acknowledged | ignored
note nullable
created_at
```

同一TextRevision/ProfileVersionかつ同rule+target+evidence fingerprintならreview状態を表示継承してよい。別revisionへ継承しない。

## 14. Sort

```text
strong_warning
warning
info
```

同severityは `sort_score DESC, target order ASC, id ASC`。

## 15. API返却

Finding list:

```text
finding metadata
metric values
最大5 excerpt
```

excerpt最大400 code points/件。

## 16. 推奨文言

v1は数値的な指摘だけ。

例:

```text
このSceneの説明文比率は42%で、参照範囲18〜31%を上回っています。
最長の説明Blockは286文字です。
```

文章生成・書き換え提案は別設計。

## 17. テスト

- range内Findingなし
- min/max上下
- zero-width MetricDefinition tolerance
- tolerance未定義Profile validation error
- specificity
- weightはseverity非影響
- evidence最大5
- missing metric warning
- missingが多くてもrun成功 + coverage
- applicable 0表示
- stale detection
- ignored継承同revisionのみ

## 18. Codex実装時の禁止事項

- 総合文章品質scoreを追加しない。
- Lintを自動修正へ接続しない。
- preferredとの差だけでwarningにしない。
- Profile外heuristicを勝手に追加しない。
- missing割合だけでLintRunをfailさせない。
- zero-width toleranceをunitから推測しない。
- 本文の長い引用をFinding rowへ複製しない。