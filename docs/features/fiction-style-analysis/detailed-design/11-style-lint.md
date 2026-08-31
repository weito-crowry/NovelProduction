# 11 Style Lint 詳細設計

## 1. 目的

Project DocumentのMeasurementを指定StyleProfileVersionと比較し、参照範囲との差をFindingとして提示する。文章の優劣を断定せず、Coverage・Evidence・Input Stalenessを示す。

上位仕様は `../basic-design.md`。

## 2. Lint Request / Scope

```text
document_id
text_revision_id
structure_revision_id
profile_id
profile_version_no
scene_id nullable
```

ClientはMetric Run IDを指定しない。LintServiceが09 Current Metric Runを必要Groupだけ`subject_partial_allowed`で解決する。

Text/Structure/ProfileVersionをlatestへ暗黙読み替えしない。

### `scene_id = NULL`

Document Lint。

```text
document rules
scene rules for all scenes
character rules
```

を評価する。

### `scene_id != NULL`

Specific Scene Lint。

```text
scene rules for that scene only
```

を評価する。Document/Character Ruleは評価しない。

v1 Character MeasurementはDocument全体人物単位でありScene×Character Measurementを持たないため。

## 3. Rule Target Enumeration

`target_scope`を正本とする。

### document

Target=StyleDocument 1件。Selector`{}`。

### scene

Target=指定StructureRevisionのScene。

### character

Selector`project_character_id`を04 Manual Linkで:

```text
project_character_id
-> same Project Documentのenabled person Style Entity
-> character Measurement target_id
```

へ解決する。

- Linkなし/Entity disabled -> Not Applicable。Pairを作らない。
- Linkあり + Character Measurementなし -> ApplicableだがMissing。
- Sceneとの組合せなし。

## 4. Scene Selector

許可Axis:

```text
function
tone
pace
information_load
interaction
```

StyleRule Selectorは08どおり`scene` wrapperなし。

複数Axis AND、同Axis配列OR。Selector`{}`は全SceneへMatch。

### Available + Match

Matching Rule候補。

### Available + Non-match

Not Applicable。Coverageへ数えない。

### Required Axis `source=unknown`

Selector判定不能。

- `applicable_rule_count += 1`。
- `missing_rule_count += 1`。
- Findingなし。
- `SELECTOR_UNAVAILABLE:{axis}` WarningをDedupe。
- Specificity競合へ参加させない。

Unavailable具体Ruleがあっても、AvailableなGlobal/低Specificity Ruleの評価を妨げない。

Effective`unclear`は通常Taxonomy値としてMatch判定する。

## 5. Specificity

同じ`target_scope`内でAvailableかつMatching RuleだけをTarget/Metricごとに比較する。

```text
document: 0
scene: Selectorに含まれるAxis数
character: 0
```

最大Specificity Ruleをすべて評価し、低Specificity Matching RuleはそのTarget/Metricでは評価しない。

同SceneへDaily RuleとCalm Ruleが同Specificityで一致すれば両方評価する。

完全同一`target_scope + canonical selector + metric + version`のEnabled Rule重複だけ08で拒否する。

## 6. Range / Deviation / Severity

08どおりEnabled Ruleは`min_value`と`max_value`を両方持つ。

- `min <= observed <= max` -> Findingなし。
- `observed < min` -> Lower Finding。
- `observed > max` -> Upper Finding。
- preferred差だけではFindingなし。

### Range幅 > 0

```text
upper deviation = (observed - max) / (max - min)
lower deviation = (min - observed) / (max - min)
```

### `min == max`

07 `MetricDefinition.zero_width_tolerance`を使う。

```text
deviation = abs(observed - min) / tolerance
```

ToleranceなしZero-width Ruleは08 Profile Validation Error。

Severity `standard`:

```text
0 < deviation <= 0.25      info
0.25 < deviation <= 0.75   warning
deviation > 0.75           strong_warning
```

`sort_score = deviation * weight`。WeightはSeverityに使わない。

## 7. Finding

```text
id
lint_run_id
rule_id
target_type
target_id
metric_name
observed_value
expected_min
expected_max
preferred_value nullable
deviation
severity
sort_score
explanation_code
evidence_json
created_at
```

同Target/Metricへ同Specificity Ruleが複数一致すればRuleごとにFinding生成可。UIはRule Scope/Selectorを表示する。

## 8. Evidence

最大5 Span。

- Narration Run: Run Span。
- Exposition Ratio: 長いEffective Exposition Block最大5。
- New Term Density: Eligible First Appearance Mention最大5。
- Explanation Delay: First Mention + Effective Sufficient Explanation。
- 一意Spanなし: `evidence_kind=scope_metric`。

