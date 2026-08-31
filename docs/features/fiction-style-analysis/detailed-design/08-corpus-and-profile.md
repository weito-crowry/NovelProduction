# 08 Corpus and Profile 詳細設計

## 1. 目的

Reference Work/EpisodeのCurrent MeasurementをCorpusとして集約し、比較可能な統計とVersion付きStyleProfileへ変換する。Membership、観測単位、Scene Filter State、Aggregate Staleness、Profile Rule Provenanceを一意に定義する。

上位仕様は `../basic-design.md`。

## 2. Corpus Membership

```text
style_corpora
style_corpus_work_memberships
style_corpus_episode_memberships
```

Effective Episode集合は`CorpusRepository.list_effective_episode_ids(corpus_id)`だけで解決する。

### include_all_episodes=true

- WorkのCurrent Catalog EpisodeをDefault Included。
- `exclude` Overrideを除外。

### include_all_episodes=false

- Default Excluded。
- `include` OverrideだけIncluded。

Validation:

- Episode Overrideには同Corpus Work Membership必須。
- 別Work Episode拒否。
- Work Membership削除時、そのWork配下Overrideも同Transaction削除。
- ReferenceEpisode削除時FK Cascade。

Aggregate/API/UIはこのResolverを共用し、Membership規則を複製しない。

## 3. AggregatePolicy

AnalysisPolicy/ProfileGenerationPolicyとは別の決定論的集約Version。

```python
@dataclass(frozen=True)
class AggregatePolicy:
    version: int = 1
```

v1でPolicyが固定するもの:

- Measurement Row等重み。
- `sample_count`をWeightに使わない。
- Percentile interpolationは07共通式。
- stddevはpopulation standard deviation。
- Scene unknown FilterのSkipped規則。
- Standard Statistic Set。

結果互換性が変わる場合`version`を上げる。

## 4. Aggregate Spec

```text
container_type = reference_work | corpus
container_id
measurement_target_type = document | scene
filter_json
metric_name
metric_version
```

Document Aggregateは`filter_json={}`固定。

Scene AggregateだけScene Axis Filterを許可する。

```json
{
  "scene": {
    "function":["daily"],
    "tone":["calm"]
  }
}
```

## 5. Source Episode集合

`reference_work`: Current ReferenceEpisode Catalog order順。

`corpus`: Section 2 Effective Episode集合。

Source Episode ID集合をAggregate Input Fingerprintへ含める。新Episode追加やMembership変更でMeasurementがまだ無くてもHistorical AggregateをStale判定できるようにする。

## 6. Current Measurement選択

各Source Episodeについて:

1. StyleDocument存在。
2. `current_text_revision_id`存在。
3. `current_structure_revision_id`存在しCurrent Text所属。
4. 09 Current Metric Run Resolverを`subject_partial_allowed`で使い対象Metric Group Runを解決。
5. Metric Name/Version一致Measurementを取得。

Latest StructureやStale RunへFallbackしない。

### document target

1 Episode Document Measurementを1候補Targetとする。条件不足/Measurementなしなら`skipped_target_count += 1`。

### scene target

Current Structureが存在するEpisodeだけSceneを列挙する。

Current Structure自体がないEpisodeはScene数を推測しない。Warning:

```text
SOURCE_DOCUMENT_UNAVAILABLE:{episode_id}
```

を追加するが架空Scene数をSkippedへ加算しない。

## 7. Aggregate Schema論理契約

```text
id
container_type
container_id
measurement_target_type
filter_json
metric_name
metric_version
statistic
aggregate_policy_version
value_real
source_measurement_count
sample_count
work_count
skipped_target_count
filter_state_fingerprint nullable
input_fingerprint
warning_json
created_at
```

Statistic:

```text
mean
median
p10
p25
p75
p90
stddev
min
max
```

Aggregate値は**常にREAL**として保存する。元Measurementが`value_int`でも、平均・Percentile・Stddevは小数になり得るため整数へ丸めない。

これをv1 Standard Statistic Setとする。Aggregate RowはImmutable Historical Snapshot。

## 8. Scene Filter

許可Axis:

```text
function
tone
pace
information_load
interaction
```

複数Axis AND、同Axis配列OR。

### Available + Match

対象Scene候補。Metricなしなら`skipped_target_count += 1`。

### Available + Non-match

Aggregate対象外。Skippedへ数えない。

### Required Axis source=unknown

Filter判定不能。

- Measurementへ入れない。
- `skipped_target_count += 1`。
- `SCENE_SELECTOR_UNAVAILABLE:{axis}` WarningをDedupe。
- Filter State Fingerprintへ`source=unknown`を含める。

Effective Taxonomy値`unclear`は通常値としてMatch/Non-match判定する。

## 9. Filter State Fingerprint

Scene Filterで実際に参照するAxisだけ:

```text
(scene_id, axis, source, effective_value)
```

をSortして09 Canonical Fingerprint UtilityでHashする。

Filter未参照Axis変更ではAggregateをStaleにしない。Document AggregateではNULL。

