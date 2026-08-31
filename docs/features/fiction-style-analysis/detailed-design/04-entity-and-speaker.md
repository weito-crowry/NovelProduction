# 04 Entity and Speaker 詳細設計

## 1. 目的

人物・組織・場所等のEntity、本文中のMention、人物同一性、会話blockの話者を抽出する。推論結果は必ずevidence spanとconfidenceを持ち、判断不能時に無理に確定しない。

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

LLM通信そのものは09の `SemanticModelClient` Protocol経由とする。COREから特定provider SDKをimportしない。

## 3. Entity種別

初期 `entity_type` を固定する。

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

`term` はEntity typeにしない。05のTermモデルで別管理し、必要ならEntityを参照する。

## 4. EntityとMention

### Entity

```text
id
reference_work_id
entity_type
canonical_name
description nullable
status = inferred | confirmed | rejected | manual
created_by_run_id nullable
created_at
```

外部reference workのEntityはwork単位。project draft解析では `document_id` を所属scopeとして保持し、既存NovelProductionのcharacter tableと自動mergeしない。

### Mention

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

`entity_id=NULL` を許可し、未解決Mentionを保持する。

`mention_type`:

```text
proper_name
alias
pronoun
role_title
implicit
```

implicit mentionはゼロ幅spanを禁止する。明示文字列がない主語省略等はMentionにせずannotationとして扱う。

## 5. 解析パイプライン

順序を固定する。

```text
Scene input
  ↓
Mention extraction
  ↓
work-level Entity resolution
  ↓
Speaker attribution
  ↓
Relation extraction
```

speaker attributionはEntity resolution成功後に実行する。未解決人物を話者候補にする場合はtemporary candidate IDを使わず、`speaker_entity_id=NULL` と候補名をevidence metadataへ残す。

## 6. Mention extraction

Scene単位でモデルへ入力する。

入力:

- Scene canonical text
- Block一覧とblock_id/type/span
- 既に確定済みEntity一覧（同work）
- 直前scene末尾最大3blockの人物名context

モデル出力JSON schema:

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

LLMのoffsetを信用し切らない。`surface` がblock内指定位置と一致することを検証し、不一致時は同block内の一意な完全一致を検索する。0件または複数件ならそのMentionをrejectしReviewQueueへ送る。

## 7. Entity resolution

同work内でのみ自動統合する。

自動統合条件:

1. canonical name完全一致
2. 既存confirmed alias完全一致
3. modelが同一人物と判定しconfidence >= 0.90、かつ conflicting evidenceなし

以下は自動統合しない。

- 同じ姓だけ
- 「彼」「彼女」だけ
- 同じ役職名だけ
- 同名人物が複数存在し得るケース

model-based resolutionは候補Entityを最大20件に絞って渡す。候補0なら新Entity、候補複数で0.90未満なら未解決Mentionとして残す。

## 8. Alias

Entity aliasは別table `style_entity_aliases` で保持する。

```text
entity_id
alias
alias_kind
status
source_mention_id nullable
```

alias_kind:

```text
name
surname
given_name
nickname
title
role
```

modelが提案したaliasは `inferred`。Human confirmed後は再解析でも維持する。

## 9. Speaker attribution

対象は `block_type=dialogue` のみ。

各dialogue blockについて候補を以下の順で作る。

1. 同Sceneのperson Entity
2. 直前/直後2blockにMentionがあるperson
3. 直前dialogueのspeaker
4. Scene participants annotation

モデル入力には対象dialogue前後最大4blockずつを渡す。

出力:

```json
{
  "block_id": 15,
  "speaker_entity_id": 3,
  "confidence": 0.87,
  "evidence_block_ids": [14, 16],
  "reason_code": "explicit_speech_tag"
}
```

reason_code初期値:

```text
explicit_speech_tag
adjacent_action
turn_taking
addressed_name
scene_context
unknown
```

confidence threshold:

| confidence | Effective扱い |
|---|---|
| >= 0.85 | inferred speakerとして利用可 |
| 0.60〜0.849 | speaker候補として保存しreview対象 |
| < 0.60 | `speaker_entity_id=NULL` として保存 |

Turn-takingだけを根拠にconfidence 0.85以上を付けない。最大0.79とする。

## 10. Speaker Annotation

話者はBlock自体の列として直接上書きせず、`style_annotations` に保存する。

```text
annotation_type = speaker
subject_type = block
subject_id = block_id
value_json = {"entity_id": 3}
confidence
analysis_run_id
```

ManualOverrideは10のEffective Viewで上書きする。

## 11. Person participation

Scene participantは次のどれかを満たすperson Entityとする。

- Scene内に明示Mentionあり
- speaker attributionあり
- modelが非発話参加者として明示しconfidence >= 0.80

単に過去文脈で名前が言及された人物はparticipantにしない。

## 12. Relation extraction

v1では文体分析に必要な最小限だけ保存する。

relation types:

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

`family/friend/...` の恒常関係はmodel confidence >=0.90でも `inferred` のまま。文体指標の必須入力にはしない。

`co_present` はScene participantsから決定論的に作成可能。

## 13. Project側characterとの対応

自作品 `project_episode_draft` を解析した場合でも、Style Analysis Entityを既存 `characters` rowへ自動mergeしない。

必要なら `style_entity_links` で明示linkする。

```text
style_entity_id
project_character_id
status = inferred | confirmed | manual
confidence nullable
```

confirmed/manual linkのみ、人物別StyleProfile比較で既存character IDとして利用する。

## 14. Prompt/version

Analyzer IDs:

```text
entity-mention-extractor v1
entity-resolver v1
speaker-attribution v1
entity-relation-extractor v1
```

prompt textはコード埋め込みではなく `CORE/src/novel_core/style_analysis/prompts/` にversion付きUTF-8 text/jsonとして置く。prompt変更時はAnalyzer versionまたはprompt versionを必ず更新する。

## 15. Fail closed

以下は推測で補完しない。

- 誰が喋ったか分からない
- 「先生」等が複数人物を指し得る
- 同姓同名
- pronounの先行詞が曖昧
- model outputのspan不整合

不明値をNULLで保持できることを正常系とする。

## 16. テスト

### deterministic

- surface offset validation
- exact alias resolution
- ambiguous aliasをmergeしない
- candidate filtering
- confidence threshold
- project character link優先順位

### mocked model

- 明示「Aが言った」でA attribution
- A/B交互会話だがturn-takingだけなら0.85未満
- 3人会話でunknown維持
- pronoun解決成功/失敗
- 同姓人物2名を誤統合しない

### gold dataset

最低20 Sceneを手動annotationし、speaker accuracyを計測する。初期acceptanceは「明示speaker tag付きdialogueのprecision >= 0.95」。全dialogue recallを無理に目標化しない。

## 17. Codex実装時の禁止事項

- 全てのdialogueへ必ずspeakerを割り当てない。
- surname一致だけでEntity mergeしない。
- existing character tableへ推論結果を書き込まない。
- modelのoffsetを検証なしで永続化しない。
- relation extractionを世界観DB自動更新へ接続しない。
- LLM provider固有SDKをCOREへ追加しない。
