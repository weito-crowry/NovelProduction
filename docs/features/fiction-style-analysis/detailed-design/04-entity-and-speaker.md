# 04 Entity and Speaker 詳細設計

## 1. 目的

人物・組織・場所等のMention候補を抽出し、Work/Document内Stable Entityへ解決し、Dialogue SpeakerとPOVの人物参照に利用する。Reference作品ではEpisodeを跨いで同じEntityを追跡する。

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
```

v1ではEntity Relation / Participant専用Analyzerを実装しない。

## 3. Entity Scope / Stable Identity

Exactly One Scope:

```text
reference_work_id  # Reference作品全Episode共通
document_id        # Project Draft等の単独Document
```

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

Effective Correction:

```text
entity.enabled
entity.canonical_name
entity.entity_type
```

Disabled EntityはResolver/Speaker/POV/Character Metricから除外する。

## 4. Manual Entity / Alias

Modelが見落としたEntityをStyle Analysis内へ直接作成できる。

```python
EntityService.create_manual_entity(
    *,
    reference_work_id: int | None,
    document_id: int | None,
    entity_type: str,
    canonical_name: str,
) -> Entity
```

- Scope exactly one。
- Name trim後1〜200文字。
- Same Name別Entityを許容。
- `origin=manual`, `created_by_run_id=NULL`。
- ReviewItem不要。

Alias:

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

Alias Kind:`name|surname|given_name|nickname|title|role`。

Manual Alias同一再送はIdempotent。

Inferred AliasだけではAuto Merge根拠にしない。Confirmed Inferred AliasまたはManual AliasだけをResolver Candidateとして使う。

## 5. Mention Extractor

`entity-mention-extractor` はEntity Registry非依存のCache可能Analyzer。

入力:

- Scene Text。
- Block ID/type/span。
- 直前Scene末尾最大3Blockの本文Context。

既存Entity/Alias一覧をPromptへ渡さない。

出力:

```json
{
  "block_id":12,
  "surface":"田中",
  "start_in_block":4,
  "end_in_block":6,
  "mention_type":"proper_name",
  "entity_type_candidate":"person",
  "canonical_name_candidate":"田中",
  "confidence":0.93
}
```

Mention Row:

```text
id
structure_revision_id
scene_id
block_id
start_cp/end_cp
surface
mention_type
entity_type_candidate
canonical_name_candidate
confidence
analysis_run_id
```

Mention RowへEntity IDを持たせない。

Mention Type:`proper_name|alias|pronoun|role_title`。

明示Surfaceのない省略主語はMentionを作らない。

Offset Validation:

1. 指定位置とSurface一致 ->採用。
2. 不一致 ->同Block内一意完全一致を1回検索。
3. 0件/複数件 ->そのMentionだけDrop + Warning。

## 6. Entity Resolver

`entity-resolver` はMention Extractor Runに`subject_partial_allowed`で依存し、Current Enabled Entity Registryを読む。Cache不可。

Scope:

```text
Reference Document -> same reference_work_id
Project Document   -> same document_id
```

候補生成ではMention Rowの`surface/mention_type/entity_type_candidate/canonical_name_candidate`を必ず利用する。

Auto Resolution:

1. Effective Canonical Name完全一致。ただし同名候補複数なら選ばない。
2. Confirmed/Manual Alias完全一致。ただし複数なら選ばない。
3. Model同一判定が09 `entity_resolution_auto_merge` 以上。

自動統合しない:

- 姓だけ。
- Pronounだけ。
- Role Titleだけ。
- 同名/同Alias候補複数。
- Disabled Entity。

Proper Name/Alias候補で既存候補なし、または明確に別実体と判断した場合だけ新`origin=inferred` Entityを作成できる。

## 7. Resolution Output

Mention RowをUpdateしない。

```text
annotation_type = mention.entity_resolution
subject_type = mention
subject_id = mention_id
value_json = {"entity_id":42}
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

Rejected ResolutionはEffectiveにしない。

## 8. Incremental Reference Registry

Reference Work Entity RegistryはIncremental Stable Registry。

- Work一括解析はEpisode Order順にResolverを実行。
- Resolver Cache不可。
- 後続EpisodeでRegistryが増えても前Episodeを即時全再解析しない。
- Work再解析時は全Episode ResolverをOrder順に再実行。
- 各RunへRegistry Input Fingerprint保存。

## 9. Speaker Attribution

対象`block_type=dialogue`。

`entity-resolver`に`subject_partial_allowed`で依存する。

Analyzer入力:

