# 04 Entity and Speaker 詳細設計

## 1. 目的

人物・組織・場所等のMention候補、Work/Document内のStable Entity Identity、本文中のEntity Resolution、Dialogue Speakerを抽出する。Reference作品ではEpisodeを跨いで同じ実体を追跡する。

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

## 3. Entity Scope / Stable Identity

Entityは次のどちらか一方に所属する。

```text
reference_work_id  # Reference作品全Episode共通
document_id        # Project Draft等の単独Document
```

両方NULL/両方非NULLは禁止。

Entity Row:

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

Stable Identity Rowは再解析でUpdateしない。

Effective Correction Field:

```text
entity.enabled        bool, default true
entity.canonical_name string
entity.entity_type    enum
```

10 ManualOverrideで修正する。`entity.enabled=false` は誤抽出Identityを履歴ごと削除せずCurrent解析から除外するCorrection Path。

Disabled EntityはResolver/Speaker/Participant/Current Relation/Character Metricから除外する。

## 4. Manual Entity Creation

ModelがEntityを見落とした場合、ユーザーは新しいManual Entityを直接作成できる。

Service:

```python
EntityService.create_manual_entity(
    *,
    reference_work_id: int | None,
    document_id: int | None,
    entity_type: str,
    canonical_name: str,
) -> Entity
```

Validation:

- Scopeはexactly one。
- Reference Work/DocumentがCurrent Projectに存在すること。
- `entity_type` は本書enum。
- `canonical_name` はtrim後1〜200文字。
- 同名Entityが既に存在しても禁止しない。同名別人物/別組織を許容する。

生成Row:

```text
origin = manual
created_by_run_id = NULL
```

Manual Entity作成はReviewItemを要求しない。Registry Stateが変わるため09 `entity_registry` State Fingerprintが変化する。

既存DocumentのResolutionへ反映したい場合、UI/APIは対象DocumentのFull Analysis再実行を提供する。作成時にWork全Episodeを自動再解析しない。

## 5. Mention ExtractorはEntity Registry非依存

`entity-mention-extractor` はCache可能なDocument Analyzerであり、既存Entity Registryを入力にしない。

入力:

- Scene Text
- Block ID/type/span
- 直前Scene末尾最大3Blockの本文Context

出力:

```json
{
  "mentions": [
    {
      "block_id": 12,
      "surface": "田中",
      "start_in_block": 4,
      "end_in_block": 6,
      "entity_type_candidate": "person",
      "canonical_name_candidate": "田中",
      "mention_type": "proper_name",
      "confidence": 0.93
    }
  ]
}
```

PersistするMention RowはResolverに必要な候補情報を失わない。

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
  entity_type_candidate
  canonical_name_candidate
  confidence
  analysis_run_id
```

`entity_type_candidate` はEntity Type enum。`canonical_name_candidate` はtrim後1〜200文字。

Mention RowはEntity IDを持たない。

Offset Validation:

1. 指定位置とSurface一致 -> 採用
2. 不一致 -> 同Block内の一意完全一致を1回だけ検索
3. 0件/複数件 -> そのMentionだけDrop + Warning

## 6. Entity Resolver

`entity-resolver` はMention Extractor Runに依存し、Current Entity Registryを読む。

Scope:

```text
Reference Document -> same reference_work_id
Project Document   -> same document_id
```

Resolverは09で `cacheable=false`。Full Analysis実行ごとにCurrent Registryを入力にする。入力Registryは `registry_input_fingerprint` へ記録する。

候補生成にはMention Rowの:

```text
surface
mention_type
entity_type_candidate
canonical_name_candidate
```

を必ず渡す。

自動統合条件:

1. Enabled EntityのEffective Canonical Name完全一致。ただし同名候補複数なら自動選択しない。
2. Confirmed/Manual Alias完全一致。ただし一致候補複数なら自動選択しない。
3. Model同一判定 >= `AnalysisPolicy.entity_resolution_auto_merge`。

自動統合しない:

- 姓だけ
- Pronounだけ
- Role Titleだけ
- 同名/同Alias候補複数
- Disabled Entity

Proper Name/Alias候補で既存候補なし、またはModelが明確に別実体と判断した場合は新 `origin=inferred` Entityを作成できる。Pronoun/Role Titleだけから新Entityを作らない。

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

未解決はAnnotationなしでよい。

Effective Mention Entity:

```text
ManualOverride mention.entity_id
> Confirmed Current Resolution
> Current Resolver Annotation
> Unknown
```

Resolverが新Entity/Aliasを作成する場合、生成RunをProvenanceとして保持する。

## 8. Reference Work Registry整合モデル

Reference WorkのEntity RegistryはIncremental Stable Registry。

- Work一括解析JobはEpisode Order順にResolverを実行。
- ResolverはCache不可。
- 後続Episodeで新Entityが増えても前Episodeを即時自動再解析しない。
- Work一括解析を再実行すれば全Episode ResolverをOrder順に再実行。
- 各Resolver RunにRegistry Input Fingerprintを保存。

これはv1のEventual Consistency方針。

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

Manual Alias Service:

```python
EntityService.add_manual_alias(entity_id, alias, alias_kind)
```

Validation:

- Entityが存在しCurrent Project内。
- Alias trim後1〜200文字。
- Alias Kindはenum。
- 同一Entity/Alias/Kindの重複Manual追加はIdempotentに既存Rowを返してよい。

Rules:

- Inferred AliasだけではAuto Merge根拠にしない。
- Confirmed Inferred AliasまたはManual AliasだけをResolution根拠にする。
- Manual Aliasは `origin=manual`, `analysis_run_id=NULL`。

## 10. Speaker Attribution

対象 `block_type=dialogue`。Dependencyは `entity-resolver`。

候補:

1. 同SceneのEffective Mention EntityのEnabled Person
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
value_json = {entity_id, reason_code, evidence_block_ids}
confidence
analysis_run_id
```