Finding Rowへ本文Excerptを複製しない。Text/Structure ID + Span/Subject IDを保持する。

## 9. Coverage

```text
enabled_rule_count
applicable_rule_count
missing_rule_count
coverage_ratio
```

`enabled_rule_count`:

- Document Lint: ProfileVersionの全Enabled Rule数。
- Scene-only Lint: Enabled Scene Rule数。

`applicable_rule_count`:

- Specificity選択後に評価対象となったRule×Target Pair。
- Selector Unavailable Rule×Scene Pair。

`missing_rule_count`:

- Applicable PairでMeasurementなし。
- Selector Unavailable Pair。

```text
applicable == 0 -> coverage_ratio = 0.0
else -> (applicable - missing) / applicable
```

Warnings:

```text
METRIC_UNAVAILABLE:{metric}
SELECTOR_UNAVAILABLE:{axis}
```

Missing割合だけでLintをFailさせない。

## 10. 必要Inputだけ解決

Enabled Rule + Request Scopeを先に読み必要Inputだけ解決する。

- Basic Metric Rule候補 -> Basic Metric Run。
- Semantic Metric Rule候補 -> Semantic Metric Run。
- Scene Rule -> そのRuleが参照するAxisだけEffective State。
- Character Rule -> 参照project_character_id Linkだけ。

Scene-only LintではDocument/Character Rule入力を解決しない。

## 11. Lint Input Fingerprint

```text
document_id
text_revision_id
structure_revision_id
profile_version_id
scene_id nullable
selected required basic_metric_run_id nullable
selected required semantic_metric_run_id nullable
referenced Scene Axis state only
referenced Project Character Link mapping only
```

Scene State:

```text
(scene_id, axis, source, effective_value)
```

Character Link:

```text
(project_character_id, style_entity_id)
```

をSortしてCanonical SHA-256。

Unknown→Known変化も反映する。未使用Run/Axis/Link変更では変えない。

ProfileVersionがImmutableなのでRule一覧を別Hashしない。

## 12. Staleness

`stale=true` if:

1. Lint TextRevision != Document Current Text、または
2. Lint StructureRevision != Document Current Structure、または
3. 同Request Scope/ProfileVersionで現在Input Fingerprintと保存値が不一致。

Historical Lintは閲覧可能。StaleはErrorではない。

## 13. LintRun Status

```text
running
succeeded
failed
cancelled
```

Metric/Selector不足はWarning/Coverage。Partial Statusは使わない。Queue状態は`style_jobs`。

09 `run_lint` Jobから実行する。

## 14. Finding Review

```text
finding_id
status = acknowledged | ignored
note nullable
created_at
```

Finding ReviewもAppend-only Eventとし、同Findingの最新Reviewを表示状態に使う。

再Lint時の表示継承条件:

```text
same text_revision_id
same structure_revision_id
same profile_version_id
same rule_id
same target identity
same evidence canonical fingerprint
```

別Revisionへ継承しない。

## 15. Sort / 文言

`strong_warning -> warning -> info`。

同Severityは:

```text
sort_score DESC
target order ASC
id ASC
```

文言は数値差を定型表示する。生成的な本文書き換え提案はv1対象外。

## 16. Test

- Document LintでDocument/Scene/Character Rule。
- Scene-onlyでScene Ruleだけ。
- Scene-only enabled_rule_countはScene Ruleだけ。
- Character Link disabled/なしNot Applicable、LinkありMeasurementなしMissing。
- Selector Available Match/Non-match。
- Selector Unknown -> Applicable+Missing+Warning。
- Unknown Specific RuleがGlobal Ruleを抑制しない。
- Effective unclearは通常Taxonomy値。
- Same Specificity複数Rule。
- Both-side Range内/上下。
- min=max Tolerance。
- Preferred差だけでFindingなし。
- Basic-onlyでSemantic Run変更Fingerprint不変。
- 未参照Scene Axis変更Fingerprint不変。
- Unknown→Known参照AxisでFingerprint変化。
- Input Fingerprint Stale。
- Coverage0 Succeeded。
- Evidence/Review継承。

## 17. Codex禁止事項

- Current Scene Axisなしを`unclear`としてSelector判定。
- Selector Unavailable RuleでGlobal Ruleを抑制。
- target_scopeをSelectorから推測。
- Aggregate形式の`scene` wrapperをStyleRule Selectorとして要求。
- Scene-onlyでDocument/Character Rule評価。
- 片側Range用の独自Deviation式追加。
- Preferred差だけでFinding生成。
- Missing割合でLint Fail。
- StaleをError扱い。
- 総合品質Score/自動本文修正追加。
