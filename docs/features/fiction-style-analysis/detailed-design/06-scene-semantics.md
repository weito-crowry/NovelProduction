# 06 Scene Semantics 詳細設計

## 1. 目的

SceneとBlockへ意味的なラベルを付与し、日常会話・説明・内省・緊張・アクション等の局面別に文体統計を比較できるようにする。Scene分類は単一ラベルではなく、相互に独立したaxisのmulti-labelを正本とする。

上位仕様は `../basic-design.md`。

## 2. 実装先

```text
CORE/src/novel_core/style_analysis/
  semantic_models.py
  semantic_service.py
  analyzers/
    scene_classifier.py
    block_semantics.py
    pov_classifier.py
    scene_boundary_candidates.py
```

## 3. Scene taxonomy

taxonomy versionを `scene-taxonomy-v1` として固定する。

### function: multi-select

```text
daily
setup
dialogue
exposition
meeting
investigation
travel
introspection
conflict
action
transition
reveal
payoff
other
```

0件は禁止。判断不能なら `other`。

### tone: multi-select

```text
neutral
calm
humorous
warm
tense
emotional
ominous
sad
excited
other
```

最低1件。極端に混在するsceneは複数可。

### pace: single-select

```text
slow
medium
fast
```

### information_load: single-select

```text
low
medium
high
```

### interaction: single-select

```text
solo
dialogue
group_dialogue
crowd
mixed
```

## 4. Scene classification出力

`style_annotations` にaxisごとに保存する。1つの巨大JSONへまとめない。

例:

```text
annotation_type = scene.function
value_json = ["daily", "dialogue"]

annotation_type = scene.pace
value_json = "medium"
```

各annotationにconfidenceとanalysis_run_idを持たせる。

function/tone複数値のconfidenceはlabelごとに持ちたいため、valueは次の形式とする。

```json
[
  {"label": "daily", "confidence": 0.91},
  {"label": "dialogue", "confidence": 0.96}
]
```

## 5. Scene classifier入力

- Scene全文
- Block ID/type/text
- speaker effective viewが存在すればspeaker名
- Term一覧は名称だけ
- 前後sceneの本文は渡さない

分類はScene単体の読み味を測るため、作品あらすじ・ジャンル等をpromptへ混ぜない。

## 6. function判定基準

曖昧さを減らすため定義を固定する。

| label | 判定基準 |
|---|---|
| daily | 日常行動・雑談・通常生活が主 |
| setup | 後続展開の前提・準備を配置 |
| dialogue | 会話そのものがscene推進の中心 |
| exposition | 設定・制度・背景・知識の伝達が中心 |
| meeting | 会議・協議・正式な打合せ |
| investigation | 情報収集・推理・検証 |
| travel | 移動そのものがsceneの主要活動 |
| introspection | 内面思考・自己評価が中心 |
| conflict | 対立・口論・交渉上の衝突 |
| action | 身体的行動・戦闘・追跡等が中心 |
| transition | 時間/場所/章の橋渡しが主 |
| reveal | 読者/人物に重要情報が明示される |
| payoff | 以前の伏線・準備の成果がscene中心 |

`dialogue` は会話率だけで自動付与しない。内容機能をmodelで判断する。

## 7. pace基準

モデルpromptに以下を明示する。

- slow: 内省・詳細描写・長い説明が多く、出来事の進行量が少ない
- medium: 標準的
- fast: 短いやり取りや行動が連続し、状態変化が多い

文長だけで決定しない。

## 8. information_load基準

新規情報量で判定する。

- low: 既知前提の会話・行動中心
- medium: 数個の新情報が自然に入る
- high: 複数の固有概念・設定・因果説明を短い範囲に集中投入

05 Term分析が完了していればterm情報を補助signalとして渡すが、Scene classifierはTerm analyzerに必須依存しない。

## 9. POV

Sceneごとに以下を保存する。

```text
pov_mode = first_person | third_limited | omniscient | objective | unclear
pov_entity_id nullable
confidence
```

`pov_entity_id` はperson Entity解決済みの場合のみ設定。名前不明でもmodeは判定可能。

POVがscene内で変化した疑いがある場合は `pov_shift_candidate=true` annotationを付け、ReviewQueueへ送る。automatic Scene再分割はしない。

## 10. Block semantics

narration/monologue blockを次のexclusive primary categoryに分類する。

```text
action
description
exposition
psychology
transition
other
```

さらにsecondary tagsを0件以上持てる。

```text
sensory
worldbuilding
backstory
emotion
reasoning
summary
foreshadowing
```

文体構成比に使用するのはprimary categoryのみ。secondary tagは探索・可視化用。

dialogue blockにはprimary semantic categoryを付けず、必要なら `dialogue_function` を別annotationで持つ。

## 11. dialogue function

初期enum:

```text
casual
information
question
exposition
conflict
command
emotional
other
```

multi-label可。v1の必須metricには使用しないが、人物別分析用に保存する。

## 12. Scene boundary candidate

03 automatic sceneより細かい境界が疑われる場合、semantic analyzerはBlock境界に候補を出せる。

出力:

```json
{
  "after_block_id": 55,
  "reasons": ["time_shift", "location_shift"],
  "confidence": 0.88
}
```

reason:

```text
time_shift
location_shift
pov_shift
participant_reset
context_reset
```

confidence >=0.80のみReviewQueueへ表示。自動splitしない。

## 13. Confidence policy

Scene axis:

- >=0.80: effective inferredとして集計可
- 0.60〜0.799: 保存するがprofile集計から除外しreview対象
- <0.60: `uncertain` 相当として保存、集計しない

Block primary:

- >=0.75: metric利用
- <0.75: `other` effective扱い、元推論値はraw annotationとして保持

## 14. Prompt/version

```text
scene-semantic-classifier v1
block-semantic-classifier v1
pov-classifier v1
scene-boundary-candidate v1
scene-taxonomy-v1
```

taxonomy label追加/定義変更はtaxonomy versionを上げる。既存Aggregateと混在させない。

## 15. Chunking

1 Sceneが30,000 code pointsを超える場合、モデルへ全文を1回で投げない。

- Block境界で最大15,000 code pointsのchunkへ分割
- 各chunkを分類
- function/toneはconfidence加重union
- pace/information_load/interactionは最終reduce callでchunk summaryだけを入力して決定
- POVは矛盾があればunclear + review

モデル固有tokenizerで分割しない。code point長でprovider非依存にする。

## 16. テスト

mocked output schema validationに加え、gold Sceneを最低30件用意する。

含めるscene:

- 日常会話
- 設定説明
- 会議
- 内省
- 戦闘
- 移動
- reveal
- dialogueだがexposition主体
- 会話率低いがconflict
- POV shift疑い

初期評価はlabelごとのprecision/recallを記録するが、CI gateはschema/invariant regressionとする。モデル精度値そのものを外部API非決定性のあるCI gateにしない。

## 17. Codex実装時の禁止事項

- Sceneを1つのscene_type enumへ縮約しない。
- functionを会話率等の数値だけで決めない。
- semantic classifierがautomatic Scene構造を書き換えない。
- block semantic複数labelを構成比で二重カウントしない。
- confidence不足結果をprofile統計へ混ぜない。