- 対象Dialogue前後最大4Block本文。
- 同Scene Current Effective Mention EntityのEnabled Person集合。

過去Speaker推論やManual Speaker値をSpeaker Analyzer入力へ入れない。

出力:

```json
{
  "block_id":15,
  "speaker_entity_id":3,
  "confidence":0.87,
  "evidence_block_ids":[14,16],
  "reason_code":"explicit_speech_tag"
}
```

Reason:`explicit_speech_tag|adjacent_action|turn_taking|addressed_name|scene_context|unknown`。

Raw AnalyzerはThresholdで確定/棄却せずConfidence + Reasonを保存する。

Effective Speaker:

```text
ManualOverride
> Confirmed Current Speaker Inference
> Raw inference if:
    confidence >= AnalysisPolicy.speaker_effective
    AND reason_code != turn_taking
> Unknown
```

`turn_taking`単独推論はConfidenceが高くても自動Effectiveにしない。User Confirm時はEffectiveにできる。

`speaker_effective`変更でRaw Speaker Runを再実行しない。

## 10. Human State Dependency

09 `entity_registry_state`:

- Manual Entity Identity。
- Entity `enabled/name/type` Override。
- Manual Alias。
- Inferred Alias最新Confirm/Reject。

09 `mention_resolution`:

- Target Structure内Latest Effective `mention.entity_id` Override。
- Current Resolution Inference Review Confirm/Reject。

Entity Resolverは`entity_registry_state`へ依存する。

Speaker/POVはEntity Resolver Dependency + `mention_resolution`へ依存する。Mention ResolutionのHuman Reviewが変わればSpeaker/POVはStaleになる。

Speaker Correction自体はSpeaker Analyzer Stateへ入れず、07 `metric_effective_state`へ入れる。

## 11. Project Character Link

Project Authoring CharacterとStyle Entityの対応はManual Linkだけ。

```text
style_entity_character_links:
  document_id
  style_entity_id
  project_character_id
  created_at
```

Validation:

- DocumentはProject Document。
- Style EntityはそのDocument scope。
- Entity Type=person。
- Enabled。
- Project CharacterがDocumentの`project_work_id`所属。
- 1 Project Characterにつき同Document内Link最大1。
- 1 Style EntityにつきLink最大1。

名前一致自動Link禁止。

Character Rule/LintはこのLinkで`project_character_id -> style_entity_id`を解決する。

## 12. Review / Correction

Low Confidence/候補複数だけでReviewItemを自動生成しない。

Semantics画面から直接:

- Manual Entity/Alias。
- Entity Enable/Disable/Name/Type。
- Mention Resolution Set/Clear/Revert。
- Resolution Confirm/Reject。
- Speaker Set/Clear/Revert/Confirm/Reject。
- Alias Confirm/Reject。
- Project Character Link。

を操作可能。

Correction後の再解析分類は10を正本とする。

## 13. Test

- Mention Extractor Registry非依存。
- Candidate Type/Name Persist。
- Mention RowにEntity IDなし。
- Resolver Candidate Fields利用。
- Resolver Cache不可/Registry Fingerprint。
- Partial Mention Run成功MentionだけResolve。
- Work Episode跨ぎResolution。
- 同名複数で強制選択なし。
- Manual Entity/Alias。
- Disabled Entity除外。
- Inferred AliasだけではMergeなし。
- Resolution Confirm/RejectでEffective Mention変更。
- Resolution Review変更でSpeaker/POV Stale。
- Explicit/Adjacent Speaker Effective。
- turn_taking単独はThreshold以上でもAuto Effectiveにならない。
- turn_taking ConfirmでEffective化。
- Speaker Manual CorrectionでRaw Speaker Run非Stale。
- `speaker_effective`変更でRaw Speaker Run非Stale。
- Project Character Manual Link Validation。
- Authoring Character自動作成なし。

## 14. Codex禁止事項

- Mention ExtractorへEntity Registry入力。
- Mention Candidate Fieldを捨てる。
- Mention RowへEntity ID追加。
- Resolver Cache。
- 全DialogueへSpeaker強制割当。
- 同名候補複数から強制Merge。
- Stable Entity Rowを再解析でUpdate。
- Inferred AliasだけでAuto Merge。
- 過去Speaker/Manual SpeakerをSpeaker Analyzer入力へ入れる。
- Raw Speaker ConfidenceをCurrent Thresholdへ合わせて書き換える。
- turn_taking単独を自動Effective化。
- Entity Relation/Participant Analyzer追加。
- Project Characterを名前一致で自動Link。
- Existing Character Tableへ推論Write。
