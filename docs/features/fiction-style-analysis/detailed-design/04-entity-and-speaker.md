# 04 Entity and Speaker 詳細設計

## 1. 目的

人物・組織・場所等のEntity、本文中Mention、作品内同一性、会話Blockの話者を抽出する。reference作品ではepisodeを跨いで同じ人物を追跡できることを必須とする。

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

## 3. Entity scope

Entityは次のどちらか一方へ所属する。

```text
reference_work_id  # reference作品全episode共通
document_id        # project draft等の単独document
```

両方NULL/両方非NULLは禁止。

reference作品では人物・組織・場所をepisode単位に分断しない。project draftでは既存 `characters` へ自動mergeしない。

## 4. Entity identity

Entity rowは「同一実体のstable identity」。再解析のたびにcanonical_name/statusを推論で上書きしない。

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

`entity_type`:

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

初回自動抽出時は `origin=inferred`。ユーザーが直接作る場合は `manual`。

確認/却下/名称修正は10 `style_inference_reviews` / `ManualOverride` でoverlayする。これにより再解析履歴とidentityを混同しない。

## 5. Mention

```text
id
entity_id nullable
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

`mention_type`:

```text
proper_name
alias
pronoun
role_title
implicit
```

明示文字列のない省略主語はMentionを作らずannotationで扱う。Mention spanは非ゼロ幅。

## 6. 解析順

```text
Scene input
  -> Mention extraction
  -> scope-level Entity resolution
  -> Speaker attribution
  -> Relation extraction
```

reference候補は同 `reference_work_id`、project候補は同 `document_id`。

## 7. Mention extraction

入力:

- Scene text
- Block ID/type/span
- 同scopeのEntity + effective canonical name/alias
- 直前Scene末尾最大3Blockの人物名context

出力例:

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

offset validation:

1. 指定位置とsurface一致 -> 採用。
2. 不一致 -> 同Block内一意完全一致を1回検索。
3. 0件/複数件 -> そのMentionだけ破棄しwarning。

単一Mention不整合でrun全体をfailさせない。

## 8. Entity resolution

自動統合条件:

1. effective canonical name完全一致
2. confirmed/manual alias完全一致
3. model同一判定 >= `AnalysisPolicy.entity_resolution_auto_merge`

初期default `0.90`。

自動統合しない:

- 姓だけ一致
- pronounだけ
- 役職だけ
- 同名候補複数

候補最大20件。threshold未満は `entity_id=NULL` Mentionとして保持可能。unknownは正常状態。

新Entityを作るのは「既存候補なし、または明確に別実体」と判定したproper name/alias候補。pronoun/role_title単独から新Entityを作らない。

## 9. Alias

`style_entity_aliases`:

```text
id
entity_id
alias
alias_kind
origin = inferred | manual
analysis_run_id nullable
source_mention_id nullable
created_at
```

alias kind:

```text
name
surname
given_name
nickname
title
role
```

自動aliasは生成runを必ず記録する。confirmed/manual相当はEffective Viewで優先され、再解析で削除しない。

## 10. Speaker attribution

対象 `block_type=dialogue`。

候補:

1. 同Scene person Entity
2. 前後2Block Mention person
3. 直前dialogue effective speaker
4. Scene participant

モデルへ対象前後最大4Block。

```json
{
  "block_id": 15,
  "speaker_entity_id": 3,
  "confidence": 0.87,
  "evidence_block_ids": [14, 16],
  "reason_code": "explicit_speech_tag"
}
```

reason:

```text
explicit_speech_tag
adjacent_action
turn_taking
addressed_name
scene_context
unknown
```

thresholdは09 AnalysisPolicy:

```text
speaker_effective = 0.85
speaker_candidate = 0.60
```

- >= effective: inferred effective speaker。
- candidate以上/effective未満: raw candidate保存、effective unknown。
- candidate未満: effective unknown。

Turn-takingだけでeffective thresholdを超えない。

## 11. Speaker Annotation

```text
annotation_type = speaker
subject_type = block
subject_id = block_id
value_json = {"entity_id": 3, "reason_code": "...", "evidence_block_ids": [...]}
confidence
analysis_run_id
```

Block rowへspeaker列を追加しない。

## 12. Scene participant

- Scene内Mentionあり
- effective speaker
- model非発話参加者 >= `participant_effective`（初期0.80）

過去文脈の名前言及だけならparticipantにしない。

## 13. Relation

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

`co_present` はparticipantsから決定論的生成可。恒常関係は文体Metric必須入力にしない。

Relation rowは `analysis_run_id` を持ち、自動再解析で旧Relationをupdateしない。

## 14. Project character link

```text
style_entity_id
project_character_id
origin = inferred | manual
confidence nullable
analysis_run_id nullable
created_at
```

自動linkをv1で作る必要はない。UIから明示linkした場合は `manual`。将来自動linkする場合も生成runを記録する。

人物別project Profile比較に使うのはmanual/confirmed effective linkだけ。名前一致自動link禁止。

## 15. Prompt/version

```text
entity-mention-extractor v1
entity-resolver v1
speaker-attribution v1
entity-relation-extractor v1
```

promptはversion付きresource。

## 16. Review方針

Speaker/Entityの低confidence・候補複数を理由にReviewItemを自動生成しない。raw candidate/unknownはSemantics画面のfilterで確認する。

ReviewItemを作るのは次だけ。

- ユーザーがSemantics画面から「Reviewへ追加」を明示したsubject
- stale ManualOverride移行のようにReview workflow自体が必要なもの

したがって「候補confidence差が小さい」のような追加heuristicはReviewServiceへ実装しない。

## 17. テスト

- reference work episode跨ぎEntity resolution
- project scope分離
- Entity identity再解析で上書きなし
- alias analysis_run provenance
- offset validation
- exact alias resolution
- ambiguous alias非merge
- explicit speech attribution
- turn-takingだけではeffectiveにしない
- 3人会話unknown
- 同姓人物誤統合なし
- low-confidence/候補複数でもReviewItem自動生成なし

## 18. Codex禁止事項

- 全dialogue speaker強制割当
- surname一致だけでmerge
- Entity identity rowを再解析でupdate
- existing character tableへ推論write
- model offset無検証保存
- world/canon自動更新
- provider SDKをCOREへ追加
- speaker ambiguity heuristicでReviewItemを自動量産