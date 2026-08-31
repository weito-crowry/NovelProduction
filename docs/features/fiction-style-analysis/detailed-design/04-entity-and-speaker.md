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

LLM通信は09の `SemanticModelClient` 経由。COREからprovider SDKをimportしない。

## 3. Entity scope

Entityの所属scopeは次のどちらか一方。

```text
reference_work_id  # reference作品。全episode共通
 document_id       # project draft等、単独document
```

両方NULL、両方非NULLは禁止する。

reference作品では人物・組織・場所をepisode単位に分断しない。project draft解析では既存NovelProduction `characters` へ自動mergeせず、Style Analysis document内Entityとして扱う。

## 4. Entity種別

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

Termは05で別管理する。

## 5. Entity / Mention

Entity:

```text
id
reference_work_id nullable
document_id nullable
entity_type
canonical_name
description nullable
status = inferred | confirmed | rejected | manual
created_by_run_id nullable
created_at
```

Mention:

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

明示文字列のない省略主語はMentionを作らずannotationで扱う。Mention spanは必ず非ゼロ幅。

## 6. 解析順

```text
Scene input
  -> Mention extraction
  -> scope-level Entity resolution
  -> Speaker attribution
  -> Relation extraction
```

reference作品のEntity resolution候補は同 `reference_work_id`。project documentは同 `document_id`。

## 7. Mention extraction

Scene単位でモデルへ渡す。

入力:

- Scene text
- Block ID/type/span
- 同scopeの既存Entity一覧
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

1. 指定位置とsurfaceが一致すれば採用。
2. 不一致なら同Block内の一意な完全一致を1回だけ検索。
3. 0件/複数件ならそのMentionだけ破棄しwarningを残す。

単一Mentionのspan不整合でrun全体をfailさせない。

## 8. Entity resolution

自動統合条件:

1. canonical name完全一致
2. confirmed/manual alias完全一致
3. model同一判定が09 `AnalysisPolicy.entity_resolution_auto_merge` 以上

初期defaultは `0.90`。

次は自動統合しない。

- 姓だけ一致
- pronounだけ
- 役職だけ
- 同名人物候補が複数

候補は最大20件。threshold未満は未解決Mentionとして保持する。未解決は正常状態であり、ReviewItemを必ず作る必要はない。

## 9. Alias

`style_entity_aliases`:

```text
entity_id
alias
alias_kind
status
source_mention_id nullable
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

confirmed/manual aliasは再解析で維持する。

## 10. Speaker attribution

対象は `block_type=dialogue`。

候補生成:

1. 同Scene person Entity
2. 前後2BlockにMentionがあるperson
3. 直前dialogue speaker
4. Scene participant

モデルへ対象前後最大4Blockを渡す。

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

thresholdは09 AnalysisPolicyを正本とする。

```text
speaker_effective = 0.85
speaker_candidate = 0.60
```

- >= effective: inferred speakerとして利用。
- candidate以上/effective未満: 候補として保存、effectiveはunknown。
- candidate未満: entity_idをeffectiveにしない。

Turn-takingだけを根拠にeffective thresholdを超えない。

## 11. Speaker Annotation

Block rowへspeaker列を追加せず `style_annotations` に保存する。

```text
annotation_type = speaker
subject_type = block
subject_id = block_id
value_json = {"entity_id": 3}
confidence
analysis_run_id
```

ManualOverrideは10のEffective Viewでoverlayする。

## 12. Scene participant

person Entityが以下のいずれかを満たせばparticipant。

- Scene内Mentionあり
- effective speaker
- modelが非発話参加者として09 policy threshold以上

初期 `participant_effective=0.80`。

過去について名前が言及されただけの人物はparticipantにしない。

## 13. Relation

v1は文体探索に使える最小限。

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

`co_present` はparticipantsから決定論的生成可能。恒常関係はinferredのままでよく、文体metricの必須入力にしない。

## 14. Project character link

既存characterとの対応が必要な場合だけ `style_entity_links` を使う。

```text
style_entity_id
project_character_id
status = inferred | confirmed | manual
confidence nullable
```

confirmed/manual linkだけ人物別StyleProfile比較へ使用する。名前一致で自動リンクしない。

## 15. Prompt/version

```text
entity-mention-extractor v1
entity-resolver v1
speaker-attribution v1
entity-relation-extractor v1
```

promptは `CORE/src/novel_core/style_analysis/prompts/` にversion付きresourceとして置く。

## 16. Review方針

低confidence結果を無差別にReviewQueueへ積まない。

ReviewItemを自動作成するのは初期状態では次だけ。

- modelが複数Entity候補の明示conflictを返した
- user-visible speaker解析で候補が複数かつconfidence差が小さい
- manual operationの対象Entityが解決不能

その他のunknown/未解決結果はSemantics画面のfilterで確認可能にする。

## 17. テスト

- reference work内episode跨ぎEntity resolution
- project document scope分離
- surface offset validation
- exact alias resolution
- ambiguous alias非merge
- candidate filtering
- policy threshold
- explicit speech tag attribution
- turn-takingだけではeffectiveにしない
- 3人会話unknown
- 同姓人物誤統合なし

Gold datasetの精度値は14の評価方針に従い、CI hard gateにしない。

## 18. Codex実装時の禁止事項

- 全dialogueへspeakerを強制割当しない。
- surname一致だけでEntity mergeしない。
- existing character tableへ推論結果を書き込まない。
- model offsetを検証なしで保存しない。
- relation抽出をworld/canon自動更新へ接続しない。
- provider SDKをCOREへ追加しない。
- unknown結果ごとにReviewItemを大量生成しない。