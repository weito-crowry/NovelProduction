# 08 Corpus and Profile 詳細設計

## 1. 目的

複数作品・episode・SceneのMeasurementを集約し、比較可能なCorpus統計と、執筆時に参照するStyleProfile/StyleRuleへ変換する。実測値と目標値を混同しない。

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

Corpusはreference work/episodeの集合。

```text
id
name
description
created_at
updated_at
```

membership:

```text
corpus_id
reference_work_id
include_all_episodes boolean
created_at
```

episode単位除外/追加が必要な場合は `style_corpus_episode_memberships` を使う。

1作品は複数Corpusへ所属可。同一Corpusへの重複membershipは禁止。

## 4. Corpusの用途

初期UIで以下のような任意Corpusを作れる。

```text
読みやすい現代SF
日常会話が好みの作品
説明が上手い作品
```

ジャンル等を自動Corpus化しない。ユーザーが比較意図を明示して作る。

## 5. Aggregate

Measurementを直接profileへ流さず、まずAggregateを生成する。

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

## 6. Aggregate scope

```text
reference_work
corpus
scene_label
character
```

`scene_label` は独立IDを持たないため `scope_id` は親work/corpus ID、`filter_json` にtaxonomy条件を入れる。

例:

```json
{
  "scene.function": "daily",
  "scene.pace": "medium"
}
```

filter key/valueはtaxonomy registryでvalidationする。任意SQL条件を保存しない。

## 7. Aggregate input

対象Measurementは次を満たすものだけ。

- 最新effective StructureRevisionに対するsucceeded analysis
- metric version一致
- reference episodeがCorpus membership内
- confidence thresholdを満たしたsemantic input
- rejected source/documentではない

同じTextRevisionに対する再解析Measurementが複数ある場合、effective analysis run 1件だけを採用する。

## 8. 統計式

mean/stddevはPython標準 `statistics` 相当のpopulation統計で実装する。

- stddevはpopulation standard deviation (`pstdev`)
- percentileは07と同じlinear interpolation utilityを共用
- sample 1件のstddevは0.0
- sample 0件はAggregate rowを作らない

## 9. 最小sample条件

StyleProfile生成に使用する最低sample数を固定する。

| profile scope | 最低sample |
|---|---:|
| global metric | 5 episode |
| scene label metric | 20 scene |
| character metric | 20 utterance |
| term metric | 10 eligible term occurrence |

不足時はprofile ruleを自動生成しない。UIには `insufficient_samples` と表示する。

## 10. StyleProfile

Profileは不変versioned snapshot。

```text
id
name
description
source_corpus_id nullable
version
parent_profile_id nullable
status = draft | active | archived
created_at
```

active profileをupdateせず、編集保存時はversion+1の新Profileを作る。

1projectでactive profileは複数可。ただしDraft Lint実行時に1つ明示選択する。

## 11. StyleRule

```text
id
profile_id
scope_selector_json
metric_name
metric_version
preferred_value nullable
min_value nullable
max_value nullable
weight
severity_policy
source_kind
created_at
```

`source_kind`:

```text
corpus_generated
manual
```

`weight` 初期範囲0.0〜5.0、default 1.0。

## 12. 自動Rule生成

Corpusからのdefault生成式を固定する。

```text
preferred = median
min = p25
max = p75
```

ただし値域が本質的に0〜1のratio metricはmin/maxを0〜1へclampする。

p25=p75の場合でもrangeを勝手に広げない。Lint側でzero-width range用の絶対toleranceを適用する。

mean±stddevはdefault ruleに使わない。外れ値に引っ張られやすいため。

## 13. scope selector

Ruleのscope selectorは宣言的JSONとし、以下だけ許可する。

```text
global
scene.function
scene.tone
scene.pace
scene.information_load
scene.interaction
character_id
```

例:

```json
{
  "scene.function": ["daily", "dialogue"]
}
```

複数条件はAND。配列内はOR。

外部reference character IDをproject characterへ自動対応させない。character scope ruleは同一document/work内、またはユーザーが明示構築したproject character profileに限定する。

## 14. 複数作品の重み

Corpus Aggregateはepisode/scene Measurementをそのままpoolし、作品ごとの手動weightはv1で実装しない。

作品長の違いで1作品が過剰支配する可能性はUIでsample countとwork countを併記して把握する。将来weight導入時はAggregate versionを変更する。

## 15. Corpus比較

2〜5 Corpusを比較可能とする。

APIはmetricごとに次を返す。

```text
median
p25
p75
sample_count
work_count
```

UIの初期visualizationはtableと単独chart。レーダーチャートは単位が異なるmetricを混ぜやすいため実装しない。

## 16. Profile編集

ユーザーは生成ruleを以下だけ編集できる。

- preferred
- min/max
- weight
- severity policy
- enabled/disabled

metric name/versionやscopeを同じrule上で変更しない。別ruleとして作成する。

## 17. Profile export/import

version付きJSONとしてexport可能。

```json
{
  "schema": "novelproduction.style-profile",
  "schema_version": 1,
  "profile": {...},
  "rules": [...]
}
```

Raw source text、作品本文、Entity/Mentionは含めない。Profileだけを共有可能にする設計とする。

import時はunknown metric/versionを拒否せず `unsupported_rules` として表示し、activeにはできない。

## 18. Aggregate再計算

Corpus membership、effective analysis、manual override、Metric versionのいずれかが変わればfingerprintが変化する。

Aggregateはappend-onlyで新規作成し、`style_aggregate_heads` のようなmutable pointer tableは作らず、repository queryで最新fingerprint一致rowを取得する。古いAggregateは監査用に保持する。

## 19. テスト

- corpus membership重複禁止
- episode include/exclude
- p25/median/p75
- sample不足時rule生成なし
- ratio clamp
- profile versioning
- active profile不変
- scope selector validation
- exportにraw textが入らない
- unsupported metric import
- effective analysisの重複排除

## 20. Codex実装時の禁止事項

- Measurementを直接StyleRuleとして保存しない。
- 平均だけでtarget rangeを生成しない。
- sample不足を0値としてrule化しない。
- cross-work characterを名前一致で自動統合しない。
- raw小説本文をprofile exportへ含めない。
- radar chartを初期scopeへ追加しない。
