# 08 Corpus and Profile 詳細設計

## 1. 目的

Reference Work/EpisodeのMeasurementをCorpusとして集約し、比較可能な統計とStyleProfileへ変換する。Membership、Current入力選択、集約単位、Countの意味を一意に定義する。

上位仕様は `../basic-design.md`。

## 2. 実装先

```text
CORE/src/novel_core/style_analysis/
  corpus_models.py
  corpus_repository.py
  aggregate_service.py
  profile_models.py
  profile_repository.py
  profile_service.py
```

## 3. Corpus / Membership

```text
style_corpora:
  id, name, description, created_at, updated_at

style_corpus_work_memberships:
  corpus_id, reference_work_id, include_all_episodes, created_at

style_corpus_episode_memberships:
  corpus_id, reference_episode_id, membership_mode = include | exclude
```

Effective Episode集合は `CorpusRepository.list_effective_episode_ids(corpus_id)` だけで解決する。

### include_all_episodes=true

- WorkのCurrent Catalog EpisodeをDefault Included。
- `exclude` Overrideを除外。
- `include` Overrideは結果上冗長。UIは通常作らない。

### include_all_episodes=false

- Default Excluded。
- `include` OverrideだけIncluded。
- `exclude` Overrideは結果上冗長。UIは通常作らない。

Validation:

- Episode Overrideには同CorpusのWork Membershipが必要。
- 別Work EpisodeはReject。
- Work Membership削除時、そのWork配下Overrideも同Transactionで削除。
- RefreshでEpisode削除時はFK Cascade。

Aggregate/API/UIはこのResolverを共用する。

## 4. Aggregate

```text
id
scope_type
scope_id
filter_json
metric_name
metric_version
statistic
value_real
source_measurement_count
sample_count
work_count
skipped_target_count
fingerprint
created_at
```

Statistic:

```text
mean | median | p10 | p25 | p75 | p90 | stddev | min | max
```

## 5. 観測単位

v1はMeasurement Rowを1観測として等重みでPoolする。

- Episode: 1 Episode Measurement = 1観測
- Scene: 1 Scene Measurement = 1観測
- Character: 1 Character Measurement = 1観測

これはWork等重みではない。Episode/Scene数が多いWorkは多くの観測を提供する。v1ではWork Weight/User Weightを導入しない。UIは `work_count` と `source_measurement_count` を表示する。

## 6. Count定義

### source_measurement_count

Statisticへ実際に使ったMeasurement Row数。

### sample_count

入力Measurementの `sample_count` 合計。Underlying Sentence/Utterance/Term等の量を示す診断値で、Aggregate Weightには使わない。

### work_count

入力Measurement由来のDistinct Reference Work数。

### skipped_target_count

Effective Membership内だがCurrent Text/Structure/Measurement不足で当該Metricへ寄与しなかったTarget数。

## 7. Current入力選択

Reference Episodeを使う条件:

1. Effective Membershipに含まれる。
2. Episodeに属するStyleDocumentがある。
3. `document.current_text_revision_id` がある。
4. `document.current_structure_revision_id` があり、そのCurrent TextRevision所属。
5. 09 Current AnalysisRun Resolverで対象Metric GroupのCurrent Runが解決できる。
6. Metric Name/Version一致Measurementがある。

不足TargetはSkipする。Latest Structureや古いSucceeded RunへFallbackしない。

Scene/Character AggregateもCurrent Document/Text/Structure/Run配下だけを使う。

## 8. Aggregate Scope / Filter

```text
reference_work
corpus
scene_label
character
```

Scene LabelはParent Work/Corpusを `scope_id`、Taxonomy条件を `filter_json` に保存する。任意SQLは保存しない。

## 9. 統計式

- Mean/Pstdev: Python `statistics` 相当
- Percentile: 07共通Utility
- 1観測のPstdev = 0
- 0観測ならAggregate Rowなし

Measurement `value_*` を等重みで計算し、Measurement `sample_count` でWeighted計算しない。

## 10. Fingerprint

Canonical SHA-256入力:

```text
aggregate_policy_version
scope_type / scope_id
canonical filter_json
metric_name / metric_version
sorted effective membership episode IDs for corpus scope
sorted input measurement IDs
```

Measurement RowはImmutableなのでID集合をProvenanceとして使う。同Fingerprint RowはReuse可能。

## 11. Profile生成Sample Policy

09 AnalysisPolicyが正本。

```text
profile_min_episode_measurements = 5
profile_min_scene_measurements = 10
profile_min_character_utterances = 10
profile_min_term_samples = 5
```

不足時はCorpus由来Ruleを自動生成しない。Manual Ruleは作成可能。

## 12. Profile Identity / Version

```text
StyleProfile:
  id
  name
  description
  source_corpus_id nullable
  status = draft | active | archived
  active_version_id nullable
  created_at
  updated_at

StyleProfileVersion:
  id
  profile_id
  version_no
  parent_version_id nullable
  created_at

StyleRule:
  profile_version_id
  scope_selector_json
  metric_name / metric_version
  preferred_value / min_value / max_value
  weight / enabled / severity_policy / source_kind
```

Version/RuleはImmutable。`status=active` なら同Profile所属 `active_version_id` 必須。New VersionだけでActive Versionを変更しない。

## 13. Corpus Default Rule

```text
preferred = median
min = p25
max = p75
```

Ratioは0〜1 Clamp。P25=P75でもRangeを勝手に広げない。

## 14. Scope Selector

許可:

```text
global
scene.function
scene.tone
scene.pace
scene.information_load
scene.interaction
character_id
```

複数条件AND、配列内OR。Cross-work Characterを名前一致で自動対応しない。

## 15. Corpus Compare

2〜5 Corpus。Metricごとに:

```text
median
p25
p75
source_measurement_count
sample_count
work_count
skipped_target_count
```

を返す。異Unitを同一Axisへ混ぜない。

## 16. Profile作成 / 編集 / Activation

Corpusから:

1. Profile Identity
2. Version 1
3. Current AggregateからRule Snapshot
4. Status Draft
5. Active Version NULL

編集はCurrent VersionをCopyしてNew Version。Activateは `profile_id + version_no` を明示し同Profile所属を検証する。

## 17. Export / Import

ExportはVersion明示。Raw Text/Entity/Mentionを含めない。Unknown Metric RuleはDisabledでImport可能。Import後はDraft。

## 18. Test

- include_all=true + exclude
- include_all=false + include
- MembershipなしEpisode Override拒否
- Work Membership削除でOverride削除
- Refresh Episode削除Cascade
- Measurement Row等重み
- Work等重みではないこと
- source_measurement_count / sample_count / work_count分離
- skipped_target_count
- Document Current Text/Structure/Runだけ使用
- Current StructureなしSkip
- 古いRunへFallbackなし
- Fingerprint Membership/Input Measurement IDs
- Sample不足Auto Ruleなし / Manual Rule可
- Profile Version / Active Version
- New VersionでActive不変

## 19. Codex禁止事項

- Measurementを直接StyleRuleとして保存
- `sample_count` をAggregate Weightとして使用
- Measurement Row等重みをWork等重みとして実装
- Membership規則をAPI/UIで重複実装
- Current StructureなしでLatest StructureへFallback
- Current TextをReferenceEpisode側Pointerから読む
- Source Measurement CountとSample Countを同義にする
- Cross-work Character名前一致統合
- Active VersionをLatestへ暗黙切替
