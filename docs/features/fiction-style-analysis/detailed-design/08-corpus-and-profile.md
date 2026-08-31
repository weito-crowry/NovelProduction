# 08 Corpus and Profile 詳細設計

## 1. 目的

複数作品・episode・SceneのMeasurementを集約し、比較可能なCorpus統計と執筆時のStyleProfileへ変換する。実測値・集約値・目標Ruleを分離し、Profileのstable identityとimmutable Versionも分離する。

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

Work membership:

```text
corpus_id
reference_work_id
include_all_episodes
created_at
```

Episode単位overrideは `style_corpus_episode_memberships`。

1 Reference Workは複数Corpusへ所属可。

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

AggregateはMeasurement rowを観測単位として等重みで集約する。

- episode scope: Episode Measurementを1観測
- scene filter: Scene Measurementを1観測
- character scope: Character Measurementを1観測

Raw sentence等へ遡って再poolしない。長い作品だけが自動的に重くならないようにする。

将来Work weightを導入する場合はAggregate policy versionを変える。

## 6. Aggregate scope/filter

```text
reference_work
corpus
scene_label
character
```

`scene_label` は `scope_id` に親Work/Corpus ID、`filter_json` にtaxonomy条件を入れる。

```json
{
  "scene.function": "daily",
  "scene.pace": "medium"
}
```

任意SQLは保存しない。

## 7. Aggregate input

- current effective StructureRevisionのMeasurement
- Metric version一致
- Corpus membership内
- Semantic Metricは07でcompleteと判定されたscopeのみ
- 同一target/metric/versionで複数runがある場合は09のeffective run選択に従う

Partial Semantic Runの成功Sceneから生成されたScene Measurementは利用可能。Document全体の不完全Metricは07で作らない。

Reference Work purge後はCorpus membershipが消えるため、以後の再集約では対象外になる。過去Aggregate rowは履歴値として残してよい。

## 8. 統計式

- mean/pstdev: Python `statistics` 相当
- percentile: 07共通utility
- sample 1件のpstdev = 0
- sample 0件はAggregate rowなし

## 9. Profile生成のsample policy

固定値は09 `AnalysisPolicy` を正本にする。

初期default:

```text
profile_min_episode_measurements = 5
profile_min_scene_measurements = 10
profile_min_character_utterances = 10
profile_min_term_samples = 5
```

不足時はCorpus由来Ruleを自動生成しない。これは処理停止用の安全チェックではなく、自動生成条件である。UIからManual Ruleは作成可能。

## 10. Profile identity / Version

### StyleProfile

Stable mutable identity/meta:

```text
id
name
description
source_corpus_id nullable
status = draft | active | archived
active_version_id nullable
created_at
updated_at
```

`active_version_id` は同Profileに属する `StyleProfileVersion.id` のみ許可する。DBの単純FKだけでは同一Profile所属を保証できないため、ProfileServiceで検証する。

意味:

- `draft`: `active_version_id` はNULLでよい
- `active`: `active_version_id` 必須
- `archived`: `active_version_id` は最後に採用していたVersionを保持してよい

### StyleProfileVersion

Immutable snapshot:

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

Profile name/status/active versionを変更しても過去Rule snapshotを変更しない。

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

Ratioは0〜1へclamp。

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

外部Reference CharacterをProject Characterへ名前一致で自動対応しない。

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

## 15. Profile作成・編集・Activation

### Corpusから作成

1. StyleProfile identityを作る
2. Version 1を作る
3. Corpus AggregateからRule snapshotを作る
4. 初期statusは `draft`
5. `active_version_id` はNULL

### Rule編集

現在選択中VersionのRulesをcopyして新Versionを作る。

編集可能:

- preferred
- min/max
- weight
- enabled
- severity_policy

Metric name/version/scopeを変更したい場合は旧Ruleをdisabledにし、新Ruleを追加する。

### Activate

Activate操作は必ずVersionを明示する。

```text
profile_id
version_no
```

ProfileServiceはそのVersionが同Profile所属であることを検証し、1 transactionで:

```text
status = active
active_version_id = selected version id
updated_at更新
```

とする。

新Version作成だけではactive versionを自動切替しない。ユーザーが保存と同時にactivateするUIを用意する場合でも、API内部ではVersion作成→Activateの明示2操作として扱う。

Archiveは `status=archived` にする。active_version_idを消す必要はない。

## 16. Export / Import

ExportはVersionを明示する。

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

Unknown Metric/Versionは `unsupported_rules` として返し、そのRuleをdisabledで保存してよい。Profile全体を拒否しない。

Import後はdraft Profile + Versionを作る。unsupported Ruleがなくても勝手にactive化しない。

## 17. Aggregate再計算

Fingerprint入力:

- Corpus membership
- input Measurement IDs/fingerprints
- Metric version
- filter
- aggregate policy version

Aggregateはappend-only。head tableは作らずfingerprint一致rowをreuseする。

## 18. API/UIへ返すCurrent Profile

Profile一覧/detailでは以下を明示する。

```text
status
active_version_no nullable
latest_version_no
```

`latest_version_no` は表示用。LintやExportの入力をlatestへ暗黙読み替えしない。

## 19. テスト

- membership重複禁止
- episode include/exclude
- equal-weight Measurement aggregate
- p25/median/p75
- sample不足時auto Ruleなし
- Manual Ruleはsample不足でも作成可
- Profile identityとVersion分離
- version_no uniqueness
- Version immutable
- active時active_version必須
- active Versionが同Profile所属か検証
- 新Version作成でactive Versionが勝手に切替わらない
- archiveでVersion不変
- scope validation
- Exportに本文なし
- unsupported Rule import disabled
- Importはdraft
- effective Measurement重複排除

## 20. Codex実装時の禁止事項

- Measurementを直接StyleRuleとして保存しない。
- raw観測を勝手に再poolして長編作品へ重みを付けない。
- sample不足を0値Ruleにしない。
- cross-work Characterを名前一致で統合しない。
- ProfileVersion/Ruleをupdateしない。
- active Versionを暗黙latestへ切替しない。
- Raw本文をProfile exportへ含めない。
