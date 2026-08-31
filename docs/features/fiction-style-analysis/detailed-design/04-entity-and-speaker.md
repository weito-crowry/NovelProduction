# 04 Entity and Speaker 詳細設計

## 1. 目的

人物・組織・場所等のEntity候補、本文中Mention、作品内同一性、会話BlockのSpeakerを抽出する。Reference作品ではEpisodeを跨いで同じ実体を追跡する。

上位仕様は `../basic-design.md`。

## 2. 実装先

```text
CORE/src/novel_core/style_analysis/
  entity_models.py
  entity_repository.py
  entity_service.py
  analyzers/
    entity_mentions.py
    entity_resolution.py
    speaker_attribution.py
    relations.py
```

LLM通信は09 `SemanticModelClient` 経由。

## 3. Entity Scope

Entityは次のどちらか一方へ所属する。

```text
reference_work_id  # Reference作品全Episode共通
document_id        # Project Draft等の単独Document
```

両方NULL/両方非NULLは禁止。

## 4. Entity Identity

Entity RowはStable Identity。

```text
id
reference_work_id nullable
document_id nullable
entity_type
canonical_name
origin = inferred | manual
created_by_run_id nullable
created_at
```

Entity Type:

```text
person
organization
location
technology
concept
product
event
other
```

Effective Correction Field:

```text
entity.enabled        bool, default true
entity.canonical_name string
entity.entity_type    enum
```

10 ManualOverrideで修正する。Identity Row自体を再解析でUpdateしない。

Disabled EntityはResolver/Speaker/Participant/Current Relation/Character Metricから除外する。

## 5. Mention ExtractionはRegistry非依存

`entity-mention-extractor` はCache可能なDocument Analyzerとし、**既存Entity Registryを入力にしない。**

入力:

- Scene Text
- Block ID/type/span
- 直前Scene末尾最大3Blockの本文Context

既存Entity名/Alias一覧をPromptへ渡さない。

出力:

```json
{
  "mentions": [
    {
      "block_id": 12,
      "surface": "田中",
      "start_in_block": 4,
      "end_in_block": 6,
      "entity_type": "person",
      "canonical_name_candidate": "田中",
      "mention_type": "proper_name",
      "confidence": 0.93
    }
  ]
}
```

Persist:

```text
style_mentions
  id
  structure_revision_id
  scene_id
  block_id
  start_cp
  end_cp
  surface
  mention_type
  confidence
  analysis_run_id
```

Mention RowはEntity IDを持たない。

Offset Validation:

1. 指定位置一致 -> 採用
2. 不一致 -> 同Block内一意完全一致を1回検索
3. 0件/複数件 -> そのMentionだけDrop + Warning

## 6. Entity Resolver

`entity-resolver` はMention Extractor Runに依存し、Current Entity Registryを読む。

Reference Document:

```text
同 reference_work_id のEnabled Entity Registry
```

Project Document:

```text
同 document_id のEnabled Entity Registry
```

Resolverは09で `cacheable=false`。Full Analysisを実行するたびにCurrent Registryを入力として再実行する。

入力Registryの内容は09 `registry_input_fingerprint` へ記録し、Historical RunのProvenanceとする。

自動統合条件:

1. Enabled EntityのEffective Canonical Name完全一致。ただし同名Enabled Entityが複数なら自動選択しない
2. Confirmed/Manual Alias完全一致。ただし一致候補複数なら自動選択しない
3. Model同一判定 >= `AnalysisPolicy.entity_resolution_auto_merge`

初期0.90。

自動統合しない:

- 姓だけ
- Pronounだけ
- Role Titleだけ
- 同名/同Alias候補複数
- Disabled Entity

新Entityを作るのはProper Name/Alias候補で既存候補なし、またはModelが明確に別実体と判断した場合。

## 7. Resolution Output

Mention RowをUpdateしない。

```text
annotation_type = mention.entity_resolution
subject_type = mention
subject_id = mention_id
value_json = {"entity_id": 42}
confidence
analysis_run_id = entity-resolver run
```

未解決はAnnotationを作らなくてよい。Effective Mention Entityは10:

```text
ManualOverride mention.entity_id
> Confirmed Current Resolution
> Current Resolver Annotation
> Unknown
```

Resolverが新Entity/EntityAliasを作成する場合、そのIdentity/Aliasの `created_by_run_id` / `analysis_run_id` をResolver Runへ紐付ける。

## 8. Work Registryのv1整合モデル

Reference WorkのEntity RegistryはIncremental Stable Registryとする。

- Work全体解析JobはEpisode Order順にResolverを実行する
- ResolverはCache不可なので再実行時はその時点のRegistryを読む
- 後続Episodeで新しいInferred Entityが追加されても、既に完了した前Episode Runを自動で全再解析しない
- Work全体解析を再実行すれば全EpisodeをOrder順に再Resolverする
- 各Resolver Runに `registry_input_fingerprint` を残すため、どのRegistry状態で解決したか追跡できる

これはv1の明示的なEventual Consistency方針。全Episode追加ごとに全過去Episodeを自動再解析する仕組みは作らない。

