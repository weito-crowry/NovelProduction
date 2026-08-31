# 08 Corpus and Profile 詳細設計

## 1. 目的

複数作品・episode・SceneのMeasurementを集約し、比較可能なCorpus統計と執筆時のStyleProfileへ変換する。実測値・集約値・目標ruleを分離する。

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

## 3. Corpus

```text
id
name
description
created_at
updated_at
```

work membership:

```text
corpus_id
reference_work_id
include_all_episodes
created_at
```

episode単位overrideは `style_corpus_episode_memberships`。

1 reference workは複数Corpusへ所属可。

## 4. Aggregate

Measurementを直接StyleRuleへ変換しない。

```text
id
scope_type
scope_id
filter_json
metric_name
metric_version
statistic
value_real
sample_count
source_measurement_count
work_count
fingerprint
created_at
```

`statistic`:

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

## 5. Aggregate単位

Aggregateは**Measurement rowを観測単位として等重み**で集約する。

- episode scope: episode Measurementを1観測
- scene filter: Scene Measurementを1観測
- character scope: character Measurementを1観測

raw sentence等へ遡って再poolしない。これにより長い作品だけが自動的に重くならない。

将来work weightを導入する場合はAggregate policy versionを変える。

## 6. Aggregate scope/filter

```text
reference_work
corpus
scene_label
character
```

`scene_label` は `scope_id` に親work/corpus ID、`filter_json` にtaxonomy条件。

```json
{
  "scene.function": "daily",
  "scene.pace": "medium"
}
```

任意SQLは保存しない。

## 7. Aggregate input

- current effective StructureRevisionのMeasurement
- metric version一致
- Corpus membership内
- semantic metricは07でcompleteと判定されたscopeのみ
- rejected source/documentを除外
- 同一target/metric/versionで複数runがある場合はcurrent effective succeeded run 1件

partial semantic runのうち成功Sceneから生成されたScene Measurementは利用可能。document全体の不完全metricは07でそもそも生成しない。

## 8. 統計式

- mean/pstdev: Python `statistics` 相当
- percentile: 07共通utility
- sample 1件のpstdev = 0
- sample 0件はAggregate rowなし

## 9. Profile生成のsample policy

固定値を各serviceへ散在させず、09 `AnalysisPolicy` を正本にする。

初期default:

```text
profile_min_episode_measurements = 5
profile_min_scene_measurements = 10
profile_min_character_utterances = 10
profile_min_term_samples = 5
```

不足時はRuleを自動生成しない。これは品質保証の停止条件ではなく、単に「統計的参考範囲を作るには少なすぎる」という生成条件である。UIからmanual Ruleは作成可能。

## 10. Profile identity/version

旧案の「Profile row自体をversion snapshotにする」方式は採用しない。stable identityとimmutable versionを分離する。

### StyleProfile

mutable identity/meta:

```text
id
name
description
source_corpus_id nullable
status = draft | active | archived
created_at
updated_at
```

### StyleProfileVersion

immutable snapshot:

```text
id
profile_id
version_no
parent_version_id nullable
created_at
```

UNIQUE `(profile_id, version_no)`。

### StyleRule

`profile_version_id` に所属する。

これによりprofile名/statusを変えても過去Rule snapshotを変更しない。

## 11. StyleRule

```text
id
profile_version_id
scope_selector_json
metric_name
metric_version
preferred_value nullable
min_value nullable
max_value nullable
weight
enabled
severity_policy
source_kind
created_at
```

`source_kind`:

```text
corpus_generated
manual
```

weight 0.0〜5.0、default 1.0。

## 12. Corpusからのdefault Rule

```text
preferred = median
min = p25
max = p75
```

ratioは0〜1へclamp。

p25=p75でもrangeを勝手に広げない。11がMetricDefinitionのzero-width toleranceを使う。

## 13. scope selector

許可key:

```text
global
scene.function
scene.tone
scene.pace
scene.information_load
scene.interaction
character_id
```

複数条件AND、配列内OR。

外部reference characterをproject characterへ名前一致で自動対応しない。

## 14. Corpus比較

2〜5 Corpus。

返却:

```text
median
p25
p75
sample_count
work_count
```

異なるunitを同一chart axisへ混ぜない。

## 15. Profile編集

Profile Editorは現在versionのrulesをcopyして新versionを作る。

編集可能:

- preferred
- min/max
- weight
- enabled
- severity_policy

metric name/version/scopeを変更したい場合は旧Ruleをdisabledにして新Ruleを追加する。

Profile `status` のactivate/archiveはversion contentを変更しない。

## 16. Export/import

```json
{
  "schema": "novelproduction.style-profile",
  "schema_version": 1,
  "profile": {
    "name": "...",
    "description": "..."
  },
  "version": 3,
  "rules": []
}
```

Raw text、Entity/Mentionは含めない。

unknown metric/versionは `unsupported_rules` としてimport結果へ返し、そのRuleをdisabledで保存してよい。Profile全体を拒否しない。

## 17. Aggregate再計算

fingerprint入力:

- Corpus membership
- input Measurement IDs/fingerprints
- metric version
- filter
- aggregate policy version

Aggregateはappend-only。head tableは作らずfingerprint一致rowをreuseする。

## 18. テスト

- membership重複禁止
- episode include/exclude
- equal-weight Measurement aggregate
- p25/median/p75
- sample不足時auto Ruleなし
- manual Ruleはsample不足でも作成可
- Profile identityとVersion分離
- version_no uniqueness
- status変更でVersion不変
- scope validation
- exportに本文なし
- unsupported Rule import disabled
- effective Measurement重複排除

## 19. Codex実装時の禁止事項

- Measurementを直接StyleRuleとして保存しない。
- raw観測を勝手に再poolして長編作品へ重みを付けない。
- sample不足を0値Ruleにしない。
- cross-work characterを名前一致で統合しない。
- Profile version contentをupdateしない。
- raw本文をProfile exportへ含めない。