AnnotationがDisabled Entityを指す場合、Effective SpeakerはUnknown。

## 11. Scene Participant / Relation

Participant:

- Scene内Effective Mention
- Effective Speaker
- Model非発話参加者 >= `participant_effective`

のEnabled Person Entity。

Relation Type:

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

`entity-relation-extractor` はSpeaker Attributionに依存する。Relation RowはRun Provenanceを持つ。Disabled Entityを含むRelationはEffective一覧から除外する。

## 12. Project Character Link

```text
style_entity_id
project_character_id
origin = inferred | manual
confidence nullable
analysis_run_id nullable
created_at
```

v1はManual Linkだけでよい。名前一致自動Link禁止。

## 13. Human State Dependency

09 `entity_registry` State Fingerprint:

- Manual Entity Identity
- Active `entity.enabled/name/type` Override
- Manual Alias
- Inferred Alias最新Confirm/Reject

`mention_resolution` State:

- 指定Structure内Active `mention.entity_id` Override

Inferred RegistryのCurrent全量はResolver `registry_input_fingerprint` に保存し、後続Episode追加だけで過去Runを全Staleにしない。

## 14. Review方針

Low Confidence/候補複数だけでReviewItemを自動生成しない。

Semantics画面から:

- Manual Entity作成
- Manual Alias追加
- Entity Disable/Name/Type修正
- Mention Resolution修正
- Speaker修正
- Alias Confirm/Reject

を直接操作可能。

## 15. Test

- Mention ExtractorがRegistry非依存
- Mention Candidate Type/Canonical Name永続化
- Mention RowにEntity IDなし
- ResolverがCandidate Fieldsを使用
- Resolver AnnotationでMapping
- Resolver Cache不可/Registry Fingerprint
- Work Episode跨ぎResolution
- 同名候補複数で強制選択なし
- Manual Entity作成 / Same-name許容
- Manual Alias追加 / Idempotent重複
- Manual Entity追加でEntity Registry State変更
- Disabled Entity除外
- Inferred AliasのみではMergeなし
- Confirmed/Manual Alias Resolution
- Explicit Speaker / Ambiguous Unknown
- Work一括再解析Episode Order

## 16. Codex禁止事項

- Mention Extractorへ既存Entity Registryを入力
- Mention Candidate Fieldsを捨てる
- Mention RowへEntity IDを戻す
- Entity ResolverをCache Hitで省略
- 全DialogueへSpeaker強制割当
- 同名候補複数から強制Merge
- Entity Identity Rowを再解析でUpdate
- Disabled EntityをCurrent候補へ含める
- Inferred AliasだけでAuto Merge
- Manual Entity作成を既存Authoring Character作成と結合
- Existing Character Tableへ推論Write
- AmbiguityだけでReviewItem量産