## 10. 観測重み / Count

v1はMeasurement Rowを1観測として等重みでPoolする。

- Document: 1 Episode Document Measurement = 1観測。
- Scene: 1 Scene Measurement = 1観測。

Work等重みではない。Measurement`sample_count`をWeightに使わない。

Count:

- `source_measurement_count`: Statisticへ使ったMeasurement Row数。
- `sample_count`: 入力Measurement`sample_count`合計。診断値。
- `work_count`: 入力Measurement由来Distinct Reference Work数。
- `skipped_target_count`: 列挙できた候補TargetのうちFilter判定不能またはMetric不足だった件数。

Scene Structure自体が無いEpisodeはWarningで別表示する。

## 11. Aggregate Input Fingerprint

09 Canonical Fingerprint Utilityへの入力:

```text
aggregate_policy_version
container_type/container_id
measurement_target_type
canonical filter_json
metric_name/metric_version
statistic
sorted source_episode_ids
sorted candidate target identities with filter result(match|unknown)
sorted input measurement IDs
filter_state_fingerprint nullable
```

12 `style_aggregate_measurements`でAggregate→Measurement Linkも保持する。

## 12. Aggregate Staleness

Historical Aggregateと同じSpec/Statisticについて、Current AggregatePolicy VersionでSection 11 Input Fingerprintを再計算する。

```text
stale = stored input_fingerprint != current input_fingerprint
        OR stored aggregate_policy_version != current AggregatePolicy.version
```

Current入力0件でもFingerprintを計算する。Stale Aggregateを自動削除しない。

## 13. 統計式

- Mean: arithmetic mean。
- Stddev: population standard deviation (`statistics.pstdev`相当)。
- Percentile: 07共通Utility。
- 1観測Stddev=0.0。
- 0観測なら新Aggregate Rowなし。
- 結果はすべてPython `float`へ正規化して`value_real`へ保存する。

## 14. ProfileGenerationPolicy

AnalysisPolicyとは分離する。

```python
@dataclass(frozen=True)
class ProfileGenerationPolicy:
    version: int = 1
    min_document_measurements: int = 5
    min_scene_measurements: int = 10
    min_term_sample_count: int = 5
```

Corpus由来Rule自動生成時だけ使用する。AnalysisRunをStaleにしない。

## 15. StyleProfile / Version / Rule

```text
StyleProfile
  id/name/description/source_corpus_id/status/active_version_id

StyleProfileVersion
  id/profile_id/version_no/parent_version_id/profile_generation_policy_version

StyleRule
  id/profile_version_id
  target_scope
  scope_selector_json
  metric_name/metric_version
  preferred_value nullable
  min_value nullable
  max_value nullable
  weight/enabled/severity_policy/source_kind
```

`target_scope=document|scene|character`。

`source_kind=corpus|manual`。

ProfileVersion/RuleはImmutable。

Ruleの`preferred/min/max`は07 Measurement Storage Typeとは別契約で、すべてfinite REAL値として扱う。Count MetricでもCorpus Percentileが小数になるため整数へ丸めない。

## 16. Rule Selector

### document

```text
target_scope=document
scope_selector_json={}
```

### scene

StyleRuleでは`scene` wrapperを持たずAxis Objectを直接保存する。

```json
{"function":["daily"],"tone":["calm"]}
```

Corpus Scene AggregateからRuleを生成する場合、Aggregate `filter_json.scene` の中身だけをRule SelectorへCopyする。

### character

```json
{"project_character_id":123}
```

CharacterとScene Selectorを組み合わせない。

## 17. Corpus由来Profile生成

Default:

```text
preferred = median
min = p25
max = p75
```

Profile生成APIはAggregateを暗黙Latest選択しない。RuleごとにExact Aggregate IDsを3件指定する。

```text
preferred_aggregate_id -> statistic=median
min_aggregate_id       -> statistic=p25
max_aggregate_id       -> statistic=p75
```

3 Aggregateについて次が完全一致することをValidationする。

```text
container_type = corpus
container_id = requested corpus_id
measurement_target_type
canonical filter_json
metric_name
metric_version
aggregate_policy_version
```

Stale Aggregateも明示IDなら利用可能。UIで警告するだけでblockingしない。

Mapping:

- Document Aggregate ->`target_scope=document`, selector`{}`。
- Scene Aggregate ->`target_scope=scene`, `filter_json.scene`をSelectorへCopy。
- Character RuleはCorpusから自動生成しない。

Sample Policy:

- Document Rule: median Aggregate`source_measurement_count >= min_document_measurements`。
- Scene Rule: median Aggregate`source_measurement_count >= min_scene_measurements`。
- Term Metric Rule: 上記に加えmedian Aggregate`sample_count >= min_term_sample_count`。

不足Ruleは生成しない。Profile/他Rule生成を全体Failさせない。

Corpus生成Ruleは`source_kind=corpus`とし、12 `style_rule_aggregate_sources`へExact3 Linkを保存する。

## 18. Manual Profile / New Version

### Manual Profile