Manual/Confirmed Correctionは09 State Fingerprint対象なので、影響AnalyzerをStale判定できる。

## 9. Alias

```text
style_entity_aliases
  id
  entity_id
  alias
  alias_kind
  origin = inferred | manual
  analysis_run_id nullable
  source_mention_id nullable
  created_at
```

Alias Kind:

```text
name
surname
given_name
nickname
title
role
```

- Inferred AliasはAuto Merge根拠にしない
- 10 InferenceReviewでConfirmed、またはManual AliasだけをMerge根拠にする
- 誤ったInferred AliasはConfirmedされなければ影響しないため専用Disable機構はv1で作らない

## 10. Speaker Attribution

対象 `block_type=dialogue`。

Dependency:

```text
entity-resolver
```

候補:

1. 同SceneのEffective Mention EntityのうちEnabled Person
2. 前後2BlockのEffective Mention Entity
3. 直前Dialogue Effective SpeakerがEnabledならそのEntity
4. Enabled Scene Participant

Modelへ対象前後最大4Block。

```json
{
  "block_id": 15,
  "speaker_entity_id": 3,
  "confidence": 0.87,
  "evidence_block_ids": [14,16],
  "reason_code": "explicit_speech_tag"
}
```

Reason:

```text
explicit_speech_tag
adjacent_action
turn_taking
addressed_name
scene_context
unknown
```

Threshold:

```text
speaker_effective = 0.85
speaker_candidate = 0.60
```

Turn-takingだけでEffective Thresholdを超えない。

Speaker Annotation:

```text
annotation_type = speaker
subject_type = block
subject_id = block_id
value_json = {
  "entity_id": 3,
  "reason_code": "explicit_speech_tag",
  "evidence_block_ids": [14,16]
}
confidence
analysis_run_id
```

Annotation EntityがDisabledならEffective SpeakerはUnknown。

## 11. Scene Participant

Enabled Person Entityが:

- Scene内Effective Mention
- Effective Speaker
- Model非発話参加者 >= `participant_effective`

のいずれかならParticipant。

Participant推論はSpeaker AnalyzerまたはRelation Analyzerの補助OutputとしてAnnotation保存してよい。専用Analyzerを増やさない。

## 12. Relation

v1:

```text
speaks_to
mentions
co_present
family
friend
colleague
superior
subordinate
other
```

`entity-relation-extractor` は `entity-resolver` に依存する。

Relation RowはRun Provenanceを持つ。Disabled Entityを含むRelationはEffective一覧から除外しRaw表示だけ可能。

## 13. Project Character Link

```text
style_entity_id
project_character_id
origin = inferred | manual
confidence nullable
analysis_run_id nullable
created_at
```

v1はManual Linkだけでよい。

Project人物別比較に使うのはEnabled EntityかつManual/Confirmed Effective Linkだけ。名前一致自動Link禁止。

## 14. Human State Dependency

09 `entity_registry` State Fingerprintには次だけを含める。

- Manual Entity Identity
- Active `entity.enabled/name/type` Override
- Manual Alias
- Inferred Aliasの最新Confirm/Reject Review

Inferred Entity RegistryそのものはCurrent Validity State Fingerprintへ入れず、Resolver Runの `registry_input_fingerprint` へ入れる。

09 `mention_resolution` StateにはActive `mention.entity_id` Overrideを含める。

Speaker/RelationはこれらState FingerprintをCurrent判定に使う。

## 15. Prompt / Version

```text
entity-mention-extractor v1
entity-resolver v1
speaker-attribution v1
entity-relation-extractor v1
```

PromptはVersion付きResource。

## 16. Review方針

Low Confidenceや候補複数だけを理由にReviewItemを自動生成しない。

Semantics画面から:

- Entity Disable
- Name/Type修正
- Mention Resolution修正
- Speaker修正
- Alias Confirm/Reject

をDirect操作可能。

## 17. Test

- Mention ExtractorがEntity Registry非依存
- Mention RowにEntity IDなし
- Resolver AnnotationでEntity Mapping
- Reference Work Episode跨ぎResolver
- Resolver `cacheable=false`
- Registry Input Fingerprint記録
- 同名Enabled Entity複数でAuto選択しない
- Entity Identity再解析Updateなし
- Entity Enabled/Name/Type Override
- Disabled EntityをResolver/Speakerから除外
- Inferred AliasのみではMergeなし
- Confirmed/Manual Alias Resolution
- Explicit Speech Attribution
- Turn-takingだけではEffectiveにしない
- 3人会話Unknown
- Work全体再解析でEpisode Order順Resolver

## 18. Codex禁止事項

- Mention Extractorへ既存Entity Registryを入力
- Mention RowのEntity IDをUpdate
- Entity ResolverをFingerprint Cache Hitで省略
- 全DialogueへSpeaker強制割当
- Surname/同名複数候補から強制Merge
- Entity Identity Rowを再解析でUpdate
- Disabled EntityをCurrent候補へ含める
- Inferred AliasだけでAuto Merge
- Existing Character Tableへ推論Write
- World/Canon自動更新
- Provider SDKをCOREへ追加
- AmbiguityだけでReviewItem量産