`POST /profiles/manual`はProfile Identity + Version1 + Full Rule Snapshotを同期Transactionで作る。Ruleはすべて`source_kind=manual`、Aggregate Source Link 0件。

### New Version

`POST /profiles/{id}/versions`:

```text
parent_version_no required
rules = full snapshot required
```

- Parentが同Profile所属か検証。
- `version_no = current max + 1`。
- 全Rule Validation後1TransactionでVersion/Rule Insert。
- New VersionだけではActive Versionを変更しない。
- UI編集保存したRule Snapshotはすべて`source_kind=manual`として扱い、旧Corpus Aggregate Source Linkを自動継承しない。

Corpus由来Provenanceを維持した新Versionが必要なら、v1では再度`from-corpus`を明示実行する。

## 19. Rule Aggregate Provenance

```text
style_rule_aggregate_sources:
  rule_id
  aggregate_id
  role = preferred | min | max
```

Corpus Ruleは3 Link。Manual Ruleは0 Link。

## 20. Profile Validation

- Metric Name/Version存在。
- 07 MetricDefinitionが`target_scope`をsupport。
- Rule値はJSON Numberとして受け、boolを拒否し、`float(value)`へ変換後`math.isfinite()`必須。
- MetricDefinition `value_type=int`でもRule値の整数性を要求しない。
- MetricDefinition UnitはRule/Observed/Aggregateで一致しているものとしてMetric Name+Versionから解決する。Ruleに別Unit列を持たない。
- Enabled Ruleは`min_value`と`max_value`を両方必須。
- Enabled Ruleは`min <= max`。
- preferredはoptionalだが指定時`min <= preferred <= max`。
- Disabled RuleはRangeなしを許可する。
- weightはfinite 0..5。
- severity_policy=`standard`。
- source_kind Known Enum。
- target_scope別Selector Schema。
- 完全同一`target_scope + canonical selector + metric + version` Enabled Rule重複禁止。
- Character Ruleはproject_character_id必須。
- `min == max`の場合、07 MetricDefinition `zero_width_tolerance > 0`必須。

片側Rangeはv1で実装しない。

## 21. Activation

`status=draft|active|archived`。

`status=active`なら同Profile所属`active_version_id`必須。

New VersionだけではActive Versionを変更しない。Activate/LintはVersion明示。

Profile Import/Exportはv1 scope外。

ArchiveはProfile Identityのstatusだけ`archived`へ変更する。Version/Ruleは保持する。

## 22. Corpus Compare

2〜5 Corpus。同Metric/Version/Measurement Target Typeだけ比較する。

返却:

```text
median
p25
p75
source_measurement_count
sample_count
work_count
skipped_target_count
stale
warnings
```

異Unitを同一Axisへ混ぜない。

## 23. Test

- Membership include/exclude。
- AggregatePolicy version persist/fingerprint/stale。
- Source Episode IDsをFingerprintへ含める。
- Current Metric Run partial allowed。
- Document missing -> skipped target。
- Scene Current Structureなし -> Warning、架空Scene Countなし。
- Scene Filter Match/Non-match/Unknown。
- Effective unclear通常Filter値。
- Measurement Row等重み / Work等重みでない。
- Count4種。
- Count Measurementのmean/median/p25等もREAL保存、丸めなし。
- Filter参照AxisだけState Hash。
- Aggregate Measurement Link。
- Current Input/Policy変更でStale。
- ProfileGenerationPolicy独立。
- Exact median/p25/p75 Aggregate Validation + policy version一致。
- Stale Aggregate明示利用許可。
- Corpus Rule Source3 Link。
- Scene Aggregate wrapper除去してRule Selector生成。
- Manual Profile Rule Source manual/link0。
- New Version Full Snapshot/parent required/source manual。
- Count Metric Manual Ruleへ小数Rangeを許可。
- NaN/Infinity/bool Rule値拒否。
- Enabled Rule min/max両方必須/preferred範囲。
- Character Rule Auto生成なし。
- New VersionでActive不変。

## 24. Codex禁止事項

- AggregatePolicyをAnalysisPolicyへ混ぜる。
- aggregate_policy_versionをRowへ保存しない。
- Aggregate結果を元Measurement `value_type=int`に合わせて丸める。
- Rule値をMetricDefinition `value_type=int`だから整数必須にする。
- Character MeasurementをCorpusでPool。
- `sample_count`をWeightに使用。
- Measurement Row等重みをWork等重みとして実装。
- Membership規則をAPI/UIへ複製。
- Current StructureなしでLatest fallback。
- Missing StructureからScene数を推測。
- Aggregateを自動上書き/削除。
- Profile生成でAggregateを暗黙Latest選択。
- Stale Aggregateを安全上の理由だけで利用禁止。
- Aggregateの`scene` wrapperをRule Selectorへそのまま保存。
- Enabled片側Rangeを独自Severity式で追加。
- New Version編集後も旧Aggregate Provenanceを自動継承。
- Character RuleをReference人物名から自動生成。
- target_scopeをSelectorから推測。
